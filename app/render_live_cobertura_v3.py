from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List

from PIL import ImageDraw

import render_live_cards_v2 as v2
import render_live_cards_v4 as v4
import render_live_cobertura_v2 as base
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "live_cobertura_v3_tres_jogos_2026_07_30"
is_coverage_event = base.is_coverage_event
render_match_cards = base.render_match_cards


def _render_board(data: Dict[str, Any], output_dir: str, opening: bool) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Cobertura sem jogos estruturados.")

    round_value = v2._round_value(data)
    pages = math.ceil(len(matches) / 3)
    files: List[str] = []
    title = (
        f"ABERTURA DO LIVE • RODADA {round_value}"
        if opening
        else f"RESULTADOS DA NOITE • RODADA {round_value}"
    )
    subtitle = (
        "A cobertura começou. Confira os jogos da noite."
        if opening
        else "Todos os resultados, marcadores e gols contra da noite."
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for page in range(pages):
        image = v2._gradient_background(*v4.RESULT_SIZE_V4)
        v4._draw_header_v4(image, title, subtitle, v2._badge(data))
        chunk = matches[page * 3:(page + 1) * 3]
        y = 325
        for index, match in enumerate(chunk, start=page * 3 + 1):
            base._draw_schedule_row(
                image,
                (48, y, 1552, y + 340),
                match,
                index,
                results=not opening,
            )
            y += 365

        draw = ImageDraw.Draw(image)
        ribbon = (120, 1425, 1480, 1478)
        v2._round(draw, ribbon, 20, fill=(4, 27, 51), outline=v2.BLUE, width=2)
        if opening:
            text = "BOLA ROLANDO: ACOMPANHE CADA LANCE COM O PORTAL SIMONSPORTS"
            v2._centered_text(
                draw,
                ribbon,
                text,
                v2._fit_text(draw, text, 1280, 25, 17, "bold", True),
                fill=v2.WHITE,
            )
        else:
            base._draw_ball(draw, (445, 1451), 25, False)
            draw.text(
                (470, 1435),
                "GOL A FAVOR",
                font=v2._font(22, "bold", True),
                fill=v2.SILVER,
            )
            base._draw_ball(draw, (850, 1451), 25, True)
            draw.text(
                (875, 1435),
                "GOL CONTRA (GC)",
                font=v2._font(22, "bold", True),
                fill=v2.SILVER,
            )

        v4._draw_footer_v4(image, (page + 1, pages) if pages > 1 else None)
        prefix = "live_abertura" if opening else "live_resultados_noite"
        path = str(Path(output_dir) / f"{prefix}_rodada_{round_value}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    caption = "Abertura do Live" if opening else "Resultados da Noite"
    return RenderOutput(
        files,
        "live_opening_v3" if opening else "night_results_v3",
        title,
        f"{caption} • Rodada {round_value}",
    )


def render_coverage_event(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    event = base.event_name(data)
    if event == "LIVE_ABERTURA":
        return _render_board(data, output_dir, opening=True)
    if event == "LIVE_RESULTADOS_NOITE":
        return _render_board(data, output_dir, opening=False)
    raise RuntimeError(f"Evento de cobertura não suportado: {event!r}")
