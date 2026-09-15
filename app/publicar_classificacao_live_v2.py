from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from gerar_resultados_telegram import enviar_foto
from publicar_classificacao_brasileirao import ler_classificacao
from publicar_classificacao_live_brasileirao import (
    _apply_matches,
    _base_signature,
    _classification_signature,
    _extract_matches,
    _is_live_or_finished,
    _match_key,
    _round_from_payload,
)
from render_classificacao_brasileirao import render_classificacao_brasileirao

PAYLOAD_FILE = Path(os.getenv("PAYLOAD_FILE", "data/payload_classificacao_live.json"))
STATE_FILE = Path(
    os.getenv(
        "CLASSIFICACAO_LIVE_STATE",
        "data/publicacoes_atuais/classificacao_brasileirao_live_estado.json",
    )
)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output").strip() or "output"
TZ_NAME = os.getenv("TZ", "America/Sao_Paulo").strip() or "America/Sao_Paulo"


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _num(value: Any, default: int = 0) -> int:
    text = _safe(value).replace(",", ".")
    if not text:
        return default
    try:
        return int(round(float(text)))
    except Exception:
        return default


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _inner(payload: Dict[str, Any]) -> Dict[str, Any]:
    value = payload.get("payload")
    return value if isinstance(value, dict) else payload


def _event(payload: Dict[str, Any]) -> str:
    inner = _inner(payload)
    return _safe(
        inner.get("evento_programado")
        or payload.get("evento_programado")
        or inner.get("tipo_publicacao")
        or payload.get("tipo_publicacao")
    ).upper()


def _context(payload: Dict[str, Any]) -> str:
    inner = _inner(payload)
    return _safe(inner.get("contexto") or payload.get("contexto")).lower()


def _find_table(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, dict):
        for key in ("classificacao", "classificação", "tabela", "standings"):
            value = obj.get(key)
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return value
        for value in obj.values():
            found = _find_table(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_table(value)
            if found:
                return found
    return []


def _normalize_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    teams: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        nome = _safe(
            row.get("nome")
            or row.get("time")
            or row.get("clube")
            or row.get("equipe")
            or row.get("sigla")
        )
        if not nome:
            continue
        v = _num(row.get("v") if row.get("v") is not None else row.get("vitorias"))
        e = _num(row.get("e") if row.get("e") is not None else row.get("empates"))
        d = _num(row.get("d") if row.get("d") is not None else row.get("derrotas"))
        j = _num(row.get("j") if row.get("j") is not None else row.get("jogos"), v + e + d)
        gm = _num(row.get("gm") if row.get("gm") is not None else row.get("gols_pro"))
        gs = _num(row.get("gs") if row.get("gs") is not None else row.get("gols_contra"))
        saldo = _num(row.get("saldo") if row.get("saldo") is not None else row.get("sg"), gm - gs)
        pts = _num(
            row.get("pts")
            if row.get("pts") is not None
            else row.get("pontos")
            if row.get("pontos") is not None
            else row.get("pts_geral")
        )
        teams.append(
            {
                "clube_id": _num(row.get("clube_id") or row.get("id")),
                "nome": nome,
                "v": v,
                "e": e,
                "d": d,
                "j": j,
                "gm": gm,
                "gs": gs,
                "saldo": saldo,
                "pts": pts,
                "pos": _num(row.get("pos") or row.get("posicao"), idx),
            }
        )

    teams.sort(key=lambda t: (-t["pts"], -t["v"], -t["saldo"], -t["gm"], t["nome"]))
    for pos, team in enumerate(teams, start=1):
        team["pos"] = pos
    return teams[:20]


def _mode(contexto: str) -> str:
    if any(token in contexto for token in ("fechamento", "final", "encerramento")):
        return "fechamento"
    if any(token in contexto for token in ("abertura", "inicio", "inicial")):
        return "abertura"
    return "parcial_ao_vivo"


def _caption(round_number: int, mode: str) -> str:
    rodada = f" • Rodada {round_number}" if round_number else ""
    if mode == "abertura":
        titulo = "Classificação do Brasileirão • Início da rodada"
    elif mode == "fechamento":
        titulo = "Classificação do Brasileirão • Encerramento da rodada"
    else:
        titulo = "Classificação Parcial do Brasileirão"
    return (
        f"<b>{titulo}{rodada}</b>\n"
        "Atualizada conforme os resultados da rodada.\n\n"
        "📡 Portal SimonSports\n"
        "🔗 @dicascartolaportalsimonsports"
    )


def main() -> None:
    if not PAYLOAD_FILE.exists():
        print("Classificação Live V2: payload não encontrado; ignorando.")
        return

    payload = json.loads(PAYLOAD_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("Classificação Live V2: payload inválido; ignorando.")
        return

    evento = _event(payload)
    if evento not in {"LIVE_CLASSIFICACAO", "LIVE_CLASSIFICAÇÃO", "LIVE_CLASSIFICATION", "LIVE_CLASSIFICACAO_CAMPEONATO"} and "LIVE_CLASSIFICACAO" not in evento:
        print(f"Classificação Live V2: evento ignorado ({evento or 'vazio'}).")
        return

    contexto = _context(payload)
    mode = _mode(contexto)
    round_number = _round_from_payload(payload)
    base = ler_classificacao()
    if len(base) < 20:
        raise RuntimeError(f"Classificação Live V2: base incompleta ({len(base)} clubes).")

    state = _load_state()
    base_sig = _base_signature(base)
    if int(state.get("rodada") or 0) != round_number or state.get("base_signature") != base_sig:
        state = {
            "rodada": round_number,
            "base_signature": base_sig,
            "partidas": {},
            "last_signature": [],
            "last_context": "",
        }

    direct = _normalize_table(_find_table(payload))
    if len(direct) >= 10:
        teams = direct
    else:
        incoming = _extract_matches(payload)
        stored = state.get("partidas") if isinstance(state.get("partidas"), dict) else {}
        for match in incoming:
            stored[_match_key(match)] = match
        state["partidas"] = stored
        applicable = [m for m in stored.values() if isinstance(m, dict) and _is_live_or_finished(m)]
        teams = _apply_matches(base, applicable) if applicable else [dict(team) for team in base]

    base_positions = {str(team["nome"]): int(team["pos"]) for team in base}
    for team in teams:
        team["variacao"] = base_positions.get(str(team["nome"]), int(team["pos"])) - int(team["pos"])

    signature = _classification_signature(teams)
    force = mode in {"abertura", "fechamento"}
    same_signature = signature == state.get("last_signature")
    same_context = contexto == _safe(state.get("last_context")).lower()

    if same_signature and not force:
        _save_state(state)
        print("Classificação Live V2: tabela sem alteração real; publicação dispensada.")
        return
    if force and same_signature and same_context:
        _save_state(state)
        print("Classificação Live V2: abertura/fechamento já publicado para este contexto.")
        return

    now = datetime.now(ZoneInfo(TZ_NAME))
    path = render_classificacao_brasileirao(
        teams,
        OUTPUT_DIR,
        mode,
        now.strftime("%d/%m/%Y - %H:%M"),
        str(round_number or ""),
    )
    enviar_foto(path, _caption(round_number, mode))

    state["last_signature"] = signature
    state["last_context"] = contexto
    state["updated_at"] = now.isoformat()
    state["last_image"] = path
    _save_state(state)
    print(
        "Classificação Live V2 publicada: "
        f"rodada={round_number}; modo={mode}; contexto={contexto}; arquivo={path}"
    )


if __name__ == "__main__":
    main()
