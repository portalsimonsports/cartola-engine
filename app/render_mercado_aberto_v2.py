from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
from render_aprovadas_v1 import (
    _background,
    _closing_text,
    _footer,
    _header,
    _remaining_minutes,
    _round_value,
    _safe,
    _value,
)
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "approved_market_open_v2_2026_07_28"
SUPPORTED_EVENTS = {"JOGOS_DA_RODADA", "LEMBRETE_MERCADO_6H"}


def _norm(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", _safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def event_name(data: Dict[str, Any]) -> str:
    values = [data.get(key) for key in ("evento_programado", "evento", "tipo_publicacao", "contexto", "titulo")]
    joined = " ".join(_norm(value) for value in values if value)
    if any(token in joined for token in ("JOGOS_DA_RODADA", "JOGOS_RODADA", "AGENDA_DA_RODADA")):
        return "JOGOS_DA_RODADA"
    if any(token in joined for token in ("LEMBRETE_MERCADO_6H", "LEMBRETE_DE_MERCADO", "LEMBRETE_MERCADO")):
        return "LEMBRETE_MERCADO_6H"
    return _norm(data.get("evento_programado"))


def is_market_open_v2_event(data: Dict[str, Any]) -> bool:
    return event_name(data) in SUPPORTED_EVENTS


def _countdown_parts(minutes: int) -> List[str]:
    days, rest = divmod(max(0, int(minutes)), 1440)
    hours, mins = divmod(rest, 60)
    return [f"{days}d", f"{hours:02d}h", f"{mins:02d}min"] if days else [f"{hours}h", f"{mins:02d}min"]


def render_lembrete_v2(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    parts = _countdown_parts(_remaining_minutes(data, 360))
    image = _background()
    _header(image, f"LEMBRETE DE MERCADO • RODADA {r}", "Tempo restante para o fechamento do mercado.", r)
    draw = ImageDraw.Draw(image)

    panel = (52, 370, 1548, 1310)
    v2._glow_outline(image, panel, v2.YELLOW, radius=42, blur=25, alpha=90)
    v2._shadow_panel(image, panel, radius=42, fill=(4, 14, 28), outline=v2.YELLOW, shadow_alpha=130, outline_width=4)
    bell = (690, 405, 910, 625)
    draw.ellipse(bell, outline=v2.YELLOW, width=8)
    v2._centered_text(draw, bell, "!", v2._font(120, "bold", True), fill=v2.YELLOW, y_offset=-10)

    sizes = [190, 155, 110] if len(parts) == 3 else [225, 130]
    fonts = [v2._font(size, "bold", True) for size in sizes]
    widths = [draw.textbbox((0, 0), part, font=font)[2] for part, font in zip(parts, fonts)]
    total = sum(widths) + 38 * (len(parts) - 1)
    x = (1600 - total) / 2
    base_y = 650 if len(parts) == 3 else 610
    offsets = [0, 42, 80] if len(parts) == 3 else [0, 80]
    for index, (part, font, width) in enumerate(zip(parts, fonts, widths)):
        draw.text((x, base_y + offsets[index]), part, font=font, fill=v2.YELLOW)
        x += width + 38

    v2._centered_text(draw, (180, 930, 1420, 1020), "TEMPO RESTANTE PARA O FECHAMENTO", v2._font(39, "bold", True), fill=v2.SILVER)
    date_box = (175, 1055, 1425, 1205)
    v2._round(draw, date_box, 30, fill=(6, 20, 35), outline=v2.YELLOW, width=3)
    limit_text = f"DATA LIMITE   {_closing_text(data)}"
    v2._centered_text(draw, date_box, limit_text, v2._fit_text(draw, limit_text, 1170, 54, 34, "bold", True), fill=v2.WHITE)

    lower = [
        (70, 1350, 780, 1710, "REVISE SUA ESCALAÇÃO", "Ajuste seu time e faça as melhores escolhas."),
        (820, 1350, 1530, 1710, "CONFIRA AS SELEÇÕES DO DIA", "Curadoria completa dos modelos SimonSports."),
    ]
    for x1, y1, x2, y2, title, subtitle in lower:
        v2._shadow_panel(image, (x1, y1, x2, y2), radius=32, fill=(4, 16, 32), outline=v2.CYAN, shadow_alpha=90, outline_width=3)
        v2._centered_text(draw, (x1 + 30, y1 + 45, x2 - 30, y1 + 150), title, v2._fit_text(draw, title, x2 - x1 - 60, 43, 28, "bold", True), fill=v2.BLUE)
        v2._centered_text(draw, (x1 + 45, y1 + 170, x2 - 45, y2 - 25), subtitle, v2._fit_text(draw, subtitle, x2 - x1 - 90, 31, 23, "semibold", True), fill=v2.SILVER)

    alert = (70, 1740, 1530, 1850)
    v2._round(draw, alert, 28, fill=(40, 25, 2), outline=v2.YELLOW, width=3)
    v2._centered_text(draw, alert, "ATENÇÃO: APROVEITE O TEMPO!", v2._font(45, "bold", True), fill=v2.YELLOW)
    _footer(image)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"aprovada_lembrete_mercado_rodada_{r}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "approved_lembrete_v2", f"Lembrete de Mercado • Rodada {r}", f"Lembrete de Mercado • Rodada {r}")


def _matches(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("jogos", "partidas", "matches", "agenda", "confrontos"):
        value = _value(data, key, default=None)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    payload = data.get("payload")
    return _matches(payload) if isinstance(payload, dict) else []


def _team(match: Dict[str, Any], home: bool) -> str:
    keys = ("mandante", "home", "time_casa", "casa", "equipe_mandante", "nome_mandante") if home else ("visitante", "away", "time_fora", "fora", "equipe_visitante", "nome_visitante")
    return _safe(_value(match, *keys, default="Mandante" if home else "Visitante"))


def _code(match: Dict[str, Any], home: bool) -> str:
    keys = ("mandante_abrev", "home_abbr", "sigla_mandante", "clube_mandante") if home else ("visitante_abrev", "away_abbr", "sigla_visitante", "clube_visitante")
    value = _safe(_value(match, *keys, default=""))
    if value:
        return value.upper()
    words = re.findall(r"[A-Za-zÀ-ÿ]+", _team(match, home))
    return ("".join(word[0] for word in words[:3]) if len(words) > 1 else _team(match, home)[:3]).upper()


def _datetime(match: Dict[str, Any]) -> str:
    combined = _safe(_value(match, "data_hora", "partida_data", "inicio", default=""))
    if combined:
        return combined[:16].replace("T", " • ") if "T" in combined else combined[:16]
    date = _safe(_value(match, "data", "data_jogo", default=""))
    time = _safe(_value(match, "hora", "horario", "hora_jogo", default=""))
    return " • ".join(part for part in (date, time) if part) or "A confirmar"


def _draw_match(image: Image.Image, match: Dict[str, Any], box: Tuple[int, int, int, int], index: int) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    v2._glow_outline(image, box, v2.CYAN, radius=28, blur=13, alpha=42)
    v2._shadow_panel(image, box, radius=28, fill=(4, 15, 30), outline=v2.CYAN, shadow_alpha=100, outline_width=3)

    tag = (x1 + 20, y1 + 18, x1 + 205, y1 + 75)
    v2._round(draw, tag, 18, fill=(5, 36, 67), outline=v2.BLUE, width=2)
    v2._centered_text(draw, tag, f"JOGO {index:02d}", v2._font(22, "bold", True), fill=v2.CYAN)
    dt = _datetime(match)
    draw.text((x1 + 230, y1 + 30), dt, font=v2._fit_text(draw, dt, x2 - x1 - 260, 29, 20, "bold", True), fill=v2.WHITE)
    draw.line((x1 + 20, y1 + 92, x2 - 20, y1 + 92), fill=(28, 105, 155), width=2)

    home, away = _team(match, True).upper(), _team(match, False).upper()
    v2._paste_crest(image, _code(match, True), (x1 + 105, y1 + 208), 112)
    v2._paste_crest(image, _code(match, False), (x2 - 105, y1 + 208), 112)
    v2._centered_text(draw, (x1 + 175, y1 + 125, x1 + 405, y1 + 255), home, v2._fit_text(draw, home, 230, 34, 22, "bold", True), fill=v2.WHITE)
    v2._centered_text(draw, (x2 - 405, y1 + 125, x2 - 175, y1 + 255), away, v2._fit_text(draw, away, 230, 34, 22, "bold", True), fill=v2.WHITE)
    v2._centered_text(draw, ((x1 + x2) // 2 - 55, y1 + 130, (x1 + x2) // 2 + 55, y1 + 255), "X", v2._font(62, "bold", True), fill=v2.CYAN)

    stadium = "▤  " + _safe(_value(match, "estadio", "estádio", "local", "arena", default="LOCAL A CONFIRMAR")).upper()
    stadium_box = (x1 + 35, y2 - 92, x2 - 35, y2 - 25)
    v2._round(draw, stadium_box, 18, fill=(5, 21, 38), outline=(34, 93, 132), width=2)
    v2._centered_text(draw, stadium_box, stadium, v2._fit_text(draw, stadium, x2 - x1 - 100, 27, 19, "semibold", True), fill=v2.MUTED)


def render_jogos_da_rodada(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = _matches(data)
    if not matches:
        raise RuntimeError("JOGOS_DA_RODADA sem partidas estruturadas.")
    r = _round_value(data)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    pages = max(1, math.ceil(len(matches) / 6))
    files: List[str] = []

    for page in range(pages):
        image = _background()
        _header(image, f"JOGOS DA RODADA • RODADA {r}", "Confira os confrontos programados da rodada.", r)
        for local_index, match in enumerate(matches[page * 6:(page + 1) * 6]):
            row, col = divmod(local_index, 2)
            x1 = 55 + col * 762
            y1 = 350 + row * 430
            _draw_match(image, match, (x1, y1, x1 + 728, y1 + 405), page * 6 + local_index + 1)

        ribbon = (70, 1648, 1530, 1818)
        draw = ImageDraw.Draw(image)
        v2._glow_outline(image, ribbon, v2.BLUE, radius=30, blur=14, alpha=55)
        v2._round(draw, ribbon, 30, fill=(4, 22, 45), outline=v2.BLUE, width=3)
        text = "ABERTURA DA RODADA • TODOS OS JOGOS PROGRAMADOS"
        v2._centered_text(draw, ribbon, text, v2._fit_text(draw, text, 1350, 48, 30, "bold", True), fill=v2.WHITE)
        _footer(image, (page + 1, pages) if pages > 1 else None)

        path = str(Path(output_dir) / f"aprovada_jogos_da_rodada_{r}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    return RenderOutput(files, "approved_jogos_da_rodada", f"Jogos da Rodada • Rodada {r}", f"Jogos da Rodada • Rodada {r}")


def render_market_open_v2(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    event = event_name(data)
    if event == "JOGOS_DA_RODADA":
        return render_jogos_da_rodada(data, output_dir)
    if event == "LEMBRETE_MERCADO_6H":
        return render_lembrete_v2(data, output_dir)
    raise RuntimeError(f"Evento de mercado aberto V2 não suportado: {event!r}")
