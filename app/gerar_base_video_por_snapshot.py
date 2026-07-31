from __future__ import annotations

import argparse
import json
import subprocess
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_BASE = "https://api.cartola.globo.com"


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def parse_datetime(value: Any) -> Optional[datetime]:
    text = safe(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def read_json(path: Path, required: bool = True) -> Dict[str, Any]:
    if not path.exists():
        if required:
            raise RuntimeError(f"Snapshot obrigatório não encontrado: {path}")
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        if required:
            raise RuntimeError(f"Snapshot inválido: {path}")
        return {}
    return payload


def snapshot_path(root: Path, rodada: int, nome: str) -> Path:
    return root / "data" / "publicacoes_atuais" / f"{nome}_rodada_{rodada}.json"


def athletes(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    return [item for item in raw if isinstance(item, dict)]


def starters(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item for item in athletes(payload)
        if safe(item.get("status"), "TITULAR").upper() != "RESERVA"
    ]


def validate_team_snapshot(payload: Dict[str, Any], rodada: int, label: str) -> None:
    if as_int(payload.get("rodada")) != rodada:
        raise RuntimeError(
            f"Snapshot {label} pertence à rodada {payload.get('rodada')}, não à rodada {rodada}."
        )
    if safe(payload.get("evento_programado")).upper() != "SELECAO_INICIAL":
        raise RuntimeError(
            f"Snapshot {label} não é da SELECAO_INICIAL: {payload.get('evento_programado')}"
        )
    if len(athletes(payload)) < 12:
        raise RuntimeError(f"Snapshot {label} incompleto: {len(athletes(payload))} registros.")


def target_time_from_teams(times: Dict[str, Dict[str, Any]]) -> Optional[datetime]:
    candidates: List[datetime] = []
    for payload in times.values():
        for key in ("gerado_em", "atualizado_em", "timestamp_base"):
            parsed = parse_datetime(payload.get(key))
            if parsed:
                candidates.append(parsed)
        for item in athletes(payload):
            parsed = parse_datetime(item.get("data"))
            if parsed:
                candidates.append(parsed)
    return max(candidates) if candidates else None


def git_json(root: Path, commit: str, path: str) -> Dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        payload = json.loads(result.stdout)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def git_commits_for_path(root: Path, path: str) -> List[str]:
    result = subprocess.run(
        ["git", "log", "--format=%H", "--all", "--", path],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def commit_time(root: Path, commit: str) -> Optional[datetime]:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", commit],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return parse_datetime(result.stdout.strip()) if result.returncode == 0 else None


def recover_initial_top5(
    root: Path,
    rodada: int,
    current_snapshot: Dict[str, Any],
    target_time: Optional[datetime],
) -> Tuple[Dict[str, Any], str]:
    if as_int(current_snapshot.get("rodada")) == rodada and len(athletes(current_snapshot)) >= 30:
        return current_snapshot, f"data/publicacoes_atuais/top5_rodada_{rodada}.json"

    candidates: List[Tuple[float, datetime, str, Dict[str, Any]]] = []
    historical_path = "data/top5_atual.json"

    for commit in git_commits_for_path(root, historical_path):
        payload = git_json(root, commit, historical_path)
        if as_int(payload.get("rodada")) != rodada or len(athletes(payload)) < 30:
            continue
        when = parse_datetime(payload.get("atualizado_em")) or commit_time(root, commit)
        if not when:
            continue
        distance = abs((when - target_time).total_seconds()) if target_time else 0.0
        candidates.append((distance, when, commit, payload))

    if not candidates:
        raise RuntimeError(
            f"Não foi encontrada no histórico Git uma revisão completa do Top 5 da rodada {rodada}."
        )

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, when, commit, payload = candidates[0]

    normalized = {
        "origem": "historico_git_top5_atual",
        "pipeline": payload.get("pipeline", "jobtelegram"),
        "tipo_publicacao": "top5",
        "evento_programado": "SELECAO_INICIAL",
        "rodada": rodada,
        "atualizado_em": payload.get("atualizado_em") or when.isoformat(),
        "commit_origem": commit,
        "dados": athletes(payload),
    }

    restored = snapshot_path(root, rodada, "top5_inicial_recuperado")
    restored.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Top 5 inicial recuperado: commit={commit} horario={when.isoformat()} "
        f"registros={len(normalized['dados'])}"
    )
    return normalized, str(restored.relative_to(root))


def cartola_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def normalize_games(rodada: int) -> List[Dict[str, Any]]:
    payload = cartola_get(f"partidas/{rodada}")
    clubes = payload.get("clubes") or {}

    def clube(clube_id: Any) -> Dict[str, Any]:
        if not isinstance(clubes, dict):
            return {}
        value = clubes.get(str(clube_id))
        if value is None:
            value = clubes.get(as_int(clube_id))
        return value if isinstance(value, dict) else {}

    jogos: List[Dict[str, Any]] = []
    for partida in payload.get("partidas") or []:
        if not isinstance(partida, dict):
            continue
        casa_id = partida.get("clube_casa_id") or partida.get("casa_id")
        fora_id = partida.get("clube_visitante_id") or partida.get("visitante_id")
        casa = clube(casa_id)
        fora = clube(fora_id)
        data_raw = safe(partida.get("partida_data") or partida.get("data"))
        data = "Data a confirmar"
        hora = "Horário a confirmar"
        if data_raw:
            try:
                parsed = datetime.fromisoformat(data_raw.replace("Z", "+00:00"))
                data = parsed.strftime("%d/%m")
                hora = parsed.strftime("%H:%M")
            except ValueError:
                data = data_raw
        mandante = safe(casa.get("nome") or casa.get("abreviacao") or casa_id)
        visitante = safe(fora.get("nome") or fora.get("abreviacao") or fora_id)
        jogos.append({
            "mandante": mandante,
            "mandante_sigla": safe(casa.get("abreviacao") or mandante),
            "visitante": visitante,
            "visitante_sigla": safe(fora.get("abreviacao") or visitante),
            "data": data,
            "hora": hora,
            "estadio": safe(partida.get("local"), "Local a confirmar"),
            "pos_mandante": as_int(casa.get("posicao")),
            "pos_visitante": as_int(fora.get("posicao")),
            "forma_mandante": "recorte histórico preservado fora do snapshot",
            "forma_visitante": "recorte histórico preservado fora do snapshot",
            "leitura": (
                f"{mandante} enfrenta {visitante}. A análise considera o confronto oficial "
                "e os atletas registrados no snapshot publicado da seleção inicial."
            ),
        })
    if not jogos:
        raise RuntimeError(f"A API não retornou partidas válidas para a rodada {rodada}.")
    return jogos


def build_players(times: Dict[str, Dict[str, Any]]) -> OrderedDict[str, Dict[str, Any]]:
    result: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    names = {
        "economico": "Econômico",
        "intermediario": "Intermediário",
        "pontuacao": "Para Pontuar",
    }
    for slug, payload in times.items():
        for atleta in starters(payload):
            nome = safe(atleta.get("nome"))
            if not nome:
                continue
            item = result.setdefault(nome, {
                "posicao": safe(atleta.get("pos") or atleta.get("posicao")),
                "clube": safe(atleta.get("clube")),
                "preco": as_float(atleta.get("preco")),
                "modelos": [],
            })
            modelo = names[slug]
            if modelo not in item["modelos"]:
                item["modelos"].append(modelo)
    for nome, item in result.items():
        qtd = len(item["modelos"])
        item["racional"] = (
            f"{nome} aparece em {qtd} modelo{'s' if qtd != 1 else ''} do snapshot publicado. "
            "A avaliação preserva exatamente a seleção enviada ao canal."
        )
        item.update({
            "adversario": "",
            "pos_clube": 0,
            "pos_adversario": 0,
            "forma_clube": "",
            "forma_adversario": "",
        })
    return result


def normalize_top5_for_video(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = athletes(payload)
    return {
        "rodada": as_int(payload.get("rodada")),
        "evento_programado": "SELECAO_INICIAL",
        "tipo_publicacao": "top5",
        "atualizado_em": payload.get("atualizado_em", ""),
        "commit_origem": payload.get("commit_origem", ""),
        "dados": [
            {
                "RODADA": as_int(row.get("RODADA") or row.get("rodada")),
                "POS": safe(row.get("POS") or row.get("pos") or row.get("posicao")),
                "NOME": safe(row.get("NOME") or row.get("nome")),
                "CLUBE": safe(row.get("CLUBE") or row.get("clube")),
                "PRECO": as_float(row.get("PRECO") or row.get("preco")),
                "EXP_SCORE": as_float(row.get("EXP_SCORE") or row.get("exp_score")),
                "FACTOR": as_float(row.get("FACTOR") or row.get("factor")),
                "ATLETA_ID": as_int(row.get("ATLETA_ID") or row.get("atleta_id")),
            }
            for row in rows
        ],
    }


def team_summary(payload: Dict[str, Any], nome: str) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        "nome": nome,
        "custo": as_float(payload.get("custo_total") or meta.get("custo_total")),
        "capitao": safe(payload.get("capitao") or meta.get("capitao")),
        "ultima_pontuacao": as_float(meta.get("pontos_total")),
        "participacao": f"{len(starters(payload))}/12",
        "tipo_pontuacao": "snapshot publicado da seleção inicial",
    }


def build(rodada: int, root: Path) -> Path:
    times = {
        "economico": read_json(snapshot_path(root, rodada, "time_economico")),
        "intermediario": read_json(snapshot_path(root, rodada, "time_intermediario")),
        "pontuacao": read_json(snapshot_path(root, rodada, "time_pontuacao")),
    }
    for slug, payload in times.items():
        validate_team_snapshot(payload, rodada, slug)

    current_top5 = read_json(snapshot_path(root, rodada, "top5"), required=False)
    top5, top5_source = recover_initial_top5(
        root,
        rodada,
        current_top5,
        target_time_from_teams(times),
    )
    if len(athletes(top5)) < 30:
        raise RuntimeError(f"Top 5 recuperado incompleto: {len(athletes(top5))} registros.")

    output = {
        "rodada": rodada,
        "status": "SNAPSHOT_PUBLICADO_SELECAO_INICIAL",
        "publicacao_automatica": True,
        "duracao_alvo_minutos": [10, 15],
        "moeda_falada": "cartoletas",
        "fontes": [
            f"data/publicacoes_atuais/time_economico_rodada_{rodada}.json",
            f"data/publicacoes_atuais/time_intermediario_rodada_{rodada}.json",
            f"data/publicacoes_atuais/time_pontuacao_rodada_{rodada}.json",
            top5_source,
            f"API Cartola: partidas/{rodada}",
        ],
        "times": {
            "economico": team_summary(times["economico"], "Time Econômico"),
            "intermediario": team_summary(times["intermediario"], "Time Intermediário"),
            "pontuacao": team_summary(times["pontuacao"], "Time para Pontuar"),
        },
        "jogos": normalize_games(rodada),
        "jogadores": build_players(times),
        "top5": normalize_top5_for_video(top5),
        "snapshot_evento": "SELECAO_INICIAL",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }

    target = root / "data" / f"analise_tecnica_rodada_{rodada}_v3.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Base gerada pelos snapshots publicados: {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    build(args.rodada, Path(args.repo_root).resolve())


if __name__ == "__main__":
    main()
