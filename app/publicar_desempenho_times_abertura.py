from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

import requests

from preparar_desempenho_rodada_anterior_v2 import (
    as_int,
    build_team_payload,
    club_index,
    market_records,
    score_records,
)

API_BASE = "https://api.cartola.globo.com"
REPO = os.getenv("GITHUB_REPOSITORY", "portalsimonsports/cartola-engine").strip()
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida da API: {path}")
    return payload


def build_payload(rodada: int) -> Dict[str, Any]:
    scores = score_records(rodada)
    market = market_records()
    clubs = club_index(rodada)
    return build_team_payload(rodada, scores, market, clubs)


def dispatch(payload: Dict[str, Any]) -> None:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN não disponível")
    response = requests.post(
        f"https://api.github.com/repos/{REPO}/dispatches",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"event_type": "cartola_live_publish", "client_payload": payload},
        timeout=45,
    )
    if response.status_code not in (200, 201, 202, 204):
        raise RuntimeError(
            f"Falha no dispatch: HTTP {response.status_code} - {response.text}"
        )
    print(f"Dispatch aceito: FECHAMENTO_FINAL_TIMES rodada {payload['rodada']}")


def rodada_anterior_atual() -> int:
    status = api_get("mercado/status")
    atual = as_int(status.get("rodada_atual") or status.get("rodada"))
    if atual <= 1:
        raise RuntimeError(f"Rodada atual inválida: {atual}")
    return atual - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, default=0)
    parser.add_argument("--payload-output", default="")
    parser.add_argument("--nao-disparar", action="store_true")
    args = parser.parse_args()

    rodada = args.rodada or rodada_anterior_atual()
    imagem = Path("output") / f"aprovada_desempenho_final_times_rodada_{rodada}.png"
    if imagem.exists() and not args.rodada:
        print(f"Resumo da rodada {rodada} já existe: {imagem}")
        return

    payload = build_payload(rodada)
    output = Path(args.payload_output or f"data/publicacoes_atuais/desempenho_times_rodada_{rodada}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Payload validado com valorização real: {output}")

    if not args.nao_disparar:
        dispatch(payload)


if __name__ == "__main__":
    main()
