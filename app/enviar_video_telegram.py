from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
ABA_TELEGRAM = os.getenv("ABA_TELEGRAM", "Telegram_Cartola").strip()
CONTA_TELEGRAM = os.getenv("CONTA_TELEGRAM", "DICAS CARTOLA PORTAL SIMONSPORTS").strip()
CHAT_FALLBACK = os.getenv("TELEGRAM_CHAT_FALLBACK", "@dicascartolaportalsimonsports").strip()


def credencial_google() -> str:
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        Path(path).write_text(json.dumps(json.loads(raw), ensure_ascii=False), encoding="utf-8")
    if not Path(path).exists():
        raise RuntimeError("Credencial Google ausente.")
    return path


def obter_telegram() -> Dict[str, str]:
    credentials = Credentials.from_service_account_file(
        credencial_google(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    values = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=PLANILHA_ID, range=f"'{ABA_TELEGRAM}'!A:D")
        .execute()
        .get("values", [])
    )
    if not values:
        raise RuntimeError("Aba de credenciais do Telegram vazia.")
    headers = [str(v).strip().upper() for v in values[0]]
    idx = {name: headers.index(name) for name in ("REDE", "CONTA", "CHAVE", "VALOR")}
    found: Dict[str, str] = {}
    for row in values[1:]:
        def get(name: str) -> str:
            i = idx[name]
            return str(row[i]).strip() if i < len(row) else ""
        if get("REDE").upper() != "TELEGRAM":
            continue
        if CONTA_TELEGRAM and get("CONTA").upper() != CONTA_TELEGRAM.upper():
            continue
        found[get("CHAVE").upper()] = get("VALOR")
    token = found.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = found.get("TELEGRAM_CHAT_ID", "") or CHAT_FALLBACK
    if not token or not chat_id:
        raise RuntimeError("Token ou chat_id do Telegram não encontrado.")
    return {"token": token, "chat_id": chat_id}


def enviar(video: Path, legenda: str) -> None:
    if not video.exists() or video.stat().st_size == 0:
        raise RuntimeError(f"Vídeo ausente: {video}")
    cfg = obter_telegram()
    with video.open("rb") as fh:
        response = requests.post(
            f"https://api.telegram.org/bot{cfg['token']}/sendVideo",
            data={
                "chat_id": cfg["chat_id"],
                "caption": legenda[:1024],
                "supports_streaming": "true",
            },
            files={"video": (video.name, fh, "video/mp4")},
            timeout=600,
        )
    if not response.ok:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text}")
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram recusou o vídeo: {payload}")
    print(f"Vídeo enviado: {video} | mensagem={payload['result']['message_id']}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--rodada", required=True, type=int)
    parser.add_argument("--fase", required=True, choices=["INICIAL", "PRE_FECHAMENTO"])
    args = parser.parse_args()
    titulo = "Análise inicial" if args.fase == "INICIAL" else "Análise de pré-fechamento"
    legenda = (
        f"🎙 {titulo} • Rodada {args.rodada}\n\n"
        "Portal SimonSports\n"
        "🔗 @dicascartolaportalsimonsports"
    )
    enviar(Path(args.video), legenda)


if __name__ == "__main__":
    main()
