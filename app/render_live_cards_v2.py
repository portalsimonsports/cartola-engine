from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

from render_telegram_cards import (
    BLUE,
    CYAN,
    GOLD,
    GREEN,
    LINE,
    MUTED,
    ORANGE,
    PANEL,
    PANEL_2,
    PURPLE,
    RED,
    RESULT_SIZE,
    SILVER,
    WHITE,
    YELLOW,
    RenderOutput,
    _centered_text,
    _clean_markdown,
    _fit_text,
    _font,
    _footer,
    _glow_outline,
    _gradient_background,
    _header_team,
    _paste_crest,
    _round,
    _safe,
    _shadow_panel,
    _value,
    render_publication as render_legacy_publication,
)

VISUAL_VERSION = "live_cards_v2_base_aprovada_2026_07_23"

MODEL_COLORS = {
    "ECONOMICO": GREEN,
    "INTERMEDIARIO": CYAN,
    "PONTUACAO": PURPLE,
}

MODEL_NAMES = {
    "ECONOMICO": "TIME ECONÔMICO",
    "INTERMEDIARIO": "TIME INTERMEDIÁRIO",
    "PONTUACAO": "TIME PARA PONTUAR",
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _round_value(data: Dict[str, Any]) -> str:
    return _safe(data.get("rodada") or data.get("rodada_atual") or "ATUAL")


def _badge(data: Dict[str, Any]) -> str:
    value = _round_value(data)
    return f"RODADA {value}" if value and value != "ATUAL" else "CARTOLA"


def _kind_text(data: Dict[str, Any]) -> str:
    return " ".join(
        _safe(data.get(key))
        for key in ("tipo_publicacao", "contexto", "titulo")
    ).lower()


def _status_label(match: Dict[str, Any]) -> Tuple[str, Tuple[int, int, int]]:
    raw = _safe(_value(match, "status", "situacao", "fase", default="PROGRAMADO"))
    minute = _safe(_value(match, "minuto", "tempo", default=""))
    normalized = raw.upper().replace("_", " ")

    if any(token in normalized for token in ("ENCERR", "FINALIZ", "FIM DE JOGO", "FINAL")):
        return "ENCERRADO", GREEN
    if "INTERVAL" in normalized:
        return "INTERVALO", ORANGE
    if any(token in normalized for token in ("ANDAMENTO", "AO VIVO", "LIVE", "2T", "1T")):
        label = "AO VIVO"
        if minute:
            clean_minute = minute if "'" in minute else f"{minute}'"
            label += f" • {clean_minute}"
        return label, ORANGE
    if any(token in normalized for token in ("ADIAD", "CANCEL")):
        return normalized[:18], RED
    return "PROGRAMADO", BLUE


def _team_name(match: Dict[str, Any], home: bool) -> str:
    keys = (
        ("casa_nome", "mandante", "home", "time_casa", "casa", "equipe_mandante")
        if home
        else ("fora_nome", "visitante", "away", "time_fora", "fora", "equipe_visitante")
    )
    return _safe(_value(match, *keys), "MANDANTE" if home else "VISITANTE")


def _team_code(match: Dict[str, Any], home: bool) -> str:
    keys = (
        ("casa_sigla", "mandante_abrev", "home_abbr", "clube_mandante")
        if home
        else ("fora_sigla", "visitante_abrev", "away_abbr", "clube_visitante")
    )
    value = _safe(_value(match, *keys))
    if value:
        return value.upper()
    name = _team_name(match, home)
    words = [word for word in re.sub(r"[^A-Za-zÀ-ÿ0-9 ]", "", name).split() if word]
    if len(words) >= 2:
        return "".join(word[0] for word in words[:3]).upper()
    return name[:3].upper()


def _score_value(match: Dict[str, Any], home: bool) -> str:
    keys = (
        ("placar_casa", "placar_mandante", "gols_mandante", "home_score", "gm")
        if home
        else ("placar_fora", "placar_visitante", "gols_visitante", "away_score", "gv")
    )
    value = _value(match, *keys, default=None)
    if value in (None, ""):
        return "–"
    try:
        return str(int(float(value)))
    except Exception:
        return _safe(value, "–")


def _goal_text(value: Any) -> str:
    text = _clean_markdown(value)
    if not text:
        return ""

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
            return f"{name}  {'⚽' * count}"

    cleaned = re.sub(r"\b(?:gol|gols)\b", "", text, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -•")
    if "⚽" in cleaned:
        return cleaned
    return f"{cleaned}  ⚽" if cleaned else ""


def _scorers(match: Dict[str, Any], home: bool) -> List[str]:
    keys = (
        ("goleadores_casa", "marcadores_casa", "gols_casa")
        if home
        else ("goleadores_fora", "marcadores_fora", "gols_fora")
    )
    raw = _value(match, *keys, default=[])
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.splitlines() if part.strip()]
    if not isinstance(raw, list):
        return []

    clean: List[str] = []
    for item in raw:
        value = _goal_text(item)
        if value:
            clean.append(value)
    return clean[:6]


def _cards(match: Dict[str, Any], home: bool) -> List[str]:
    keys = (
        ("cartoes_casa", "cartões_casa")
        if home
        else ("cartoes_fora", "cartões_fora")
    )
    raw = _value(match, *keys, default=[])
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.splitlines() if part.strip()]
    if not isinstance(raw, list):
        return []

    result: List[str] = []
    for item in raw:
        text = _clean_markdown(item)
        if not text:
            continue
        upper = text.upper()
        if "VERMELH" in upper or "RED" in upper or "🟥" in text:
            icon = "🟥"
        else:
            icon = "🟨"
        text = text.replace("🟥", "").replace("🟨", "").strip(" -•")
        result.append(f"{icon}  {text}" if text else icon)
    return result[:4]


def _events(match: Dict[str, Any], home: bool) -> List[str]:
    return (_scorers(match, home) + _cards(match, home))[:7]


def _date_line(match: Dict[str, Any]) -> str:
    date = _safe(_value(match, "data", "data_jogo", default=""))
    hour = _safe(_value(match, "hora", "horario", "início", "inicio", default=""))
    stadium = _safe(_value(match, "estadio", "estádio", "local", default=""))
    parts = []
    if date or hour:
        parts.append(" • ".join(value for value in (date, hour) if value))
    if stadium:
        parts.append(stadium)
    return "  |  ".join(parts)


def _extract_matches(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("partidas", "jogos", "resultados", "lista", "matches"):
        value = data.get(key)
        if isinstance(value, list) and value:
            matches = [item for item in value if isinstance(item, dict)]
            if matches:
                return matches
    return []


def _draw_event_column(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    team_name: str,
    team_code: str,
    events: Sequence[str],
    accent: Tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    _shadow_panel(
        image,
        box,
        radius=28,
        fill=(4, 15, 30),
        outline=accent,
        shadow_alpha=72,
        outline_width=2,
    )

    _paste_crest(image, team_code, (x1 + 72, y1 + 66), 74)
    title_font = _fit_text(draw, team_name.upper(), x2 - x1 - 170, 31, 20, "bold", True)
    draw.text((x1 + 128, y1 + 43), team_name.upper(), font=title_font, fill=WHITE)
    draw.line((x1 + 30, y1 + 112, x2 - 30, y1 + 112), fill=accent, width=3)

    y = y1 + 145
    for text in list(events)[:6]:
        font = _fit_text(draw, text, x2 - x1 - 110, 31, 21, "semibold", True)
        if text.startswith("🟥"):
            marker = RED
        elif text.startswith("🟨"):
            marker = YELLOW
        else:
            marker = accent
        draw.ellipse((x1 + 34, y + 11, x1 + 52, y + 29), fill=marker)
        draw.text((x1 + 72, y), text, font=font, fill=WHITE)
        y += 54
        if y > y2 - 55:
            break


def _draw_single_match(image: Image.Image, match: Dict[str, Any]) -> None:
    draw = ImageDraw.Draw(image)
    panel = (65, 345, 1535, 1825)
    status, accent = _status_label(match)

    _glow_outline(image, panel, accent, radius=34, blur=18, alpha=55)
    _shadow_panel(
        image,
        panel,
        radius=34,
        fill=PANEL,
        outline=accent,
        shadow_alpha=110,
        outline_width=3,
    )

    date_line = _date_line(match)
    if date_line:
        date_font = _fit_text(draw, date_line, 930, 30, 20, "semibold", True)
        draw.text((118, 390), date_line, font=date_font, fill=SILVER)

    status_box = (1160, 378, 1488, 458)
    _round(draw, status_box, 27, fill=accent)
    _centered_text(
        draw,
        status_box,
        status,
        _fit_text(draw, status, 285, 28, 19, "bold", True),
        fill=(5, 17, 30),
        y_offset=-2,
    )

    home = _team_name(match, True)
    away = _team_name(match, False)
    home_code = _team_code(match, True)
    away_code = _team_code(match, False)
    home_score = _score_value(match, True)
    away_score = _score_value(match, False)

    _paste_crest(image, home_code, (285, 685), 230)
    _paste_crest(image, away_code, (1315, 685), 230)

    home_font = _fit_text(draw, home.upper(), 480, 48, 29, "bold", True)
    away_font = _fit_text(draw, away.upper(), 480, 48, 29, "bold", True)
    _centered_text(draw, (65, 820, 565, 905), home.upper(), home_font, fill=WHITE)
    _centered_text(draw, (1035, 820, 1535, 905), away.upper(), away_font, fill=WHITE)

    score_box = (565, 545, 1035, 815)
    _glow_outline(image, score_box, CYAN, radius=40, blur=22, alpha=78)
    _round(draw, score_box, 40, fill=(3, 20, 40), outline=CYAN, width=3)
    _centered_text(
        draw,
        score_box,
        f"{home_score}  ×  {away_score}",
        _font(118, "bold", True),
        fill=WHITE,
        y_offset=-5,
    )

    section = (95, 955, 1505, 1585)
    _shadow_panel(
        image,
        section,
        radius=30,
        fill=(4, 14, 29),
        outline=LINE,
        shadow_alpha=80,
        outline_width=2,
    )
    title_box = (545, 925, 1055, 1000)
    _round(draw, title_box, 24, fill=(5, 24, 43), outline=CYAN, width=2)
    _centered_text(draw, title_box, "EVENTOS DA PARTIDA", _font(29, "bold", True), fill=WHITE)

    _draw_event_column(
        image,
        (112, 1015, 775, 1545),
        home,
        home_code,
        _events(match, True),
        GREEN,
    )
    _draw_event_column(
        image,
        (825, 1015, 1488, 1545),
        away,
        away_code,
        _events(match, False),
        RED,
    )

    summary_box = (255, 1625, 1345, 1715)
    _round(draw, summary_box, 27, fill=(5, 24, 43), outline=LINE, width=2)
    _centered_text(
        draw,
        summary_box,
        "PLACAR E EVENTOS ATUALIZADOS AUTOMATICAMENTE",
        _font(28, "bold", True),
        fill=SILVER,
    )


def _draw_compact_events(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    max_width: int,
    events: Sequence[str],
    align_right: bool = False,
) -> None:
    for text in list(events)[:3]:
        font = _fit_text(draw, text, max_width, 23, 16, "semibold", True)
        bbox = draw.textbbox((0, 0), text, font=font)
        tx = x - (bbox[2] - bbox[0]) if align_right else x
        draw.text((tx, y), text, font=font, fill=SILVER)
        y += 31


def _draw_compact_match(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    match: Dict[str, Any],
    index: int,
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    status, accent = _status_label(match)

    _glow_outline(image, box, accent, radius=28, blur=13, alpha=38)
    _shadow_panel(
        image,
        box,
        radius=28,
        fill=PANEL,
        outline=accent,
        shadow_alpha=90,
        outline_width=2,
    )

    draw.text((x1 + 28, y1 + 18), f"JOGO {index:02d}", font=_font(24, "bold", True), fill=BLUE)
    status_box = (x2 - 285, y1 + 16, x2 - 26, y1 + 70)
    _round(draw, status_box, 22, fill=accent)
    _centered_text(
        draw,
        status_box,
        status,
        _fit_text(draw, status, 230, 20, 15, "bold", True),
        fill=(5, 17, 30),
    )

    home = _team_name(match, True)
    away = _team_name(match, False)
    hc = _team_code(match, True)
    ac = _team_code(match, False)
    hs = _score_value(match, True)
    aws = _score_value(match, False)

    _paste_crest(image, hc, (x1 + 105, y1 + 170), 118)
    _paste_crest(image, ac, (x2 - 105, y1 + 170), 118)

    home_font = _fit_text(draw, home.upper(), 340, 35, 21, "bold", True)
    away_font = _fit_text(draw, away.upper(), 340, 35, 21, "bold", True)
    draw.text((x1 + 180, y1 + 112), home.upper(), font=home_font, fill=WHITE)
    away_bbox = draw.textbbox((0, 0), away.upper(), font=away_font)
    draw.text((x2 - 180 - (away_bbox[2] - away_bbox[0]), y1 + 112), away.upper(), font=away_font, fill=WHITE)

    _draw_compact_events(draw, x1 + 180, y1 + 160, 330, _events(match, True))
    _draw_compact_events(draw, x2 - 180, y1 + 160, 330, _events(match, False), True)

    score_box = ((x1 + x2) // 2 - 170, y1 + 95, (x1 + x2) // 2 + 170, y1 + 225)
    _round(draw, score_box, 28, fill=(3, 20, 40), outline=BLUE, width=2)
    _centered_text(draw, score_box, f"{hs}  ×  {aws}", _font(66, "bold", True), fill=WHITE)

    date_line = _date_line(match)
    if date_line:
        _centered_text(
            draw,
            (x1 + 310, y1 + 250, x2 - 310, y1 + 292),
            date_line,
            _fit_text(draw, date_line, 790, 24, 17, "semibold", True),
            fill=MUTED,
        )


def render_results_v2(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = _extract_matches(data)
    if not matches:
        raise RuntimeError("Payload de resultados sem partidas estruturadas; card vazio bloqueado.")

    round_value = _round_value(data)
    statuses = [_status_label(match)[0] for match in matches]
    live = any("AO VIVO" in status or "INTERVALO" in status for status in statuses)
    final = all(status == "ENCERRADO" for status in statuses)
    kind = _kind_text(data)

    if "placar" in kind or live:
        title = f"ATUALIZAÇÃO DE PLACAR • RODADA {round_value}"
        subtitle = "Acompanhe ao vivo os placares e eventos da partida."
    elif final:
        title = f"RESULTADOS DA RODADA • RODADA {round_value}"
        subtitle = "Resultados oficiais e marcadores dos jogos."
    else:
        title = f"JOGOS DA RODADA • RODADA {round_value}"
        subtitle = "Agenda oficial e status das partidas."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files: List[str] = []

    if len(matches) == 1:
        image = _gradient_background(*RESULT_SIZE)
        _header_team(image, title, subtitle, _badge(data))
        _draw_single_match(image, matches[0])
        _footer(image, 1888)
        path = str(Path(output_dir) / f"live_placar_rodada_{round_value}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    else:
        pages = math.ceil(len(matches) / 4)
        for page in range(pages):
            image = _gradient_background(*RESULT_SIZE)
            _header_team(image, title, subtitle, _badge(data))
            y = 335
            chunk = matches[page * 4:(page + 1) * 4]
            for index, match in enumerate(chunk, start=page * 4 + 1):
                _draw_compact_match(image, (42, y, 1558, y + 345), match, index)
                y += 370
            _footer(image, 1888, (page + 1, pages) if pages > 1 else None)
            path = str(Path(output_dir) / f"live_resultados_rodada_{round_value}_p{page + 1}.png")
            image.convert("RGB").save(path, "PNG", optimize=True)
            files.append(path)

    caption = "Atualização de Placar" if live or "placar" in kind else "Resultados da Rodada"
    return RenderOutput(files, "results_v2", title, f"{caption} • Rodada {round_value}")


def _team_summaries(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = data.get("tipos")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _metric(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    accent: Tuple[int, int, int],
    width: int,
) -> None:
    label_font = _fit_text(draw, label, width, 26, 19, "bold", True)
    value_font = _fit_text(draw, value, width, 52, 36, "bold", True)
    draw.text((x, y), label, font=label_font, fill=SILVER)
    draw.text((x, y + 42), value, font=value_font, fill=accent)


def render_summary_v2(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    teams = _team_summaries(data)
    if not teams:
        raise RuntimeError("Resumo ao vivo sem os três modelos estruturados.")

    round_value = _round_value(data)
    title = f"PARCIAIS AO VIVO • RODADA {round_value}"
    subtitle = "Desempenho atualizado dos três modelos SimonSports."
    image = _gradient_background(*RESULT_SIZE)
    _header_team(image, title, subtitle, _badge(data))
    draw = ImageDraw.Draw(image)

    y = 345
    panel_height = 445
    for index, item in enumerate(teams[:3]):
        model = _safe(item.get("tipo"), f"MODELO {index + 1}").upper()
        accent = MODEL_COLORS.get(model, CYAN)
        name = MODEL_NAMES.get(model, f"TIME {model}")
        box = (55, y, 1545, y + panel_height)

        _glow_outline(image, box, accent, radius=34, blur=16, alpha=52)
        _shadow_panel(
            image,
            box,
            radius=34,
            fill=PANEL,
            outline=accent,
            shadow_alpha=105,
            outline_width=3,
        )

        draw.text((100, y + 34), name, font=_font(51, "bold", True), fill=WHITE)
        pill = (1165, y + 28, 1490, y + 94)
        _round(draw, pill, 26, fill=accent)
        _centered_text(draw, pill, "PARCIAL ATUAL", _font(22, "bold", True), fill=(4, 17, 30))

        sem_cap = _num(item.get("pontos_sem_capitao"))
        com_cap = _num(item.get("pontos_com_capitao"))
        valorizacao = _num(item.get("valorizacao"))
        participacao = _int(item.get("participacao"))
        total = _int(item.get("total"), 12) or 12

        _metric(draw, 100, y + 140, "PONTOS SEM CAPITÃO", f"{sem_cap:.2f} pts", WHITE, 385)
        _metric(draw, 575, y + 140, "PONTOS COM CAPITÃO", f"{com_cap:.2f} pts", accent, 400)
        _metric(draw, 1090, y + 140, "VALORIZAÇÃO", f"C$ {valorizacao:.2f}", YELLOW, 365)

        progress_y = y + 312
        draw.line((100, progress_y - 22, 1490, progress_y - 22), fill=LINE, width=2)
        draw.text((100, progress_y), "PARTICIPAÇÃO DOS ATLETAS", font=_font(27, "bold", True), fill=SILVER)

        count_text = f"{participacao}/{total}"
        count_font = _font(34, "bold", True)
        count_box = draw.textbbox((0, 0), count_text, font=count_font)
        draw.text((1490 - (count_box[2] - count_box[0]), progress_y - 2), count_text, font=count_font, fill=WHITE)

        bar = (100, progress_y + 58, 1490, progress_y + 98)
        _round(draw, bar, 19, fill=(10, 30, 52), outline=LINE, width=2)
        ratio = max(0.0, min(1.0, participacao / max(1, total)))
        fill_box = (
            bar[0] + 4,
            bar[1] + 4,
            int(bar[0] + 4 + (bar[2] - bar[0] - 8) * ratio),
            bar[3] - 4,
        )
        if fill_box[2] > fill_box[0]:
            _round(draw, fill_box, 15, fill=accent)

        y += panel_height + 28

    _footer(image, 1888)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"live_parciais_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "summary_v2", title, f"Parciais ao Vivo • Rodada {round_value}")


def _ranking_items(data: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = data.get(key)
    if isinstance(value, list):
        normalized: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                normalized.append({"nome": item})
        if normalized:
            return normalized[:5]

    message = _safe(data.get("mensagem_oficial"))
    heading = "TOP 5 PONTUADORES" if key == "top_5" else "5 PIORES PONTUAÇÕES"
    lines = message.splitlines()
    capture = False
    parsed: List[Dict[str, Any]] = []
    for raw in lines:
        clean = _clean_markdown(raw)
        upper = clean.upper()
        if heading in upper:
            capture = True
            continue
        if capture and ("TOP 5" in upper or "PIORES" in upper) and heading not in upper:
            break
        if capture:
            match = re.match(r"^\d+[º°]?\s+(.+?):\s*(-?\d+(?:[.,]\d+)?)\s*PTS?", clean, re.I)
            if match:
                parsed.append({"nome": match.group(1), "pontos": _num(match.group(2))})
        if len(parsed) >= 5:
            break
    return parsed


def _ranking_name(item: Dict[str, Any]) -> str:
    return _safe(_value(item, "nome", "apelido", "jogador", "atleta"), "Atleta")


def _ranking_points(item: Dict[str, Any]) -> float:
    return _num(_value(item, "pontos", "pontuacao", "score", "pts", default=0))


def _draw_ranking_panel(
    image: Image.Image,
    box: Tuple[int, int, int, int],
    title: str,
    items: Sequence[Dict[str, Any]],
    accent: Tuple[int, int, int],
    positive: bool,
) -> None:
    draw = ImageDraw.Draw(image)
    _glow_outline(image, box, accent, radius=34, blur=17, alpha=50)
    _shadow_panel(
        image,
        box,
        radius=34,
        fill=PANEL,
        outline=accent,
        shadow_alpha=105,
        outline_width=3,
    )
    x1, y1, x2, y2 = box
    draw.text((x1 + 34, y1 + 30), title, font=_font(41, "bold", True), fill=accent)
    draw.line((x1 + 34, y1 + 92, x2 - 34, y1 + 92), fill=LINE, width=3)

    row_y = y1 + 120
    row_h = 236
    for rank, item in enumerate(list(items)[:5], start=1):
        row = (x1 + 25, row_y, x2 - 25, row_y + row_h - 18)
        _round(draw, row, 24, fill=PANEL_2, outline=LINE, width=2)

        medal_color = GOLD if rank == 1 else SILVER if rank == 2 else ORANGE if rank == 3 else LINE
        medal = (x1 + 48, row_y + 58, x1 + 130, row_y + 140)
        draw.ellipse(medal, fill=(9, 21, 38), outline=medal_color, width=4)
        _centered_text(draw, medal, str(rank), _font(36, "bold", True), fill=WHITE)

        name = _ranking_name(item).upper()
        name_font = _fit_text(draw, name, x2 - x1 - 245, 39, 23, "bold", True)
        draw.text((x1 + 155, row_y + 42), name, font=name_font, fill=WHITE)

        points = _ranking_points(item)
        points_color = accent if positive or points >= 0 else RED
        draw.text((x1 + 155, row_y + 106), "PONTUAÇÃO", font=_font(23, "semibold", True), fill=MUTED)
        draw.text((x1 + 155, row_y + 145), f"{points:.2f} pts", font=_font(43, "bold", True), fill=points_color)

        row_y += row_h
        if row_y + row_h > y2:
            break


def render_ranking_v2(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    top = _ranking_items(data, "top_5")
    worst = _ranking_items(data, "piores_5")
    if not top and not worst:
        raise RuntimeError("Ranking sem Top 5 ou piores pontuações estruturadas.")

    round_value = _round_value(data)
    title = f"MITOS E ZICAS • RODADA {round_value}"
    subtitle = "Maiores e menores pontuações parciais da rodada."
    image = _gradient_background(*RESULT_SIZE)
    _header_team(image, title, subtitle, _badge(data))

    _draw_ranking_panel(image, (45, 345, 780, 1815), "TOP 5 PONTUADORES", top, CYAN, True)
    _draw_ranking_panel(image, (820, 345, 1555, 1815), "5 PIORES PONTUAÇÕES", worst, RED, False)
    _footer(image, 1888)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"live_mitos_zicas_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "ranking_v2", title, f"Mitos e Zicas • Rodada {round_value}")


def render_live_publication_v2(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    kind = _kind_text(data)

    if _extract_matches(data) or any(token in kind for token in ("placar", "resultado", "partida", "live")):
        return render_results_v2(data, output_dir)

    if _team_summaries(data) or any(token in kind for token in ("resumo_geral", "time_delta", "abertura_dia")):
        return render_summary_v2(data, output_dir)

    if data.get("top_5") or data.get("piores_5") or any(token in kind for token in ("ranking", "mitos", "zicas")):
        return render_ranking_v2(data, output_dir)

    if any(token in kind for token in ("top5", "top 5", "time", "campinho", "escalacao", "econom", "intermedi", "pontua")):
        return render_legacy_publication(data, output_dir)

    message = _safe(data.get("mensagem_oficial"))
    message_upper = message.upper()
    if "MITOS E ZICAS" in message_upper:
        return render_ranking_v2(data, output_dir)
    if "RESULTADOS E RESUMOS" in message_upper or "ATUALIZAÇÃO DE PLACAR" in message_upper:
        return render_results_v2(data, output_dir)
    if "RESUMO GERAL" in message_upper:
        return render_summary_v2(data, output_dir)

    raise RuntimeError(
        "Tipo de publicação Live não reconhecido. "
        "Boletim genérico bloqueado para preservar o padrão visual aprovado."
    )
