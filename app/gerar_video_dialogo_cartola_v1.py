from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import subprocess
import tempfile
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import edge_tts
from PIL import Image, ImageDraw, ImageFilter, ImageFont


VOICE_FRANCISCA = "pt-BR-FranciscaNeural"
VOICE_THALITA = "pt-BR-ThalitaMultilingualNeural"
VOICE_ANTONIO = "pt-BR-AntonioNeural"

VOICE_SETTINGS = {
    VOICE_FRANCISCA: {"rate": "-4%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_THALITA: {"rate": "-3%", "pitch": "+0Hz", "volume": "+0%"},
    VOICE_ANTONIO: {"rate": "-4%", "pitch": "-1Hz", "volume": "+0%"},
}

SPEAKER_COLORS = {
    "FRANCISCA": (32, 196, 255),
    "ANTÔNIO": (255, 190, 55),
    "THALITA": (181, 86, 255),
}

WIDTH = 720
HEIGHT = 1280
FPS = 24
BG = (2, 12, 27)
WHITE = (242, 247, 252)
SILVER = (177, 195, 211)
PANEL = (5, 20, 39)
LINE = (31, 128, 194)


@dataclass(frozen=True)
class DialogueSegment:
    speaker: str
    voice: str
    text: str
    visual: str


def run(command: Sequence[str]) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RuntimeError(
            "Falha ao gerar o vídeo piloto:\n"
            + " ".join(command)
            + "\n"
            + process.stderr[-7000:]
        )


def ffprobe_duration(path: Path) -> float:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return max(0.1, float(process.stdout.strip()))


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def slug(value: Any) -> str:
    text = safe(value).lower()
    table = str.maketrans("áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    text = text.translate(table)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def titulares(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    players = data.get("atletas") or data.get("jogadores") or []
    return [
        item
        for item in players
        if isinstance(item, dict) and safe(item.get("status")).upper() != "RESERVA"
    ][:12]


def names(data: Dict[str, Any]) -> List[str]:
    return [safe(item.get("nome")) for item in titulares(data) if safe(item.get("nome"))]


def money(value: Any) -> str:
    try:
        return f"C$ {float(value):.2f}".replace(".", ",")
    except Exception:
        return "C$ 0,00"


def natural_list(items: Iterable[str], limit: int = 5) -> str:
    values = [safe(item) for item in items if safe(item)][:limit]
    if not values:
        return "nenhum nome disponível"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " e " + values[-1]


def top5_by_position(top5: Dict[str, Any], position: str) -> List[str]:
    return [
        safe(item.get("nome"))
        for item in top5.get("lista", [])
        if isinstance(item, dict) and safe(item.get("pos")).upper() == position
    ][:5]


def build_dialogue(
    round_value: int,
    economic: Dict[str, Any],
    intermediate: Dict[str, Any],
    scoring: Dict[str, Any],
    top5: Dict[str, Any],
) -> List[DialogueSegment]:
    economic_players = titulares(economic)
    inter_players = titulares(intermediate)
    scoring_players = titulares(scoring)

    economic_clubs = Counter(safe(item.get("clube")).upper() for item in economic_players)
    dominant_club, dominant_count = economic_clubs.most_common(1)[0] if economic_clubs else ("", 0)
    common = sorted(set(names(economic)) & set(names(intermediate)) & set(names(scoring)))

    attackers = top5_by_position(top5, "ATA")
    midfielders = top5_by_position(top5, "MEI")
    goalkeepers = top5_by_position(top5, "GOL")

    economic_caption = (
        f"O Econômico usa {safe(economic.get('formacao'), '4-3-3')}, custa {money(economic.get('custo_total'))} "
        f"e tem {safe(economic.get('capitao'), 'capitão não informado')} como capitão."
    )
    concentration = (
        f"São {dominant_count} titulares do {dominant_club}. Isso aumenta a correlação: "
        "se o clube for bem, o time ganha força; se não for, o impacto também fica concentrado."
        if dominant_count >= 3
        else "A distribuição por clubes está relativamente equilibrada, reduzindo a dependência de um único confronto."
    )
    inter_caption = (
        f"O Intermediário sobe para {money(intermediate.get('custo_total'))} e mantém "
        f"{safe(intermediate.get('capitao'), 'o capitão')} com uma base mais valorizada."
    )
    scoring_caption = (
        f"O Time para Pontuar chega a {money(scoring.get('custo_total'))}. A formação é "
        f"{safe(scoring.get('formacao'), '4-3-3')} e a escolha final de treinador é {safe(titulares(scoring)[-1].get('nome') if titulares(scoring) else '', 'não informada')}."
    )

    return [
        DialogueSegment(
            "FRANCISCA",
            VOICE_FRANCISCA,
            f"Olá! Está começando o piloto de análise dialogada do Portal SimonSports para a rodada {round_value} do Cartola. Antônio e Thalita, vamos comparar os três modelos e o Top 5 confirmado?",
            "intro",
        ),
        DialogueSegment(
            "ANTÔNIO",
            VOICE_ANTONIO,
            f"Vamos sim, Francisca. Começando pelo Time Econômico. {economic_caption} A proposta é controlar o patrimônio sem abrir mão de nomes com presença nos principais setores.",
            "economico",
        ),
        DialogueSegment(
            "THALITA",
            VOICE_THALITA,
            f"Antônio, há uma característica que chama atenção nessa escalação: {concentration} Essa leitura é importante para quem acompanha o risco do modelo.",
            "economico",
        ),
        DialogueSegment(
            "FRANCISCA",
            VOICE_FRANCISCA,
            "Então o Econômico não significa apenas gastar menos. Ele também assume uma estratégia mais concentrada. E o modelo Intermediário, Thalita, como se diferencia?",
            "intermediario",
        ),
        DialogueSegment(
            "THALITA",
            VOICE_THALITA,
            f"{inter_caption} No meio, aparecem Arias, Matheus Pereira e Josué. No ataque, Viveros divide espaço com Pedro e Samuel Lino. É um desenho mais equilibrado entre custo e nomes de maior investimento.",
            "intermediario",
        ),
        DialogueSegment(
            "ANTÔNIO",
            VOICE_ANTONIO,
            "E vale observar que Viveros foi mantido como capitão. Isso cria uma linha comum entre os modelos, mas o restante da composição muda o nível de exposição e o patrimônio utilizado.",
            "intermediario",
        ),
        DialogueSegment(
            "FRANCISCA",
            VOICE_FRANCISCA,
            "Chegamos agora ao Time para Pontuar. Antônio, ele é apenas uma cópia do Intermediário ou existe uma diferença real na proposta?",
            "pontuacao",
        ),
        DialogueSegment(
            "ANTÔNIO",
            VOICE_ANTONIO,
            f"A base de jogadores é muito próxima, Francisca, mas o fechamento usa o maior patrimônio dos três. {scoring_caption} É a versão que aceita investir mais para manter os nomes considerados prioritários.",
            "pontuacao",
        ),
        DialogueSegment(
            "THALITA",
            VOICE_THALITA,
            f"E há quatro nomes presentes nos três times: {natural_list(common, 6)}. Esse núcleo mostra quais escolhas tiveram maior consenso na análise automática do SimonSports.",
            "comparativo",
        ),
        DialogueSegment(
            "FRANCISCA",
            VOICE_FRANCISCA,
            "Muito bem. Agora vamos ao Top 5 da rodada, que amplia as opções por posição e ajuda a enxergar alternativas além das três escalações.",
            "top5",
        ),
        DialogueSegment(
            "ANTÔNIO",
            VOICE_ANTONIO,
            f"Entre os atacantes, o painel destaca {natural_list(attackers)}. No meio-campo, aparecem {natural_list(midfielders)}. São opções com preços diferentes para adaptar a montagem ao patrimônio disponível.",
            "top5",
        ),
        DialogueSegment(
            "THALITA",
            VOICE_THALITA,
            f"E no gol, o Top 5 oferece {natural_list(goalkeepers)}. O ponto principal é comparar preço, clube e encaixe no restante do time, sem tratar qualquer nome como garantia de pontuação.",
            "top5",
        ),
        DialogueSegment(
            "FRANCISCA",
            VOICE_FRANCISCA,
            f"Este foi o vídeo piloto da rodada {round_value}, com análise informativa dos três times e do Top 5. Portal SimonSports, simplesmente o melhor. Até a próxima rodada!",
            "final",
        ),
    ]


def font_path(bold: bool = False) -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Fonte compatível com português não encontrada.")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(bold), size=size)


def fit_image(source: Image.Image, width: int, height: int) -> Image.Image:
    image = source.convert("RGB")
    ratio = min(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), BG)
    x = (width - resized.width) // 2
    y = (height - resized.height) // 2
    canvas.paste(resized, (x, y))
    return canvas


def rounded(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int = 31, min_size: int = 22) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    for size in range(max_size, min_size - 1, -1):
        candidate = font(size, False)
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            proposal = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), proposal, font=candidate)
            if bbox[2] - bbox[0] <= max_width:
                current = proposal
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= 6:
            return candidate, lines
    candidate = font(min_size, False)
    return candidate, textwrap.wrap(text, width=48)[:7]


def make_collage(paths: List[Path]) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, 875), BG)
    positions = [(24, 20), (366, 20), (24, 445), (366, 445)]
    for path, (x, y) in zip(paths, positions):
        image = Image.open(path).convert("RGB")
        thumb = fit_image(image, 330, 405)
        canvas.paste(thumb, (x, y))
    return canvas


def create_frame(
    visual_path: Path | None,
    collage_paths: List[Path],
    speaker: str,
    text: str,
    round_value: int,
    output: Path,
) -> None:
    if visual_path is None:
        foreground = make_collage(collage_paths)
    else:
        foreground = fit_image(Image.open(visual_path), 660, 825)

    if visual_path is None:
        background_source = foreground.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    else:
        background_source = Image.open(visual_path).convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    background = background_source.filter(ImageFilter.GaussianBlur(25)).convert("RGBA")
    dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 8, 22, 178))
    frame = Image.alpha_composite(background, dark)
    draw = ImageDraw.Draw(frame)

    rounded(draw, (20, 18, 700, 78), 25, (3, 20, 39, 235), LINE, 2)
    header = f"ANÁLISE DIALOGADA • RODADA {round_value}"
    hb = draw.textbbox((0, 0), header, font=font(26, True))
    draw.text(((WIDTH - (hb[2] - hb[0])) / 2, 34), header, font=font(26, True), fill=WHITE)

    if visual_path is None:
        frame.alpha_composite(foreground.convert("RGBA"), (0, 85))
    else:
        x = (WIDTH - foreground.width) // 2
        frame.alpha_composite(foreground.convert("RGBA"), (x, 88))

    accent = SPEAKER_COLORS[speaker]
    panel = (22, 925, 698, 1250)
    rounded(draw, panel, 30, (4, 18, 36, 245), accent, 3)
    rounded(draw, (48, 945, 275, 1005), 20, (accent[0] // 5, accent[1] // 5, accent[2] // 5, 255), accent, 2)
    draw.text((70, 959), speaker, font=font(27, True), fill=accent)

    text_font, lines = wrap_text(draw, text, 610, 30, 21)
    line_height = text_font.size + 10
    y = 1030
    for line in lines:
        draw.text((54, y), line, font=text_font, fill=WHITE)
        y += line_height

    footer = "@dicascartolaportalsimonsports  •  PORTAL SIMONSPORTS"
    fb = draw.textbbox((0, 0), footer, font=font(17, True))
    draw.text(((WIDTH - (fb[2] - fb[0])) / 2, 1258), footer, font=font(17, True), fill=SILVER)
    frame.convert("RGB").save(output, "PNG", optimize=True)


async def synthesize(segment: DialogueSegment, output: Path) -> None:
    settings = VOICE_SETTINGS[segment.voice]
    communicator = edge_tts.Communicate(
        text=segment.text,
        voice=segment.voice,
        rate=settings["rate"],
        pitch=settings["pitch"],
        volume=settings["volume"],
    )
    await communicator.save(str(output))


async def synthesize_all(segments: List[DialogueSegment], directory: Path) -> List[Path]:
    files: List[Path] = []
    for index, segment in enumerate(segments):
        path = directory / f"fala_{index:02d}.mp3"
        await synthesize(segment, path)
        files.append(path)
    return files


def segment_video(frame: Path, audio: Path, output: Path, duration: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(frame),
            "-i",
            str(audio),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},format=yuv420p,fade=t=in:st=0:d=0.18,fade=t=out:st={max(0.2, duration - 0.20):.3f}:d=0.18",
            "-af",
            "apad=pad_dur=0.38,alimiter=limit=0.96,loudnorm=I=-15.5:TP=-1.2:LRA=9",
            "-t",
            f"{duration + 0.38:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def visual_for(segment: DialogueSegment, images: Dict[str, Path]) -> Path | None:
    return {
        "economico": images["economico"],
        "intermediario": images["intermediario"],
        "pontuacao": images["pontuacao"],
        "top5": images["top5"],
        "comparativo": None,
        "intro": None,
        "final": None,
    }.get(segment.visual)


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_dir = repo_root / "data" / "publicacoes_atuais"
    output_dir = repo_root / "output"
    economic = load_json(data_dir / f"time_economico_rodada_{round_value}.json")
    intermediate = load_json(data_dir / f"time_intermediario_rodada_{round_value}.json")
    scoring = load_json(data_dir / f"time_pontuacao_rodada_{round_value}.json")
    top5 = load_json(data_dir / f"top5_rodada_{round_value}.json")

    images = {
        "economico": output_dir / f"time_economico_rodada_{round_value}.png",
        "intermediario": output_dir / f"time_intermediario_rodada_{round_value}.png",
        "pontuacao": output_dir / f"time_pontuacao_rodada_{round_value}.png",
        "top5": output_dir / f"top5_rodada_{round_value}.png",
    }
    missing = [str(path) for path in images.values() if not path.exists()]
    if missing:
        raise RuntimeError(f"Imagens da rodada ausentes: {missing}")

    segments = build_dialogue(round_value, economic, intermediate, scoring, top5)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cartola-dialogo-piloto-") as temp_name:
        temp = Path(temp_name)
        try:
            audio_files = asyncio.run(synthesize_all(segments, temp))
        except Exception as exc:
            raise RuntimeError(
                "Não foi possível gerar Francisca, Thalita e Antônio. "
                "O piloto foi interrompido para não utilizar voz genérica de contingência."
            ) from exc

        collage_paths = list(images.values())
        clips: List[Path] = []
        timeline: List[Dict[str, Any]] = []
        elapsed = 0.0
        for index, (segment, audio) in enumerate(zip(segments, audio_files)):
            duration = ffprobe_duration(audio)
            frame = temp / f"frame_{index:02d}.png"
            clip = temp / f"clip_{index:02d}.mp4"
            create_frame(
                visual_for(segment, images),
                collage_paths,
                segment.speaker,
                segment.text,
                round_value,
                frame,
            )
            segment_video(frame, audio, clip, duration)
            clip_duration = duration + 0.38
            timeline.append(
                {
                    "indice": index + 1,
                    "inicio": round(elapsed, 3),
                    "fim": round(elapsed + clip_duration, 3),
                    "apresentador": segment.speaker,
                    "voz": segment.voice,
                    "texto": segment.text,
                    "visual": segment.visual,
                }
            )
            elapsed += clip_duration
            clips.append(clip)

        concat_file = temp / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{clip.as_posix()}'" for clip in clips),
            encoding="utf-8",
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

    manifest = output_path.with_suffix(".json")
    manifest.write_text(
        json.dumps(
            {
                "versao": "cartola_dialogo_v1_2026_07_30",
                "rodada": round_value,
                "duracao_segundos": round(ffprobe_duration(output_path), 3),
                "resolucao": f"{WIDTH}x{HEIGHT}",
                "vozes": [VOICE_FRANCISCA, VOICE_ANTONIO, VOICE_THALITA],
                "publicacao_automatica": False,
                "status": "PILOTO_PARA_APROVACAO",
                "segmentos": timeline,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, default=21)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/piloto_analise_dialogada_rodada_21.mp4")
    args = parser.parse_args()

    result = generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output).resolve())
    print(f"Vídeo piloto concluído: {result} | duração={ffprobe_duration(result):.2f}s")


if __name__ == "__main__":
    main()
