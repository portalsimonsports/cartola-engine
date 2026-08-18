from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2


CANVAS = (1600, 2000)

CLUB_NAMES = {
    "FLA": "Flamengo", "PAL": "Palmeiras", "CRU": "Cruzeiro", "BAH": "Bahia",
    "BOT": "Botafogo", "SAO": "São Paulo", "SAO PAULO": "São Paulo",
    "CAP": "Athletico-PR", "ATH": "Athletico-PR", "INT": "Internacional",
    "CAM": "Atlético-MG", "FLU": "Fluminense", "CEA": "Ceará", "COR": "Corinthians",
    "GRE": "Grêmio", "VAS": "Vasco", "SAN": "Santos", "RBB": "Bragantino",
    "JUV": "Juventude", "FOR": "Fortaleza", "MIR": "Mirassol", "VIT": "Vitória",
    "SPT": "Sport", "CHA": "Chapecoense", "REM": "Remo", "CFC": "Coritiba",
}


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _club_name(value: Any) -> str:
    raw = _safe(value).upper()
    return CLUB_NAMES.get(raw, _safe(value))


def _background() -> Image.Image:
    image = v2._gradient_background(*CANVAS, stadium=False)
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for x in range(-600, 2200, 260):
        draw.line((x, 0, x + 920, 2000), fill=(255, 112, 0, 17), width=5)
    image.alpha_composite(layer)
    return image


def _header(image: Image.Image, subtitle: str, rodada: str) -> None:
    draw = ImageDraw.Draw(image)
    try:
        from render_telegram_cards import _logo_ps
        _logo_ps(image, (64, 34, 202, 165))
    except Exception:
        v2._round(draw, (64, 42, 185, 158), 24, fill=(8, 20, 35), outline=v2.ORANGE, width=3)
        v2._centered_text(draw, (64, 42, 185, 158), "PS", v2._font(46, "bold", True), fill=v2.WHITE)

    draw.text((225, 42), "PORTAL", font=v2._font(31, "bold", True), fill=v2.WHITE)
    draw.text((225, 81), "SIMON", font=v2._font(50, "bold", True), fill=v2.WHITE)
    draw.text((394, 81), "SPORTS", font=v2._font(50, "bold", True), fill=v2.ORANGE)
    draw.text((1235, 66), "BRASILEIRÃO", font=v2._font(36, "bold", True), fill=v2.WHITE)
    draw.text((1444, 66), "2026", font=v2._font(36, "bold", True), fill=v2.ORANGE)

    v2._centered_text(draw, (60, 190, 1540, 290), "CLASSIFICAÇÃO DO BRASILEIRÃO", v2._font(68, "bold", True), fill=v2.WHITE)
    v2._centered_text(draw, (60, 286, 1540, 344), "SÉRIE A", v2._font(40, "bold", True), fill=v2.ORANGE)

    if rodada:
        badge = (675, 355, 925, 418)
        v2._round(draw, badge, 24, fill=(7, 19, 34), outline=v2.ORANGE, width=3)
        v2._centered_text(draw, badge, f"RODADA {rodada}", v2._font(29, "bold", True), fill=v2.WHITE)

    info = (100, 438, 1500, 506)
    v2._round(draw, info, 22, fill=(218, 93, 0), outline=v2.ORANGE, width=2)
    v2._centered_text(draw, info, subtitle.upper(), v2._font(31, "bold", True), fill=(8, 13, 18))


def _variation(delta: Any) -> Tuple[str, Tuple[int, int, int]]:
    try:
        value = int(delta)
    except Exception:
        return "—", v2.MUTED
    if value > 0:
        return f"▲ +{value}", v2.GREEN
    if value < 0:
        return f"▼ {value}", v2.RED
    return "—", v2.MUTED


def _column(image: Image.Image, items: List[Dict[str, Any]], box: Tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    v2._shadow_panel(image, box, radius=25, fill=(5, 16, 29), outline=v2.ORANGE, shadow_alpha=85, outline_width=2)
    header_h = 58
    draw.rectangle((x1, y1, x2, y1 + header_h), fill=(218, 93, 0))
    draw.text((x1 + 18, y1 + 14), "POS.", font=v2._font(23, "bold", True), fill=v2.WHITE)
    draw.text((x1 + 92, y1 + 14), "VAR.", font=v2._font(23, "bold", True), fill=v2.WHITE)
    draw.text((x1 + 195, y1 + 14), "CLUBE", font=v2._font(23, "bold", True), fill=v2.WHITE)
    draw.text((x2 - 100, y1 + 14), "PTS", font=v2._font(23, "bold", True), fill=v2.WHITE)

    row_h = 111
    y = y1 + header_h
    for item in items:
        pos = int(item.get("pos") or 0)
        if y + row_h > y2:
            break
        fill = (8, 22, 38) if pos % 2 else (5, 18, 32)
        draw.rectangle((x1, y, x2, y + row_h), fill=fill)
        draw.line((x1, y + row_h, x2, y + row_h), fill=(45, 61, 75), width=2)
        pos_color = v2.GOLD if pos == 1 else v2.SILVER if pos == 2 else v2.ORANGE if pos == 3 else v2.WHITE
        draw.text((x1 + 22, y + 30), str(pos), font=v2._font(35, "bold", True), fill=pos_color)
        vt, vc = _variation(item.get("variacao"))
        draw.text((x1 + 90, y + 34), vt, font=v2._font(24, "bold", True), fill=vc)
        nome = _club_name(item.get("nome"))
        nf = v2._fit_text(draw, nome, x2 - x1 - 340, 31, 22, "bold", True)
        draw.text((x1 + 195, y + 22), nome, font=nf, fill=v2.WHITE)
        small = f"J {int(item.get('j') or 0)}  V {int(item.get('v') or 0)}  SG {int(item.get('saldo') or 0):+d}"
        draw.text((x1 + 195, y + 62), small, font=v2._font(20, "semibold", True), fill=v2.MUTED)
        pts = str(int(item.get("pts") or 0))
        pf = v2._font(39, "bold", True)
        pb = draw.textbbox((0, 0), pts, font=pf)
        draw.text((x2 - 42 - (pb[2] - pb[0]), y + 29), pts, font=pf, fill=v2.ORANGE)
        y += row_h


def render_classificacao_brasileirao(
    teams: List[Dict[str, Any]], output_dir: str, modo: str,
    atualizado_em: str, rodada: str = "",
) -> str:
    if not teams:
        raise RuntimeError("Classificação sem clubes para renderizar.")

    image = _background()
    if modo == "fechamento":
        subtitle = "Classificação final do dia"
        footer = "FECHAMENTO DO DIA"
    elif modo == "parcial_ao_vivo":
        subtitle = "Classificação parcial ao vivo"
        footer = "TABELA PARCIAL • AO VIVO"
    else:
        subtitle = "Classificação após os jogos"
        footer = "TABELA ATUALIZADA"
    _header(image, subtitle, rodada)

    _column(image, teams[:10], (55, 545, 785, 1715))
    _column(image, teams[10:20], (815, 545, 1545, 1715))

    draw = ImageDraw.Draw(image)
    draw.line((64, 1810, 1536, 1810), fill=(120, 62, 25), width=3)
    draw.text((64, 1842), f"ATUALIZAÇÃO: {atualizado_em}", font=v2._font(25, "bold", True), fill=v2.WHITE)
    ff = v2._font(27, "bold", True)
    fb = draw.textbbox((0, 0), footer, font=ff)
    draw.text((1536 - (fb[2] - fb[0]), 1840), footer, font=ff, fill=v2.ORANGE)
    draw.text((64, 1910), "@dicascartolaportalsimonsports", font=v2._font(21, "semibold", True), fill=v2.MUTED)
    brand = "PORTAL SIMONSPORTS"
    bf = v2._font(23, "bold", True)
    bb = draw.textbbox((0, 0), brand, font=bf)
    draw.text((1536 - (bb[2] - bb[0]), 1908), brand, font=bf, fill=v2.WHITE)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"classificacao_brasileirao_{modo}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return path
