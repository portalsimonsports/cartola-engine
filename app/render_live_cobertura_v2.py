from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
import render_live_cards_v3 as v3
import render_live_cards_v4 as v4
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "live_cobertura_v2_gol_contra_2026_07_30"
COVERAGE_EVENTS = {"LIVE_ABERTURA", "LIVE_RESULTADOS_NOITE"}
Event = Dict[str, Any]


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", _safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def event_name(data: Dict[str, Any]) -> str:
    joined = " ".join(
        _norm(data.get(key))
        for key in ("evento_programado", "tipo_publicacao", "contexto", "titulo")
        if data.get(key)
    )
    if any(token in joined for token in ("LIVE_ABERTURA", "ABERTURA_DIA", "ABERTURA_DO_LIVE")):
        return "LIVE_ABERTURA"
    if any(token in joined for token in ("LIVE_RESULTADOS_NOITE", "RESULTADOS_DA_NOITE", "FECHAMENTO_DIA")):
        return "LIVE_RESULTADOS_NOITE"
    return _norm(data.get("evento_programado"))


def is_coverage_event(data: Dict[str, Any]) -> bool:
    return event_name(data) in COVERAGE_EVENTS


def _raw_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [value]


def _goal_event(item: Any) -> Event | None:
    if isinstance(item, dict):
        name = _safe(v2._value(item, "nome", "jogador", "atleta", "goleador", default=""))
        count = v2._int(v2._value(item, "quantidade", "gols", "count", "total", default=1), 1)
        raw_kind = _norm(v2._value(item, "tipo", "kind", "evento", default=""))
        own = bool(item.get("gol_contra") or item.get("own_goal")) or raw_kind in {
            "GC", "GOL_CONTRA", "GOLS_CONTRA", "OWN_GOAL", "OWN_GOALS"
        }
        if not name:
            return None
        return {"kind": "own_goal" if own else "goal", "label": name, "count": max(1, min(6, count))}

    text = v2._clean_markdown(item).strip()
    if not text:
        return None
    upper = _norm(text)
    own = any(token in upper for token in ("GOL_CONTRA", "GC", "OWN_GOAL")) or "🔴" in text
    clean = re.sub(r"\b(?:GOL\s*CONTRA|GC|OWN\s*GOAL)\b", "", text, flags=re.I)
    clean = clean.replace("🔴", "").strip(" -•[]()")
    base = v3._goal_event(clean)
    if not base:
        return None
    base["kind"] = "own_goal" if own else "goal"
    return base


def _events(match: Dict[str, Any], home: bool) -> List[Event]:
    scorer_keys = (
        ("goleadores_casa", "marcadores_casa", "gols_casa")
        if home
        else ("goleadores_fora", "marcadores_fora", "gols_fora")
    )
    card_keys = (
        ("cartoes_casa", "cartões_casa")
        if home
        else ("cartoes_fora", "cartões_fora")
    )
    result: List[Event] = []
    for item in _raw_list(v2._value(match, *scorer_keys, default=[])):
        event = _goal_event(item)
        if event:
            result.append(event)
    for item in _raw_list(v2._value(match, *card_keys, default=[])):
        event = v3._card_event(item)
        if event:
            result.append(event)
    return result[:7]


def _draw_ball(draw: ImageDraw.ImageDraw, center: Tuple[int, int], diameter: int, own_goal: bool) -> None:
    cx, cy = center
    radius = diameter // 2
    base = v2.RED if own_goal else (238, 243, 248)
    outline = (255, 118, 118) if own_goal else v2.WHITE
    patch = (60, 8, 16) if own_goal else (15, 28, 44)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=base, outline=outline, width=max(2, diameter // 10))
    core = max(3, diameter // 6)
    draw.ellipse((cx - core, cy - core, cx + core, cy + core), fill=patch)
    orbit = max(6, diameter // 3)
    spot = max(2, diameter // 10)
    for dx, dy in ((0, -orbit), (orbit, -2), (orbit // 2, orbit), (-orbit // 2, orbit), (-orbit, -2)):
        draw.ellipse((cx + dx - spot, cy + dy - spot, cx + dx + spot, cy + dy + spot), fill=patch)


def _event_icons_width(event: Event, diameter: int, gap: int) -> int:
    if event.get("kind") in ("goal", "own_goal"):
        return min(6, max(1, int(event.get("count") or 1))) * (diameter + gap) - gap
    return diameter


def _draw_event_row(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_width: int,
    event: Event,
    accent: Tuple[int, int, int],
    align_right: bool = False,
    max_font: int = 31,
    min_font: int = 21,
) -> None:
    label = _safe(event.get("label"), "Evento")
    own_goal = event.get("kind") == "own_goal"
    if own_goal:
        label += "  (GC)"
    diameter = 27 if max_font >= 28 else 21
    gap = 7
    icons_width = _event_icons_width(event, diameter, gap)
    separation = 18
    text_width_limit = max(100, max_width - icons_width - separation)
    font = v2._fit_text(draw, label, text_width_limit, max_font, min_font, "semibold", True)
    bbox = draw.textbbox((0, 0), label, font=font)
    label_width = bbox[2] - bbox[0]
    total_width = label_width + separation + icons_width
    start_x = x - total_width if align_right else x

    marker_color = v2.RED if own_goal or event.get("kind") == "red_card" else accent
    if event.get("kind") == "yellow_card":
        marker_color = v2.YELLOW
    draw.ellipse((start_x, y + 10, start_x + 16, y + 26), fill=marker_color)
    text_x = start_x + 30
    draw.text((text_x, y), label, font=font, fill=v2.WHITE)

    icon_x = text_x + label_width + separation + diameter // 2
    icon_y = y + max(diameter // 2 + 2, 18)
    kind = event.get("kind")
    if kind in ("goal", "own_goal"):
        for index in range(min(6, max(1, int(event.get("count") or 1)))):
            _draw_ball(draw, (icon_x + index * (diameter + gap), icon_y), diameter, kind == "own_goal")
    else:
        v3._draw_card(draw, (icon_x, icon_y), kind == "red_card")


def _draw_legend(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    box = (245, 1392, 1355, 1465)
    v2._round(draw, box, 24, fill=(5, 24, 43), outline=v2.LINE, width=2)
    _draw_ball(draw, (445, 1428), 29, False)
    draw.text((475, 1408), "GOL A FAVOR", font=v2._font(25, "bold", True), fill=v2.SILVER)
    _draw_ball(draw, (845, 1428), 29, True)
    draw.text((875, 1408), "GOL CONTRA (GC)", font=v2._font(25, "bold", True), fill=v2.SILVER)


def render_match_cards(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Payload de placar sem partidas estruturadas.")
    round_value = v2._round_value(data)
    statuses = [v2._status_label(match)[0] for match in matches]
    live = any("AO VIVO" in status or "INTERVALO" in status for status in statuses)
    final = all(status == "ENCERRADO" for status in statuses)
    kind = v2._kind_text(data)
    if "placar" in kind or live:
        title = f"ATUALIZAÇÃO DE PLACAR • RODADA {round_value}"
        subtitle = "Acompanhe ao vivo os placares e eventos da partida."
        caption = "Atualização de Placar"
    elif final:
        title = f"RESULTADOS DA RODADA • RODADA {round_value}"
        subtitle = "Resultados oficiais, marcadores e gols contra."
        caption = "Resultados da Rodada"
    else:
        title = f"JOGOS DA RODADA • RODADA {round_value}"
        subtitle = "Agenda oficial e status das partidas."
        caption = "Jogos da Rodada"

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files: List[str] = []
    original_events, original_draw = v3._events, v3._draw_event_row
    try:
        v3._events = _events
        v3._draw_event_row = _draw_event_row
        for index, match in enumerate(matches, start=1):
            image = v2._gradient_background(*v4.RESULT_SIZE_V4)
            v4._draw_header_v4(image, title, subtitle, v2._badge(data))
            v4._draw_info_bar(image, match)
            v4._draw_single_match_v4(image, match)
            _draw_legend(image)
            v4._draw_footer_v4(image, (index, len(matches)) if len(matches) > 1 else None)
            path = str(Path(output_dir) / f"live_placar_gc_rodada_{round_value}_j{index:02d}.png")
            image.convert("RGB").save(path, "PNG", optimize=True)
            files.append(path)
    finally:
        v3._events, v3._draw_event_row = original_events, original_draw

    return RenderOutput(files, "results_own_goal_v2", title, f"{caption} • Rodada {round_value}")


def _draw_schedule_row(image: Image.Image, box: Tuple[int, int, int, int], match: Dict[str, Any], index: int, results: bool) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    status, accent = v2._status_label(match)
    v2._shadow_panel(image, box, radius=27, fill=v2.PANEL, outline=accent, shadow_alpha=85, outline_width=2)
    draw.text((x1 + 25, y1 + 18), f"JOGO {index:02d}", font=v2._font(23, "bold", True), fill=v2.BLUE)
    date_line = v2._date_line(match)
    if date_line:
        draw.text((x1 + 180, y1 + 20), date_line, font=v2._fit_text(draw, date_line, x2 - x1 - 480, 27, 18, "semibold", True), fill=v2.SILVER)
    status_box = (x2 - 250, y1 + 15, x2 - 25, y1 + 67)
    v2._round(draw, status_box, 18, fill=accent)
    v2._centered_text(draw, status_box, status, v2._fit_text(draw, status, 195, 21, 15, "bold", True), fill=(5, 17, 30))

    home, away = v2._team_name(match, True), v2._team_name(match, False)
    hc, ac = v2._team_code(match, True), v2._team_code(match, False)
    v2._paste_crest(image, hc, (x1 + 105, y1 + 165), 120)
    v2._paste_crest(image, ac, (x2 - 105, y1 + 165), 120)
    v2._centered_text(draw, (x1 + 170, y1 + 90, x1 + 545, y1 + 205), home.upper(), v2._fit_text(draw, home.upper(), 375, 35, 21, "bold", True), fill=v2.WHITE)
    v2._centered_text(draw, (x2 - 545, y1 + 90, x2 - 170, y1 + 205), away.upper(), v2._fit_text(draw, away.upper(), 375, 35, 21, "bold", True), fill=v2.WHITE)

    center = ((x1 + x2) // 2 - 170, y1 + 83, (x1 + x2) // 2 + 170, y1 + 220)
    v2._round(draw, center, 26, fill=(3, 20, 40), outline=v2.CYAN, width=3)
    score = f"{v2._score_value(match, True)}  ×  {v2._score_value(match, False)}" if results else "X"
    v2._centered_text(draw, center, score, v2._font(67 if results else 56, "bold", True), fill=v2.WHITE)

    if results:
        home_events = [event for event in _events(match, True) if event.get("kind") in ("goal", "own_goal")][:3]
        away_events = [event for event in _events(match, False) if event.get("kind") in ("goal", "own_goal")][:3]
        y = y1 + 235
        for event in home_events:
            _draw_event_row(draw, x1 + 50, y, 520, event, v2.CYAN, max_font=22, min_font=16)
            y += 36
        y = y1 + 235
        for event in away_events:
            _draw_event_row(draw, x2 - 50, y, 520, event, v2.BLUE, align_right=True, max_font=22, min_font=16)
            y += 36


def _render_board(data: Dict[str, Any], output_dir: str, opening: bool) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Cobertura sem jogos estruturados.")
    round_value = v2._round_value(data)
    pages = math.ceil(len(matches) / 4)
    files: List[str] = []
    title = f"ABERTURA DO LIVE • RODADA {round_value}" if opening else f"RESULTADOS DA NOITE • RODADA {round_value}"
    subtitle = "A cobertura começou. Confira os jogos da noite." if opening else "Todos os resultados, marcadores e gols contra da noite."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for page in range(pages):
        image = v2._gradient_background(*v4.RESULT_SIZE_V4)
        v4._draw_header_v4(image, title, subtitle, v2._badge(data))
        chunk = matches[page * 4:(page + 1) * 4]
        y = 325
        for index, match in enumerate(chunk, start=page * 4 + 1):
            _draw_schedule_row(image, (48, y, 1552, y + 270), match, index, results=not opening)
            y += 285

        draw = ImageDraw.Draw(image)
        ribbon = (120, 1470, 1480, 1535)
        v2._round(draw, ribbon, 22, fill=(4, 27, 51), outline=v2.BLUE, width=2)
        text = (
            "BOLA ROLANDO: ACOMPANHE CADA LANCE COM O PORTAL SIMONSPORTS"
            if opening
            else "⚪ GOL A FAVOR     🔴 GOL CONTRA (GC)"
        )
        v2._centered_text(draw, ribbon, text, v2._fit_text(draw, text, 1280, 27, 18, "bold", True), fill=v2.WHITE)
        v4._draw_footer_v4(image, (page + 1, pages) if pages > 1 else None)
        prefix = "live_abertura" if opening else "live_resultados_noite"
        path = str(Path(output_dir) / f"{prefix}_rodada_{round_value}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    caption = "Abertura do Live" if opening else "Resultados da Noite"
    return RenderOutput(files, "live_opening_v2" if opening else "night_results_v2", title, f"{caption} • Rodada {round_value}")


def render_coverage_event(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    event = event_name(data)
    if event == "LIVE_ABERTURA":
        return _render_board(data, output_dir, opening=True)
    if event == "LIVE_RESULTADOS_NOITE":
        return _render_board(data, output_dir, opening=False)
    raise RuntimeError(f"Evento de cobertura não suportado: {event!r}")
