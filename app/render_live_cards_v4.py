from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
import render_live_cards_v3 as v3
from render_telegram_cards import RenderOutput, _logo_ps


VISUAL_VERSION = "live_cards_v4_premium_square_2026_07_26"
RESULT_SIZE_V4 = (1600, 1600)


def _draw_header_v4(image: Image.Image, title: str, subtitle: str, badge: str) -> None:
    draw = ImageDraw.Draw(image)
    width, _ = image.size

    _logo_ps(image, (55, 28, 205, 165))
    draw.text((235, 34), "PORTAL", font=v2._font(34, "bold", True), fill=v2.WHITE)
    draw.text((235, 73), "SIMON", font=v2._font(55, "bold", True), fill=v2.WHITE)
    draw.text((425, 73), "SPORTS", font=v2._font(55, "bold", True), fill=v2.BLUE)
    draw.text((236, 136), "CARTOLA • DADOS • ANÁLISE", font=v2._font(21, "semibold"), fill=v2.SILVER)

    badge_box = (1240, 42, 1535, 137)
    v2._glow_outline(image, badge_box, v2.CYAN, radius=30, blur=14, alpha=78)
    v2._round(draw, badge_box, 30, fill=(4, 17, 35), outline=(71, 187, 244), width=3)
    v2._centered_text(draw, badge_box, badge, v2._font(40, "bold", True), fill=v2.WHITE, y_offset=-3)

    title_font = v2._fit_text(draw, title, 1500, 76, 52, "bold", True)
    if "•" in title:
        prefix, suffix = [part.strip() for part in title.split("•", 1)]
        left_text = prefix + " • "
        left_box = draw.textbbox((0, 0), left_text, font=title_font)
        right_box = draw.textbbox((0, 0), suffix, font=title_font)
        total_width = (left_box[2] - left_box[0]) + (right_box[2] - right_box[0])
        x0 = (width - total_width) / 2
        draw.text((x0, 180), left_text, font=title_font, fill=v2.WHITE)
        draw.text((x0 + (left_box[2] - left_box[0]), 180), suffix, font=title_font, fill=v2.BLUE)
    else:
        box = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((width - (box[2] - box[0])) / 2, 180), title, font=title_font, fill=v2.WHITE)

    subtitle_font = v2._fit_text(draw, subtitle, 1450, 30, 22, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    draw.text(((width - (sb[2] - sb[0])) / 2, 262), subtitle, font=subtitle_font, fill=v2.MUTED)


def _draw_info_bar(image: Image.Image, match: Dict[str, Any]) -> None:
    draw = ImageDraw.Draw(image)
    status, accent = v2._status_label(match)
    info_box = (55, 315, 1545, 410)
    v2._glow_outline(image, info_box, v2.CYAN, radius=25, blur=12, alpha=38, width=5)
    v2._round(draw, info_box, 25, fill=(4, 16, 32), outline=(48, 135, 197), width=2)

    date_line = v2._date_line(match)
    if date_line:
        font = v2._fit_text(draw, date_line, 1080, 39, 26, "bold", True)
        draw.text((105, 340), date_line, font=font, fill=v2.WHITE)

    status_box = (1230, 329, 1510, 396)
    v2._round(draw, status_box, 22, fill=accent)
    v2._centered_text(
        draw,
        status_box,
        status,
        v2._fit_text(draw, status, 245, 30, 21, "bold", True),
        fill=(5, 17, 30),
        y_offset=-2,
    )


def _draw_event_column_v4(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    team_name: str,
    team_code: str,
    events: Sequence[v3.Event],
    accent: Tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    v2._shadow_panel(
        image,
        box,
        radius=24,
        fill=(4, 15, 30),
        outline=accent,
        shadow_alpha=70,
        outline_width=2,
    )

    v2._paste_crest(image, team_code, (x1 + 72, y1 + 62), 96)
    title_font = v2._fit_text(draw, team_name.upper(), x2 - x1 - 180, 40, 28, "bold", True)
    draw.text((x1 + 135, y1 + 34), team_name.upper(), font=title_font, fill=v2.WHITE)
    draw.line((x1 + 28, y1 + 112, x2 - 28, y1 + 112), fill=accent, width=3)

    y = y1 + 145
    for event in list(events)[:4]:
        v3._draw_event_row(
            draw,
            x1 + 35,
            y,
            x2 - x1 - 70,
            event,
            accent,
            max_font=43,
            min_font=27,
        )
        y += 68
        if y > y2 - 62:
            break


def _draw_single_match_v4(image: Image.Image, match: Dict[str, Any]) -> None:
    draw = ImageDraw.Draw(image)
    _, accent = v2._status_label(match)

    panel = (55, 440, 1545, 975)
    v2._glow_outline(image, panel, accent, radius=30, blur=18, alpha=52)
    v2._shadow_panel(image, panel, radius=30, fill=v2.PANEL, outline=accent, shadow_alpha=105, outline_width=3)

    home = v2._team_name(match, True)
    away = v2._team_name(match, False)
    home_code = v2._team_code(match, True)
    away_code = v2._team_code(match, False)
    home_score = v2._score_value(match, True)
    away_score = v2._score_value(match, False)

    v2._paste_crest(image, home_code, (275, 665), 330)
    v2._paste_crest(image, away_code, (1325, 665), 330)

    score_box = (535, 535, 1065, 805)
    v2._glow_outline(image, score_box, v2.CYAN, radius=38, blur=24, alpha=88)
    v2._round(draw, score_box, 38, fill=(3, 20, 40), outline=v2.CYAN, width=4)
    v2._centered_text(
        draw,
        score_box,
        f"{home_score}  ×  {away_score}",
        v2._font(138, "bold", True),
        fill=v2.WHITE,
        y_offset=-8,
    )

    home_font = v2._fit_text(draw, home.upper(), 500, 58, 36, "bold", True)
    away_font = v2._fit_text(draw, away.upper(), 500, 58, 36, "bold", True)
    v2._centered_text(draw, (55, 835, 555, 925), home.upper(), home_font, fill=v2.WHITE)
    v2._centered_text(draw, (1045, 835, 1545, 925), away.upper(), away_font, fill=v2.WHITE)

    title_box = (545, 945, 1055, 1015)
    v2._round(draw, title_box, 22, fill=(5, 24, 43), outline=v2.CYAN, width=2)
    v2._centered_text(draw, title_box, "EVENTOS DA PARTIDA", v2._font(33, "bold", True), fill=v2.WHITE)

    _draw_event_column_v4(
        image,
        (70, 1018, 780, 1368),
        home,
        home_code,
        v3._events(match, True),
        v2.CYAN,
    )
    _draw_event_column_v4(
        image,
        (820, 1018, 1530, 1368),
        away,
        away_code,
        v3._events(match, False),
        v2.BLUE,
    )

    summary_box = (245, 1392, 1355, 1465)
    v2._round(draw, summary_box, 24, fill=(5, 24, 43), outline=v2.LINE, width=2)
    v2._centered_text(
        draw,
        summary_box,
        "PLACAR E EVENTOS ATUALIZADOS AUTOMATICAMENTE",
        v2._fit_text(draw, "PLACAR E EVENTOS ATUALIZADOS AUTOMATICAMENTE", 1040, 30, 23, "bold", True),
        fill=v2.SILVER,
    )


def _draw_footer_v4(image: Image.Image, page: Tuple[int, int] | None = None) -> None:
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    y = 1490
    draw.line((55, y, width - 55, y), fill=(32, 91, 142), width=3)
    draw.ellipse((55, y + 18, 113, y + 76), fill=(28, 163, 227))
    v2._centered_text(draw, (55, y + 18, 113, y + 76), "➤", v2._font(28, "bold"), fill=v2.WHITE)
    draw.text((130, y + 28), "@dicascartolaportalsimonsports", font=v2._font(27, "semibold", True), fill=v2.WHITE)

    brand = "PORTAL SIMONSPORTS"
    bf = v2._font(34, "bold", True)
    bb = draw.textbbox((0, 0), brand, font=bf)
    draw.text((width - 55 - (bb[2] - bb[0]), y + 23), brand, font=bf, fill=v2.WHITE)

    if page:
        pf = v2._font(23, "bold")
        text = f"{page[0]}/{page[1]}"
        pb = draw.textbbox((0, 0), text, font=pf)
        draw.text(((width - (pb[2] - pb[0])) / 2, y + 32), text, font=pf, fill=v2.MUTED)


def _draw_compact_match_v4(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    match: Dict[str, Any],
    index: int,
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    status, accent = v2._status_label(match)

    v2._glow_outline(image, box, accent, radius=25, blur=12, alpha=36)
    v2._shadow_panel(image, box, radius=25, fill=v2.PANEL, outline=accent, shadow_alpha=85, outline_width=2)

    home = v2._team_name(match, True)
    away = v2._team_name(match, False)
    hc = v2._team_code(match, True)
    ac = v2._team_code(match, False)
    hs = v2._score_value(match, True)
    aws = v2._score_value(match, False)

    draw.text((x1 + 28, y1 + 20), f"JOGO {index:02d}", font=v2._font(25, "bold", True), fill=v2.BLUE)
    status_box = (x2 - 275, y1 + 16, x2 - 24, y1 + 70)
    v2._round(draw, status_box, 20, fill=accent)
    v2._centered_text(draw, status_box, status, v2._fit_text(draw, status, 220, 21, 16, "bold", True), fill=(5, 17, 30))

    v2._paste_crest(image, hc, (x1 + 135, y1 + 190), 155)
    v2._paste_crest(image, ac, (x2 - 135, y1 + 190), 155)

    home_font = v2._fit_text(draw, home.upper(), 360, 39, 24, "bold", True)
    away_font = v2._fit_text(draw, away.upper(), 360, 39, 24, "bold", True)
    draw.text((x1 + 225, y1 + 120), home.upper(), font=home_font, fill=v2.WHITE)
    away_bbox = draw.textbbox((0, 0), away.upper(), font=away_font)
    draw.text((x2 - 225 - (away_bbox[2] - away_bbox[0]), y1 + 120), away.upper(), font=away_font, fill=v2.WHITE)

    score_box = ((x1 + x2) // 2 - 180, y1 + 105, (x1 + x2) // 2 + 180, y1 + 245)
    v2._round(draw, score_box, 28, fill=(3, 20, 40), outline=v2.CYAN, width=3)
    v2._centered_text(draw, score_box, f"{hs}  ×  {aws}", v2._font(72, "bold", True), fill=v2.WHITE)

    y_events = y1 + 260
    for event in v3._events(match, True)[:2]:
        v3._draw_event_row(draw, x1 + 225, y_events, 320, event, v2.CYAN, max_font=27, min_font=19)
        y_events += 38
    y_events = y1 + 260
    for event in v3._events(match, False)[:2]:
        v3._draw_event_row(draw, x2 - 225, y_events, 320, event, v2.BLUE, align_right=True, max_font=27, min_font=19)
        y_events += 38

    date_line = v2._date_line(match)
    if date_line:
        v2._centered_text(
            draw,
            (x1 + 330, y2 - 55, x2 - 330, y2 - 15),
            date_line,
            v2._fit_text(draw, date_line, 760, 25, 18, "semibold", True),
            fill=v2.MUTED,
        )


def render_results_v4(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Payload de resultados sem partidas estruturadas; card vazio bloqueado.")

    round_value = v2._round_value(data)
    statuses = [v2._status_label(match)[0] for match in matches]
    live = any("AO VIVO" in status or "INTERVALO" in status for status in statuses)
    final = all(status == "ENCERRADO" for status in statuses)
    kind = v2._kind_text(data)

    if "placar" in kind or live:
        title = f"ATUALIZAÇÃO DE PLACAR • RODADA {round_value}"
        subtitle = "Acompanhe ao vivo os placares e eventos da partida."
    elif final:
        title = f"RESULTADOS DA RODADA • RODADA {round_value}"
        subtitle = "Resultados oficiais e eventos dos jogos."
    else:
        title = f"JOGOS DA RODADA • RODADA {round_value}"
        subtitle = "Agenda oficial e status das partidas."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files: List[str] = []

    if len(matches) == 1:
        image = v2._gradient_background(*RESULT_SIZE_V4)
        _draw_header_v4(image, title, subtitle, v2._badge(data))
        _draw_info_bar(image, matches[0])
        _draw_single_match_v4(image, matches[0])
        _draw_footer_v4(image)
        path = str(Path(output_dir) / f"live_placar_v4_rodada_{round_value}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    else:
        pages = math.ceil(len(matches) / 2)
        for page in range(pages):
            image = v2._gradient_background(*RESULT_SIZE_V4)
            _draw_header_v4(image, title, subtitle, v2._badge(data))
            chunk = matches[page * 2:(page + 1) * 2]
            y = 335
            for index, match in enumerate(chunk, start=page * 2 + 1):
                _draw_compact_match_v4(image, (45, y, 1555, y + 510), match, index)
                y += 535
            _draw_footer_v4(image, (page + 1, pages) if pages > 1 else None)
            path = str(Path(output_dir) / f"live_jogos_v4_rodada_{round_value}_p{page + 1}.png")
            image.convert("RGB").save(path, "PNG", optimize=True)
            files.append(path)

    caption = "Atualização de Placar" if live or "placar" in kind else "Resultados da Rodada"
    return RenderOutput(files, "results_v4", title, f"{caption} • Rodada {round_value}")


def render_live_publication_v4(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    kind = v2._kind_text(data)

    if v2._extract_matches(data) or any(token in kind for token in ("placar", "resultado", "partida", "live")):
        return render_results_v4(data, output_dir)

    return v3.render_live_publication_v3(data, output_dir)
