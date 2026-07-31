from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
from render_telegram_cards import RenderOutput, _logo_ps

CANVAS = (1600, 2000)
VERSION = "desempenho_top5_v1_2026_07_31"


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def is_top5_performance_event(data: Dict[str, Any]) -> bool:
    joined = " ".join(
        norm(data.get(key))
        for key in ("evento_programado", "tipo_publicacao", "contexto", "titulo")
        if data.get(key)
    )
    return any(
        token in joined
        for token in (
            "FECHAMENTO_FINAL_TOP5",
            "DESEMPENHO_FINAL_TOP5",
            "DESEMPENHO_DO_TOP5",
            "TOP5_FINAL",
        )
    )


def round_value(data: Dict[str, Any]) -> str:
    value = data.get("rodada") or data.get("round") or "ATUAL"
    try:
        return str(int(float(value)))
    except Exception:
        return safe(value, "ATUAL")


def float_value(value: Any) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return 0.0


def extract_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = data.get("lista") or data.get("top5") or data.get("jogadores") or data.get("dados")
    if isinstance(candidates, dict):
        flattened: List[Dict[str, Any]] = []
        for position, items in candidates.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        copy = dict(item)
                        copy.setdefault("pos", position)
                        flattened.append(copy)
        candidates = flattened
    if not isinstance(candidates, list):
        raise RuntimeError("Desempenho final do Top 5 sem lista estruturada.")
    result = [item for item in candidates if isinstance(item, dict) and safe(item.get("nome"))]
    if not result:
        raise RuntimeError("Desempenho final do Top 5 sem jogadores válidos.")
    return result


def background() -> Image.Image:
    return v2._gradient_background(*CANVAS, stadium=False)


def header(image: Image.Image, round_number: str, page: int, pages: int) -> None:
    draw = ImageDraw.Draw(image)
    _logo_ps(image, (60, 30, 196, 160))
    draw.text((220, 42), "PORTAL SIMONSPORTS", font=v2._font(47, "bold", True), fill=v2.WHITE)
    draw.text((220, 105), "CARTOLA • DADOS • ANÁLISE", font=v2._font(22, "semibold", True), fill=v2.SILVER)
    badge = (1260, 45, 1530, 135)
    v2._round(draw, badge, 28, fill=(4, 18, 38), outline=v2.CYAN, width=3)
    v2._centered_text(draw, badge, f"RODADA {round_number}", v2._font(35, "bold", True), fill=v2.WHITE)
    title = "DESEMPENHO FINAL DO TOP 5"
    v2._centered_text(draw, (70, 185, 1530, 285), title, v2._font(65, "bold", True), fill=v2.WHITE)
    v2._centered_text(
        draw,
        (100, 275, 1500, 335),
        "Pontuação obtida pelos jogadores indicados em cada posição.",
        v2._font(28, "semibold", True),
        fill=v2.MUTED,
    )
    v2._centered_text(draw, (690, 1880, 910, 1940), f"{page}/{pages}", v2._font(28, "bold", True), fill=v2.MUTED)


def row(image: Image.Image, item: Dict[str, Any], box, rank: int) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    points = float_value(item.get("pontos") or item.get("pontuacao"))
    accent = v2.GREEN if points >= 8 else v2.ORANGE if points >= 4 else v2.RED
    v2._shadow_panel(image, box, radius=24, fill=(4, 16, 33), outline=accent, shadow_alpha=75, outline_width=2)
    rank_box = (x1 + 18, y1 + 18, x1 + 95, y2 - 18)
    v2._round(draw, rank_box, 20, fill=(7, 30, 55), outline=accent, width=2)
    v2._centered_text(draw, rank_box, str(rank), v2._font(31, "bold", True), fill=accent)

    position = safe(item.get("pos") or item.get("posicao"), "-").upper()
    club = safe(item.get("clube"), "-").upper()
    name = safe(item.get("nome"))
    draw.text((x1 + 125, y1 + 18), f"{position} • {club}", font=v2._font(22, "bold", True), fill=v2.CYAN)
    name_font = v2._fit_text(draw, name.upper(), 760, 39, 25, "bold", True)
    draw.text((x1 + 125, y1 + 57), name.upper(), font=name_font, fill=v2.WHITE)

    price = float_value(item.get("preco"))
    draw.text((x1 + 930, y1 + 28), f"C$ {price:.2f}", font=v2._font(28, "semibold", True), fill=v2.SILVER)
    points_box = (x2 - 300, y1 + 18, x2 - 20, y2 - 18)
    v2._round(draw, points_box, 22, fill=(8, 28, 49), outline=accent, width=3)
    v2._centered_text(draw, points_box, f"{points:.2f} pts", v2._font(42, "bold", True), fill=accent)


def render_top5_performance(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    players = extract_list(data)
    players.sort(key=lambda item: (safe(item.get("pos") or item.get("posicao")), -float_value(item.get("pontos") or item.get("pontuacao"))))
    round_number = round_value(data)
    per_page = 10
    pages = max(1, math.ceil(len(players) / per_page))
    files: List[str] = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for page_index in range(pages):
        image = background()
        header(image, round_number, page_index + 1, pages)
        chunk = players[page_index * per_page : (page_index + 1) * per_page]
        y = 365
        for local_index, item in enumerate(chunk, start=1):
            row(image, item, (65, y, 1535, y + 132), page_index * per_page + local_index)
            y += 145
        draw = ImageDraw.Draw(image)
        draw.line((65, 1845, 1535, 1845), fill=v2.LINE, width=3)
        draw.text((90, 1900), "@dicascartolaportalsimonsports", font=v2._font(25, "semibold", True), fill=v2.WHITE)
        brand = "PORTAL SIMONSPORTS"
        font = v2._font(30, "bold", True)
        bbox = draw.textbbox((0, 0), brand, font=font)
        draw.text((1510 - (bbox[2] - bbox[0]), 1894), brand, font=font, fill=v2.WHITE)
        path = str(Path(output_dir) / f"desempenho_final_top5_rodada_{round_number}_p{page_index + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    return RenderOutput(
        files,
        "desempenho_final_top5",
        f"Desempenho Final do Top 5 • Rodada {round_number}",
        f"Desempenho Final do Top 5 • Rodada {round_number}",
    )
