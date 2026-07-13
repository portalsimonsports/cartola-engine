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

TOP5_SIZE = (1600, 2500)
TEAM_SIZE = (1600, 2000)
RESULT_SIZE = (1600, 2000)

NAVY = (4, 14, 28)
NAVY_2 = (9, 31, 53)
PANEL = (9, 30, 51)
PANEL_2 = (15, 44, 72)
PANEL_3 = (5, 23, 40)
WHITE = (248, 251, 255)
MUTED = (164, 185, 205)
LINE = (45, 82, 114)
CYAN = (39, 220, 239)
BLUE = (54, 126, 255)
ORANGE = (255, 174, 58)
GREEN = (44, 198, 120)
YELLOW = (255, 214, 74)
RED = (255, 84, 112)
PURPLE = (171, 102, 255)
SILVER = (174, 190, 207)

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


def _font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if weight == "bold":
        candidates = [
            "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    elif weight == "semibold":
        candidates = [
            "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
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


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 16, weight: str = "semibold") -> ImageFont.FreeTypeFont:
    size = start_size
    while size > min_size:
        font = _font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, weight)


def _centered_text(draw, box, text: str, font, fill=WHITE, y_offset=0):
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((x1 + x2 - (bbox[2] - bbox[0])) / 2, (y1 + y2 - (bbox[3] - bbox[1])) / 2 + y_offset),
        text,
        font=font,
        fill=fill,
    )


def _gradient_background(width: int, height: int) -> Image.Image:
    base = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(NAVY[i] * (1 - t) + NAVY_2[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(40, 0), (330, 0), (690, height), (470, height)], fill=(38, 193, 255, 20))
    od.polygon([(width - 330, 0), (width - 40, 0), (width - 470, height), (width - 690, height)], fill=(38, 193, 255, 18))
    od.ellipse((width * 0.50, -height * 0.18, width * 1.16, height * 0.42), fill=(29, 202, 235, 24))
    od.ellipse((-width * 0.20, height * 0.56, width * 0.50, height * 1.10), fill=(36, 107, 255, 12))
    overlay = overlay.filter(ImageFilter.GaussianBlur(100))
    base = Image.alpha_composite(base.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(base)
    for x in range(0, width, 80):
        draw.line((x, 0, x, height), fill=(255, 255, 255, 4), width=1)
    for y in range(0, height, 80):
        draw.line((0, y, width, y), fill=(255, 255, 255, 3), width=1)
    for i in range(22):
        x = 50 + (i * 73) % (width - 100)
        draw.ellipse((x, 20, x + 5, 25), fill=(160, 226, 255, 100))
    return base


def _shadow_panel(image: Image.Image, box, radius=28, fill=PANEL, outline=LINE, shadow_alpha=95):
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 12, y1 + 16, x2 + 12, y2 + 16), radius=radius, fill=(0, 0, 0, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _glow_outline(image: Image.Image, box, color, radius=28, blur=18, alpha=95):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rgba = tuple(color) + (alpha,)
    draw.rounded_rectangle(box, radius=radius, outline=rgba, width=7)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    image.alpha_composite(layer)


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
                response = requests.get(CREST_URL.format(club=code), timeout=(2, 4))
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
    code = _safe(club, "--")[:3].upper()
    font = _font(max(14, size // 4), "bold")
    _centered_text(draw, (x - radius, y - radius, x + radius, y + radius), code, font)


def _metal_logo(image: Image.Image, box):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    _glow_outline(image, box, CYAN, radius=30, blur=16, alpha=110)
    _round(draw, box, 30, fill=(5, 38, 66), outline=(126, 231, 247), width=3)
    inset = 10
    _round(draw, (x1 + inset, y1 + inset, x2 - inset, y2 - inset), 24, fill=(10, 65, 99), outline=(255, 255, 255, 75), width=2)
    _centered_text(draw, box, "PS", _font(43, "bold"), fill=WHITE, y_offset=-2)


def _brand_header(image: Image.Image, title: str, subtitle: str, badge: str, *, large: bool = False):
    width, _ = image.size
    draw = ImageDraw.Draw(image)
    top = 42
    logo_size = 118 if large else 102
    logo_box = (64, top, 64 + logo_size, top + logo_size)
    _metal_logo(image, logo_box)

    x = logo_box[2] + 30
    draw.text((x, top + 1), "PORTAL", font=_font(24 if large else 20, "semibold"), fill=CYAN)
    draw.text((x, top + 32), "SIMONSPORTS", font=_font(48 if large else 40, "bold"), fill=WHITE)
    draw.text((x, top + 90), "CARTOLA • DADOS • ANÁLISE", font=_font(18 if large else 16), fill=MUTED)

    badge_font = _font(22 if large else 20, "bold")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    bw = bbox[2] - bbox[0] + 56
    badge_box = (width - bw - 64, top + 14, width - 64, top + 74)
    _glow_outline(image, badge_box, CYAN, radius=28, blur=12, alpha=80)
    _round(draw, badge_box, 28, fill=(13, 61, 96), outline=CYAN, width=2)
    _centered_text(draw, badge_box, badge, badge_font, fill=WHITE, y_offset=-1)

    line_y = top + logo_size + 30
    draw.line((64, line_y, width - 64, line_y), fill=LINE, width=3)
    draw.rectangle((64, line_y - 3, 245, line_y + 3), fill=CYAN)
    title_font = _fit_text(draw, title, width - 128, 64 if large else 54, 38, "bold")
    draw.text((64, line_y + 28), title, font=title_font, fill=WHITE)
    draw.text((66, line_y + 106), subtitle[:115], font=_font(25 if large else 22), fill=MUTED)


def _footer(image: Image.Image, y: Optional[int] = None, page: Optional[Tuple[int, int]] = None):
    width, height = image.size
    y = y or height - 102
    draw = ImageDraw.Draw(image)
    draw.line((64, y, width - 64, y), fill=LINE, width=3)
    draw.rectangle((64, y - 2, 215, y + 2), fill=CYAN)
    draw.text((64, y + 25), "@dicascartolaportalsimonsports", font=_font(21, "semibold"), fill=CYAN)
    brand = "PORTAL SIMONSPORTS"
    font = _font(21, "semibold")
    bbox = draw.textbbox((0, 0), brand, font=font)
    draw.text((width - 64 - (bbox[2] - bbox[0]), y + 25), brand, font=font, fill=MUTED)
    if page:
        text = f"{page[0]}/{page[1]}"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((width / 2 - (bbox[2] - bbox[0]) / 2, y + 25), text, font=font, fill=WHITE)


def _title_round(data: Dict[str, Any], default_title: str):
    round_value = _safe(data.get("rodada") or data.get("rodada_atual"))
    title = _clean_markdown(data.get("titulo") or default_title)
    if "atualização" in title.lower() and round_value:
        title = "TOP 5 DA RODADA"
    blocks = data.get("blocos_topo") or []
    subtitle = ""
    if isinstance(blocks, list) and blocks:
        subtitle = _clean_markdown(blocks[0])
    subtitle = subtitle or _clean_markdown(data.get("status") or data.get("status_mercado"))
    subtitle = subtitle or "Seleção oficial atualizada pelo Portal SimonSports"
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


def _rank_badge(draw: ImageDraw.ImageDraw, center: Tuple[int, int], rank: int):
    colors = {1: (255, 205, 66), 2: (202, 213, 226), 3: (208, 139, 86)}
    color = colors.get(rank, (56, 80, 105))
    x, y = center
    draw.ellipse((x - 27, y - 27, x + 27, y + 27), fill=(5, 20, 35), outline=color, width=4)
    _centered_text(draw, (x - 27, y - 27, x + 27, y + 27), f"{rank:02d}", _font(18, "bold"), fill=color)


def _draw_top5_block(image: Image.Image, box, pos: str, items: Sequence[Dict[str, Any]]):
    accent = POSITION_COLORS[pos]
    _glow_outline(image, box, accent, radius=30, blur=18, alpha=55)
    _shadow_panel(image, box, radius=30, fill=PANEL, outline=tuple(min(255, c + 10) for c in accent))
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x2, y1 + 86), radius=30, fill=(8, 28, 48))
    draw.rectangle((x1, y1 + 55, x2, y1 + 86), fill=(8, 28, 48))
    draw.rounded_rectangle((x1, y1, x1 + 15, y2), radius=8, fill=accent)
    draw.text((x1 + 36, y1 + 23), POSITION_LABELS[pos], font=_font(34, "bold"), fill=WHITE)
    pill = (x2 - 110, y1 + 20, x2 - 28, y1 + 66)
    _round(draw, pill, 22, fill=accent)
    _centered_text(draw, pill, pos, _font(20, "bold"), fill=(5, 18, 30))

    row_y = y1 + 96
    row_h = 99
    for rank in range(1, 6):
        yy = row_y + (rank - 1) * row_h
        row_box = (x1 + 24, yy, x2 - 24, yy + 86)
        _round(draw, row_box, 18, fill=PANEL_2 if rank % 2 else PANEL_3, outline=(35, 65, 92), width=1)
        _rank_badge(draw, (x1 + 61, yy + 43), rank)
        item = items[rank - 1] if rank - 1 < len(items) else None
        if not item:
            draw.text((x1 + 120, yy + 26), "Sem dado", font=_font(27), fill=MUTED)
            continue
        club = _safe(_value(item, "clube"), "--").upper()
        _paste_crest(image, club, (x1 + 132, yy + 43), 56, fallback_color=(17, 61, 97))
        name = _safe(_value(item, "nome"), "Jogador")
        name_font = _fit_text(draw, name, 270, 28, 20, "bold")
        draw.text((x1 + 174, yy + 13), name, font=name_font, fill=WHITE)
        projection = _value(item, "exp_score", "projecao", "pontuacao")
        meta = _points(projection) if projection not in (None, "") else club
        draw.text((x1 + 176, yy + 52), meta, font=_font(17, "semibold"), fill=MUTED)
        price = _money(_value(item, "preco", "preco_num"))
        price_font = _font(23, "bold")
        pb = draw.textbbox((0, 0), price, font=price_font)
        price_box = (x2 - 175, yy + 20, x2 - 34, yy + 68)
        _round(draw, price_box, 20, fill=(5, 22, 38), outline=accent, width=2)
        draw.text((x2 - 104 - (pb[2] - pb[0]) / 2, yy + 32), price, font=price_font, fill=accent)


def render_top5(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    items = data.get("lista") or data.get("jogadores") or data.get("dados") or []
    groups = _top5_groups(items if isinstance(items, list) else [])
    _, subtitle, badge, round_value = _title_round(data, "TOP 5 DA RODADA")
    title = "TOP 5 DA RODADA"
    width, height = TOP5_SIZE
    image = _gradient_background(width, height)
    _brand_header(image, title, subtitle, badge, large=True)
    margin, gap_x, gap_y, top = 68, 34, 32, 365
    footer_y = height - 112
    usable_w = width - 2 * margin
    block_w = (usable_w - gap_x) // 2
    block_h = (footer_y - top - 2 * gap_y) // 3
    order = ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]
    for index, pos in enumerate(order):
        row, col = index // 2, index % 2
        x1 = margin + col * (block_w + gap_x)
        y1 = top + row * (block_h + gap_y)
        _draw_top5_block(image, (x1, y1, x1 + block_w, y1 + block_h), pos, groups[pos])
    _footer(image, footer_y)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"top5_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "top5", title, f"Top 5 da Rodada {round_value}")


def _extract_team_players(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("jogadores", "time", "escalacao", "lista", "atletas", "dados"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    return []


def _field(image: Image.Image, box, accent):
    x1, y1, x2, y2 = box
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(box, radius=38, fill=(10, 78, 51, 255), outline=(166, 239, 203, 255), width=5)
    inset = 25
    inner = (x1 + inset, y1 + inset, x2 - inset, y2 - inset)
    stripe_h = max(1, (inner[3] - inner[1]) // 12)
    for i in range(12):
        fill = (18, 125, 72, 255) if i % 2 == 0 else (20, 142, 80, 255)
        ld.rectangle((inner[0], inner[1] + i * stripe_h, inner[2], inner[1] + (i + 1) * stripe_h), fill=fill)
    vignette = Image.new("RGBA", image.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    vd.rounded_rectangle(box, radius=38, outline=(0, 0, 0, 130), width=50)
    vignette = vignette.filter(ImageFilter.GaussianBlur(26))
    layer = Image.alpha_composite(layer, vignette)
    ld = ImageDraw.Draw(layer)
    line = (221, 249, 231, 225)
    ld.rectangle(inner, outline=line, width=4)
    mid_y = (inner[1] + inner[3]) // 2
    center_x = (inner[0] + inner[2]) // 2
    ld.line((inner[0], mid_y, inner[2], mid_y), fill=line, width=4)
    ld.ellipse((center_x - 92, mid_y - 92, center_x + 92, mid_y + 92), outline=line, width=4)
    ld.ellipse((center_x - 6, mid_y - 6, center_x + 6, mid_y + 6), fill=line)
    penalty_w, penalty_h = 360, 130
    ld.rectangle((center_x - penalty_w // 2, inner[1], center_x + penalty_w // 2, inner[1] + penalty_h), outline=line, width=4)
    ld.rectangle((center_x - penalty_w // 2, inner[3] - penalty_h, center_x + penalty_w // 2, inner[3]), outline=line, width=4)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle(box, radius=38, outline=tuple(accent) + (90,), width=10)
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    image.alpha_composite(glow)
    image.alpha_composite(layer)


def _line_positions(count: int, y: int, x1: int, x2: int) -> List[Tuple[int, int]]:
    if count <= 0:
        return []
    if count == 1:
        return [((x1 + x2) // 2, y)]
    step = (x2 - x1) / (count - 1)
    return [(int(x1 + index * step), y) for index in range(count)]


def _jersey(draw: ImageDraw.ImageDraw, center: Tuple[int, int], color, width=110, height=96):
    x, y = center
    left, top = x - width // 2, y - height // 2
    shade = tuple(max(0, c - 35) for c in color)
    points = [(left + 22, top), (left + 42, top + 15), (left + width - 42, top + 15), (left + width - 22, top), (left + width, top + 30), (left + width - 20, top + 55), (left + width - 37, top + 45), (left + width - 37, top + height), (left + 37, top + height), (left + 37, top + 45), (left + 20, top + 55), (left, top + 30)]
    draw.polygon(points, fill=color, outline=WHITE)
    draw.polygon([(left + 37, top + 45), (left + width // 2, top + 62), (left + width // 2, top + height), (left + 37, top + height)], fill=shade)
    draw.line((x, top + 15, x, top + height - 6), fill=(255, 255, 255, 100), width=2)


def _player_card(image: Image.Image, x: int, y: int, player: Dict[str, Any], pos: str, captain: bool = False):
    draw = ImageDraw.Draw(image)
    color = POSITION_COLORS.get(pos, BLUE)
    card_w, card_h = 232, 190
    x1, y1 = x - card_w // 2, y - card_h // 2
    x2, y2 = x1 + card_w, y1 + card_h
    _glow_outline(image, (x1, y1, x2, y2), color, radius=24, blur=13, alpha=65)
    _shadow_panel(image, (x1, y1, x2, y2), radius=24, fill=(3, 23, 39, 245), outline=(185, 235, 211), shadow_alpha=75)
    draw = ImageDraw.Draw(image)
    _round(draw, (x1 + 8, y1 + 8, x2 - 8, y1 + 88), 19, fill=(8, 45, 61))
    _jersey(draw, (x, y1 + 51), color, 92, 78)
    club = _safe(_value(player, "clube"), "--").upper()
    _paste_crest(image, club, (x, y1 + 50), 57, fallback_color=(13, 55, 86))
    if captain:
        captain_box = (x2 - 55, y1 - 15, x2 - 5, y1 + 35)
        _glow_outline(image, captain_box, YELLOW, radius=24, blur=10, alpha=90)
        draw.ellipse(captain_box, fill=YELLOW, outline=WHITE, width=2)
        _centered_text(draw, captain_box, "C", _font(20, "bold"), fill=(23, 27, 30), y_offset=-1)
    name = _safe(_value(player, "nome"), "Jogador")
    name_font = _fit_text(draw, name, card_w - 24, 25, 17, "bold")
    bbox = draw.textbbox((0, 0), name, font=name_font)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y1 + 100), name, font=name_font, fill=WHITE)
    price = _money(_value(player, "preco", "preco_num"))
    projection = _value(player, "exp_score", "projecao", "pontuacao")
    draw.text((x1 + 13, y1 + 146), price, font=_font(17, "semibold"), fill=ORANGE)
    if projection not in (None, ""):
        points_text = _points(projection)
        pf = _font(17, "semibold")
        pb = draw.textbbox((0, 0), points_text, font=pf)
        draw.text((x2 - 13 - (pb[2] - pb[0]), y1 + 146), points_text, font=pf, fill=CYAN)


def _reserve_card(image: Image.Image, box, player: Dict[str, Any]):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    pos = _normalize_pos(_value(player, "pos", "posicao"))
    color = POSITION_COLORS.get(pos, BLUE)
    _round(draw, box, 20, fill=PANEL_2, outline=color, width=2)
    _paste_crest(image, _safe(_value(player, "clube"), "--"), (x1 + 42, (y1 + y2) // 2), 54)
    name = _safe(_value(player, "nome"), "Reserva")
    name_font = _fit_text(draw, name, x2 - x1 - 96, 20, 15, "bold")
    draw.text((x1 + 78, y1 + 20), name, font=name_font, fill=WHITE)
    draw.text((x1 + 78, y1 + 51), _money(_value(player, "preco", "preco_num")), font=_font(16, "semibold"), fill=ORANGE)
    pill = (x2 - 62, y1 + 12, x2 - 12, y1 + 40)
    _round(draw, pill, 14, fill=color)
    _centered_text(draw, pill, pos or "--", _font(12, "bold"), fill=(5, 18, 30))


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
        title, accent = f"TIME ECONÔMICO • RODADA {round_value}", GREEN
    elif "intermedi" in kind:
        title, accent = f"TIME INTERMEDIÁRIO • RODADA {round_value}", CYAN
    elif "pontua" in kind or "ideal" in kind:
        title, accent = f"TIME PARA PONTUAR • RODADA {round_value}", ORANGE
    else:
        title, accent = f"TIME DA RODADA • RODADA {round_value}", BLUE
    width, height = TEAM_SIZE
    image = _gradient_background(width, height)
    _brand_header(image, title, subtitle, badge)
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
    projection_total = 0.0
    has_projection = False
    for player in starters:
        value = _value(player, "exp_score", "projecao", "pontuacao", default=None)
        try:
            projection_total += float(str(value).replace(",", "."))
            has_projection = True
        except Exception:
            pass
    formation = _safe(data.get("formacao")) or f"{len(groups['LAT']) + len(groups['ZAG'])}-{len(groups['MEI'])}-{len(groups['ATA'])}"
    chips = [("FORMAÇÃO", formation, CYAN), ("PATRIMÔNIO", _money(total), ORANGE), ("PROJEÇÃO", _points(projection_total) if has_projection else "--", GREEN), ("TÉCNICO", _safe(_value(coach or {}, "nome"), "Não informado"), WHITE)]
    stats_y, stats_h, gap = 258, 82, 18
    chip_w = (width - 128 - 3 * gap) // 4
    for index, (label, value, color) in enumerate(chips):
        x1 = 64 + index * (chip_w + gap)
        chip_box = (x1, stats_y, x1 + chip_w, stats_y + stats_h)
        _glow_outline(image, chip_box, color if color != WHITE else CYAN, radius=22, blur=10, alpha=35)
        _round(draw, chip_box, 22, fill=(9, 38, 62), outline=LINE, width=2)
        draw.text((x1 + 18, stats_y + 11), label, font=_font(15, "bold"), fill=MUTED)
        value_font = _fit_text(draw, value, chip_w - 36, 25, 16, "bold")
        draw.text((x1 + 18, stats_y + 39), value, font=value_font, fill=color)
    field_box = (64, 372, width - 64, 1495)
    _field(image, field_box, accent)
    fx1, fy1, fx2, _ = field_box
    rows = [(groups["ATA"], fy1 + 160), (groups["MEI"], fy1 + 425), (groups["LAT"] + groups["ZAG"], fy1 + 705), (groups["GOL"][:1], fy1 + 970)]
    captain_name = _safe(data.get("capitao") or data.get("capitão")).lower()
    for players, y in rows:
        coords = _line_positions(len(players), y, fx1 + 160, fx2 - 160)
        for player, (x, yy) in zip(players, coords):
            name = _safe(_value(player, "nome")).lower()
            captain = bool(_value(player, "capitao", "capitão", default=False)) or bool(captain_name and name == captain_name)
            _player_card(image, x, yy, player, _normalize_pos(_value(player, "pos", "posicao")), captain)
    bench_y = 1525
    bench_box = (64, bench_y, width - 64, 1880)
    _glow_outline(image, bench_box, accent, radius=28, blur=15, alpha=35)
    _shadow_panel(image, bench_box, radius=28, fill=PANEL)
    draw = ImageDraw.Draw(image)
    draw.text((90, bench_y + 22), "BANCO DE RESERVAS", font=_font(27, "bold"), fill=accent)
    if reserves:
        count = min(5, len(reserves))
        card_gap = 16
        card_w = (width - 180 - (count - 1) * card_gap) // count
        for index, player in enumerate(reserves[:5]):
            x1 = 90 + index * (card_w + card_gap)
            _reserve_card(image, (x1, bench_y + 78, x1 + card_w, bench_y + 190), player)
    else:
        draw.text((90, bench_y + 104), "Reservas não informados neste payload.", font=_font(24), fill=MUTED)
    captain_display = _safe(data.get("capitao") or "—")
    model_display = title.split("•")[0].strip()
    _round(draw, (90, bench_y + 226, 520, bench_y + 292), 22, fill=(7, 28, 47), outline=YELLOW, width=2)
    draw.text((112, bench_y + 240), "CAPITÃO", font=_font(16, "bold"), fill=YELLOW)
    draw.text((225, bench_y + 237), captain_display, font=_font(22, "bold"), fill=WHITE)
    _round(draw, (550, bench_y + 226, width - 90, bench_y + 292), 22, fill=(7, 28, 47), outline=accent, width=2)
    draw.text((575, bench_y + 240), "MODELO", font=_font(16, "bold"), fill=MUTED)
    draw.text((690, bench_y + 237), model_display, font=_font(22, "bold"), fill=WHITE)
    _footer(image, height - 102)
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


def _match_value(match: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    return _value(match, *keys, default=default)


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
    _shadow_panel(image, box, radius=30, fill=PANEL)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, _ = box
    home = _safe(_match_value(match, "mandante", "home", "time_casa", "casa", "equipe_mandante"), "Mandante")
    away = _safe(_match_value(match, "visitante", "away", "time_fora", "fora", "equipe_visitante"), "Visitante")
    home_club = _safe(_match_value(match, "mandante_abrev", "home_abbr", "clube_mandante"), _abbr(home))
    away_club = _safe(_match_value(match, "visitante_abrev", "away_abbr", "clube_visitante"), _abbr(away))
    hs = _score(_match_value(match, "placar_mandante", "gols_mandante", "home_score", "gm", "placar_casa", default=None))
    aws = _score(_match_value(match, "placar_visitante", "gols_visitante", "away_score", "gv", "placar_fora", default=None))
    status = _clean_markdown(_match_value(match, "status", "situacao", "minuto", "fase", default="Programado"))
    date_time = _clean_markdown(_match_value(match, "data_hora", "data", "horario", "inicio", default=""))
    status_color = GREEN if any(token in status.lower() for token in ("encerr", "fim", "final")) else ORANGE if any(token in status.lower() for token in ("andamento", "ao vivo", "live", "interval")) else BLUE
    _glow_outline(image, box, status_color, radius=30, blur=13, alpha=32)
    draw = ImageDraw.Draw(image)
    draw.text((x1 + 30, y1 + 24), f"JOGO {index:02d}", font=_font(19, "bold"), fill=MUTED)
    status_box = (x2 - 245, y1 + 20, x2 - 28, y1 + 70)
    _round(draw, status_box, 24, fill=status_color)
    _centered_text(draw, status_box, status[:18].upper(), _font(18, "bold"), fill=(6, 22, 34))
    _paste_crest(image, home_club, (x1 + 120, y1 + 160), 104)
    _paste_crest(image, away_club, (x2 - 120, y1 + 160), 104)
    home_font = _fit_text(draw, home, 360, 30, 20, "bold")
    away_font = _fit_text(draw, away, 360, 30, 20, "bold")
    draw.text((x1 + 195, y1 + 125), home, font=home_font, fill=WHITE)
    away_box = draw.textbbox((0, 0), away, font=away_font)
    draw.text((x2 - 195 - (away_box[2] - away_box[0]), y1 + 125), away, font=away_font, fill=WHITE)
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
    per_page = 4
    pages = max(1, math.ceil(len(matches) / per_page))
    files: List[str] = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for page in range(pages):
        image = _gradient_background(width, height)
        _brand_header(image, title, subtitle, badge)
        y = 330
        for index, match in enumerate(matches[page * per_page:(page + 1) * per_page], start=page * per_page + 1):
            _draw_match_card(image, (64, y, width - 64, y + 300), match, index)
            y += 330
        _footer(image, height - 102, (page + 1, pages))
        path = str(Path(output_dir) / f"resultados_rodada_{round_value}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    return RenderOutput(files, "results", title, f"Resultados da Rodada {round_value}")


def render_bulletin(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    title, subtitle, badge, round_value = _title_round(data, "BOLETIM CARTOLA")
    width, height = RESULT_SIZE
    image = _gradient_background(width, height)
    _brand_header(image, title, subtitle, badge)
    panel = (64, 330, width - 64, height - 145)
    _glow_outline(image, panel, CYAN, radius=30, blur=15, alpha=35)
    _shadow_panel(image, panel, radius=30, fill=PANEL)
    draw = ImageDraw.Draw(image)
    draw.text((100, 372), "INFORMAÇÕES DA PUBLICAÇÃO", font=_font(34, "bold"), fill=CYAN)
    message = _safe(data.get("mensagem_oficial") or data.get("mensagem") or data.get("texto"))
    lines = []
    for raw in message.splitlines():
        clean = _clean_markdown(raw)
        if clean and "t.me/" not in clean and not clean.startswith("http"):
            lines.append(clean)
    y = 450
    for line in lines[:20]:
        for sub in textwrap.wrap(line, width=62)[:2]:
            draw.ellipse((102, y + 12, 118, y + 28), fill=ORANGE)
            draw.text((142, y), sub[:92], font=_font(27), fill=WHITE)
            y += 48
        y += 18
        if y > height - 230:
            break
    if not lines:
        draw.text((100, 470), "Publicação recebida sem dados estruturados.", font=_font(29), fill=MUTED)
    _footer(image, height - 102)
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
