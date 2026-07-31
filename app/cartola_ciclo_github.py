from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests

API_BASE = "https://api.cartola.globo.com"
STATE_PATH = Path("data/estado_ciclo_cartola.json")
REPO = os.getenv("GITHUB_REPOSITORY", "portalsimonsports/cartola-engine").strip()
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_state() -> Dict[str, Any]:
    state = load_json(STATE_PATH)
    state.setdefault("versao", 2)
    state.setdefault("rodadas", {})
    return state


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida: {path}")
    return payload


def closing_time(payload: Dict[str, Any]) -> datetime | None:
    raw = payload.get("fechamento")
    if isinstance(raw, dict):
        raw = raw.get("timestamp") or raw.get("data") or raw.get("date")
    raw = raw or payload.get("fechamento_mercado")
    if raw in (None, ""):
        return None
    try:
        if isinstance(raw, (int, float)) or safe(raw).isdigit():
            number = float(raw)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc)
        return datetime.fromisoformat(safe(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def dispatch(event_type: str, payload: Dict[str, Any]) -> None:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN não disponível.")
    response = requests.post(
        f"https://api.github.com/repos/{REPO}/dispatches",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"event_type": event_type, "client_payload": payload},
        timeout=45,
    )
    if response.status_code not in (200, 201, 202, 204):
        raise RuntimeError(f"Dispatch {event_type}: HTTP {response.status_code} - {response.text}")
    print(f"Dispatch: {event_type} | {payload.get('evento_programado') or payload.get('fase')}")


def team_file(round_value: int, slug: str) -> Path:
    return Path("data/publicacoes_atuais") / f"time_{slug}_rodada_{round_value}.json"


def top5_file(round_value: int) -> Path:
    return Path("data/publicacoes_atuais") / f"top5_rodada_{round_value}.json"


def athletes_from_team(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    values = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    return [
        item
        for item in values
        if isinstance(item, dict) and safe(item.get("status"), "TITULAR").upper() != "RESERVA"
    ]


def scored_athletes(round_value: int) -> Dict[str, Dict[str, Any]]:
    payload = api_get(f"atletas/pontuados/{round_value}")
    raw = payload.get("atletas") or payload
    iterable: Iterable[Any]
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []
    result: Dict[str, Dict[str, Any]] = {}
    for item in iterable:
        if not isinstance(item, dict):
            continue
        points = as_float(item.get("pontuacao") or item.get("pontos"))
        names = {
            safe(item.get("apelido")),
            safe(item.get("nome")),
            safe(item.get("slug")),
        }
        for name in names:
            key = norm(name)
            if key:
                result[key] = {"pontos": points, "dados": item}
    return result


def athlete_points(item: Dict[str, Any], score_map: Dict[str, Dict[str, Any]]) -> Tuple[float, bool]:
    for value in (item.get("nome"), item.get("apelido"), item.get("slug")):
        key = norm(value)
        if key in score_map:
            return as_float(score_map[key].get("pontos")), True
    return 0.0, False


def performance_payload(round_value: int, score_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    models = [
        ("ECONOMICO", "economico"),
        ("INTERMEDIARIO", "intermediario"),
        ("PONTUACAO", "pontuacao"),
    ]
    times: Dict[str, Dict[str, Any]] = {}
    for model, slug in models:
        payload = load_json(team_file(round_value, slug))
        players = athletes_from_team(payload)
        captain = norm(payload.get("capitao") or (payload.get("meta") or {}).get("capitao"))
        total = 0.0
        found = 0
        captain_points = 0.0
        for player in players:
            points, exists = athlete_points(player, score_map)
            total += points
            found += int(exists)
            if captain and captain in norm(player.get("nome")):
                captain_points = points
        times[model] = {
            "pontos_sem_c": round(total, 2),
            "pontos_com_c": round(total + captain_points, 2),
            "participacao": f"{found}/12",
            "valorizacao": as_float((payload.get("meta") or {}).get("variacao_total")),
        }
    return {
        "origem": "cartola_ciclo_github",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "FECHAMENTO_FINAL_TIMES",
        "tipo_publicacao": "DESEMPENHO_FINAL_DOS_TIMES",
        "contexto": "ENCERRAMENTO",
        "rodada": round_value,
        "times": times,
        "payload": {"rodada": round_value, "times": times},
    }


def top5_performance_payload(round_value: int, score_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    source = load_json(top5_file(round_value))
    raw = source.get("lista") or source.get("dados") or []
    players: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        points, found = athlete_points(item, score_map)
        copy = dict(item)
        copy["pontos"] = round(points, 2)
        copy["pontuacao_localizada"] = found
        players.append(copy)
    return {
        "origem": "cartola_ciclo_github",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "FECHAMENTO_FINAL_TOP5",
        "tipo_publicacao": "DESEMPENHO_FINAL_TOP5",
        "contexto": "ENCERRAMENTO",
        "rodada": round_value,
        "lista": players,
        "payload": {"rodada": round_value, "lista": players},
    }


def final_games_payload(round_value: int) -> Dict[str, Any]:
    source = api_get(f"partidas/{round_value}")
    clubs = source.get("clubes") or {}

    def club(club_id: Any) -> Dict[str, Any]:
        value = clubs.get(str(club_id)) if isinstance(clubs, dict) else None
        if value is None and isinstance(clubs, dict):
            value = clubs.get(as_int(club_id))
        return value if isinstance(value, dict) else {}

    matches: List[Dict[str, Any]] = []
    for item in source.get("partidas") or []:
        if not isinstance(item, dict):
            continue
        home_id = item.get("clube_casa_id") or item.get("casa_id")
        away_id = item.get("clube_visitante_id") or item.get("visitante_id")
        home = club(home_id)
        away = club(away_id)
        home_score = item.get("placar_oficial_mandante")
        away_score = item.get("placar_oficial_visitante")
        if home_score is None:
            home_score = item.get("placar_casa")
        if away_score is None:
            away_score = item.get("placar_vis") or item.get("placar_visitante")
        if home_score is None or away_score is None:
            continue
        matches.append(
            {
                "mandante": safe(home.get("nome") or home.get("abreviacao") or home_id),
                "visitante": safe(away.get("nome") or away.get("abreviacao") or away_id),
                "mandante_abrev": safe(home.get("abreviacao")),
                "visitante_abrev": safe(away.get("abreviacao")),
                "placar_mandante": home_score,
                "placar_visitante": away_score,
                "data_hora": safe(item.get("partida_data")),
                "local": safe(item.get("local")),
                "gols_mandante": item.get("gols_mandante") or [],
                "gols_visitante": item.get("gols_visitante") or [],
                "status": "ENCERRADO",
            }
        )
    return {
        "origem": "cartola_ciclo_github",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "RESUMO_FINAL_RODADA",
        "tipo_publicacao": "JOGOS_FINALIZADOS",
        "contexto": "ENCERRAMENTO",
        "rodada": round_value,
        "partidas": matches,
        "jogos": matches,
        "payload": {"rodada": round_value, "partidas": matches, "jogos": matches},
    }


def selection_payload(round_value: int, event_name: str, publication_type: str) -> Dict[str, Any]:
    return {
        "origem": "cartola_ciclo_github",
        "pipeline": "jobtelegram",
        "tipo_publicacao": publication_type,
        "rodada": round_value,
        "evento_programado": event_name,
        "forcar_envio": True,
        "payload": {
            "rodada": round_value,
            "evento_programado": event_name,
            "tipo_publicacao": publication_type,
            "forcar_envio": True,
        },
    }


def run(force_round: int = 0, force_all: bool = False) -> Dict[str, Any]:
    status = api_get("mercado/status")
    current_round = force_round or as_int(status.get("rodada_atual") or status.get("rodada"))
    if not current_round:
        raise RuntimeError(f"Rodada atual não identificada: {status}")

    market_code = as_int(status.get("status_mercado"), 0)
    market_open = market_code == 1
    close = closing_time(status)
    now = datetime.now(timezone.utc)
    minutes_to_close = (close - now).total_seconds() / 60 if close else None

    state = load_state()
    rounds = state.setdefault("rodadas", {})
    current_state = rounds.setdefault(str(current_round), {})
    previous_round = current_round - 1
    previous_state = rounds.setdefault(str(previous_round), {})
    events: List[str] = []

    if market_open or force_all:
        if force_all or not previous_state.get("encerramento_publicado"):
            scores = scored_athletes(previous_round)
            dispatch("cartola_live_publish", performance_payload(previous_round, scores))
            dispatch("cartola_live_publish", top5_performance_payload(previous_round, scores))
            dispatch("cartola_live_publish", final_games_payload(previous_round))
            previous_state["encerramento_publicado"] = True
            events.append(f"ENCERRAMENTO_R{previous_round}")

        if force_all or not current_state.get("video_inicial"):
            dispatch("cartola_video_analise", {"rodada": current_round, "fase": "INICIAL", "forcar": force_all})
            current_state["video_inicial"] = True
            events.append(f"VIDEO_INICIAL_R{current_round}")

        if force_all or not current_state.get("selecao_inicial"):
            dispatch("cartola_publish_times", selection_payload(current_round, "SELECAO_INICIAL", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "SELECAO_INICIAL", "top5"))
            current_state["selecao_inicial"] = True
            events.append(f"SELECAO_INICIAL_R{current_round}")

        preclose = minutes_to_close is not None and 30 < minutes_to_close <= 150
        if force_all or (preclose and not current_state.get("pre_fechamento")):
            dispatch("cartola_publish_times", selection_payload(current_round, "PRE_FECHAMENTO_TIMES", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "PRE_FECHAMENTO_TOP5", "top5"))
            dispatch("cartola_video_analise", {"rodada": current_round, "fase": "PRE_FECHAMENTO", "forcar": force_all})
            current_state["pre_fechamento"] = True
            events.append(f"PRE_FECHAMENTO_R{current_round}")

        confirmed = minutes_to_close is not None and 0 < minutes_to_close <= 25
        if force_all or (confirmed and not current_state.get("confirmados")):
            dispatch("cartola_publish_times", selection_payload(current_round, "CONFIRMADOS", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "CONFIRMADOS", "top5"))
            current_state["confirmados"] = True
            events.append(f"CONFIRMADOS_R{current_round}")

    current_state.update(
        {
            "mercado_aberto": market_open,
            "status_mercado": market_code,
            "fechamento": close.isoformat() if close else "",
            "ultima_verificacao": now.isoformat(),
        }
    )
    save_state(state)
    result = {
        "rodada": current_round,
        "mercado_aberto": market_open,
        "status_mercado": market_code,
        "minutos_para_fechamento": minutes_to_close,
        "eventos": events,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, default=0)
    parser.add_argument("--forcar-tudo", action="store_true")
    args = parser.parse_args()
    run(args.rodada, args.forcar_tudo)


if __name__ == "__main__":
    main()
