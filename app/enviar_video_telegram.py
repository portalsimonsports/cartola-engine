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
CONTA_TELEGRAM = os.getenv(
    "CONTA_TELEGRAM",
    "DICAS CARTOLA PORTAL SIMONSPORTS",
).strip()
CHAT_FALLBACK = os.getenv(
    "TELEGRAM_CHAT_FALLBACK",
    "@dicascartolaportalsimonsports",
).strip()

# Margem operacional abaixo do limite que vinha retornando HTTP 413.
MAX_VIDEO_BYTES = int(os.getenv("TELEGRAM_MAX_VIDEO_BYTES", "45000000"))
LIMITE_REENVIO_413 = int(
    os.getenv("TELEGRAM_RETRY_MAX_VIDEO_BYTES", "32000000")
)
AUDIO_BITRATE = 48_000
MAX_TENTATIVAS_COMPACTACAO = 4


def credencial_google() -> str:
    path = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "service_account.json",
    ).strip()
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if raw:
        Path(path).write_text(
            json.dumps(json.loads(raw), ensure_ascii=False),
            encoding="utf-8",
        )

    if not Path(path).exists():
        raise RuntimeError("Credencial Google ausente.")

    return path


def obter_telegram() -> Dict[str, str]:
    credentials = Credentials.from_service_account_file(
        credencial_google(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )
    values = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=PLANILHA_ID,
            range=f"'{ABA_TELEGRAM}'!A:D",
        )
        .execute()
        .get("values", [])
    )

    if not values:
        raise RuntimeError("Aba de credenciais do Telegram vazia.")

    headers = [str(value).strip().upper() for value in values[0]]
    idx = {
        name: headers.index(name)
        for name in ("REDE", "CONTA", "CHAVE", "VALOR")
    }

    found: Dict[str, str] = {}
    for row in values[1:]:

        def get(name: str) -> str:
            index = idx[name]
            return str(row[index]).strip() if index < len(row) else ""

        if get("REDE").upper() != "TELEGRAM":
            continue
        if (
            CONTA_TELEGRAM
            and get("CONTA").upper() != CONTA_TELEGRAM.upper()
        ):
            continue

        found[get("CHAVE").upper()] = get("VALOR")

    token = found.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = found.get("TELEGRAM_CHAT_ID", "") or CHAT_FALLBACK

    if not token or not chat_id:
        raise RuntimeError(
            "Token ou chat_id do Telegram não encontrado."
        )

    return {
        "token": token,
        "chat_id": chat_id,
    }


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
        raise RuntimeError(
            f"Não foi possível obter a duração de {video}."
        ) from exc

    if duracao <= 0:
        raise RuntimeError(
            f"Duração inválida para {video}: {duracao}"
        )

    return duracao


def remover_passlog(prefixo: Path) -> None:
    for path in prefixo.parent.glob(prefixo.name + "*"):
        if path.is_file():
            path.unlink(missing_ok=True)


def compactar_tentativa(
    video: Path,
    saida: Path,
    duracao: float,
    bitrate_video: int,
    largura: int,
    passlog: Path,
) -> int:
    saida.unlink(missing_ok=True)
    remover_passlog(passlog)

    filtro = (
        f"scale={largura}:-2:"
        "force_original_aspect_ratio=decrease,"
        "fps=24"
    )
    comum = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-sn",
        "-dn",
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
        str(int(bitrate_video * 1.05)),
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
            "0:a:0?",
            "-c:a",
            "aac",
            "-b:a",
            "48k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(saida),
        ]
    )

    if not saida.exists() or saida.stat().st_size == 0:
        raise RuntimeError(
            "A compactação do vídeo não gerou um arquivo válido."
        )

    tamanho = saida.stat().st_size
    print(
        "Tentativa de compactação concluída: "
        f"{tamanho / 1_000_000:.2f} MB; "
        f"{duracao:.2f}s; "
        f"{bitrate_video / 1000:.0f} kbps; "
        f"largura {largura}px."
    )
    return tamanho


def compactar_para_telegram(
    video: Path,
    limite_bytes: int = MAX_VIDEO_BYTES,
) -> Tuple[Path, Optional[tempfile.TemporaryDirectory]]:
    tamanho_original = video.stat().st_size
    print(
        f"Vídeo original: {tamanho_original / 1_000_000:.2f} MB; "
        f"limite operacional: {limite_bytes / 1_000_000:.2f} MB."
    )

    if tamanho_original <= limite_bytes:
        return video, None

    duracao = duracao_video(video)
    temporario = tempfile.TemporaryDirectory(
        prefix="cartola-video-telegram-"
    )
    pasta = Path(temporario.name)
    saida = pasta / f"{video.stem}_telegram.mp4"

    # Alvo inicial abaixo do limite para absorver contêiner e variações
    # do codificador. Nas tentativas seguintes o bitrate é recalculado
    # a partir do tamanho realmente produzido.
    alvo_inicial = int(limite_bytes * 0.78)
    bits_por_segundo = int(alvo_inicial * 8 / duracao)
    bitrate_video = max(
        90_000,
        int((bits_por_segundo - AUDIO_BITRATE) * 0.94),
    )

    larguras = (720, 640, 540, 480)
    tamanho_final = 0

    try:
        for tentativa in range(1, MAX_TENTATIVAS_COMPACTACAO + 1):
            largura = larguras[min(tentativa - 1, len(larguras) - 1)]
            passlog = pasta / f"ffmpeg-pass-{tentativa}"

            tamanho_final = compactar_tentativa(
                video=video,
                saida=saida,
                duracao=duracao,
                bitrate_video=bitrate_video,
                largura=largura,
                passlog=passlog,
            )

            if tamanho_final <= limite_bytes:
                print(
                    "Vídeo pronto para o Telegram: "
                    f"{tamanho_final / 1_000_000:.2f} MB "
                    f"na tentativa {tentativa}."
                )
                return saida, temporario

            # Ajuste proporcional com margem adicional. Isso corrige
            # automaticamente casos em que a primeira codificação fica
            # acima do tamanho previsto, como os 54 MB do último erro.
            proporcao = (limite_bytes * 0.82) / tamanho_final
            bitrate_video = max(
                70_000,
                int(bitrate_video * proporcao * 0.92),
            )
            print(
                f"Arquivo ainda acima do limite; nova tentativa com "
                f"{bitrate_video / 1000:.0f} kbps."
            )

        raise RuntimeError(
            "Vídeo continuou acima do limite após "
            f"{MAX_TENTATIVAS_COMPACTACAO} tentativas: "
            f"{tamanho_final / 1_000_000:.2f} MB."
        )
    except Exception:
        temporario.cleanup()
        raise


def postar_video(
    cfg: Dict[str, str],
    video_envio: Path,
    nome_original: str,
    legenda: str,
) -> requests.Response:
    with video_envio.open("rb") as fh:
        return requests.post(
            f"https://api.telegram.org/bot{cfg['token']}/sendVideo",
            data={
                "chat_id": cfg["chat_id"],
                "caption": legenda[:1024],
                "supports_streaming": "true",
            },
            files={
                "video": (
                    nome_original,
                    fh,
                    "video/mp4",
                )
            },
            timeout=900,
        )


def validar_resposta_telegram(
    response: requests.Response,
    video: Path,
) -> None:
    if not response.ok:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}: {response.text}"
        )

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram recusou o vídeo: {payload}"
        )

    print(
        f"Vídeo enviado: {video} | "
        f"mensagem={payload['result']['message_id']}"
    )


def enviar(video: Path, legenda: str) -> None:
    if not video.exists() or video.stat().st_size == 0:
        raise RuntimeError(f"Vídeo ausente: {video}")

    cfg = obter_telegram()
    video_envio: Path
    temporario: Optional[tempfile.TemporaryDirectory]
    video_envio, temporario = compactar_para_telegram(
        video,
        MAX_VIDEO_BYTES,
    )

    try:
        response = postar_video(
            cfg=cfg,
            video_envio=video_envio,
            nome_original=video.name,
            legenda=legenda,
        )

        # Proteção adicional: se o endpoint ainda responder 413,
        # refaz a compactação para um teto menor e tenta uma vez.
        if response.status_code == 413:
            print(
                "Telegram retornou HTTP 413 mesmo após a preparação. "
                "Gerando versão de segurança abaixo de "
                f"{LIMITE_REENVIO_413 / 1_000_000:.0f} MB."
            )
            if temporario is not None:
                temporario.cleanup()
                temporario = None

            video_envio, temporario = compactar_para_telegram(
                video,
                LIMITE_REENVIO_413,
            )
            response = postar_video(
                cfg=cfg,
                video_envio=video_envio,
                nome_original=video.name,
                legenda=legenda,
            )

        validar_resposta_telegram(response, video_envio)
    finally:
        if temporario is not None:
            temporario.cleanup()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--rodada", required=True, type=int)
    parser.add_argument(
        "--fase",
        required=True,
        choices=["INICIAL", "PRE_FECHAMENTO"],
    )
    args = parser.parse_args()

    titulo = (
        "Análise inicial"
        if args.fase == "INICIAL"
        else "Análise de pré-fechamento"
    )
    legenda = (
        f"🎙 {titulo} • Rodada {args.rodada}\n\n"
        "Portal SimonSports\n"
        "🔗 @dicascartolaportalsimonsports"
    )
    enviar(Path(args.video), legenda)


if __name__ == "__main__":
    main()
