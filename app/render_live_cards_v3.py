from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "live_cards_v3_eventos_vetoriais_2026_07_23"


Event = Dict[str, Any]


def _clean(value: Any) -> str:
    return v2._clean_markdown(value).strip()


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
        name = v2._safe(v2._value(item, "nome", "jogador", "atleta", "goleador", default=""))
        count = v2._int(v2._value(item, "gols", "quantidade", "count", "total", default=1), 1)
        if not name:
            return None
        return {"kind": "goal", "label": name, "count": max(1, min(6, count))}

    text = _clean(item)
    if not text:
        return None

    repeated_balls = text.count("⚽")
    patterns = (
        r"^(.*?)\s*\((\d+)\s*⚽?\)\s*$",
        r"^(.*?)\s*[•\-]\s*(\d+)\s*(?:gol|gols|⚽)?\s*$",
        r"^(.*?)\s+(\d+)\s*(?:gol|gols|⚽)\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            name = match.group(1).strip(" -•")
            count = max(1, min(6, int(match.group(2))))
            return {"kind": "goal", "label": name, "count": count}

    name = text.replace("⚽", "")
    name = re.sub(r"\b(?:gol|gols)\b", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -•")
    if not name:
        return None
    return {
        "kind": "goal",
        "label": name,
        "count": max(1, min(6, repeated_balls or 1)),
    }


def _card_event(item: Any) -> Event | None:
    if isinstance(item, dict):
        name = v2._safe(v2._value(item, "nome", "jogador", "atleta", default=""))
        card_type = v2._safe(v2._value(item, "tipo", "cor", "cartao", "cartão", default="amarelo"))
        minute = v2._safe(v2._value(item, "minuto", "tempo", default=""))
        label = name + (f" • {minute}'" if name and minute else "")
        if not label:
            return None
        kind = "red_card" if any(token in card_type.upper() for token in ("VERMELH", "RED")) else "yellow_card"
        return {"kind": kind, "label": label, "count": 1}

    text = _clean(item)
    if not text:
        return None
    upper = text.upper()
    kind = "red_card" if ("VERMELH" in upper or "RED" in upper or "🟥" in text) else "yellow_card"
    label = text.replace("🟥", "").replace("🟨", "")
    label = re.sub(r"\bCART(?:A|ÃO|AO)\s+(?:AMAREL[AO]|VERMELH[AO])\b", "", label, flags=re.I)
    label = re.sub(r"\s+", " ", label).strip(" -•")
    return {"kind": kind, "label": label, "count": 1} if label else None


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
        event = _card_event(item)
        if event:
            result.append(event)
    return result[:7]


def _draw_ball(draw: ImageDraw.ImageDraw, center: Tuple[int, int], diameter: int = 27) -> None:
    cx, cy = center
    radius = diameter // 2
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=(238, 243, 248),
        outline=(255, 255, 255),
        width=max(2, diameter // 10),
    )
    core = max(3, diameter // 6)
    draw.ellipse((cx - core, cy - core, cx + core, cy + core), fill=(15, 28, 44))
    orbit = max(6, diameter // 3)
    spot = max(2, diameter // 10)
    for dx, dy in ((0, -orbit), (orbit, -2), (orbit // 2, orbit), (-orbit // 2, orbit), (-orbit, -2)):
        draw.ellipse((cx + dx - spot, cy + dy - spot, cx + dx + spot, cy + dy + spot), fill=(15, 28, 44))


def _draw_card(draw: ImageDraw.ImageDraw, center: Tuple[int, int], red: bool) -> None:
    cx, cy = center
    color = v2.RED if red else v2.YELLOW
    draw.rounded_rectangle((cx - 10, cy - 15, cx + 10, cy + 15), radius=3, fill=color, outline=(255, 255, 255), width=1)


def _event_icons_width(event: Event, diameter: int, gap: int) -> int:
    if event.get("kind") == "goal":
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
    label = v2._safe(event.get("label"), "Evento")
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

    marker_color = accent
    if event.get("kind") == "red_card":
        marker_color = v2.RED
    elif event.get("kind") == "yellow_card":
        marker_color = v2.YELLOW
    draw.ellipse((start_x, y + 10, start_x + 16, y + 26), fill=marker_color)
    text_x = start_x + 30
    draw.text((text_x, y), label, font=font, fill=v2.WHITE)

    icon_x = text_x + label_width + separation + diameter // 2
    icon_y = y + max(diameter // 2 + 2, 18)
    kind = event.get("kind")
    if kind == "goal":
        for index in range(min(6, max(1, int(event.get("count") or 1)))):
            _draw_ball(draw, (icon_x + index * (diameter + gap), icon_y), diameter)
    else:
        _draw_card(draw, (icon_x, icon_y), kind == "red_card")


def _draw_event_column(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    team_name: str,
    team_code: str,
    events: Sequence[Event],
    accent: Tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    v2._shadow_panel(
        image,
        box,
        radius=28,
        fill=(4, 15, 30),
        outline=accent,
        shadow_alpha=72,
        outline_width=2,
    )

    v2._paste_crest(image, team_code, (x1 + 82, y1 + 66), 92)
    title_font = v2._fit_text(draw, team_name.upper(), x2 - x1 - 195, 34, 22, "bold", True)
    draw.text((x1 + 148, y1 + 42), team_name.upper(), font=title_font, fill=v2.WHITE)
    draw.line((x1 + 30, y1 + 118, x2 - 30, y1 + 118), fill=accent, width=3)

    y = y1 + 152
    for event in list(events)[:6]:
        _draw_event_row(draw, x1 + 34, y, x2 - x1 - 68, event, accent)
        y += 58
        if y > y2 - 58:
            break


def _draw_single_match(image: Image.Image, match: Dict[str, Any]) -> None:
    draw = ImageDraw.Draw(image)
    panel = (65, 345, 1535, 1825)
    status, accent = v2._status_label(match)

    v2._glow_outline(image, panel, accent, radius=34, blur=18, alpha=55)
    v2._shadow_panel(image, panel, radius=34, fill=v2.PANEL, outline=accent, shadow_alpha=110, outline_width=3)

    date_line = v2._date_line(match)
    if date_line:
        date_font = v2._fit_text(draw, date_line, 930, 32, 21, "semibold", True)
        draw.text((118, 390), date_line, font=date_font, fill=v2.SILVER)

    status_box = (1160, 378, 1488, 458)
    v2._round(draw, status_box, 27, fill=accent)
    v2._centered_text(draw, status_box, status, v2._fit_text(draw, status, 285, 28, 19, "bold", True), fill=(5, 17, 30), y_offset=-2)

    home = v2._team_name(match, True)
    away = v2._team_name(match, False)
    home_code = v2._team_code(match, True)
    away_code = v2._team_code(match, False)
    home_score = v2._score_value(match, True)
    away_score = v2._score_value(match, False)

    v2._paste_crest(image, home_code, (285, 685), 275)
    v2._paste_crest(image, away_code, (1315, 685), 275)

    home_font = v2._fit_text(draw, home.upper(), 500, 50, 30, "bold", True)
    away_font = v2._fit_text(draw, away.upper(), 500, 50, 30, "bold", True)
    v2._centered_text(draw, (65, 820, 565, 905), home.upper(), home_font, fill=v2.WHITE)
    v2._centered_text(draw, (1035, 820, 1535, 905), away.upper(), away_font, fill=v2.WHITE)

    score_box = (565, 545, 1035, 815)
    v2._glow_outline(image, score_box, v2.CYAN, radius=40, blur=22, alpha=78)
    v2._round(draw, score_box, 40, fill=(3, 20, 40), outline=v2.CYAN, width=3)
    v2._centered_text(draw, score_box, f"{home_score}  ×  {away_score}", v2._font(118, "bold", True), fill=v2.WHITE, y_offset=-5)

    section = (95, 955, 1505, 1585)
    v2._shadow_panel(image, section, radius=30, fill=(4, 14, 29), outline=v2.LINE, shadow_alpha=80, outline_width=2)
    title_box = (545, 925, 1055, 1000)
    v2._round(draw, title_box, 24, fill=(5, 24, 43), outline=v2.CYAN, width=2)
    v2._centered_text(draw, title_box, "EVENTOS DA PARTIDA", v2._font(29, "bold", True), fill=v2.WHITE)

    _draw_event_column(image, (112, 1015, 775, 1545), home, home_code, _events(match, True), v2.CYAN)
    _draw_event_column(image, (825, 1015, 1488, 1545), away, away_code, _events(match, False), v2.BLUE)

    summary_box = (255, 1625, 1345, 1715)
    v2._round(draw, summary_box, 27, fill=(5, 24, 43), outline=v2.LINE, width=2)
    v2._centered_text(draw, summary_box, "PLACAR E EVENTOS ATUALIZADOS AUTOMATICAMENTE", v2._font(28, "bold", True), fill=v2.SILVER)


def _draw_compact_events(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_width: int,
    events: Sequence[Event],
    align_right: bool = False,
) -> None:
    for event in list(events)[:3]:
        _draw_event_row(draw, x, y, max_width, event, v2.CYAN, align_right=align_right, max_font=24, min_font=17)
        y += 34


def _draw_compact_match(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    match: Dict[str, Any],
    index: int,
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    status, accent = v2._status_label(match)

    v2._glow_outline(image, box, accent, radius=28, blur=13, alpha=38)
    v2._shadow_panel(image, box, radius=28, fill=v2.PANEL, outline=accent, shadow_alpha=90, outline_width=2)

    draw.text((x1 + 28, y1 + 18), f"JOGO {index:02d}", font=v2._font(24, "bold", True), fill=v2.BLUE)
    status_box = (x2 - 285, y1 + 16, x2 - 26, y1 + 70)
    v2._round(draw, status_box, 22, fill=accent)
    v2._centered_text(draw, status_box, status, v2._fit_text(draw, status, 230, 20, 15, "bold", True), fill=(5, 17, 30))

    home = v2._team_name(match, True)
    away = v2._team_name(match, False)
    hc = v2._team_code(match, True)
    ac = v2._team_code(match, False)
    hs = v2._score_value(match, True)
    aws = v2._score_value(match, False)

    v2._paste_crest(image, hc, (x1 + 105, y1 + 170), 142)
    v2._paste_crest(image, ac, (x2 - 105, y1 + 170), 142)

    home_font = v2._fit_text(draw, home.upper(), 350, 37, 22, "bold", True)
    away_font = v2._fit_text(draw, away.upper(), 350, 37, 22, "bold", True)
    draw.text((x1 + 190, y1 + 112), home.upper(), font=home_font, fill=v2.WHITE)
    away_bbox = draw.textbbox((0, 0), away.upper(), font=away_font)
    draw.text((x2 - 190 - (away_bbox[2] - away_bbox[0]), y1 + 112), away.upper(), font=away_font, fill=v2.WHITE)

    _draw_compact_events(draw, x1 + 190, y1 + 160, 330, _events(match, True))
    _draw_compact_events(draw, x2 - 190, y1 + 160, 330, _events(match, False), True)

    score_box = ((x1 + x2) // 2 - 170, y1 + 95, (x1 + x2) // 2 + 170, y1 + 225)
    v2._round(draw, score_box, 28, fill=(3, 20, 40), outline=v2.BLUE, width=2)
    v2._centered_text(draw, score_box, f"{hs}  ×  {aws}", v2._font(66, "bold", True), fill=v2.WHITE)

    date_line = v2._date_line(match)
    if date_line:
        v2._centered_text(draw, (x1 + 310, y1 + 250, x2 - 310, y1 + 292), date_line, v2._fit_text(draw, date_line, 790, 25, 18, "semibold", True), fill=v2.MUTED)


def render_results_v3(data: Dict[str, Any], output_dir: str) -> RenderOutput:
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
        image = v2._gradient_background(*v2.RESULT_SIZE)
        v2._header_team(image, title, subtitle, v2._badge(data))
        _draw_single_match(image, matches[0])
        v2._footer(image, 1888)
        path = str(Path(output_dir) / f"live_placar_v3_rodada_{round_value}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    else:
        pages = math.ceil(len(matches) / 4)
        for page in range(pages):
            image = v2._gradient_background(*v2.RESULT_SIZE)
            v2._header_team(image, title, subtitle, v2._badge(data))
            y = 335
            chunk = matches[page * 4:(page + 1) * 4]
            for index, match in enumerate(chunk, start=page * 4 + 1):
                _draw_compact_match(image, (42, y, 1558, y + 345), match, index)
                y += 370
            v2._footer(image, 1888, (page + 1, pages) if pages > 1 else None)
            path = str(Path(output_dir) / f"live_jogos_v3_rodada_{round_value}_p{page + 1}.png")
            image.convert("RGB").save(path, "PNG", optimize=True)
            files.append(path)

    caption = "Atualização de Placar" if live or "placar" in kind else "Resultados da Rodada"
    return RenderOutput(files, "results_v3", title, f"{caption} • Rodada {round_value}")


def render_live_publication_v3(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    kind = v2._kind_text(data)

    if v2._extract_matches(data) or any(token in kind for token in ("placar", "resultado", "partida", "live")):
        return render_results_v3(data, output_dir)

    if v2._team_summaries(data) or any(token in kind for token in ("resumo_geral", "time_delta", "abertura_dia")):
        return v2.render_summary_v2(data, output_dir)

    if data.get("top_5") or data.get("piores_5") or any(token in kind for token in ("ranking", "mitos", "zicas")):
        return v2.render_ranking_v2(data, output_dir)

    if any(token in kind for token in ("top5", "top 5", "time", "campinho", "escalacao", "econom", "intermedi", "pontua")):
        return v2.render_legacy_publication(data, output_dir)

    message = v2._safe(data.get("mensagem_oficial"))
    message_upper = message.upper()
    if "MITOS E ZICAS" in message_upper:
        return v2.render_ranking_v2(data, output_dir)
    if "RESULTADOS E RESUMOS" in message_upper or "ATUALIZAÇÃO DE PLACAR" in message_upper:
        return render_results_v3(data, output_dir)
    if "RESUMO GERAL" in message_upper:
        return v2.render_summary_v2(data, output_dir)

    raise RuntimeError(
        "Tipo de publicação Live não reconhecido. "
        "Boletim genérico bloqueado para preservar o padrão visual aprovado."
    )
