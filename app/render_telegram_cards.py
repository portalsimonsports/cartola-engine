from __future__ import annotations

import io
import math
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOP5_SIZE = (1600, 2000)
TEAM_SIZE = (1600, 2000)
RESULT_SIZE = (1600, 2000)

NAVY = (3, 10, 24)
NAVY_2 = (5, 22, 48)
PANEL = (5, 15, 31)
PANEL_2 = (8, 24, 45)
PANEL_3 = (12, 32, 55)
WHITE = (246, 249, 252)
MUTED = (171, 183, 197)
LINE = (42, 94, 143)
CYAN = (24, 207, 255)
BLUE = (26, 103, 235)
ORANGE = (255, 159, 15)
GREEN = (36, 180, 91)
YELLOW = (255, 201, 54)
RED = (244, 47, 61)
PURPLE = (159, 72, 231)
SILVER = (210, 216, 225)
GOLD = (221, 177, 73)

POSITION_COLORS = {
    "GOL": ORANGE,
    "LAT": CYAN,
    "ZAG": BLUE,
    "MEI": PURPLE,
    "ATA": RED,
    "TEC": SILVER,
}
POSITION_LABELS = {
    "GOL": "GOLEIROS",
    "LAT": "LATERAIS",
    "ZAG": "ZAGUEIROS",
    "MEI": "MEIAS",
    "ATA": "ATACANTES",
    "TEC": "TÉCNICOS",
}

CLUB_STYLES: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], str]] = {
    "FLA": ((198, 24, 35), (20, 20, 22), "horizontal"),
    "CAP": ((203, 29, 46), (20, 20, 22), "diagonal"),
    "COR": ((239, 239, 235), (30, 30, 30), "solid"),
    "CAM": ((26, 26, 27), (235, 235, 230), "vertical"),
    "CRU": ((26, 82, 183), (240, 240, 245), "solid"),
    "PAL": ((25, 111, 66), (238, 242, 235), "solid"),
    "INT": ((204, 29, 42), (245, 245, 245), "solid"),
    "CFC": ((26, 103, 62), (238, 242, 235), "horizontal"),
    "BAH": ((32, 93, 177), (217, 33, 46), "vertical"),
    "REM": ((24, 50, 110), (240, 240, 245), "solid"),
    "CHA": ((18, 117, 62), (238, 242, 235), "vertical"),
    "SAN": ((242, 242, 240), (25, 25, 25), "vertical"),
    "GRE": ((39, 133, 198), (19, 32, 48), "vertical"),
    "BOT": ((27, 27, 28), (238, 238, 238), "vertical"),
    "VAS": ((24, 24, 25), (238, 238, 238), "diagonal"),
    "SAO": ((240, 240, 238), (214, 30, 45), "horizontal"),
    "FOR": ((35, 67, 170), (218, 35, 48), "horizontal"),
}

CREST_URL = (
    "https://s3.glbimg.com/v1/AUTH_58d78b787ec34892b5aaa0c7a146155f/"
    "clubes_2026/escudos/{club}/60x60.png"
)
CREST_CACHE = Path(os.getenv("CARTOLA_CREST_CACHE", "/tmp/cartola_crest_cache"))
_CREST_NETWORK_DISABLED = False


@dataclass
class RenderOutput:
    files: List[str]
    kind: str
    title: str
    caption: str


def _font(size: int, weight: str = "regular", condensed: bool = False) -> ImageFont.FreeTypeFont:
    candidates: List[str] = []
    if condensed and weight in ("bold", "semibold"):
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSansNarrow-Bold.ttf",
        ])
    if weight == "bold":
        candidates.extend([
            "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    elif weight == "semibold":
        candidates.extend([
            "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _value(item: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
        upper = key.upper()
        if upper in item and item.get(upper) not in (None, ""):
            return item.get(upper)
    return default


def _clean_markdown(value: Any) -> str:
    text = _safe(value)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _money(value: Any) -> str:
    try:
        return f"C$ {float(str(value).replace(',', '.')):.2f}"
    except Exception:
        return "C$ --"


def _points(value: Any) -> str:
    try:
        return f"{float(str(value).replace(',', '.')):.2f} pts"
    except Exception:
        return "-- pts"


def _normalize_pos(value: Any) -> str:
    text = _safe(value).upper()
    aliases = {
        "GOLEIRO": "GOL", "G": "GOL",
        "LATERAL": "LAT", "L": "LAT",
        "ZAGUEIRO": "ZAG", "Z": "ZAG",
        "MEIA": "MEI", "M": "MEI",
        "ATACANTE": "ATA", "A": "ATA",
        "TECNICO": "TEC", "TÉCNICO": "TEC", "T": "TEC",
    }
    return aliases.get(text, text[:3])


def _round(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 16, weight: str = "semibold", condensed: bool = False) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > min_size:
        font = _font(size, weight, condensed)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, weight, condensed)


def _centered_text(draw: ImageDraw.ImageDraw, box, text: str, font, fill=WHITE, y_offset=0):
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((x1 + x2 - (bbox[2] - bbox[0])) / 2, (y1 + y2 - (bbox[3] - bbox[1])) / 2 + y_offset),
        text,
        font=font,
        fill=fill,
    )


def _gradient_background(width: int, height: int, *, stadium: bool = True) -> Image.Image:
    base = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(NAVY[i] * (1 - t) + NAVY_2[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(0, 0), (230, 0), (700, height), (520, height)], fill=(24, 100, 255, 25))
    od.polygon([(width - 230, 0), (width, 0), (width - 520, height), (width - 700, height)], fill=(24, 100, 255, 22))
    od.ellipse((width * 0.45, -height * 0.20, width * 1.20, height * 0.42), fill=(16, 176, 255, 26))
    overlay = overlay.filter(ImageFilter.GaussianBlur(95))
    base = Image.alpha_composite(base.convert("RGBA"), overlay)

    if stadium:
        lights = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lights)
        for side in (0, 1):
            origin_x = 88 if side == 0 else width - 88
            direction = 1 if side == 0 else -1
            for row in range(3):
                for col in range(8):
                    x = origin_x + direction * col * 28
                    y = 245 + row * 28 + col * 2
                    ld.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(215, 244, 255, 220))
            ld.polygon([
                (origin_x, 235),
                (origin_x + direction * 245, 285),
                (origin_x + direction * 520, 610),
                (origin_x + direction * 60, 355),
            ], fill=(64, 164, 255, 20))
        lights = lights.filter(ImageFilter.GaussianBlur(13))
        base = Image.alpha_composite(base, lights)
    return base


def _shadow_panel(image: Image.Image, box, radius=28, fill=PANEL, outline=LINE, shadow_alpha=110, outline_width=2):
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 12, y1 + 16, x2 + 12, y2 + 16), radius=radius, fill=(0, 0, 0, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=outline_width)


def _glow_outline(image: Image.Image, box, color, radius=28, blur=18, alpha=95, width=7):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=radius, outline=tuple(color) + (alpha,), width=width)
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _load_crest(club: str, size: int) -> Optional[Image.Image]:
    global _CREST_NETWORK_DISABLED
    code = _safe(club).upper()
    if not code:
        return None
    try:
        CREST_CACHE.mkdir(parents=True, exist_ok=True)
        cache = CREST_CACHE / f"{code}.png"
        if cache.exists() and cache.stat().st_size > 100:
            crest = Image.open(cache).convert("RGBA")
        elif not _CREST_NETWORK_DISABLED:
            try:
                response = requests.get(CREST_URL.format(club=code), timeout=(2, 5))
            except requests.RequestException:
                _CREST_NETWORK_DISABLED = True
                return None
            if not response.ok:
                return None
            cache.write_bytes(response.content)
            crest = Image.open(io.BytesIO(response.content)).convert("RGBA")
        else:
            return None
        crest.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(crest, ((size - crest.width) // 2, (size - crest.height) // 2))
        return canvas
    except Exception:
        return None


def _paste_crest(image: Image.Image, club: str, center: Tuple[int, int], size: int, fallback_color=(31, 89, 138)):
    crest = _load_crest(club, size)
    x, y = center
    if crest:
        image.alpha_composite(crest, (x - size // 2, y - size // 2))
        return
    draw = ImageDraw.Draw(image)
    radius = size // 2
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fallback_color, outline=WHITE, width=3)
    font = _font(max(14, size // 4), "bold", True)
    _centered_text(draw, (x - radius, y - radius, x + radius, y + radius), _safe(club, "--")[:3].upper(), font)


def _logo_ps(image: Image.Image, box):
    draw = ImageDraw.Draw(image)
    _glow_outline(image, box, CYAN, radius=28, blur=15, alpha=110)
    _round(draw, box, 28, fill=(2, 15, 30), outline=(40, 164, 235), width=3)
    x1, y1, _, _ = box
    for offset in range(0, 5):
        color = tuple(min(255, 180 + offset * 14) for _ in range(3))
        draw.text((x1 + 24 + offset, y1 + 13 + offset), "PS", font=_font(58, "bold", True), fill=color)


def _header_team(image: Image.Image, title: str, subtitle: str, badge: str):
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    _logo_ps(image, (66, 32, 196, 150))
    draw.text((225, 36), "PORTAL", font=_font(31, "bold", True), fill=WHITE)
    draw.text((225, 72), "SIMON", font=_font(49, "bold", True), fill=WHITE)
    draw.text((395, 72), "SPORTS", font=_font(49, "bold", True), fill=BLUE)
    draw.text((226, 128), "CARTOLA • DADOS • ANÁLISE", font=_font(20, "semibold"), fill=SILVER)
    badge_box = (1240, 38, 1530, 130)
    _glow_outline(image, badge_box, CYAN, radius=30, blur=14, alpha=75)
    _round(draw, badge_box, 30, fill=(4, 17, 35), outline=(71, 187, 244), width=3)
    _centered_text(draw, badge_box, badge, _font(38, "bold", True), fill=WHITE, y_offset=-3)
    title_font = _fit_text(draw, title, 1480, 73, 52, "bold", True)
    if "•" in title:
        prefix, suffix = [part.strip() for part in title.split("•", 1)]
        left_text = prefix + " • "
        left_box = draw.textbbox((0, 0), left_text, font=title_font)
        right_box = draw.textbbox((0, 0), suffix, font=title_font)
        total_width = (left_box[2] - left_box[0]) + (right_box[2] - right_box[0])
        x0 = (width - total_width) / 2
        draw.text((x0, 172), left_text, font=title_font, fill=WHITE)
        draw.text((x0 + (left_box[2] - left_box[0]), 172), suffix, font=title_font, fill=BLUE)
    else:
        bbox = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, 172), title, font=title_font, fill=WHITE)
    subtitle_font = _font(27, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    draw.text(((width - (sb[2] - sb[0])) / 2, 252), subtitle, font=subtitle_font, fill=MUTED)


def _header_top5(image: Image.Image, badge: str, subtitle: str):
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    _logo_ps(image, (640, 25, 780, 155))
    draw.text((815, 37), "PORTAL", font=_font(29, "bold", True), fill=WHITE)
    draw.text((815, 76), "SIMON", font=_font(44, "bold", True), fill=WHITE)
    draw.text((960, 76), "SPORTS", font=_font(44, "bold", True), fill=CYAN)
    draw.text((816, 130), "CARTOLA • DADOS • ANÁLISE", font=_font(18, "semibold"), fill=SILVER)
    badge_box = (1260, 38, 1532, 128)
    _glow_outline(image, badge_box, CYAN, radius=28, blur=14, alpha=80)
    _round(draw, badge_box, 28, fill=(4, 18, 36), outline=CYAN, width=3)
    _centered_text(draw, badge_box, badge, _font(38, "bold", True), fill=WHITE)
    title = "TOP 5 DA RODADA"
    title_font = _font(104, "bold", True)
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (tb[2] - tb[0])) / 2, 170), title, font=title_font, fill=WHITE)
    sub_font = _font(31, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=sub_font)
    draw.text(((width - (sb[2] - sb[0])) / 2, 292), subtitle, font=sub_font, fill=CYAN)


def _footer(image: Image.Image, y: int, page: Optional[Tuple[int, int]] = None):
    draw = ImageDraw.Draw(image)
    width, _ = image.size
    draw.line((66, y, width - 66, y), fill=(32, 91, 142), width=3)
    draw.ellipse((66, y + 18, 116, y + 68), fill=(28, 163, 227))
    _centered_text(draw, (66, y + 18, 116, y + 68), "➤", _font(26, "bold"), fill=WHITE)
    draw.text((132, y + 24), "@dicascartolaportalsimonsports", font=_font(24, "semibold", True), fill=WHITE)
    brand = "PORTAL SIMONSPORTS"
    bf = _font(31, "bold", True)
    bb = draw.textbbox((0, 0), brand, font=bf)
    draw.text((width - 66 - (bb[2] - bb[0]), y + 17), brand, font=bf, fill=WHITE)
    if page:
        pf = _font(22, "bold")
        text = f"{page[0]}/{page[1]}"
        pb = draw.textbbox((0, 0), text, font=pf)
        draw.text(((width - (pb[2] - pb[0])) / 2, y + 28), text, font=pf, fill=MUTED)


def _title_round(data: Dict[str, Any], default_title: str):
    round_value = _safe(data.get("rodada") or data.get("rodada_atual"))
    title = _clean_markdown(data.get("titulo") or default_title)
    blocks = data.get("blocos_topo") or []
    subtitle = _clean_markdown(blocks[0]) if isinstance(blocks, list) and blocks else ""
    subtitle = subtitle or _clean_markdown(data.get("status") or data.get("status_mercado"))
    subtitle = subtitle or "Seleção oficial atualizada pelo Portal SimonSports."
    badge = f"RODADA {round_value}" if round_value else "CARTOLA"
    return title or default_title, subtitle, badge, round_value or "atual"


def _top5_groups(items: Sequence[Dict[str, Any]]):
    groups = {key: [] for key in POSITION_LABELS}
    for item in items:
        if not isinstance(item, dict):
            continue
        pos = _normalize_pos(_value(item, "pos", "posicao"))
        if pos in groups:
            groups[pos].append(item)
    for pos in groups:
        groups[pos] = groups[pos][:5]
    return groups


def _draw_medal(draw: ImageDraw.ImageDraw, center: Tuple[int, int], rank: int):
    colors = {1: (255, 194, 30), 2: (205, 211, 219), 3: (191, 112, 52)}
    color = colors.get(rank, (50, 56, 66))
    x, y = center
    draw.ellipse((x - 29, y - 29, x + 29, y + 29), fill=(16, 17, 22), outline=color, width=5)
    _centered_text(draw, (x - 29, y - 29, x + 29, y + 29), str(rank), _font(25, "bold", True), fill=WHITE, y_offset=-2)


def _draw_position_icon(draw: ImageDraw.ImageDraw, center: Tuple[int, int], pos: str, color):
    x, y = center
    draw.rounded_rectangle((x - 46, y - 45, x + 46, y + 45), radius=20, fill=(7, 19, 36), outline=color, width=4)
    if pos == "GOL":
        draw.rectangle((x - 20, y - 18, x + 20, y + 24), outline=color, width=5)
        draw.line((x - 18, y + 2, x + 18, y + 2), fill=color, width=4)
    elif pos == "LAT":
        draw.polygon([(x - 22, y + 20), (x + 25, y - 23), (x + 8, y + 25)], fill=color)
    elif pos == "ZAG":
        draw.polygon([(x, y - 28), (x + 27, y - 12), (x + 20, y + 23), (x, y + 35), (x - 20, y + 23), (x - 27, y - 12)], outline=color, fill=(6, 22, 41))
    elif pos == "MEI":
        draw.ellipse((x - 24, y - 24, x + 24, y + 24), outline=color, width=5)
        draw.line((x - 17, y - 17, x + 17, y + 17), fill=color, width=3)
        draw.line((x + 17, y - 17, x - 17, y + 17), fill=color, width=3)
    elif pos == "ATA":
        draw.ellipse((x - 26, y - 26, x + 26, y + 26), outline=color, width=4)
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color)
        draw.line((x - 34, y, x + 34, y), fill=color, width=3)
        draw.line((x, y - 34, x, y + 34), fill=color, width=3)
    else:
        draw.rectangle((x - 21, y - 27, x + 21, y + 27), outline=color, width=4)
        draw.line((x - 10, y - 5, x + 10, y - 5), fill=color, width=3)


def _draw_top5_block(image: Image.Image, box, pos: str, items: Sequence[Dict[str, Any]]):
    accent = POSITION_COLORS[pos]
    _glow_outline(image, box, accent, radius=30, blur=19, alpha=75, width=8)
    _shadow_panel(image, box, radius=30, fill=(4, 11, 23), outline=accent, shadow_alpha=130, outline_width=3)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, _ = box
    header_h = 95
    _round(draw, (x1, y1, x2, y1 + header_h), 30, fill=(8, 18, 34))
    draw.rectangle((x1, y1 + 54, x2, y1 + header_h), fill=(8, 18, 34))
    _draw_position_icon(draw, (x1 + 68, y1 + 48), pos, accent)
    draw.text((x1 + 130, y1 + 20), POSITION_LABELS[pos], font=_font(46, "bold", True), fill=accent)

    row_h = 68
    row_y = y1 + 104
    for rank in range(1, 6):
        yy = row_y + (rank - 1) * row_h
        if rank < 5:
            draw.line((x1 + 18, yy + row_h - 2, x2 - 18, yy + row_h - 2), fill=accent, width=2)
        item = items[rank - 1] if rank - 1 < len(items) else None
        _draw_medal(draw, (x1 + 48, yy + 32), rank)
        if not item:
            draw.text((x1 + 100, yy + 12), "Sem dado", font=_font(29, "semibold", True), fill=MUTED)
            continue
        club = _safe(_value(item, "clube"), "--").upper()
        _paste_crest(image, club, (x1 + 112, yy + 32), 52, fallback_color=(16, 49, 78))
        name = _safe(_value(item, "nome"), "Jogador")
        display = f"{name} ({club})"
        name_font = _fit_text(draw, display, 410, 31, 22, "bold", True)
        draw.text((x1 + 153, yy + 10), display, font=name_font, fill=WHITE)
        price = _money(_value(item, "preco", "preco_num"))
        pf = _font(29, "bold", True)
        pb = draw.textbbox((0, 0), price, font=pf)
        draw.text((x2 - 28 - (pb[2] - pb[0]), yy + 11), price, font=pf, fill=accent)


def render_top5(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    items = data.get("lista") or data.get("jogadores") or data.get("dados") or []
    groups = _top5_groups(items if isinstance(items, list) else [])
    _, subtitle, badge, round_value = _title_round(data, "TOP 5 DA RODADA")
    width, height = TOP5_SIZE
    image = _gradient_background(width, height, stadium=True)
    _header_top5(image, badge, subtitle)

    margin = 58
    gap_x = 26
    gap_y = 26
    top = 355
    footer_y = 1908
    block_w = (width - 2 * margin - gap_x) // 2
    block_h = (footer_y - top - 2 * gap_y) // 3
    order = ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]
    for index, pos in enumerate(order):
        row, col = divmod(index, 2)
        x1 = margin + col * (block_w + gap_x)
        y1 = top + row * (block_h + gap_y)
        _draw_top5_block(image, (x1, y1, x1 + block_w, y1 + block_h), pos, groups[pos])

    _footer(image, footer_y)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"top5_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "top5", "TOP 5 DA RODADA", f"Top 5 da Rodada {round_value}")


def _extract_team_players(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("jogadores", "time", "escalacao", "lista", "atletas", "dados"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    return []


def _club_style(club: str):
    return CLUB_STYLES.get(_safe(club).upper(), ((36, 104, 180), (238, 240, 244), "solid"))


def _draw_jersey(image: Image.Image, center: Tuple[int, int], club: str, width: int, height: int):
    x, y = center
    primary, secondary, pattern = _club_style(club)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top = x - width // 2, y - height // 2
    shirt = [
        (left + width * 0.20, top + height * 0.10),
        (left + width * 0.36, top),
        (left + width * 0.64, top),
        (left + width * 0.80, top + height * 0.10),
        (left + width, top + height * 0.30),
        (left + width * 0.84, top + height * 0.52),
        (left + width * 0.73, top + height * 0.44),
        (left + width * 0.73, top + height),
        (left + width * 0.27, top + height),
        (left + width * 0.27, top + height * 0.44),
        (left + width * 0.16, top + height * 0.52),
        (left, top + height * 0.30),
    ]
    draw.polygon(shirt, fill=primary, outline=(240, 240, 240, 230))

    mask = Image.new("L", image.size, 0)
    md = ImageDraw.Draw(mask)
    md.polygon(shirt, fill=255)
    pattern_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pattern_layer)
    if pattern == "horizontal":
        for i in range(5):
            y1 = int(top + height * (0.18 + i * 0.16))
            pd.rectangle((left, y1, left + width, y1 + max(8, height // 12)), fill=secondary + (255,))
    elif pattern == "vertical":
        for i in range(4):
            x1 = int(left + width * (0.18 + i * 0.20))
            pd.rectangle((x1, top, x1 + max(9, width // 10), top + height), fill=secondary + (255,))
    elif pattern == "diagonal":
        pd.polygon([(left, top + height * 0.25), (left + width * 0.16, top), (left + width, top + height * 0.75), (left + width * 0.84, top + height)], fill=secondary + (255,))
    else:
        pd.rectangle((left + width * 0.46, top, left + width * 0.54, top + height), fill=secondary + (100,))
    pattern_layer.putalpha(Image.composite(pattern_layer.getchannel("A"), Image.new("L", image.size, 0), mask))
    layer = Image.alpha_composite(layer, pattern_layer)

    shadow = layer.filter(ImageFilter.GaussianBlur(9))
    image.alpha_composite(shadow, (5, 8))
    image.alpha_composite(layer)
    _paste_crest(image, club, (int(x + width * 0.22), int(y - height * 0.04)), max(36, width // 3))


def _field_polygon(image: Image.Image, box, accent):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    top_inset = 115
    points = [(x1 + top_inset, y1), (x2 - top_inset, y1), (x2, y2), (x1, y2)]
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.polygon(points, outline=tuple(accent) + (95,), width=13)
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))
    draw.polygon(points, fill=(15, 102, 48), outline=(210, 235, 205), width=5)
    for i in range(11):
        y_start = y1 + int((y2 - y1) * i / 11)
        y_end = y1 + int((y2 - y1) * (i + 1) / 11)
        color = (20, 126, 58) if i % 2 == 0 else (16, 112, 51)
        ratio1 = (y_start - y1) / (y2 - y1)
        ratio2 = (y_end - y1) / (y2 - y1)
        l1 = x1 + top_inset * (1 - ratio1)
        r1 = x2 - top_inset * (1 - ratio1)
        l2 = x1 + top_inset * (1 - ratio2)
        r2 = x2 - top_inset * (1 - ratio2)
        draw.polygon([(l1, y_start), (r1, y_start), (r2, y_end), (l2, y_end)], fill=color)
    draw.line(points + [points[0]], fill=(224, 244, 220), width=5)
    mid = (y1 + y2) // 2
    ratio = (mid - y1) / (y2 - y1)
    left = x1 + top_inset * (1 - ratio)
    right = x2 - top_inset * (1 - ratio)
    draw.line((left, mid, right, mid), fill=(224, 244, 220), width=4)
    cx = (x1 + x2) // 2
    draw.ellipse((cx - 85, mid - 85, cx + 85, mid + 85), outline=(224, 244, 220), width=4)
    draw.ellipse((cx - 6, mid - 6, cx + 6, mid + 6), fill=(224, 244, 220))
    draw.polygon([(cx - 240, y1), (cx + 240, y1), (cx + 285, y1 + 150), (cx - 285, y1 + 150)], outline=(224, 244, 220))
    draw.polygon([(cx - 285, y2 - 155), (cx + 285, y2 - 155), (cx + 240, y2), (cx - 240, y2)], outline=(224, 244, 220))


def _field_bounds(box, y: int) -> Tuple[int, int]:
    x1, y1, x2, y2 = box
    top_inset = 115
    ratio = max(0.0, min(1.0, (y - y1) / max(1, y2 - y1)))
    left = int(x1 + top_inset * (1 - ratio))
    right = int(x2 - top_inset * (1 - ratio))
    return left, right


def _line_positions(count: int, y: int, box, padding: int = 145) -> List[Tuple[int, int]]:
    if count <= 0:
        return []
    left, right = _field_bounds(box, y)
    left += padding
    right -= padding
    if count == 1:
        return [((left + right) // 2, y)]
    step = (right - left) / (count - 1)
    return [(int(left + index * step), y) for index in range(count)]


def _player_card(image: Image.Image, x: int, y: int, player: Dict[str, Any], pos: str, captain: bool = False):
    draw = ImageDraw.Draw(image)
    club = _safe(_value(player, "clube"), "--").upper()
    card_w, card_h = 250, 220
    box = (x - card_w // 2, y - card_h // 2, x + card_w // 2, y + card_h // 2)
    _glow_outline(image, box, GOLD, radius=27, blur=14, alpha=48, width=6)
    _shadow_panel(image, box, radius=27, fill=(4, 12, 25), outline=GOLD, shadow_alpha=145, outline_width=3)
    draw = ImageDraw.Draw(image)
    _round(draw, (box[0] + 7, box[1] + 7, box[2] - 7, box[1] + 132), 22, fill=(8, 19, 33))
    _draw_jersey(image, (x, box[1] + 72), club, 160, 125)
    if captain:
        cbox = (box[2] - 58, box[1] - 18, box[2] - 3, box[1] + 37)
        _glow_outline(image, cbox, YELLOW, radius=25, blur=10, alpha=90)
        draw.ellipse(cbox, fill=YELLOW, outline=(255, 240, 180), width=3)
        _centered_text(draw, cbox, "C", _font(28, "bold", True), fill=(30, 24, 10), y_offset=-2)
    name = _safe(_value(player, "nome"), "Jogador").upper()
    nf = _fit_text(draw, name, card_w - 24, 31, 20, "bold", True)
    nb = draw.textbbox((0, 0), name, font=nf)
    draw.text((x - (nb[2] - nb[0]) / 2, box[1] + 137), name, font=nf, fill=WHITE)
    price = _money(_value(player, "preco", "preco_num"))
    pf = _font(25, "bold", True)
    pb = draw.textbbox((0, 0), price, font=pf)
    draw.text((x - (pb[2] - pb[0]) / 2, box[1] + 177), price, font=pf, fill=YELLOW)


def _reserve_card(image: Image.Image, box, player: Dict[str, Any]):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, _ = box
    pos = _normalize_pos(_value(player, "pos", "posicao"))
    club = _safe(_value(player, "clube"), "--").upper()
    _shadow_panel(image, box, radius=24, fill=(4, 12, 25), outline=GOLD, shadow_alpha=115, outline_width=3)
    draw.text((x1 + 18, y1 + 12), pos or "--", font=_font(22, "bold", True), fill=BLUE)
    _draw_jersey(image, ((x1 + x2) // 2, y1 + 78), club, 115, 92)
    name = _safe(_value(player, "nome"), "Reserva").upper()
    nf = _fit_text(draw, name, x2 - x1 - 18, 23, 16, "bold", True)
    nb = draw.textbbox((0, 0), name, font=nf)
    draw.text(((x1 + x2 - (nb[2] - nb[0])) / 2, y1 + 126), name, font=nf, fill=WHITE)
    price = _money(_value(player, "preco", "preco_num"))
    pf = _font(21, "bold", True)
    pb = draw.textbbox((0, 0), price, font=pf)
    draw.text(((x1 + x2 - (pb[2] - pb[0])) / 2, y1 + 158), price, font=pf, fill=YELLOW)


def _info_card(image: Image.Image, box, label: str, value: str, icon: str, accent):
    draw = ImageDraw.Draw(image)
    _glow_outline(image, box, accent, radius=28, blur=10, alpha=40)
    _shadow_panel(image, box, radius=28, fill=(5, 16, 31), outline=(92, 153, 202), shadow_alpha=90, outline_width=2)
    x1, y1, x2, y2 = box
    icon_box = (x1 + 22, y1 + 18, x1 + 96, y2 - 18)
    _round(draw, icon_box, 20, fill=(14, 28, 47), outline=accent, width=2)
    _centered_text(draw, icon_box, icon, _font(38, "bold", True), fill=WHITE)
    draw.text((x1 + 118, y1 + 20), label, font=_font(23, "bold", True), fill=BLUE)
    vf = _fit_text(draw, value, x2 - x1 - 140, 36, 23, "bold", True)
    draw.text((x1 + 118, y1 + 55), value, font=vf, fill=WHITE)


def render_team(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    all_players = _extract_team_players(data)
    reserves = data.get("reservas") or []
    if not isinstance(reserves, list):
        reserves = []
    if not reserves:
        reserves = [p for p in all_players if _safe(_value(p, "status")).upper() == "RESERVA"]
    starters = [p for p in all_players if _safe(_value(p, "status"), "TITULAR").upper() != "RESERVA"]
    if not starters:
        starters = all_players
    groups = {key: [] for key in POSITION_LABELS}
    for player in starters:
        pos = _normalize_pos(_value(player, "pos", "posicao"))
        if pos in groups:
            groups[pos].append(player)

    _, subtitle, badge, round_value = _title_round(data, "TIME DA RODADA")
    kind = _safe(data.get("tipo_publicacao") or data.get("tipo") or "time").lower()
    if "econom" in kind:
        model_name, accent = "TIME ECONÔMICO", GREEN
    elif "intermedi" in kind:
        model_name, accent = "TIME INTERMEDIÁRIO", CYAN
    elif "pontua" in kind or "ideal" in kind:
        model_name, accent = "TIME PARA PONTUAR", BLUE
    else:
        model_name, accent = "TIME DA RODADA", BLUE
    title = f"{model_name} • RODADA {round_value}"

    width, height = TEAM_SIZE
    image = _gradient_background(width, height, stadium=False)
    _header_team(image, title, subtitle, badge)
    draw = ImageDraw.Draw(image)

    coach = groups["TEC"][0] if groups["TEC"] else None
    total = data.get("custo_total")
    if total in (None, ""):
        total = 0.0
        for player in starters:
            try:
                total += float(str(_value(player, "preco", default=0)).replace(",", "."))
            except Exception:
                pass
    formation = _safe(data.get("formacao")) or f"{len(groups['LAT']) + len(groups['ZAG'])}-{len(groups['MEI'])}-{len(groups['ATA'])}"
    coach_name = _safe(_value(coach or {}, "nome"), "Não informado")

    _info_card(image, (95, 305, 510, 430), "FORMAÇÃO", formation, "•••", CYAN)
    _info_card(image, (592, 305, 1008, 430), "PATRIMÔNIO", _money(total), "$", YELLOW)
    _info_card(image, (1090, 305, 1505, 430), "TÉC.", coach_name, "T", SILVER)

    field_box = (60, 455, 1540, 1455)
    _field_polygon(image, field_box, accent)
    rows = [
        (groups["ATA"], 605),
        (groups["MEI"], 830),
        (groups["LAT"] + groups["ZAG"], 1060),
        (groups["GOL"][:1], 1320),
    ]
    captain_name = _safe(data.get("capitao") or data.get("capitão")).lower()
    for players, y in rows:
        coords = _line_positions(len(players), y, field_box, 150 if len(players) <= 3 else 125)
        for player, (x, yy) in zip(players, coords):
            name = _safe(_value(player, "nome")).lower()
            is_captain = bool(_value(player, "capitao", "capitão", default=False)) or bool(captain_name and name == captain_name)
            _player_card(image, x, yy, player, _normalize_pos(_value(player, "pos", "posicao")), is_captain)

    draw.text((705, 1472), "RESERVAS", font=_font(32, "bold", True), fill=BLUE)
    draw.line((65, 1492, 650, 1492), fill=(31, 90, 145), width=3)
    draw.line((950, 1492, 1535, 1492), fill=(31, 90, 145), width=3)
    reserve_y = 1510
    count = min(5, len(reserves))
    if count:
        gap = 18
        card_w = (1470 - (count - 1) * gap) // count
        for index, player in enumerate(reserves[:5]):
            x1 = 65 + index * (card_w + gap)
            _reserve_card(image, (x1, reserve_y, x1 + card_w, reserve_y + 205), player)
    else:
        draw.text((580, reserve_y + 70), "Reservas não informados", font=_font(28, "semibold", True), fill=MUTED)

    captain_display = _safe(data.get("capitao") or "—").upper()
    bar_y = 1738
    _round(draw, (65, bar_y, 1535, bar_y + 88), 28, fill=(4, 13, 27), outline=(32, 135, 212), width=3)
    draw.ellipse((94, bar_y + 18, 148, bar_y + 72), fill=YELLOW, outline=WHITE, width=2)
    _centered_text(draw, (94, bar_y + 18, 148, bar_y + 72), "C", _font(30, "bold", True), fill=(33, 25, 8), y_offset=-2)
    draw.text((168, bar_y + 24), "CAPITÃO:", font=_font(29, "bold", True), fill=BLUE)
    draw.text((335, bar_y + 24), captain_display, font=_font(31, "bold", True), fill=WHITE)
    draw.line((760, bar_y + 16, 760, bar_y + 72), fill=SILVER, width=3)
    draw.text((810, bar_y + 24), "MODELO:", font=_font(29, "bold", True), fill=BLUE)
    draw.text((980, bar_y + 24), model_name, font=_fit_text(draw, model_name, 490, 31, 22, "bold", True), fill=WHITE)

    _footer(image, 1860)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", kind).strip("_") or "time"
    path = str(Path(output_dir) / f"{slug}_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "team", title, title.title())


def _extract_matches(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("partidas", "jogos", "resultados", "lista", "matches"):
        value = data.get(key)
        if isinstance(value, list) and value:
            candidates = [item for item in value if isinstance(item, dict)]
            if any(any(key in match for key in ("mandante", "visitante", "home", "away", "time_casa", "time_fora")) for match in candidates):
                return candidates
    return []


def _score(value: Any) -> str:
    if value in (None, ""):
        return "–"
    try:
        return str(int(float(value)))
    except Exception:
        return _safe(value, "–")


def _abbr(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-zÀ-ÿ0-9 ]", "", _safe(name, "---")).strip()
    if len(cleaned) <= 4:
        return cleaned.upper()
    words = [word for word in cleaned.split() if word]
    if len(words) >= 2:
        return "".join(word[0] for word in words[:3]).upper()
    return cleaned[:3].upper()


def _draw_match_card(image: Image.Image, box, match: Dict[str, Any], index: int):
    _shadow_panel(image, box, radius=30, fill=PANEL, outline=LINE)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, _ = box
    home = _safe(_value(match, "mandante", "home", "time_casa", "casa", "equipe_mandante"), "Mandante")
    away = _safe(_value(match, "visitante", "away", "time_fora", "fora", "equipe_visitante"), "Visitante")
    home_club = _safe(_value(match, "mandante_abrev", "home_abbr", "clube_mandante"), _abbr(home))
    away_club = _safe(_value(match, "visitante_abrev", "away_abbr", "clube_visitante"), _abbr(away))
    hs = _score(_value(match, "placar_mandante", "gols_mandante", "home_score", "gm", "placar_casa", default=None))
    aws = _score(_value(match, "placar_visitante", "gols_visitante", "away_score", "gv", "placar_fora", default=None))
    status = _clean_markdown(_value(match, "status", "situacao", "minuto", "fase", default="Programado"))
    date_time = _clean_markdown(_value(match, "data_hora", "data", "horario", "inicio", default=""))
    status_color = GREEN if any(token in status.lower() for token in ("encerr", "fim", "final")) else ORANGE if any(token in status.lower() for token in ("andamento", "ao vivo", "live", "interval")) else BLUE
    _glow_outline(image, box, status_color, radius=30, blur=13, alpha=32)
    draw.text((x1 + 30, y1 + 24), f"JOGO {index:02d}", font=_font(19, "bold"), fill=MUTED)
    status_box = (x2 - 245, y1 + 20, x2 - 28, y1 + 70)
    _round(draw, status_box, 24, fill=status_color)
    _centered_text(draw, status_box, status[:18].upper(), _font(18, "bold"), fill=(6, 22, 34))
    _paste_crest(image, home_club, (x1 + 120, y1 + 160), 104)
    _paste_crest(image, away_club, (x2 - 120, y1 + 160), 104)
    hf = _fit_text(draw, home, 360, 30, 20, "bold")
    af = _fit_text(draw, away, 360, 30, 20, "bold")
    draw.text((x1 + 195, y1 + 125), home, font=hf, fill=WHITE)
    ab = draw.textbbox((0, 0), away, font=af)
    draw.text((x2 - 195 - (ab[2] - ab[0]), y1 + 125), away, font=af, fill=WHITE)
    score = f"{hs}  ×  {aws}"
    score_box = (image.size[0] // 2 - 160, y1 + 100, image.size[0] // 2 + 160, y1 + 205)
    _round(draw, score_box, 28, fill=(5, 24, 41), outline=LINE, width=2)
    _centered_text(draw, score_box, score, _font(62, "bold"))
    if date_time:
        _centered_text(draw, (x1 + 350, y1 + 220, x2 - 350, y1 + 260), date_time[:54], _font(18), fill=MUTED)


def render_results(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = _extract_matches(data)
    title, subtitle, badge, round_value = _title_round(data, "RESULTADOS DA RODADA")
    if not matches:
        matches = [{"mandante": "Aguardando", "visitante": "dados das partidas", "status": "Sem resultados"}]
    width, height = RESULT_SIZE
    pages = max(1, math.ceil(len(matches) / 4))
    files: List[str] = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for page in range(pages):
        image = _gradient_background(width, height)
        _header_team(image, title, subtitle, badge)
        y = 345
        for index, match in enumerate(matches[page * 4:(page + 1) * 4], start=page * 4 + 1):
            _draw_match_card(image, (64, y, width - 64, y + 300), match, index)
            y += 330
        _footer(image, 1888, (page + 1, pages))
        path = str(Path(output_dir) / f"resultados_rodada_{round_value}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    return RenderOutput(files, "results", title, f"Resultados da Rodada {round_value}")


def render_bulletin(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    title, subtitle, badge, round_value = _title_round(data, "BOLETIM CARTOLA")
    image = _gradient_background(*RESULT_SIZE)
    _header_team(image, title, subtitle, badge)
    panel = (64, 345, 1536, 1825)
    _shadow_panel(image, panel, radius=30, fill=PANEL, outline=CYAN)
    draw = ImageDraw.Draw(image)
    draw.text((100, 382), "INFORMAÇÕES DA PUBLICAÇÃO", font=_font(34, "bold", True), fill=CYAN)
    message = _safe(data.get("mensagem_oficial") or data.get("mensagem") or data.get("texto"))
    lines: List[str] = []
    for raw in message.splitlines():
        clean = _clean_markdown(raw)
        if clean and "t.me/" not in clean and not clean.startswith("http"):
            lines.append(clean)
    y = 460
    for line in lines[:20]:
        for sub in textwrap.wrap(line, width=62)[:2]:
            draw.ellipse((102, y + 12, 118, y + 28), fill=ORANGE)
            draw.text((142, y), sub[:92], font=_font(27), fill=WHITE)
            y += 48
        y += 18
        if y > 1740:
            break
    if not lines:
        draw.text((100, 470), "Publicação recebida sem dados estruturados.", font=_font(29), fill=MUTED)
    _footer(image, 1888)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"boletim_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "bulletin", title, "Boletim Cartola")


def detect_kind(data: Dict[str, Any]) -> str:
    kind = _safe(data.get("tipo_publicacao") or data.get("tipo") or data.get("contexto")).lower()
    if any(token in kind for token in ("resultado", "placar", "partida", "live")):
        return "results"
    if any(token in kind for token in ("time", "campinho", "escalacao", "escalação", "econom", "intermedi", "pontua", "ideal")):
        return "team"
    if "top5" in kind or "top 5" in kind:
        return "top5"
    if _extract_matches(data):
        return "results"
    if any(key in data for key in ("jogadores", "time", "escalacao", "atletas")):
        return "team"
    items = data.get("lista") or data.get("dados")
    if isinstance(items, list) and items:
        counts = {pos: 0 for pos in POSITION_LABELS}
        for item in items:
            if isinstance(item, dict):
                pos = _normalize_pos(_value(item, "pos", "posicao"))
                if pos in counts:
                    counts[pos] += 1
        if max(counts.values() or [0]) >= 4:
            return "top5"
        if any(counts.values()):
            return "team"
    return "bulletin"


def render_publication(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    kind = detect_kind(data)
    if kind == "top5":
        return render_top5(data, output_dir)
    if kind == "team":
        return render_team(data, output_dir)
    if kind == "results":
        return render_results(data, output_dir)
    return render_bulletin(data, output_dir)
