from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
ABA_TELEGRAM = os.getenv("ABA_TELEGRAM", "Telegram_Cartola").strip()
CONTA_TELEGRAM = os.getenv("CONTA_TELEGRAM", "DICAS CARTOLA PORTAL SIMONSPORTS").strip()
CHAT_FALLBACK = os.getenv("TELEGRAM_CHAT_FALLBACK", "@dicascartolaportalsimonsports").strip()

# Margem conservadora para evitar HTTP 413 no endpoint sendVideo.
MAX_VIDEO_BYTES = int(os.getenv("TELEGRAM_MAX_VIDEO_BYTES", "45000000"))
AUDIO_BITRATE = 64_000


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


def executar(comando: list[str]) -> None:
    print("Executando:", " ".join(comando))
    subprocess.run(comando, check=True)


def duracao_video(video: Path) -> float:
    resultado = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        duracao = float(resultado.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Não foi possível obter a duração de {video}.") from exc
    if duracao <= 0:
        raise RuntimeError(f"Duração inválida para {video}: {duracao}")
    return duracao


def compactar_para_telegram(video: Path) -> Tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    tamanho_original = video.stat().st_size
    print(
        f"Vídeo original: {tamanho_original / 1_000_000:.2f} MB; "
        f"limite operacional: {MAX_VIDEO_BYTES / 1_000_000:.2f} MB"
    )
    if tamanho_original <= MAX_VIDEO_BYTES:
        return video, None

    duracao = duracao_video(video)
    # Reserva margem para áudio, contêiner e variações do codificador.
    bits_disponiveis = int(MAX_VIDEO_BYTES * 8 * 0.92)
    bitrate_video = int((bits_disponiveis / duracao) - AUDIO_BITRATE)
    bitrate_video = max(180_000, bitrate_video)

    temporario: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(
        prefix="cartola-video-telegram-"
    )
    pasta = Path(temporario.name)
    saida = pasta / f"{video.stem}_telegram.mp4"
    passlog = pasta / "ffmpeg-pass"

    filtro = "scale=720:-2:force_original_aspect_ratio=decrease,fps=24"
    comum = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-vf",
        filtro,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        str(bitrate_video),
        "-maxrate",
        str(int(bitrate_video * 1.12)),
        "-bufsize",
        str(int(bitrate_video * 2)),
        "-passlogfile",
        str(passlog),
    ]

    executar(
        comum
        + [
            "-pass",
            "1",
            "-an",
            "-f",
            "mp4",
            os.devnull,
        ]
    )
    executar(
        comum
        + [
            "-pass",
            "2",
            "-map",
            "0:a?",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(saida),
        ]
    )

    if not saida.exists() or saida.stat().st_size == 0:
        temporario.cleanup()
        raise RuntimeError("A compactação do vídeo não gerou um arquivo válido.")

    tamanho_final = saida.stat().st_size
    print(
        f"Vídeo compactado: {tamanho_final / 1_000_000:.2f} MB "
        f"({duracao:.2f}s; vídeo {bitrate_video / 1000:.0f} kbps)."
    )
    if tamanho_final > MAX_VIDEO_BYTES:
        temporario.cleanup()
        raise RuntimeError(
            "Vídeo continuou acima do limite após a compactação: "
            f"{tamanho_final / 1_000_000:.2f} MB."
        )

    return saida, temporario


def enviar(video: Path, legenda: str) -> None:
    if not video.exists() or video.stat().st_size == 0:
        raise RuntimeError(f"Vídeo ausente: {video}")

    video_envio, temporario = compactar_para_telegram(video)
    try:
        cfg = obter_telegram()
        with video_envio.open("rb") as fh:
            response = requests.post(
                f"https://api.telegram.org/bot{cfg['token']}/sendVideo",
                data={
                    "chat_id": cfg["chat_id"],
                    "caption": legenda[:1024],
                    "supports_streaming": "true",
                },
                files={"video": (video.name, fh, "video/mp4")},
                timeout=900,
            )
        if not response.ok:
            raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text}")
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram recusou o vídeo: {payload}")
        print(
            f"Vídeo enviado: {video_envio} | "
            f"mensagem={payload['result']['message_id']}"
        )
    finally:
        if temporario is not None:
            temporario.cleanup()


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
