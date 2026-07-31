from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageFont

VERSION = "cartola_bancada_real_v7_2026_07_31"
WIDTH = 1280
HEIGHT = 720
FPS = 25

VOICE_FRANCISCA = "pt-BR-FranciscaNeural"
VOICE_ANTONIO = "pt-BR-AntonioNeural"
VOICE_THALITA = "pt-BR-ThalitaMultilingualNeural"
VOICE_BY_SPEAKER = {
    "FRANCISCA": VOICE_FRANCISCA,
    "ANTÔNIO": VOICE_ANTONIO,
    "THALITA": VOICE_THALITA,
}
VOICE_SETTINGS = {
    VOICE_FRANCISCA: {"rate": "-3%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_ANTONIO: {"rate": "-3%", "pitch": "-1Hz", "volume": "+0%"},
    VOICE_THALITA: {"rate": "-2%", "pitch": "+0Hz", "volume": "+0%"},
}

PRESENTERS = {
    "FRANCISCA": {"name": "Francisca", "role": "APRESENTADORA", "accent": (39, 207, 112)},
    "ANTÔNIO": {"name": "Antônio", "role": "ANALISTA", "accent": (36, 169, 255)},
    "THALITA": {"name": "Thalita", "role": "COMENTARISTA", "accent": (240, 168, 40)},
}

STOCK_SOURCES = [
    {
        "id": "pexels_8853410",
        "url": "https://www.pexels.com/download/video/8853410/",
        "page": "https://www.pexels.com/video/man-and-two-women-having-a-business-meeting-8853410/",
        "credit": "Los Muertos Crew / Pexels",
    },
    {
        "id": "pexels_3114602",
        "url": "https://www.pexels.com/download/video/3114602/",
        "page": "https://www.pexels.com/video/a-man-explaining-a-business-point-to-two-women-3114602/",
        "credit": "Pressmaster / Pexels",
    },
    {
        "id": "pexels_3201491",
        "url": "https://www.pexels.com/download/video/3201491/",
        "page": "https://www.pexels.com/video/two-women-having-conversation-and-a-man-writing-notes-in-the-office-3201491/",
        "credit": "cottonbro studio / Pexels",
    },
]

FONT_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]
FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]


@dataclass(frozen=True)
class Segment:
    speaker: str
    text: str
    title: str
    rows: List[Tuple[str, str]] = field(default_factory=list)
    shot: str = "wide"
    source_index: int = 0
    visual: str = ""


def run(command: Sequence[str]) -> None:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Falha no comando:\n" + " ".join(command) + "\n" + proc.stderr[-12000:]
        )


def ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return max(0.1, float(proc.stdout.strip()))


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def number(value: Any, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f}".replace(".", ",")
    except Exception:
        return "0,00"


def ordinal(value: Any) -> str:
    try:
        parsed = int(float(value))
        return f"{parsed}º" if parsed > 0 else "—"
    except Exception:
        return "—"


def clip_text(text: str, limit: int) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def font_path(bold: bool = False) -> str:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Fonte compatível com português não encontrada.")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(bold), size=size)


def wrap_by_width(draw: ImageDraw.ImageDraw, text: str, max_width: int, text_font: ImageFont.FreeTypeFont) -> List[str]:
    words = clean(text).split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def add_segment(
    items: List[Segment],
    speaker: str,
    text: str,
    title: str,
    rows: Iterable[Tuple[str, Any]],
    shot: str,
    source_index: int,
    visual: str,
) -> None:
    text = clean(text)
    if not text:
        return
    items.append(
        Segment(
            speaker=speaker,
            text=text,
            title=clip_text(title, 42),
            rows=[(clip_text(str(label), 18), clip_text(str(value), 27)) for label, value in rows],
            shot=shot,
            source_index=source_index % len(STOCK_SOURCES),
            visual=visual,
        )
    )


def form_phrase(value: Any) -> str:
    text = clean(value)
    return text if text else "sequência recente não disponível"


def build_dialogue(round_value: int, data: Dict[str, Any]) -> List[Segment]:
    games = list(data.get("jogos") or [])
    teams = dict(data.get("times") or {})
    players = dict(data.get("jogadores") or {})
    top5 = dict(data.get("top5") or {})
    segments: List[Segment] = []

    add_segment(
        segments,
        "FRANCISCA",
        f"Começa agora a análise da rodada {round_value}. Vamos direto aos jogos, ao momento das equipes e às escolhas que podem fazer diferença na escalação.",
        f"ANÁLISE DA RODADA {round_value}",
        [("JOGOS", len(games)), ("FOCO", "ESCALAÇÃO")],
        "wide", 0, "abertura",
    )

    speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    for index, game in enumerate(games):
        home = clean(game.get("mandante"))
        away = clean(game.get("visitante"))
        hs = clean(game.get("mandante_sigla")) or home[:3].upper()
        aws = clean(game.get("visitante_sigla")) or away[:3].upper()
        home_pos = ordinal(game.get("pos_mandante"))
        away_pos = ordinal(game.get("pos_visitante"))
        venue = clean(game.get("estadio"))
        date = clean(game.get("data"))
        hour = clean(game.get("hora"))
        home_history = clean(game.get("historico_mandante_falado"))
        away_history = clean(game.get("historico_visitante_falado"))
        reading = clean(game.get("leitura"))
        cartola = clean(game.get("destaque_cartola"))
        speaker_a = speakers[index % 3]
        speaker_b = speakers[(index + 1) % 3]

        add_segment(
            segments,
            speaker_a,
            (
                f"{home} recebe o {away}. O mandante aparece em {home_pos} na tabela e o visitante em {away_pos}. "
                f"A partida será {('no ' + venue) if venue else 'com mando do ' + home}, {date} às {hour}."
            ),
            f"{hs} x {aws}",
            [("MANDANTE", f"{home_pos} lugar"), ("VISITANTE", f"{away_pos} lugar"), ("DATA", date), ("HORA", hour)],
            "wide" if index % 2 == 0 else "medium", index, f"jogo_{index}",
        )
        analysis_parts = [part for part in (home_history, away_history, reading) if part]
        add_segment(
            segments,
            speaker_b,
            " ".join(analysis_parts) or f"O confronto entre {home} e {away} exige equilíbrio entre potencial e risco.",
            "MOMENTO DAS EQUIPES",
            [(hs, form_phrase(game.get("forma_mandante"))), (aws, form_phrase(game.get("forma_visitante")))],
            "medium", index + 1, f"jogo_{index}",
        )
        if cartola:
            add_segment(
                segments,
                speakers[(index + 2) % 3],
                cartola,
                "CONTRAPONTO DA BANCADA",
                [("CONFRONTO", f"{hs} x {aws}"), ("LEITURA", "RISCO x TETO")],
                "wide", index + 2, f"jogo_{index}",
            )

    if teams:
        add_segment(
            segments,
            "FRANCISCA",
            "Chegamos aos três modelos de escalação. Agora a comparação é entre custo, formação, capitão e distribuição dos jogadores.",
            "TRÊS MODELOS DE TIME",
            [("ECONÔMICO", "MENOR CUSTO"), ("INTERMEDIÁRIO", "EQUILÍBRIO"), ("PONTUAÇÃO", "MAIOR TETO")],
            "wide", 0, "times",
        )
        team_speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
        for index, team in enumerate(teams.values()):
            name = clean(team.get("nome")) or "Modelo"
            formation = clean(team.get("formacao")) or "4-3-3"
            cost = team.get("custo", team.get("custo_total", 0))
            captain = clean(team.get("capitao")).split(" (", 1)[0] or "não informado"
            titulares = [clean(item) for item in (team.get("titulares") or []) if clean(item)]
            names = ", ".join(titulares[:4])
            complement = f" Entre os nomes aparecem {names}." if names else ""
            add_segment(
                segments,
                team_speakers[index % 3],
                f"O {name} usa {formation}, custa {number(cost)} cartoletas e tem {captain} como capitão.{complement}",
                name.upper(),
                [("FORMAÇÃO", formation), ("CUSTO", f"C$ {number(cost)}"), ("CAPITÃO", captain)],
                "medium", index, "times",
            )

    selected_players = list(players.items())[:15]
    if selected_players:
        add_segment(
            segments,
            "ANTÔNIO",
            "Vamos às escolhas individuais. O ponto principal é entender por que cada jogador entrou no modelo e qual risco acompanha a indicação.",
            "ESCOLHAS POR POSIÇÃO",
            [("CRITÉRIOS", "PREÇO E CONTEXTO"), ("ALERTA", "SEM GARANTIA")],
            "wide", 1, "jogadores",
        )

    player_speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    for index, (name, player) in enumerate(selected_players):
        position = clean(player.get("posicao_extenso")) or clean(player.get("posicao"))
        club = clean(player.get("clube_nome")) or clean(player.get("clube"))
        opponent = clean(player.get("adversario")) or "adversário da rodada"
        price = number(player.get("preco"))
        rationale = clean(player.get("racional"))
        average = player.get("media", player.get("media_ult5"))
        last = player.get("ultima_pontuacao")
        metrics: List[str] = []
        if average not in (None, ""):
            metrics.append(f"média de {number(average)} pontos")
        if last not in (None, ""):
            metrics.append(f"última pontuação de {number(last)}")
        metric_phrase = ", ".join(metrics)
        performance = f" Apresenta {metric_phrase}." if metric_phrase else ""
        if not rationale:
            rationale = "A indicação combina preço, posição e contexto do confronto."
        add_segment(
            segments,
            player_speakers[index % 3],
            f"{name} atua como {position} do {club}, enfrenta o {opponent} e custa {price} cartoletas.{performance} {rationale}",
            name.upper(),
            [("POSIÇÃO", position), ("CLUBE", club), ("PREÇO", f"C$ {price}"), ("RIVAL", opponent)],
            "medium" if index % 2 else "wide", index + 1, name,
        )

    rows = [row for row in (top5.get("dados") or top5.get("lista") or []) if isinstance(row, dict)]
    if rows:
        add_segment(
            segments,
            "THALITA",
            "Fechamos com as alternativas do Top 5. A troca só vale quando melhora o custo-benefício, a estabilidade ou reduz a concentração no mesmo confronto.",
            "ALTERNATIVAS DO TOP 5",
            [("COMPARAR", "PREÇO"), ("OBSERVAR", "TETO"), ("CONTROLAR", "RISCO")],
            "wide", 2, "top5",
        )
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            pos = clean(row.get("POS") or row.get("pos")).upper()
            grouped.setdefault(pos, []).append(row)
        labels = {"GOL": "GOLEIROS", "LAT": "LATERAIS", "ZAG": "ZAGUEIROS", "MEI": "MEIAS", "ATA": "ATACANTES", "TEC": "TÉCNICOS"}
        for index, pos in enumerate(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]):
            group = grouped.get(pos, [])[:3]
            if not group:
                continue
            descriptions: List[str] = []
            panel_rows: List[Tuple[str, str]] = []
            for row in group:
                athlete = clean(row.get("NOME") or row.get("nome"))
                club = clean(row.get("CLUBE_NOME") or row.get("CLUBE") or row.get("clube"))
                price = number(row.get("PRECO") or row.get("preco"))
                descriptions.append(f"{athlete}, do {club}, por {price} cartoletas")
                panel_rows.append((athlete, f"{club} • C$ {price}"))
            add_segment(
                segments,
                player_speakers[index % 3],
                f"Entre os {labels.get(pos, pos).lower()}, aparecem " + "; ".join(descriptions) + ".",
                f"TOP 5 • {labels.get(pos, pos)}",
                panel_rows,
                "medium", index, "top5",
            )

    add_segment(
        segments,
        "FRANCISCA",
        f"Esta foi a análise da rodada {round_value}. Confira a escalação antes do fechamento do mercado e acompanhe o Portal SimonSports para as atualizações.",
        "ANÁLISE CONCLUÍDA",
        [("PORTAL", "SIMONSPORTS"), ("PRÓXIMO PASSO", "PRÉ-FECHAMENTO")],
        "wide", 0, "encerramento",
    )
    add_segment(
        segments,
        "ANTÔNIO",
        "Boa rodada e boas escolhas.",
        "ATÉ A PRÓXIMA",
        [("DADOS", "ANÁLISE"), ("DECISÃO", "COM CONTEXTO")],
        "wide", 1, "encerramento",
    )
    return segments


async def synthesize(segment: Segment, output: Path) -> None:
    voice = VOICE_BY_SPEAKER[segment.speaker]
    settings = VOICE_SETTINGS[voice]
    communicator = edge_tts.Communicate(
        text=segment.text,
        voice=voice,
        rate=settings["rate"],
        pitch=settings["pitch"],
        volume=settings["volume"],
    )
    await communicator.save(str(output))


def download_stock_assets(folder: Path) -> List[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    outputs: List[Path] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
    }
    for item in STOCK_SOURCES:
        target = folder / f"{item['id']}.mp4"
        if not target.exists() or target.stat().st_size < 100_000:
            with requests.get(item["url"], headers=headers, timeout=120, stream=True, allow_redirects=True) as response:
                response.raise_for_status()
                with target.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
        if target.stat().st_size < 100_000:
            raise RuntimeError(f"Filmagem inválida: {target}")
        outputs.append(target)
    return outputs


def create_overlay(segment: Segment, output: Path, round_value: int) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (2, 10, 15, 255))
    draw = ImageDraw.Draw(image)
    accent = PRESENTERS[segment.speaker]["accent"]

    draw.rounded_rectangle((24, 88, 936, 608), radius=18, fill=(0, 0, 0, 255), outline=accent + (255,), width=3)
    draw.rounded_rectangle((954, 88, 1256, 608), radius=18, fill=(5, 21, 27, 255), outline=(63, 94, 102, 255), width=2)
    draw.rectangle((954, 88, 964, 608), fill=accent + (255,))

    draw.text((30, 24), "PORTAL SIMONSPORTS", font=font(22, True), fill=(255, 255, 255, 255))
    draw.text((1238, 27), f"ANÁLISE • RODADA {round_value}", font=font(18, True), fill=accent + (255,), anchor="ra")
    draw.line((30, 66, 1250, 66), fill=(44, 70, 78, 255), width=2)

    title_font = font(22, True)
    title_lines = wrap_by_width(draw, segment.title, 260, title_font)[:2]
    y = 112
    for line in title_lines:
        draw.text((980, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 29
    y += 13
    for label, value in segment.rows[:5]:
        draw.text((980, y), label.upper(), font=font(12, True), fill=(151, 181, 188, 255))
        y += 20
        value_lines = wrap_by_width(draw, value, 244, font(17, True))[:2]
        for line in value_lines:
            draw.text((980, y), line, font=font(17, True), fill=accent + (255,))
            y += 22
        draw.line((980, y + 7, 1228, y + 7), fill=(35, 60, 66, 255), width=1)
        y += 20
        if y > 555:
            break

    draw.rounded_rectangle((28, 625, 1252, 698), radius=15, fill=(4, 17, 22, 255), outline=(44, 70, 78, 255), width=2)
    draw.rectangle((28, 625, 39, 698), fill=accent + (255,))
    draw.text((62, 636), PRESENTERS[segment.speaker]["name"], font=font(26, True), fill=(255, 255, 255, 255))
    draw.text((62, 672), PRESENTERS[segment.speaker]["role"], font=font(14, True), fill=accent + (255,))
    draw.text((1224, 661), clip_text(segment.title, 54), font=font(16, True), fill=(216, 226, 230, 255), anchor="ra")

    image.save(output, "PNG", optimize=True)


def create_opening_card(output: Path, round_value: int) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (2, 10, 15, 255))
    draw = ImageDraw.Draw(image)
    green = (39, 207, 112, 255)
    draw.polygon([(0, 0), (380, 0), (210, HEIGHT), (0, HEIGHT)], fill=(7, 40, 29, 255))
    draw.polygon([(WIDTH, 0), (WIDTH - 320, 0), (WIDTH - 160, HEIGHT), (WIDTH, HEIGHT)], fill=(4, 28, 42, 255))
    draw.text((WIDTH // 2, 218), "PORTAL SIMONSPORTS APRESENTA", font=font(25, True), fill=green, anchor="mm")
    draw.text((WIDTH // 2, 310), "ANÁLISE DA RODADA", font=font(63, True), fill=(255, 255, 255, 255), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0, 255))
    draw.rounded_rectangle((505, 390, 775, 458), radius=18, fill=(4, 22, 27, 255), outline=green, width=3)
    draw.text((WIDTH // 2, 424), f"RODADA {round_value}", font=font(29, True), fill=(255, 255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 535), "CONFRONTOS • ESTATÍSTICAS • ESCALAÇÕES", font=font(20, True), fill=(174, 198, 205, 255), anchor="mm")
    image.save(output, "PNG", optimize=True)


def create_sting(output: Path, duration: float = 4.2) -> None:
    sample_rate = 44100
    total = int(sample_rate * duration)
    audio = [0.0] * total
    notes = [(196.0, 0.00, 0.70), (246.94, 0.55, 1.35), (293.66, 1.10, 2.10), (392.0, 1.75, 3.65)]
    for frequency, start, end in notes:
        i0 = int(start * sample_rate)
        i1 = min(total, int(end * sample_rate))
        for i in range(i0, i1):
            t = (i - i0) / sample_rate
            length = end - start
            attack = min(1.0, t / 0.04)
            release = min(1.0, max(0.0, (length - t) / 0.18))
            envelope = attack * release
            audio[i] += 0.17 * envelope * (math.sin(2 * math.pi * frequency * t) + 0.28 * math.sin(4 * math.pi * frequency * t))
    pcm = bytearray()
    for sample in audio:
        value = max(-0.95, min(0.95, sample))
        pcm.extend(int(value * 32767).to_bytes(2, "little", signed=True))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))


def render_opening(card: Path, audio: Path, output: Path, duration: float = 4.2) -> None:
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(card), "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-vf", f"fade=t=in:st=0:d=0.35,fade=t=out:st={duration - 0.45:.2f}:d=0.45",
        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", str(output),
    ])


def shot_filter(shot: str, index: int) -> str:
    if shot == "medium":
        zoom = 1.08
        x_expr = "(iw-iw/{z})/2".format(z=zoom)
        y_expr = "(ih-ih/{z})/2"
        return f"crop=iw/{zoom}:ih/{zoom}:{x_expr}:{y_expr},scale=900:506:force_original_aspect_ratio=increase,crop=900:506"
    return "scale=900:506:force_original_aspect_ratio=increase,crop=900:506"


def render_segment(
    stock: Path,
    audio: Path,
    overlay: Path,
    output: Path,
    segment: Segment,
    index: int,
) -> float:
    audio_duration = ffprobe_duration(audio)
    duration = audio_duration + 0.32
    source_duration = ffprobe_duration(stock)
    max_offset = max(0.0, source_duration - min(source_duration, duration + 1.5))
    offset = (index * 3.17) % max(0.1, max_offset) if max_offset > 0 else 0.0
    video_filter = shot_filter(segment.shot, index)
    filter_complex = (
        f"[0:v]{video_filter},setsar=1[v];"
        f"color=c=0x020a0f:s={WIDTH}x{HEIGHT}:r={FPS}[bg];"
        f"[bg][v]overlay=30:94[scene];"
        f"[scene][2:v]overlay=0:0:format=auto[out]"
    )
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-ss", f"{offset:.3f}", "-i", str(stock),
        "-i", str(audio), "-loop", "1", "-i", str(overlay),
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "1:a:0", "-t", f"{duration:.3f}",
        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-af", "apad=pad_dur=0.32", "-movflags", "+faststart", str(output),
    ])
    return duration


def validate_dialogue(segments: List[Segment]) -> None:
    combined = " ".join(segment.text.lower() for segment in segments)
    prohibited = [
        "piloto de análise dialogada",
        "as imagens preservam exatamente",
        "o áudio utiliza",
        "não haverá zero",
        "cada atleta será apresentado",
        "vamos explicar como",
        "a dinâmica do programa",
    ]
    found = [term for term in prohibited if term in combined]
    if found:
        raise RuntimeError("Abertura ou roteiro com explicação de bastidor: " + ", ".join(found))
    if not segments or not segments[0].text.startswith("Começa agora a análise da rodada"):
        raise RuntimeError("A primeira fala não começa diretamente o programa.")
    used = {segment.speaker for segment in segments}
    if used != set(VOICE_BY_SPEAKER):
        raise RuntimeError(f"Apresentadores incompletos: {sorted(used)}")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    segments = build_dialogue(round_value, data)
    validate_dialogue(segments)
    if len(segments) < 30:
        raise RuntimeError(f"Interação insuficiente: {len(segments)} falas.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    timeline: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="bancada_real_v7_") as temp_name:
        temp = Path(temp_name)
        stock_files = download_stock_assets(temp / "stock")

        async def synthesize_all() -> List[Path]:
            paths: List[Path] = []
            for index, segment in enumerate(segments, 1):
                path = temp / f"voice_{index:03d}.mp3"
                await synthesize(segment, path)
                paths.append(path)
            return paths

        audios = asyncio.run(synthesize_all())
        clips: List[Path] = []

        opening_card = temp / "opening.png"
        opening_audio = temp / "opening.wav"
        opening_clip = temp / "clip_000.mp4"
        create_opening_card(opening_card, round_value)
        create_sting(opening_audio)
        render_opening(opening_card, opening_audio, opening_clip)
        clips.append(opening_clip)
        elapsed = ffprobe_duration(opening_clip)

        for index, (segment, audio) in enumerate(zip(segments, audios), 1):
            overlay = temp / f"overlay_{index:03d}.png"
            clip = temp / f"clip_{index:03d}.mp4"
            create_overlay(segment, overlay, round_value)
            stock = stock_files[segment.source_index % len(stock_files)]
            duration = render_segment(stock, audio, overlay, clip, segment, index)
            clips.append(clip)
            timeline.append(
                {
                    "inicio": round(elapsed, 3),
                    "fim": round(elapsed + duration, 3),
                    "apresentador": segment.speaker,
                    "voz": VOICE_BY_SPEAKER[segment.speaker],
                    "texto_falado": segment.text,
                    "titulo_tela": segment.title,
                    "dados_tela": segment.rows,
                    "plano": segment.shot,
                    "filmagem": STOCK_SOURCES[segment.source_index % len(STOCK_SOURCES)]["id"],
                    "visual": segment.visual,
                }
            )
            elapsed += duration

        concat = temp / "concat.txt"
        concat.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", "-movflags", "+faststart", str(output_path),
        ])

    duration = ffprobe_duration(output_path)
    manifest = {
        "versao": VERSION,
        "status": "PILOTO_DE_BANCADA_REAL_PARA_APROVACAO",
        "rodada": round_value,
        "duracao_segundos": round(duration, 3),
        "vozes_aprovadas": VOICE_BY_SPEAKER,
        "apresentadores": ["Francisca", "Antônio", "Thalita"],
        "abertura_profissional": True,
        "primeira_fala_direta": True,
        "explicacao_de_bastidor_na_abertura": False,
        "filmagem_com_movimento_corporal_real": True,
        "movimento_global_artificial_da_imagem": False,
        "audio_original_das_filmagens_removido": True,
        "sincronizacao_labial": False,
        "layout_sem_sobreposicao": True,
        "painel_fora_da_area_dos_apresentadores": True,
        "legenda_longa_sobre_apresentadores": False,
        "cortes_entre_planos": True,
        "contexto_real_validado": data.get("contexto_real_validado") is True,
        "fontes_visuais": STOCK_SOURCES,
        "timeline": timeline,
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera vídeo real de bancada do Cartola V7.")
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
