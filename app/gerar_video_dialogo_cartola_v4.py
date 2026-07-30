from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFilter

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3


VERSION = "cartola_dialogo_tecnico_v4_2026_07_30"
WIDTH = base.WIDTH
HEIGHT = base.HEIGHT

# Guarda a função original ANTES de qualquer substituição temporária.
# Sem esta referência, build_dialogue_v4 chamaria a si própria depois do monkey patch.
V3_BUILD_DIALOGUE_ORIGINAL = v3.build_dialogue


def concise_onscreen(text: str, limit: int = 150) -> str:
    """Mantém a legenda visual curta e impede texto de roteiro no vídeo."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def create_frame_v4(
    visual_path: Path | None,
    collage_paths: List[Path],
    speaker: str,
    text: str,
    round_value: int,
    output: Path,
) -> None:
    """
    Layout V4:
    - visual reduzido e encerrado antes da área de fala;
    - faixa física de separação entre card e legenda;
    - texto de tela limitado a poucas linhas;
    - nenhuma fala integral/teleprompter é desenhada.
    """
    if visual_path is None:
        foreground = base.make_collage(collage_paths)
        foreground = base.fit_image(foreground, 620, 720)
    else:
        foreground = base.fit_image(Image.open(visual_path), 620, 720)

    background_source = foreground.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    background = background_source.filter(ImageFilter.GaussianBlur(25)).convert("RGBA")
    frame = Image.alpha_composite(
        background,
        Image.new("RGBA", (WIDTH, HEIGHT), (0, 8, 22, 190)),
    )
    draw = ImageDraw.Draw(frame)

    v3.rounded(draw, (20, 18, 700, 76), 24, (3, 20, 39, 238), base.LINE, 2)
    header = f"ANÁLISE DIALOGADA • RODADA {round_value}"
    hb = draw.textbbox((0, 0), header, font=base.font(25, True))
    draw.text(
        ((WIDTH - (hb[2] - hb[0])) / 2, 32),
        header,
        font=base.font(25, True),
        fill=base.WHITE,
    )

    x = (WIDTH - foreground.width) // 2
    frame.alpha_composite(foreground.convert("RGBA"), (x, 92))

    # Barreira visual: o card termina acima desta faixa e nunca invade a legenda.
    v3.rounded(draw, (28, 824, 692, 850), 12, (2, 12, 27, 255), base.LINE, 1)

    accent = base.SPEAKER_COLORS[speaker]
    panel = (22, 862, 698, 1238)
    v3.rounded(draw, panel, 30, (4, 18, 36, 252), accent, 3)
    v3.rounded(
        draw,
        (48, 884, 275, 942),
        20,
        (accent[0] // 5, accent[1] // 5, accent[2] // 5, 255),
        accent,
        2,
    )
    draw.text((70, 897), speaker, font=base.font(26, True), fill=accent)

    short_text = concise_onscreen(text)
    text_font, lines = base.wrap_text(draw, short_text, 610, 27, 20)
    while len(lines) > 6 and text_font.size > 18:
        text_font = base.font(text_font.size - 1, False)
        lines = v3.wrap(draw, short_text, 610, text_font)

    line_height = text_font.size + 9
    y = 967
    for line in lines[:6]:
        draw.text((52, y), line, font=text_font, fill=base.WHITE)
        y += line_height

    draw.text(
        (52, 1192),
        "RESUMO VISUAL • A FALA COMPLETA PERMANECE SOMENTE NO ÁUDIO",
        font=base.font(12, True),
        fill=base.SILVER,
    )

    footer = "@dicascartolaportalsimonsports  •  PORTAL SIMONSPORTS"
    fb = draw.textbbox((0, 0), footer, font=base.font(16, True))
    draw.text(
        ((WIDTH - (fb[2] - fb[0])) / 2, 1253),
        footer,
        font=base.font(16, True),
        fill=base.SILVER,
    )
    frame.convert("RGB").save(output, "PNG", optimize=True)


def build_dialogue_v4(round_value: int, data: dict) -> List[v3.Segment]:
    """Aproveita a análise V3 e torna as transições mais dialogadas."""
    # Usa obrigatoriamente a referência original preservada no carregamento do módulo.
    original = V3_BUILD_DIALOGUE_ORIGINAL(round_value, data)
    result: List[v3.Segment] = []

    for index, segment in enumerate(original):
        text = segment.text
        onscreen = concise_onscreen(segment.onscreen)

        if segment.visual.startswith("jogo_") and index > 0:
            previous = original[index - 1]
            if previous.visual == segment.visual and "Qual é a leitura" in previous.text:
                text = (
                    "Boa pergunta. "
                    + text
                    + " E você concorda que, neste confronto, o risco precisa pesar tanto quanto o potencial?"
                )

        if segment.visual in data.get("jogadores", {}) and not text.startswith("Sobre"):
            text = "Retomando o ponto anterior: " + text

        result.append(
            v3.Segment(
                speaker=segment.speaker,
                voice=segment.voice,
                text=v3.sanitize_tts(text),
                visual=segment.visual,
                onscreen=onscreen,
            )
        )

    return result


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    """Executa o motor V3 com os componentes visuais e dialogais da V4."""
    original_version = v3.VERSION
    original_frame = v3.create_frame_v3
    original_dialogue = v3.build_dialogue

    try:
        v3.VERSION = VERSION
        v3.create_frame_v3 = create_frame_v4
        v3.build_dialogue = build_dialogue_v4
        return v3.generate(round_value, repo_root, output_path)
    finally:
        # Restaura o módulo para evitar efeitos colaterais em testes ou outras execuções.
        v3.VERSION = original_version
        v3.create_frame_v3 = original_frame
        v3.build_dialogue = original_dialogue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera o vídeo técnico dialogado V4 do Cartola sem sobreposição."
    )
    parser.add_argument("--rodada", type=int, default=21)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--output",
        default="output/piloto_analise_tecnica_dialogada_rodada_21_v4.mp4",
    )
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
