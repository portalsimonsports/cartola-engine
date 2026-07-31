from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"versao": 1, "rodadas": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("rodadas", {})
            return data
    except Exception:
        pass
    return {"versao": 1, "rodadas": {}}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def api_status() -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/mercado/status",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Resposta inválida do status do mercado.")
    return payload


def closing_time(payload: Dict[str, Any]) -> datetime | None:
    raw = payload.get("fechamento")
    if isinstance(raw, dict):
        raw = raw.get("timestamp") or raw.get("data") or raw.get("date")
    if raw in (None, ""):
        raw = payload.get("fechamento_mercado")
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
        raise RuntimeError(
            f"Dispatch {event_type} falhou: HTTP {response.status_code} - {response.text}"
        )
    print(f"Dispatch enviado: {event_type} | {json.dumps(payload, ensure_ascii=False)}")


def live_payload(round_value: int, publication_type: str, event_name: str) -> Dict[str, Any]:
    return {
        "origem": "cartola_ciclo_github",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": event_name,
        "tipo_publicacao": publication_type,
        "contexto": "ENCERRAMENTO" if round_value else "",
        "rodada": round_value,
        "payload": {
            "rodada": round_value,
            "evento_programado": event_name,
            "tipo_publicacao": publication_type,
            "forcar_envio": True,
        },
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
    status = api_status()
    current_round = force_round or as_int(
        status.get("rodada_atual") or status.get("rodada") or status.get("game_round")
    )
    if not current_round:
        raise RuntimeError(f"Rodada atual não identificada: {status}")

    market_code = as_int(status.get("status_mercado"), 0)
    market_open = market_code == 1
    close = closing_time(status)
    now = datetime.now(timezone.utc)
    minutes_to_close = (close - now).total_seconds() / 60 if close else None

    state = load_state()
    rounds = state.setdefault("rodadas", {})
    round_state = rounds.setdefault(str(current_round), {})
    events: List[str] = []

    previous_round = current_round - 1
    previous_state = rounds.setdefault(str(previous_round), {})

    if market_open or force_all:
        if force_all or not previous_state.get("encerramento_publicado"):
            for publication_type, event_name in (
                ("DESEMPENHO_TIMES", "DESEMPENHO_FINAL_TIMES"),
                ("DESEMPENHO_TOP5", "DESEMPENHO_FINAL_TOP5"),
                ("JOGOS_FINALIZADOS", "JOGOS_FINALIZADOS"),
            ):
                dispatch("cartola_live_publish", live_payload(previous_round, publication_type, event_name))
                events.append(f"{event_name}_R{previous_round}")
            previous_state["encerramento_publicado"] = True

        if force_all or not round_state.get("video_inicial"):
            dispatch(
                "cartola_video_analise",
                {"rodada": current_round, "fase": "INICIAL", "forcar": force_all},
            )
            round_state["video_inicial"] = True
            events.append(f"VIDEO_INICIAL_R{current_round}")

        if force_all or not round_state.get("selecao_inicial"):
            dispatch("cartola_publish_times", selection_payload(current_round, "SELECAO_INICIAL", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "SELECAO_INICIAL", "top5"))
            round_state["selecao_inicial"] = True
            events.append(f"SELECAO_INICIAL_R{current_round}")

        preclose = minutes_to_close is not None and 30 < minutes_to_close <= 150
        if force_all or (preclose and not round_state.get("pre_fechamento")):
            dispatch("cartola_publish_times", selection_payload(current_round, "PRE_FECHAMENTO_TIMES", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "PRE_FECHAMENTO_TOP5", "top5"))
            dispatch(
                "cartola_video_analise",
                {"rodada": current_round, "fase": "PRE_FECHAMENTO", "forcar": force_all},
            )
            round_state["pre_fechamento"] = True
            events.append(f"PRE_FECHAMENTO_R{current_round}")

        confirmed = minutes_to_close is not None and 0 < minutes_to_close <= 25
        if force_all or (confirmed and not round_state.get("confirmados")):
            dispatch("cartola_publish_times", selection_payload(current_round, "CONFIRMADOS", "times"))
            dispatch("cartola_publish_top5", selection_payload(current_round, "CONFIRMADOS", "top5"))
            round_state["confirmados"] = True
            events.append(f"CONFIRMADOS_R{current_round}")

    round_state.update(
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
