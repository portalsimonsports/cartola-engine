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

NAVY = (5, 17, 32)
NAVY_2 = (10, 31, 53)
PANEL = (12, 34, 57)
PANEL_2 = (17, 45, 73)
WHITE = (248, 251, 255)
MUTED = (166, 187, 207)
LINE = (46, 81, 112)
CYAN = (40, 218, 238)
BLUE = (54, 125, 255)
ORANGE = (255, 173, 58)
GREEN = (47, 197, 121)
YELLOW = (255, 213, 76)
RED = (255, 87, 113)
PURPLE = (170, 102, 255)

POSITION_COLORS = {
    "GOL": ORANGE,
    "LAT": CYAN,
    "ZAG": BLUE,
    "MEI": PURPLE,
    "ATA": RED,
    "TEC": (155, 173, 192),
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
    candidates: List[str] = []
    if weight == "bold":
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
        ])
    elif weight == "semibold":
        candidates.extend([
            "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf",
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


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 16, weight: str = "semibold") -> ImageFont.FreeTypeFont:
    size = start_size
    while size > min_size:
        font = _font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, weight)


def _centered_text(draw: ImageDraw.ImageDraw, box, text: str, font, fill=WHITE, y_offset=0):
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
    od.polygon(
        [(width * 0.58, 0), (width, 0), (width, height * 0.48), (width * 0.34, height * 0.12)],
        fill=(30, 170, 255, 24),
    )
    od.ellipse(
        (width * 0.50, -height * 0.16, width * 1.14, height * 0.40),
        fill=(31, 202, 235, 20),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(base.convert("RGBA"), overlay)


def _shadow_panel(image: Image.Image, box, radius=28, fill=PANEL, outline=LINE, shadow_alpha=90):
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 10, y1 + 14, x2 + 10, y2 + 14), radius=radius, fill=(0, 0, 0, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


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


def _brand_header(image: Image.Image, title: str, subtitle: str, badge: str, *, large: bool = False):
    width, _ = image.size
    draw = ImageDraw.Draw(image)
    top = 44
    logo_size = 116 if large else 100
    logo_box = (64, top, 64 + logo_size, top + logo_size)
    _round(draw, logo_box, 28, fill=(8, 55, 91), outline=CYAN, width=4)
    _centered_text(draw, logo_box, "PS", _font(42 if large else 36, "bold"))
    x = logo_box[2] + 28
    draw.text((x, top + 2), "PORTAL", font=_font(24 if large else 20, "semibold"), fill=CYAN)
    draw.text((x, top + 34), "SIMONSPORTS", font=_font(46 if large else 38, "bold"), fill=WHITE)
    draw.text((x, top + 86), "CARTOLA • DADOS • ANÁLISE", font=_font(18 if large else 16), fill=MUTED)

    badge_font = _font(22 if large else 19, "bold")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    bw = bbox[2] - bbox[0] + 48
    _round(draw, (width - bw - 64, top + 16, width - 64, top + 72), 26, fill=(16, 65, 101), outline=CYAN, width=2)
    draw.text((width - bw - 40, top + 30), badge, font=badge_font, fill=WHITE)

    line_y = top + logo_size + 32
    draw.line((64, line_y, width - 64, line_y), fill=LINE, width=3)
    title_font = _fit_text(draw, title, width - 128, 64 if large else 54, 38, "bold")
    draw.text((64, line_y + 30), title, font=title_font, fill=WHITE)
    draw.text((66, line_y + 108), subtitle[:115], font=_font(25 if large else 22), fill=MUTED)


def _footer(image: Image.Image, y: Optional[int] = None, page: Optional[Tuple[int, int]] = None):
    width, height = image.size
    y = y or height - 102
    draw = ImageDraw.Draw(image)
    draw.line((64, y, width - 64, y), fill=LINE, width=3)
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
        title = f"TOP 5 DA RODADA {round_value}"
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


def _rank_badge(draw: ImageDraw.ImageDraw, center: Tuple[int, int], rank: int, accent):
    colors = {
        1: (255, 205, 66),
        2: (198, 210, 224),
        3: (207, 140, 87),
    }
    color = colors.get(rank, (69, 93, 117))
    x, y = center
    draw.ellipse((x - 25, y - 25, x + 25, y + 25), fill=color, outline=WHITE if rank <= 3 else LINE, width=2)
    _centered_text(draw, (x - 25, y - 25, x + 25, y + 25), str(rank), _font(20, "bold"), fill=(9, 23, 38))


def _draw_top5_block(image: Image.Image, box, pos: str, items: Sequence[Dict[str, Any]]):
    _shadow_panel(image, box, radius=30, fill=PANEL)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    accent = POSITION_COLORS[pos]
    draw.rounded_rectangle((x1, y1, x1 + 15, y2), radius=8, fill=accent)
    draw.text((x1 + 34, y1 + 24), POSITION_LABELS[pos], font=_font(34, "bold"), fill=WHITE)
    _round(draw, (x2 - 106, y1 + 20, x2 - 26, y1 + 66), 22, fill=accent)
    _centered_text(draw, (x2 - 106, y1 + 20, x2 - 26, y1 + 66), pos, _font(20, "bold"), fill=(7, 20, 34))

    row_y = y1 + 90
    row_h = 91
    for rank in range(1, 6):
        yy = row_y + (rank - 1) * row_h
        if rank % 2:
            draw.rounded_rectangle((x1 + 24, yy, x2 - 24, yy + 78), radius=16, fill=PANEL_2)
        item = items[rank - 1] if rank - 1 < len(items) else None
        _rank_badge(draw, (x1 + 58, yy + 39), rank, accent)
        if not item:
            draw.text((x1 + 108, yy + 22), "Sem dado", font=_font(27), fill=MUTED)
            continue
        club = _safe(_value(item, "clube"), "--").upper()
        _paste_crest(image, club, (x1 + 122, yy + 39), 52)
        name = _safe(_value(item, "nome"), "Jogador")
        name_font = _fit_text(draw, name, 260, 28, 20, "semibold")
        draw.text((x1 + 162, yy + 12), name, font=name_font, fill=WHITE)
        projection = _value(item, "exp_score", "projecao", "pontuacao")
        if projection not in (None, ""):
            draw.text((x1 + 164, yy + 48), _points(projection), font=_font(17), fill=MUTED)
        else:
            draw.text((x1 + 164, yy + 48), club, font=_font(17), fill=MUTED)
        price = _money(_value(item, "preco", "preco_num"))
        price_font = _font(23, "bold")
        pb = draw.textbbox((0, 0), price, font=price_font)
        draw.text((x2 - 32 - (pb[2] - pb[0]), yy + 27), price, font=price_font, fill=accent)


def render_top5(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    items = data.get("lista") or data.get("jogadores") or data.get("dados") or []
    groups = _top5_groups(items if isinstance(items, list) else [])
    title, subtitle, badge, round_value = _title_round(data, "TOP 5 DA RODADA")
    width, height = TOP5_SIZE
    image = _gradient_background(width, height)
    _brand_header(image, title, subtitle, badge, large=True)

    margin = 68
    gap_x = 34
    gap_y = 34
    top = 365
    footer_y = height - 112
    usable_w = width - 2 * margin
    block_w = (usable_w - gap_x) // 2
    block_h = (footer_y - top - 2 * gap_y) // 3
    order = ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]
    for index, pos in enumerate(order):
        row = index // 2
        col = index % 2
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


def _field(image: Image.Image, box):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=36, fill=(18, 112, 66), outline=(192, 241, 211), width=5)
    inset = 26
    inner = (x1 + inset, y1 + inset, x2 - inset, y2 - inset)
    stripe_h = max(1, (inner[3] - inner[1]) // 10)
    for i in range(10):
        fill = (21, 128, 74) if i % 2 == 0 else (25, 139, 81)
        draw.rectangle((inner[0], inner[1] + i * stripe_h, inner[2], inner[1] + (i + 1) * stripe_h), fill=fill)
    draw.rectangle(inner, outline=(210, 246, 223), width=4)
    mid_y = (inner[1] + inner[3]) // 2
    draw.line((inner[0], mid_y, inner[2], mid_y), fill=(210, 246, 223), width=4)
    center_x = (inner[0] + inner[2]) // 2
    draw.ellipse((center_x - 88, mid_y - 88, center_x + 88, mid_y + 88), outline=(210, 246, 223), width=4)
    draw.ellipse((center_x - 6, mid_y - 6, center_x + 6, mid_y + 6), fill=(210, 246, 223))
    penalty_w = 360
    penalty_h = 125
    draw.rectangle((center_x - penalty_w // 2, inner[1], center_x + penalty_w // 2, inner[1] + penalty_h), outline=(210, 246, 223), width=4)
    draw.rectangle((center_x - penalty_w // 2, inner[3] - penalty_h, center_x + penalty_w // 2, inner[3]), outline=(210, 246, 223), width=4)


def _line_positions(count: int, y: int, x1: int, x2: int) -> List[Tuple[int, int]]:
    if count <= 0:
        return []
    if count == 1:
        return [((x1 + x2) // 2, y)]
    step = (x2 - x1) / (count - 1)
    return [(int(x1 + index * step), y) for index in range(count)]


def _jersey(draw: ImageDraw.ImageDraw, center: Tuple[int, int], color, width=114, height=105):
    x, y = center
    left = x - width // 2
    top = y - height // 2
    points = [
        (left + 22, top),
        (left + 42, top + 15),
        (left + width - 42, top + 15),
        (left + width - 22, top),
        (left + width, top + 30),
        (left + width - 20, top + 55),
        (left + width - 37, top + 45),
        (left + width - 37, top + height),
        (left + 37, top + height),
        (left + 37, top + 45),
        (left + 20, top + 55),
        (left, top + 30),
    ]
    draw.polygon(points, fill=color, outline=WHITE)
    draw.line((x, top + 15, x, top + height - 8), fill=(255, 255, 255, 55), width=2)


def _player_card(image: Image.Image, x: int, y: int, player: Dict[str, Any], pos: str, captain: bool = False, compact: bool = False):
    draw = ImageDraw.Draw(image)
    color = POSITION_COLORS.get(pos, BLUE)
    card_w = 230 if not compact else 210
    card_h = 202 if not compact else 170
    x1 = x - card_w // 2
    y1 = y - card_h // 2
    x2 = x1 + card_w
    y2 = y1 + card_h
    _shadow_panel(image, (x1, y1, x2, y2), radius=24, fill=(5, 26, 43, 238), outline=(184, 232, 210), shadow_alpha=70)
    _jersey(draw, (x, y1 + 58), color, 98 if compact else 110, 86 if compact else 98)
    club = _safe(_value(player, "clube"), "--").upper()
    _paste_crest(image, club, (x, y1 + 56), 58 if compact else 66)

    if captain:
        draw.ellipse((x2 - 50, y1 - 12, x2 - 8, y1 + 30), fill=YELLOW, outline=WHITE, width=2)
        _centered_text(draw, (x2 - 50, y1 - 12, x2 - 8, y1 + 30), "C", _font(18, "bold"), fill=(20, 26, 30))

    name = _safe(_value(player, "nome"), "Jogador")
    name_font = _fit_text(draw, name, card_w - 24, 25 if not compact else 21, 17, "bold")
    bbox = draw.textbbox((0, 0), name, font=name_font)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y1 + 112 if not compact else y1 + 96), name, font=name_font, fill=WHITE)

    price = _money(_value(player, "preco", "preco_num"))
    projection = _value(player, "exp_score", "projecao", "pontuacao")
    meta_y = y1 + 150 if not compact else y1 + 130
    price_font = _font(18 if not compact else 16, "semibold")
    draw.text((x1 + 14, meta_y), price, font=price_font, fill=ORANGE)
    if projection not in (None, ""):
        points_text = _points(projection)
        pf = _font(18 if not compact else 16, "semibold")
        pb = draw.textbbox((0, 0), points_text, font=pf)
        draw.text((x2 - 14 - (pb[2] - pb[0]), meta_y), points_text, font=pf, fill=CYAN)


def _reserve_card(image: Image.Image, box, player: Dict[str, Any]):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    _round(draw, box, 20, fill=PANEL_2, outline=LINE, width=2)
    club = _safe(_value(player, "clube"), "--").upper()
    _paste_crest(image, club, (x1 + 43, (y1 + y2) // 2), 58)
    name = _safe(_value(player, "nome"), "Reserva")
    font = _fit_text(draw, name, x2 - x1 - 116, 21, 16, "semibold")
    draw.text((x1 + 82, y1 + 20), name, font=font, fill=WHITE)
    pos = _normalize_pos(_value(player, "pos", "posicao"))
    draw.text((x1 + 84, y1 + 51), f"{pos} • {_money(_value(player, 'preco'))}", font=_font(15), fill=MUTED)


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

    title, subtitle, badge, round_value = _title_round(data, "TIME DA RODADA")
    kind = _safe(data.get("tipo_publicacao") or data.get("tipo") or "time").lower()
    if "econom" in kind:
        title = f"TIME ECONÔMICO • RODADA {round_value}"
        accent = GREEN
    elif "intermedi" in kind:
        title = f"TIME INTERMEDIÁRIO • RODADA {round_value}"
        accent = CYAN
    elif "pontua" in kind or "ideal" in kind:
        title = f"TIME PARA PONTUAR • RODADA {round_value}"
        accent = ORANGE
    else:
        title = f"TIME DA RODADA {round_value}"
        accent = BLUE

    width, height = TEAM_SIZE
    image = _gradient_background(width, height)
    _brand_header(image, title, subtitle, badge)
    draw = ImageDraw.Draw(image)

    total = data.get("custo_total")
    if total in (None, ""):
        total = 0.0
        for player in starters + groups["TEC"]:
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
    coach = groups["TEC"][0] if groups["TEC"] else None

    stats_y = 258
    stats_h = 80
    chips = [
        ("FORMAÇÃO", formation, CYAN),
        ("CUSTO TOTAL", _money(total), ORANGE),
        ("PROJEÇÃO", _points(projection_total) if has_projection else "--", GREEN),
        ("TÉCNICO", _safe(_value(coach or {}, "nome"), "Não informado"), WHITE),
    ]
    gap = 18
    chip_w = (width - 128 - 3 * gap) // 4
    for index, (label, value, color) in enumerate(chips):
        x1 = 64 + index * (chip_w + gap)
        _round(draw, (x1, stats_y, x1 + chip_w, stats_y + stats_h), 22, fill=(12, 42, 66), outline=LINE, width=2)
        draw.text((x1 + 18, stats_y + 12), label, font=_font(15, "bold"), fill=MUTED)
        value_font = _fit_text(draw, value, chip_w - 36, 25, 16, "bold")
        draw.text((x1 + 18, stats_y + 38), value, font=value_font, fill=color)

    field_box = (64, 370, width - 64, 1510)
    _field(image, field_box)
    fx1, fy1, fx2, fy2 = field_box
    rows = [
        (groups["ATA"], fy1 + 165, "ATA"),
        (groups["MEI"], fy1 + 430, "MEI"),
        (groups["LAT"] + groups["ZAG"], fy1 + 710, "ZAG"),
        (groups["GOL"][:1], fy1 + 975, "GOL"),
    ]
    captain_name = _safe(data.get("capitao") or data.get("capitão")).lower()
    for players, y, pos in rows:
        coords = _line_positions(len(players), y, fx1 + 155, fx2 - 155)
        for player, (x, yy) in zip(players, coords):
            name = _safe(_value(player, "nome")).lower()
            captain = bool(_value(player, "capitao", "capitão", default=False)) or bool(captain_name and name == captain_name)
            _player_card(image, x, yy, player, _normalize_pos(_value(player, "pos", "posicao")) or pos, captain)

    bench_y = 1540
    _shadow_panel(image, (64, bench_y, width - 64, 1880), radius=28, fill=PANEL)
    draw.text((90, bench_y + 24), "BANCO DE RESERVAS", font=_font(26, "bold"), fill=accent)
    if reserves:
        count = min(5, len(reserves))
        gap = 16
        card_w = (width - 180 - (count - 1) * gap) // count
        for index, player in enumerate(reserves[:5]):
            x1 = 90 + index * (card_w + gap)
            _reserve_card(image, (x1, bench_y + 82, x1 + card_w, bench_y + 202), player)
        draw.text((90, bench_y + 238), "Capitão", font=_font(18, "bold"), fill=YELLOW)
        draw.text((176, bench_y + 238), _safe(data.get("capitao") or "—"), font=_font(18, "semibold"), fill=WHITE)
        draw.text((520, bench_y + 238), "Modelo", font=_font(18, "bold"), fill=MUTED)
        draw.text((600, bench_y + 238), title.split("•")[0].strip(), font=_font(18, "semibold"), fill=WHITE)
    else:
        draw.text((90, bench_y + 100), "Reservas não informados neste payload.", font=_font(24), fill=MUTED)

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
            if any(
                any(key in match for key in ("mandante", "visitante", "home", "away", "time_casa", "time_fora"))
                for match in candidates
            ):
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
    x1, y1, x2, y2 = box
    home = _safe(_match_value(match, "mandante", "home", "time_casa", "casa", "equipe_mandante"), "Mandante")
    away = _safe(_match_value(match, "visitante", "away", "time_fora", "fora", "equipe_visitante"), "Visitante")
    home_club = _safe(_match_value(match, "mandante_abrev", "home_abbr", "clube_mandante"), _abbr(home))
    away_club = _safe(_match_value(match, "visitante_abrev", "away_abbr", "clube_visitante"), _abbr(away))
    hs = _score(_match_value(match, "placar_mandante", "gols_mandante", "home_score", "gm", "placar_casa", default=None))
    aws = _score(_match_value(match, "placar_visitante", "gols_visitante", "away_score", "gv", "placar_fora", default=None))
    status = _clean_markdown(_match_value(match, "status", "situacao", "minuto", "fase", default="Programado"))
    date_time = _clean_markdown(_match_value(match, "data_hora", "data", "horario", "inicio", default=""))

    draw.text((x1 + 30, y1 + 24), f"JOGO {index:02d}", font=_font(19, "bold"), fill=MUTED)
    status_color = GREEN if any(token in status.lower() for token in ("encerr", "fim", "final")) else ORANGE if any(token in status.lower() for token in ("andamento", "ao vivo", "live", "interval")) else BLUE
    _round(draw, (x2 - 245, y1 + 20, x2 - 28, y1 + 70), 24, fill=status_color)
    _centered_text(draw, (x2 - 245, y1 + 20, x2 - 28, y1 + 70), status[:18].upper(), _font(18, "bold"), fill=(6, 22, 34))

    _paste_crest(image, home_club, (x1 + 120, y1 + 160), 104)
    _paste_crest(image, away_club, (x2 - 120, y1 + 160), 104)
    home_font = _fit_text(draw, home, 360, 30, 20, "bold")
    away_font = _fit_text(draw, away, 360, 30, 20, "bold")
    draw.text((x1 + 195, y1 + 125), home, font=home_font, fill=WHITE)
    away_box = draw.textbbox((0, 0), away, font=away_font)
    draw.text((x2 - 195 - (away_box[2] - away_box[0]), y1 + 125), away, font=away_font, fill=WHITE)

    score = f"{hs}  ×  {aws}"
    _round(draw, (image.size[0] // 2 - 160, y1 + 100, image.size[0] // 2 + 160, y1 + 205), 28, fill=(5, 24, 41), outline=LINE, width=2)
    _centered_text(draw, (image.size[0] // 2 - 160, y1 + 100, image.size[0] // 2 + 160, y1 + 205), score, _font(62, "bold"))
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
    _shadow_panel(image, (64, 330, width - 64, height - 145), radius=30, fill=PANEL)
    draw = ImageDraw.Draw(image)
    draw.text((100, 372), "INFORMAÇÕES DA PUBLICAÇÃO", font=_font(34, "bold"), fill=CYAN)
    message = _safe(data.get("mensagem_oficial") or data.get("mensagem") or data.get("texto"))
    lines: List[str] = []
    for raw in message.splitlines():
        clean = _clean_markdown(raw)
        if clean and "t.me/" not in clean and not clean.startswith("http"):
            lines.append(clean)
    y = 460
    for line in lines[:20]:
        for subline in textwrap.wrap(line, width=54)[:2]:
            draw.ellipse((100, y + 12, 115, y + 27), fill=ORANGE)
            draw.text((140, y), subline[:82], font=_font(27), fill=WHITE)
            y += 48
        y += 16
        if y > height - 220:
            break
    if not lines:
        draw.text((100, 480), "Publicação recebida sem dados estruturados.", font=_font(29), fill=MUTED)
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
