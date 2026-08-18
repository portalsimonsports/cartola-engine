from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from gerar_resultados_telegram import enviar_foto
from publicar_classificacao_brasileirao import ler_classificacao
from render_classificacao_brasileirao import render_classificacao_brasileirao


PAYLOAD_FILE = Path(os.getenv("PAYLOAD_FILE", "data/payload_dispatch.json"))
STATE_FILE = Path(
    os.getenv(
        "CLASSIFICACAO_LIVE_STATE",
        "data/publicacoes_atuais/classificacao_brasileirao_live_estado.json",
    )
)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output").strip() or "output"
TZ_NAME = os.getenv("TZ", "America/Sao_Paulo").strip() or "America/Sao_Paulo"


ALIASES = {
    "FLA": {"FLA", "FLAMENGO", "CR FLAMENGO"},
    "BOT": {"BOT", "BOTAFOGO", "BOTAFOGO FR"},
    "COR": {"COR", "CORINTHIANS", "SC CORINTHIANS PAULISTA"},
    "BAH": {"BAH", "BAHIA", "EC BAHIA"},
    "FLU": {"FLU", "FLUMINENSE", "FLUMINENSE FC"},
    "VAS": {"VAS", "VASCO", "VASCO DA GAMA", "CR VASCO DA GAMA"},
    "PAL": {"PAL", "PALMEIRAS", "SE PALMEIRAS"},
    "SAO": {"SAO", "SAO PAULO", "SÃO PAULO", "SAO PAULO FC", "SÃO PAULO FC"},
    "SAN": {"SAN", "SANTOS", "SANTOS FC"},
    "RBB": {"RBB", "BRAGANTINO", "RED BULL BRAGANTINO", "RB BRAGANTINO"},
    "CAM": {"CAM", "ATLETICO MG", "ATLÉTICO MG", "ATLETICO-MG", "ATLÉTICO-MG", "ATLETICO MINEIRO"},
    "CRU": {"CRU", "CRUZEIRO", "CRUZEIRO EC"},
    "GRE": {"GRE", "GREMIO", "GRÊMIO", "GREMIO FBPA", "GRÊMIO FBPA"},
    "INT": {"INT", "INTERNACIONAL", "SC INTERNACIONAL"},
    "VIT": {"VIT", "VITORIA", "VITÓRIA", "EC VITORIA", "EC VITÓRIA"},
    "CAP": {"CAP", "ATHLETICO PR", "ATHLETICO-PR", "ATHLETICO PARANAENSE", "CLUB ATHLETICO PARANAENSE"},
    "CFC": {"CFC", "CORITIBA", "CORITIBA FC"},
    "CHA": {"CHA", "CHAPECOENSE", "ASSOCIACAO CHAPECOENSE", "ASSOCIAÇÃO CHAPECOENSE"},
    "REM": {"REM", "REMO", "CLUBE DO REMO"},
    "MIR": {"MIR", "MIRASSOL", "MIRASSOL FC"},
}

LIVE_STATUS = (
    "ANDAMENTO",
    "AO VIVO",
    "LIVE",
    "1T",
    "2T",
    "INTERVAL",
    "ENCERR",
    "FINALIZ",
    "FIM DE JOGO",
    "FINAL",
)


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _num(value: Any, default: int = 0) -> int:
    text = _safe(value).replace(",", ".")
    if not text:
        return default
    try:
        return int(float(text))
    except Exception:
        return default


def _norm(value: Any) -> str:
    text = _safe(value).upper()
    try:
        import unicodedata

        text = "".join(
            c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
        )
    except Exception:
        pass
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def _alias_index() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sigla, values in ALIASES.items():
        out[_norm(sigla)] = sigla
        for value in values:
            out[_norm(value)] = sigla
    return out


ALIAS_INDEX = _alias_index()


def _team_code(match: Dict[str, Any], home: bool) -> str:
    keys = (
        (
            "casa_sigla",
            "mandante_abrev",
            "home_abbr",
            "clube_mandante",
            "mandante_sigla",
            "casa_nome",
            "mandante",
            "home",
            "time_casa",
            "casa",
            "equipe_mandante",
        )
        if home
        else (
            "fora_sigla",
            "visitante_abrev",
            "away_abbr",
            "clube_visitante",
            "visitante_sigla",
            "fora_nome",
            "visitante",
            "away",
            "time_fora",
            "fora",
            "equipe_visitante",
        )
    )
    for key in keys:
        value = match.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, dict):
            for subkey in ("abreviacao", "sigla", "nome", "name"):
                if value.get(subkey):
                    code = ALIAS_INDEX.get(_norm(value.get(subkey)))
                    if code:
                        return code
        else:
            code = ALIAS_INDEX.get(_norm(value))
            if code:
                return code
    return ""


def _score(match: Dict[str, Any], home: bool) -> Optional[int]:
    keys = (
        ("placar_casa", "placar_mandante", "gols_mandante", "home_score", "gm")
        if home
        else ("placar_fora", "placar_visitante", "gols_visitante", "away_score", "gv")
    )
    for key in keys:
        value = match.get(key)
        if value not in (None, ""):
            try:
                return int(float(str(value).replace(",", ".")))
            except Exception:
                pass
    return None


def _status(match: Dict[str, Any]) -> str:
    return _norm(
        match.get("status")
        or match.get("situacao")
        or match.get("fase")
        or match.get("status_transmissao")
        or ""
    )


def _is_live_or_finished(match: Dict[str, Any]) -> bool:
    status = _status(match)
    if not status:
        return False
    return any(_norm(token) in status for token in LIVE_STATUS)


def _extract_matches(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    stack: List[Any] = [data]
    seen = set()

    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, dict):
            for key, value in current.items():
                if key in ("partidas", "jogos", "resultados", "matches", "lista") and isinstance(value, list):
                    candidates.extend(item for item in value if isinstance(item, dict))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(item for item in current if isinstance(item, (dict, list)))

    unique: List[Dict[str, Any]] = []
    hashes = set()
    for match in candidates:
        home = _team_code(match, True)
        away = _team_code(match, False)
        if not home or not away:
            continue
        key = json.dumps(match, sort_keys=True, ensure_ascii=False, default=str)
        if key in hashes:
            continue
        hashes.add(key)
        unique.append(match)
    return unique


def _match_key(match: Dict[str, Any]) -> str:
    for key in ("partida_id", "jogo_id", "id", "match_id"):
        if match.get(key) not in (None, ""):
            return f"ID:{_safe(match.get(key))}"
    return f"{_team_code(match, True)}x{_team_code(match, False)}"


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


def _base_signature(base: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "nome": t.get("nome"),
            "j": int(t.get("j") or 0),
            "pts": int(t.get("pts") or 0),
            "v": int(t.get("v") or 0),
            "saldo": int(t.get("saldo") or 0),
        }
        for t in base
    ]


def _classification_signature(teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "nome": t["nome"],
            "pos": t["pos"],
            "pts": t["pts"],
            "v": t["v"],
            "saldo": t["saldo"],
            "gm": t["gm"],
        }
        for t in teams
    ]


def _apply_matches(base: List[Dict[str, Any]], matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    table = {str(t.get("nome") or "").upper(): deepcopy(t) for t in base}

    for match in matches:
        if not _is_live_or_finished(match):
            continue
        home = _team_code(match, True)
        away = _team_code(match, False)
        hs = _score(match, True)
        as_ = _score(match, False)
        if not home or not away or hs is None or as_ is None:
            continue
        if home not in table or away not in table:
            continue

        h = table[home]
        a = table[away]
        h["j"] = int(h.get("j") or 0) + 1
        a["j"] = int(a.get("j") or 0) + 1
        h["gm"] = int(h.get("gm") or 0) + hs
        h["gs"] = int(h.get("gs") or 0) + as_
        a["gm"] = int(a.get("gm") or 0) + as_
        a["gs"] = int(a.get("gs") or 0) + hs
        h["saldo"] = h["gm"] - h["gs"]
        a["saldo"] = a["gm"] - a["gs"]

        if hs > as_:
            h["v"] = int(h.get("v") or 0) + 1
            a["d"] = int(a.get("d") or 0) + 1
            h["pts"] = int(h.get("pts") or 0) + 3
        elif hs < as_:
            a["v"] = int(a.get("v") or 0) + 1
            h["d"] = int(h.get("d") or 0) + 1
            a["pts"] = int(a.get("pts") or 0) + 3
        else:
            h["e"] = int(h.get("e") or 0) + 1
            a["e"] = int(a.get("e") or 0) + 1
            h["pts"] = int(h.get("pts") or 0) + 1
            a["pts"] = int(a.get("pts") or 0) + 1

    teams = list(table.values())
    teams.sort(key=lambda t: (-int(t["pts"]), -int(t["v"]), -int(t["saldo"]), -int(t["gm"]), t["nome"]))
    for pos, team in enumerate(teams, start=1):
        team["pos"] = pos
    return teams[:20]


def _round_from_payload(payload: Dict[str, Any]) -> int:
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return _num(
        payload.get("rodada")
        or inner.get("rodada")
        or inner.get("rodada_atual")
        or payload.get("rodada_atual")
    )


def _caption(round_number: int) -> str:
    suffix = f" • Rodada {round_number}" if round_number else ""
    return (
        f"<b>Classificação Parcial do Brasileirão{suffix}</b>\n"
        "Atualizada de acordo com os placares ao vivo.\n\n"
        "📡 Portal SimonSports\n"
        "🔗 @dicascartolaportalsimonsports"
    )


def main() -> None:
    if not PAYLOAD_FILE.exists():
        print("Classificação Live: payload não encontrado; ignorando.")
        return

    payload = json.loads(PAYLOAD_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("Classificação Live: payload inválido; ignorando.")
        return

    incoming = _extract_matches(payload)
    if not incoming:
        print("Classificação Live: evento sem partidas; ignorando.")
        return

    base = ler_classificacao()
    if len(base) < 20:
        raise RuntimeError(f"Classificação Live: base incompleta ({len(base)} clubes).")

    round_number = _round_from_payload(payload)
    state = _load_state()
    base_sig = _base_signature(base)

    # Nova rodada ou atualização consolidada da base: descarta jogos acumulados antigos.
    if int(state.get("rodada") or 0) != round_number or state.get("base_signature") != base_sig:
        state = {
            "rodada": round_number,
            "base_signature": base_sig,
            "partidas": {},
            "last_signature": [],
        }

    stored = state.get("partidas") if isinstance(state.get("partidas"), dict) else {}
    for match in incoming:
        stored[_match_key(match)] = match
    state["partidas"] = stored

    applicable = [m for m in stored.values() if isinstance(m, dict) and _is_live_or_finished(m)]
    if not applicable:
        _save_state(state)
        print("Classificação Live: nenhum jogo ao vivo/encerrado com placar válido.")
        return

    teams = _apply_matches(base, applicable)
    base_positions = {str(t["nome"]): int(t["pos"]) for t in base}
    for team in teams:
        team["variacao"] = base_positions.get(str(team["nome"]), int(team["pos"])) - int(team["pos"])

    signature = _classification_signature(teams)
    if signature == state.get("last_signature"):
        _save_state(state)
        print("Classificação Live: tabela sem mudança real; publicação dispensada.")
        return

    # Exige pelo menos um jogo com placar reconhecido antes de publicar.
    recognized = 0
    for match in applicable:
        if _team_code(match, True) and _team_code(match, False) and _score(match, True) is not None and _score(match, False) is not None:
            recognized += 1
    if recognized <= 0:
        _save_state(state)
        print("Classificação Live: nenhum placar reconhecido; publicação dispensada.")
        return

    now = datetime.now(ZoneInfo(TZ_NAME))
    path = render_classificacao_brasileirao(
        teams,
        OUTPUT_DIR,
        "parcial_ao_vivo",
        now.strftime("%d/%m/%Y - %H:%M"),
        str(round_number or ""),
    )
    enviar_foto(path, _caption(round_number))

    state["last_signature"] = signature
    state["updated_at"] = now.isoformat()
    state["last_image"] = path
    _save_state(state)
    print(
        "Classificação Live publicada: "
        f"rodada={round_number}; jogos considerados={recognized}; arquivo={path}"
    )


if __name__ == "__main__":
    main()
