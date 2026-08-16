from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

import gerar_base_video_por_snapshot as base
import gerar_base_video_por_fase as fase_v1

VERSION = "base_video_fases_v2_comparacao_abertura_pre_2026_08_16"


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", clean(value).lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or payload.get("lista") or []
    return [item for item in raw if isinstance(item, dict)]


def event(payload: Dict[str, Any]) -> str:
    return clean(payload.get("evento_programado")).upper()


def valid(payload: Dict[str, Any], rodada: int, evento: str, minimo: int) -> bool:
    return (
        isinstance(payload, dict)
        and base.as_int(payload.get("rodada")) == rodada
        and event(payload) == evento
        and len(rows(payload)) >= minimo
    )


def find_snapshot(root: Path, relative_path: str, rodada: int, evento: str, minimo: int) -> Tuple[Dict[str, Any], str]:
    current = base.read_json(root / relative_path, required=False)
    if valid(current, rodada, evento, minimo):
        return current, "WORKTREE"

    for commit in base.git_commits_for_path(root, relative_path):
        payload = base.git_json(root, commit, relative_path)
        if valid(payload, rodada, evento, minimo):
            return payload, commit

    raise RuntimeError(
        f"Snapshot {evento} da rodada {rodada} não encontrado no histórico: {relative_path}"
    )


def restore_snapshot(root: Path, relative_path: str, rodada: int, evento: str, minimo: int, image_path: str = "") -> Tuple[Dict[str, Any], str]:
    payload, source = find_snapshot(root, relative_path, rodada, evento, minimo)
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if source != "WORKTREE" and image_path:
        fase_v1.restore_binary(root, source, image_path)
    print(f"Snapshot restaurado: {relative_path} evento={evento} fonte={source} registros={len(rows(payload))}")
    return payload, source


def prepare_initial(rodada: int, root: Path) -> Dict[str, str]:
    sources: Dict[str, str] = {}
    for slug in ("economico", "intermediario", "pontuacao"):
        path = f"data/publicacoes_atuais/time_{slug}_rodada_{rodada}.json"
        _, source = restore_snapshot(
            root, path, rodada, "SELECAO_INICIAL", 12,
            f"output/time_{slug}_rodada_{rodada}.png",
        )
        sources[slug] = source
    top_path = f"data/publicacoes_atuais/top5_rodada_{rodada}.json"
    _, source = restore_snapshot(
        root, top_path, rodada, "SELECAO_INICIAL", 30,
        f"output/top5_rodada_{rodada}.png",
    )
    sources["top5"] = source
    return sources


def player_key(item: Dict[str, Any]) -> str:
    athlete_id = base.as_int(item.get("ATLETA_ID") or item.get("atleta_id"))
    if athlete_id:
        return f"id:{athlete_id}"
    return "|".join([
        norm(item.get("NOME") or item.get("nome")),
        norm(item.get("POS") or item.get("pos") or item.get("posicao")),
        norm(item.get("CLUBE") or item.get("clube")),
    ])


def player_name(item: Dict[str, Any]) -> str:
    return clean(item.get("NOME") or item.get("nome")) or "Atleta"


def number(item: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return base.as_float(item.get(key))
    return 0.0


def index_players(payload: Dict[str, Any], starters_only: bool = False) -> Dict[str, Dict[str, Any]]:
    items = rows(payload)
    if starters_only:
        items = [item for item in items if clean(item.get("status") or "TITULAR").upper() != "RESERVA"]
    return {player_key(item): item for item in items if player_key(item).strip("|")}


def reason(before: Dict[str, Any], after: Dict[str, Any], action: str) -> str:
    if action == "ENTROU":
        score_before = number(before, "EXP_SCORE", "exp_score") if before else 0.0
        score_after = number(after, "EXP_SCORE", "exp_score")
        if score_after and score_after > score_before:
            return f"expectativa do modelo subiu para {score_after:.2f} no pré-fechamento"
        return "o recálculo de pré-fechamento passou a priorizar este atleta"
    if action == "SAIU":
        score_before = number(before, "EXP_SCORE", "exp_score")
        score_after = number(after, "EXP_SCORE", "exp_score") if after else 0.0
        if score_before and score_after and score_after < score_before:
            return f"expectativa do modelo caiu de {score_before:.2f} para {score_after:.2f}"
        return "o recálculo de pré-fechamento deixou de priorizar este atleta"
    score_before = number(before, "EXP_SCORE", "exp_score")
    score_after = number(after, "EXP_SCORE", "exp_score")
    if score_before or score_after:
        delta = score_after - score_before
        if abs(delta) >= 0.01:
            return f"expectativa do modelo variou {delta:+.2f} ponto(s)"
    price_before = number(before, "PRECO", "preco")
    price_after = number(after, "PRECO", "preco")
    if price_before or price_after:
        delta = price_after - price_before
        if abs(delta) >= 0.01:
            return f"preço variou {delta:+.2f} cartoleta(s)"
    return "permaneceu estável entre a abertura e o pré-fechamento"


def compare_team(before: Dict[str, Any], after: Dict[str, Any], model: str) -> Dict[str, Any]:
    b = index_players(before, starters_only=True)
    a = index_players(after, starters_only=True)
    entered = []
    exited = []
    kept = []
    for key in sorted(set(a) | set(b)):
        if key in a and key not in b:
            entered.append({"nome": player_name(a[key]), "motivo": reason({}, a[key], "ENTROU")})
        elif key in b and key not in a:
            exited.append({"nome": player_name(b[key]), "motivo": reason(b[key], {}, "SAIU")})
        else:
            kept.append({"nome": player_name(a[key]), "motivo": reason(b[key], a[key], "MANTEVE")})

    cap_before = clean(before.get("capitao") or (before.get("meta") or {}).get("capitao"))
    cap_after = clean(after.get("capitao") or (after.get("meta") or {}).get("capitao"))
    form_before = clean(before.get("formacao") or (before.get("meta") or {}).get("esquema"))
    form_after = clean(after.get("formacao") or (after.get("meta") or {}).get("esquema"))
    cost_before = base.as_float(before.get("custo_total") or (before.get("meta") or {}).get("custo_total"))
    cost_after = base.as_float(after.get("custo_total") or (after.get("meta") or {}).get("custo_total"))

    return {
        "modelo": model,
        "houve_mudanca": bool(entered or exited or cap_before != cap_after or form_before != form_after or abs(cost_after - cost_before) >= 0.01),
        "entraram": entered,
        "sairam": exited,
        "mantidos": kept,
        "capitao_abertura": cap_before,
        "capitao_pre_fechamento": cap_after,
        "capitao_mudou": cap_before != cap_after,
        "formacao_abertura": form_before,
        "formacao_pre_fechamento": form_after,
        "formacao_mudou": form_before != form_after,
        "custo_abertura": round(cost_before, 2),
        "custo_pre_fechamento": round(cost_after, 2),
        "variacao_custo": round(cost_after - cost_before, 2),
    }


def position(item: Dict[str, Any]) -> str:
    return clean(item.get("POS") or item.get("pos") or item.get("posicao")).upper()


def compare_top5(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"posicoes": {}, "total_entraram": 0, "total_sairam": 0, "total_subiram": 0, "total_cairam": 0}
    positions = sorted(set(position(x) for x in rows(before) + rows(after) if position(x)))
    for pos in positions:
        b_rows = [x for x in rows(before) if position(x) == pos]
        a_rows = [x for x in rows(after) if position(x) == pos]
        b_idx = {player_key(x): (i + 1, x) for i, x in enumerate(b_rows)}
        a_idx = {player_key(x): (i + 1, x) for i, x in enumerate(a_rows)}
        entered, exited, moved, kept = [], [], [], []
        for key in sorted(set(b_idx) | set(a_idx)):
            if key in a_idx and key not in b_idx:
                rank, item = a_idx[key]
                entered.append({"nome": player_name(item), "posicao": rank, "motivo": reason({}, item, "ENTROU")})
            elif key in b_idx and key not in a_idx:
                rank, item = b_idx[key]
                exited.append({"nome": player_name(item), "posicao_anterior": rank, "motivo": reason(item, {}, "SAIU")})
            else:
                rb, ib = b_idx[key]
                ra, ia = a_idx[key]
                if rb != ra:
                    direction = "SUBIU" if ra < rb else "CAIU"
                    moved.append({"nome": player_name(ia), "de": rb, "para": ra, "movimento": direction, "motivo": reason(ib, ia, "MANTEVE")})
                else:
                    kept.append({"nome": player_name(ia), "posicao": ra})
        result["posicoes"][pos] = {"entraram": entered, "sairam": exited, "mudaram_posicao": moved, "mantidos": kept}
        result["total_entraram"] += len(entered)
        result["total_sairam"] += len(exited)
        result["total_subiram"] += sum(1 for x in moved if x["movimento"] == "SUBIU")
        result["total_cairam"] += sum(1 for x in moved if x["movimento"] == "CAIU")
    result["houve_mudanca"] = any(result[k] for k in ("total_entraram", "total_sairam", "total_subiram", "total_cairam"))
    return result


def load_phase_snapshots(root: Path, rodada: int, evento_times: str, evento_top5: str) -> Dict[str, Dict[str, Any]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    for slug in ("economico", "intermediario", "pontuacao"):
        path = f"data/publicacoes_atuais/time_{slug}_rodada_{rodada}.json"
        payloads[slug], _ = find_snapshot(root, path, rodada, evento_times, 12)
    top_path = f"data/publicacoes_atuais/top5_rodada_{rodada}.json"
    payloads["top5"], _ = find_snapshot(root, top_path, rodada, evento_top5, 30)
    return payloads


def build_comparison(root: Path, rodada: int) -> Dict[str, Any]:
    opening = load_phase_snapshots(root, rodada, "SELECAO_INICIAL", "SELECAO_INICIAL")
    pre = load_phase_snapshots(root, rodada, "PRE_FECHAMENTO_TIMES", "PRE_FECHAMENTO_TOP5")
    teams = {
        "economico": compare_team(opening["economico"], pre["economico"], "Time Econômico"),
        "intermediario": compare_team(opening["intermediario"], pre["intermediario"], "Time Intermediário"),
        "pontuacao": compare_team(opening["pontuacao"], pre["pontuacao"], "Time para Pontuar"),
    }
    top5 = compare_top5(opening["top5"], pre["top5"])
    changed_teams = [name for name, item in teams.items() if item["houve_mudanca"]]
    return {
        "versao": VERSION,
        "rodada": rodada,
        "comparacao_obrigatoria": True,
        "houve_mudanca": bool(changed_teams or top5["houve_mudanca"]),
        "times_com_mudanca": changed_teams,
        "times": teams,
        "top5": top5,
        "criterio_motivos": "motivos derivados de mudança de seleção, ranking, expectativa do modelo, preço, capitão, formação e custo disponíveis nos snapshots",
    }


def build(rodada: int, root: Path, fase: str) -> Path:
    fase = clean(fase).upper()
    if fase == "INICIAL":
        sources = prepare_initial(rodada, root)
        path = base.build(rodada, root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fase_video"] = "INICIAL"
        data["versao_automacao_fases"] = VERSION
        data["snapshots_recuperados_do_git"] = sources
        data["fotografia_abertura_preservada"] = True
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    if fase == "PRE_FECHAMENTO":
        path = fase_v1.build_pre_fechamento(rodada, root)
        data = json.loads(path.read_text(encoding="utf-8"))
        comparison = build_comparison(root, rodada)
        data["versao_automacao_fases"] = VERSION
        data["comparacao_abertura_pre_fechamento"] = comparison
        data["comparacao_abertura_pre_fechamento_ok"] = True
        data["fotografia_abertura_preservada"] = True
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    raise RuntimeError(f"Fase inválida: {fase}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--fase", required=True, choices=["INICIAL", "PRE_FECHAMENTO"])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    print(build(args.rodada, Path(args.repo_root).resolve(), args.fase))


if __name__ == "__main__":
    main()
