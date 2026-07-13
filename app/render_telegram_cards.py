from __future__ import annotations

import math
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont


W = 1080
H = 1350
BG_TOP = (5, 15, 30)
BG_BOTTOM = (12, 35, 58)
PANEL = (14, 31, 51)
PANEL_2 = (20, 43, 68)
WHITE = (244, 248, 252)
MUTED = (153, 173, 194)
LINE = (48, 79, 108)
CYAN = (34, 211, 238)
BLUE = (38, 126, 255)
ORANGE = (255, 169, 54)
GREEN = (35, 184, 112)
YELLOW = (250, 204, 78)

POSITION_COLORS = {
    "GOL": (255, 191, 61),
    "LAT": (46, 213, 196),
    "ZAG": (93, 144, 255),
    "MEI": (166, 107, 255),
    "ATA": (255, 93, 118),
    "TEC": (151, 167, 184),
}
POSITION_LABELS = {
    "GOL": "GOLEIROS",
    "LAT": "LATERAIS",
    "ZAG": "ZAGUEIROS",
    "MEI": "MEIAS",
    "ATA": "ATACANTES",
    "TEC": "TÉCNICOS",
}


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


F14 = _font(14)
F16 = _font(16)
F18 = _font(18)
F20 = _font(20)
F22 = _font(22)
F24 = _font(24)
F26 = _font(26, "semibold")
F34 = _font(34, "bold")
F42 = _font(42, "bold")
F48 = _font(48, "bold")


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _clean_markdown(value: Any) -> str:
    text = _safe(value)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _money(value: Any) -> str:
    try:
        return f"C$ {float(str(value).replace(',', '.')):.2f}"
    except Exception:
        return "C$ --"


def _round(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _gradient_background(width: int = W, height: int = H) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_TOP)
    pixels = image.load()
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3))
        for x in range(width):
            glow = int(10 * max(0.0, 1.0 - math.hypot(x - width * 0.78, y - height * 0.16) / 700))
            pixels[x, y] = tuple(min(255, c + glow if i < 2 else c + glow * 2) for i, c in enumerate(color))
    return image


def _shadowed_panel(image: Image.Image, box: Tuple[int, int, int, int], radius: int = 24, fill=PANEL, outline=LINE) -> None:
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 7, y1 + 10, x2 + 7, y2 + 10), radius=radius, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _brand_header(image: Image.Image, title: str, subtitle: str, badge: str = "") -> None:
    draw = ImageDraw.Draw(image)
    _round(draw, (56, 44, 150, 138), 26, fill=(10, 55, 90), outline=CYAN, width=3)
    draw.text((82, 58), "PS", font=F34, fill=WHITE)
    draw.text((172, 48), "PORTAL", font=F20, fill=CYAN)
    draw.text((172, 73), "SIMONSPORTS", font=F34, fill=WHITE)
    draw.text((172, 113), "DADOS • ANÁLISE • CARTOLA", font=F14, fill=MUTED)

    if badge:
        bbox = draw.textbbox((0, 0), badge, font=F18)
        bw = bbox[2] - bbox[0] + 38
        _round(draw, (W - bw - 54, 58, W - 54, 108), 22, fill=(17, 63, 96), outline=CYAN, width=2)
        draw.text((W - bw - 35, 70), badge, font=F18, fill=WHITE)

    draw.line((56, 165, W - 56, 165), fill=LINE, width=2)
    draw.text((56, 194), title[:44], font=F48, fill=WHITE)
    draw.text((58, 252), subtitle[:80], font=F20, fill=MUTED)


def _footer(image: Image.Image, page: Optional[Tuple[int, int]] = None) -> None:
    draw = ImageDraw.Draw(image)
    draw.line((56, H - 90, W - 56, H - 90), fill=LINE, width=2)
    draw.text((56, H - 65), "@dicascartolaportalsimonsports", font=F18, fill=CYAN)
    draw.text((W - 318, H - 65), "PORTAL SIMONSPORTS", font=F18, fill=MUTED)
    if page:
        p, total = page
        draw.text((W // 2 - 24, H - 65), f"{p}/{total}", font=F18, fill=WHITE)


def _club_badge(draw: ImageDraw.ImageDraw, center: Tuple[int, int], club: str, radius: int = 27, fill=BLUE) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=WHITE, width=2)
    code = (_safe(club, "--")[:3]).upper()
    bbox = draw.textbbox((0, 0), code, font=F14)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 2), code, font=F14, fill=WHITE)


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


def _title_and_round(dados: Dict[str, Any], default_title: str) -> Tuple[str, str, str]:
    round_value = dados.get("rodada") or dados.get("rodada_atual") or ""
    title = _clean_markdown(dados.get("titulo") or default_title)
    if title.startswith("Atualização") and round_value:
        title = f"TOP 5 • RODADA {round_value}"
    subtitle_parts = []
    blocos = dados.get("blocos_topo") or []
    if isinstance(blocos, list) and blocos:
        subtitle_parts.append(_clean_markdown(blocos[0]))
    status = _clean_markdown(dados.get("status_mercado") or dados.get("status") or "")
    if status:
        subtitle_parts.append(status)
    subtitle = " • ".join([x for x in subtitle_parts if x]) or "Seleção atualizada pelo Portal SimonSports"
    badge = f"RODADA {round_value}" if round_value else "CARTOLA"
    return title or default_title, subtitle, badge


def _top5_groups(items: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups = {key: [] for key in POSITION_LABELS}
    for item in items:
        pos = _normalize_pos(item.get("pos") or item.get("posicao"))
        if pos in groups:
            groups[pos].append(item)
    for pos in groups:
        groups[pos] = groups[pos][:5]
    return groups


def _draw_rank_block(image: Image.Image, box: Tuple[int, int, int, int], pos: str, items: Sequence[Dict[str, Any]]) -> None:
    _shadowed_panel(image, box, radius=24, fill=PANEL)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    accent = POSITION_COLORS[pos]
    draw.rounded_rectangle((x1, y1, x1 + 12, y2), radius=6, fill=accent)
    draw.text((x1 + 30, y1 + 22), POSITION_LABELS[pos], font=F26, fill=WHITE)
    _round(draw, (x2 - 82, y1 + 16, x2 - 24, y1 + 54), 18, fill=accent)
    code_box = draw.textbbox((0, 0), pos, font=F16)
    draw.text((x2 - 53 - (code_box[2] - code_box[0]) / 2, y1 + 25), pos, font=F16, fill=(5, 16, 29))

    row_y = y1 + 74
    row_h = 60
    if not items:
        draw.text((x1 + 32, row_y + 20), "Sem dados disponíveis", font=F20, fill=MUTED)
        return
    for idx, item in enumerate(items, 1):
        yy = row_y + (idx - 1) * row_h
        if idx % 2 == 1:
            draw.rounded_rectangle((x1 + 22, yy, x2 - 22, yy + 52), radius=12, fill=PANEL_2)
        rank_color = accent if idx <= 3 else MUTED
        draw.text((x1 + 32, yy + 12), f"{idx:02d}", font=F18, fill=rank_color)
        _club_badge(draw, (x1 + 100, yy + 26), _safe(item.get("clube")), radius=20, fill=(27, 73, 112))
        name = _safe(item.get("nome"), "Jogador")
        if len(name) > 22:
            name = name[:21] + "…"
        draw.text((x1 + 132, yy + 9), name, font=F20, fill=WHITE)
        club = _safe(item.get("clube"), "--")
        draw.text((x1 + 134, yy + 32), club, font=F14, fill=MUTED)
        price = _money(item.get("preco") or item.get("preco_num"))
        bbox = draw.textbbox((0, 0), price, font=F18)
        draw.text((x2 - 30 - (bbox[2] - bbox[0]), yy + 16), price, font=F18, fill=accent)


def render_top5(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    items = dados.get("lista") or dados.get("jogadores") or []
    groups = _top5_groups(items if isinstance(items, list) else [])
    title, subtitle, badge = _title_and_round(dados, "TOP 5 DA RODADA")
    pages = [
        ("GOLEIROS • LATERAIS", ["GOL", "LAT"]),
        ("DEFESA • CRIAÇÃO", ["ZAG", "MEI"]),
        ("ATAQUE • COMISSÃO", ["ATA", "TEC"]),
    ]
    files: List[str] = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    round_value = _safe(dados.get("rodada") or "atual")

    for page_index, (page_title, positions) in enumerate(pages, 1):
        image = _gradient_background().convert("RGBA")
        _brand_header(image, title, f"{page_title} • {subtitle}", badge)
        block_y = 320
        block_h = 390
        for pos in positions:
            _draw_rank_block(image, (56, block_y, W - 56, block_y + block_h), pos, groups[pos])
            block_y += block_h + 24
        _footer(image, (page_index, len(pages)))
        path = str(Path(output_dir) / f"top5_rodada_{round_value}_p{page_index}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    caption = f"Top 5 da Rodada {round_value} • Portal SimonSports"
    return RenderOutput(files=files, kind="top5", title=title, caption=caption)


def _extract_team_players(dados: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("jogadores", "time", "escalacao", "lista", "atletas"):
        value = dados.get(key)
        if isinstance(value, list) and value:
            return [x for x in value if isinstance(x, dict)]
    collected: List[Dict[str, Any]] = []
    for pos in POSITION_LABELS:
        value = dados.get(pos) or dados.get(pos.lower())
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    clone = dict(item)
                    clone.setdefault("pos", pos)
                    collected.append(clone)
    return collected


def _field(image: Image.Image, box: Tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    stripe_h = max(1, (y2 - y1) // 10)
    for i in range(10):
        fill = (25, 119, 74) if i % 2 == 0 else (29, 132, 81)
        draw.rectangle((x1, y1 + i * stripe_h, x2, y1 + (i + 1) * stripe_h), fill=fill)
    draw.rounded_rectangle(box, radius=30, outline=(205, 242, 220), width=4)
    pad = 26
    draw.rectangle((x1 + pad, y1 + pad, x2 - pad, y2 - pad), outline=(205, 242, 220), width=3)
    mid_y = (y1 + y2) // 2
    draw.line((x1 + pad, mid_y, x2 - pad, mid_y), fill=(205, 242, 220), width=3)
    draw.ellipse((W // 2 - 72, mid_y - 72, W // 2 + 72, mid_y + 72), outline=(205, 242, 220), width=3)
    draw.ellipse((W // 2 - 5, mid_y - 5, W // 2 + 5, mid_y + 5), fill=(205, 242, 220))
    penalty_w = 330
    penalty_h = 130
    draw.rectangle((W // 2 - penalty_w // 2, y1 + pad, W // 2 + penalty_w // 2, y1 + pad + penalty_h), outline=(205, 242, 220), width=3)
    draw.rectangle((W // 2 - penalty_w // 2, y2 - pad - penalty_h, W // 2 + penalty_w // 2, y2 - pad), outline=(205, 242, 220), width=3)


def _line_positions(count: int, y: int, x1: int, x2: int) -> List[Tuple[int, int]]:
    if count <= 0:
        return []
    if count == 1:
        return [((x1 + x2) // 2, y)]
    step = (x2 - x1) / (count - 1)
    return [(int(x1 + i * step), y) for i in range(count)]


def _player_token(image: Image.Image, x: int, y: int, player: Dict[str, Any], color: Tuple[int, int, int], captain: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 45, y - 38, x + 45, y + 52), fill=(0, 0, 0, 80))
    draw.ellipse((x - 38, y - 46, x + 38, y + 30), fill=color, outline=WHITE, width=3)
    club = _safe(player.get("clube"), "--")[:3].upper()
    club_box = draw.textbbox((0, 0), club, font=F16)
    draw.text((x - (club_box[2] - club_box[0]) / 2, y - 30), club, font=F16, fill=WHITE)
    if captain:
        draw.ellipse((x + 24, y - 48, x + 52, y - 20), fill=YELLOW, outline=WHITE, width=2)
        draw.text((x + 33, y - 43), "C", font=F14, fill=(30, 30, 30))

    name = _safe(player.get("nome"), "Jogador")
    short = name if len(name) <= 18 else name[:17] + "…"
    name_box = draw.textbbox((0, 0), short, font=F18)
    label_w = max(148, name_box[2] - name_box[0] + 28)
    _round(draw, (x - label_w // 2, y + 38, x + label_w // 2, y + 93), 16, fill=(7, 28, 43), outline=(161, 212, 190), width=2)
    draw.text((x - (name_box[2] - name_box[0]) / 2, y + 47), short, font=F18, fill=WHITE)
    price = _money(player.get("preco") or player.get("preco_num"))
    price_box = draw.textbbox((0, 0), price, font=F14)
    draw.text((x - (price_box[2] - price_box[0]) / 2, y + 72), price, font=F14, fill=(180, 240, 211))


def render_team(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    players = _extract_team_players(dados)
    groups: Dict[str, List[Dict[str, Any]]] = {key: [] for key in POSITION_LABELS}
    for player in players:
        pos = _normalize_pos(player.get("pos") or player.get("posicao"))
        if pos in groups:
            groups[pos].append(player)

    title, subtitle, badge = _title_and_round(dados, "TIME DA RODADA")
    kind_raw = _safe(dados.get("tipo_publicacao") or "time").lower()
    if "econom" in kind_raw:
        title = f"TIME ECONÔMICO • {badge}"
    elif "intermedi" in kind_raw:
        title = f"TIME INTERMEDIÁRIO • {badge}"
    elif "pontua" in kind_raw or "ideal" in kind_raw:
        title = f"TIME PARA PONTUAR • {badge}"
    elif "time" in kind_raw:
        title = f"TIME DA RODADA • {badge}"

    image = _gradient_background().convert("RGBA")
    _brand_header(image, title, subtitle, badge)
    draw = ImageDraw.Draw(image)
    field_box = (56, 360, W - 56, 1190)
    total = 0.0
    for player in players:
        try:
            total += float(str(player.get("preco") or player.get("preco_num") or 0).replace(',', '.'))
        except Exception:
            pass
    formation = _safe(dados.get("formacao")) or f"{len(groups['LAT']) + len(groups['ZAG'])}-{len(groups['MEI'])}-{len(groups['ATA'])}"
    coach = groups["TEC"][0] if groups["TEC"] else None
    _shadowed_panel(image, (56, 300, W - 56, 346), radius=20, fill=(12, 38, 60))
    draw.text((78, 311), f"FORMAÇÃO {formation}", font=F18, fill=CYAN)
    draw.text((340, 311), f"PATRIMÔNIO {_money(total)}", font=F18, fill=ORANGE)
    if coach:
        coach_name = _safe(coach.get("nome"))
        if len(coach_name) > 22:
            coach_name = coach_name[:21] + "…"
        draw.text((690, 311), f"TÉC. {coach_name}", font=F18, fill=WHITE)

    _field(image, field_box)
    x1, y1, x2, _ = field_box
    field_margin = 115
    lines = [
        (groups["ATA"], y1 + 115, POSITION_COLORS["ATA"]),
        (groups["MEI"], y1 + 330, POSITION_COLORS["MEI"]),
        (groups["LAT"] + groups["ZAG"], y1 + 545, POSITION_COLORS["ZAG"]),
        (groups["GOL"][:1], y1 + 720, POSITION_COLORS["GOL"]),
    ]
    captain_name = _safe(dados.get("capitao") or dados.get("capitão")).lower()
    for line_players, y, color in lines:
        coords = _line_positions(len(line_players), y, x1 + field_margin, x2 - field_margin)
        for player, (x, yy) in zip(line_players, coords):
            player_name = _safe(player.get("nome")).lower()
            captain = bool(player.get("capitao") or player.get("capitão")) or (captain_name and captain_name == player_name)
            _player_token(image, x, yy, player, color, captain)

    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    round_value = _safe(dados.get("rodada") or "atual")
    slug = re.sub(r"[^a-z0-9]+", "_", kind_raw).strip("_") or "time"
    path = str(Path(output_dir) / f"{slug}_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    caption = f"{title.title()} • Portal SimonSports"
    return RenderOutput(files=[path], kind="team", title=title, caption=caption)


def _extract_matches(dados: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("partidas", "jogos", "resultados", "lista", "matches"):
        value = dados.get(key)
        if isinstance(value, list) and value:
            candidates = [x for x in value if isinstance(x, dict)]
            if any(any(k in item for k in ("mandante", "visitante", "home", "away", "time_casa", "time_fora")) for item in candidates):
                return candidates
    return []


def _match_value(match: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in match and match.get(key) not in (None, ""):
            return match.get(key)
    return default


def _score_text(value: Any) -> str:
    if value is None or value == "":
        return "–"
    try:
        return str(int(float(value)))
    except Exception:
        return _safe(value, "–")


def _team_abbr(name: str) -> str:
    name = _safe(name, "---")
    cleaned = re.sub(r"[^A-Za-zÀ-ÿ0-9 ]", "", name).strip()
    if len(cleaned) <= 4:
        return cleaned.upper()
    words = [word for word in cleaned.split() if word]
    if len(words) >= 2:
        return "".join(word[0] for word in words[:3]).upper()
    return cleaned[:3].upper()


def _draw_match_card(image: Image.Image, box: Tuple[int, int, int, int], match: Dict[str, Any], index: int) -> None:
    _shadowed_panel(image, box, radius=24, fill=PANEL)
    draw = ImageDraw.Draw(image)
    x1, y1, x2, _ = box
    home = _safe(_match_value(match, "mandante", "home", "time_casa", "casa", "equipe_mandante"), "Mandante")
    away = _safe(_match_value(match, "visitante", "away", "time_fora", "fora", "equipe_visitante"), "Visitante")
    home_score = _score_text(_match_value(match, "placar_mandante", "gols_mandante", "home_score", "gm", "placar_casa", default=None))
    away_score = _score_text(_match_value(match, "placar_visitante", "gols_visitante", "away_score", "gv", "placar_fora", default=None))
    status = _clean_markdown(_match_value(match, "status", "situacao", "minuto", "fase", default="Programado"))
    date_time = _clean_markdown(_match_value(match, "data_hora", "data", "horario", "inicio", default=""))

    draw.text((x1 + 24, y1 + 18), f"JOGO {index:02d}", font=F14, fill=MUTED)
    status_color = GREEN if any(token in status.lower() for token in ("encerr", "fim", "final")) else ORANGE if any(token in status.lower() for token in ("andamento", "ao vivo", "live", "interval")) else BLUE
    _round(draw, (x2 - 178, y1 + 14, x2 - 22, y1 + 48), 16, fill=status_color)
    status_box = draw.textbbox((0, 0), status[:16].upper(), font=F14)
    draw.text((x2 - 100 - (status_box[2] - status_box[0]) / 2, y1 + 23), status[:16].upper(), font=F14, fill=(5, 20, 30))

    _club_badge(draw, (x1 + 70, y1 + 93), _team_abbr(home), radius=29, fill=(31, 89, 138))
    _club_badge(draw, (x2 - 70, y1 + 93), _team_abbr(away), radius=29, fill=(31, 89, 138))
    home_display = home if len(home) <= 22 else home[:21] + "…"
    away_display = away if len(away) <= 22 else away[:21] + "…"
    draw.text((x1 + 112, y1 + 69), home_display, font=F22, fill=WHITE)
    away_box = draw.textbbox((0, 0), away_display, font=F22)
    draw.text((x2 - 112 - (away_box[2] - away_box[0]), y1 + 69), away_display, font=F22, fill=WHITE)

    score_box = (W // 2 - 112, y1 + 55, W // 2 + 112, y1 + 132)
    _round(draw, score_box, 22, fill=(5, 24, 41), outline=LINE, width=2)
    score = f"{home_score}  ×  {away_score}"
    bbox = draw.textbbox((0, 0), score, font=F42)
    draw.text((W // 2 - (bbox[2] - bbox[0]) / 2, y1 + 68), score, font=F42, fill=WHITE)
    if date_time:
        short_date = date_time[:42]
        date_box = draw.textbbox((0, 0), short_date, font=F14)
        draw.text((W // 2 - (date_box[2] - date_box[0]) / 2, y1 + 144), short_date, font=F14, fill=MUTED)


def render_results(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = _extract_matches(dados)
    title, subtitle, badge = _title_and_round(dados, "RESULTADOS DA RODADA")
    round_value = _safe(dados.get("rodada") or "atual")
    per_page = 5
    total_pages = max(1, math.ceil(len(matches) / per_page))
    files: List[str] = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if not matches:
        matches = [{"mandante": "Aguardando", "visitante": "dados das partidas", "status": "Sem resultados"}]
        total_pages = 1

    for page_index in range(total_pages):
        page_matches = matches[page_index * per_page:(page_index + 1) * per_page]
        image = _gradient_background().convert("RGBA")
        _brand_header(image, title, subtitle, badge)
        y = 320
        for idx, match in enumerate(page_matches, start=page_index * per_page + 1):
            _draw_match_card(image, (56, y, W - 56, y + 165), match, idx)
            y += 181
        _footer(image, (page_index + 1, total_pages))
        path = str(Path(output_dir) / f"resultados_rodada_{round_value}_p{page_index + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    caption = f"Resultados da Rodada {round_value} • Portal SimonSports"
    return RenderOutput(files=files, kind="results", title=title, caption=caption)


def _message_lines(message: str) -> List[str]:
    lines: List[str] = []
    for raw in _safe(message).splitlines():
        cleaned = _clean_markdown(raw)
        if cleaned and not cleaned.startswith("http") and "t.me/" not in cleaned:
            lines.append(cleaned)
    return lines


def render_bulletin(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    title, subtitle, badge = _title_and_round(dados, "BOLETIM CARTOLA")
    message = _safe(dados.get("mensagem_oficial") or dados.get("mensagem") or dados.get("texto"))
    lines = _message_lines(message)
    image = _gradient_background().convert("RGBA")
    _brand_header(image, title, subtitle, badge)
    _shadowed_panel(image, (56, 320, W - 56, H - 130), radius=28, fill=PANEL)
    draw = ImageDraw.Draw(image)
    draw.text((88, 352), "INFORMAÇÕES DA PUBLICAÇÃO", font=F24, fill=CYAN)
    y = 410
    for line in lines[:18]:
        wrapped = textwrap.wrap(line, width=56) or [line]
        for subline in wrapped[:2]:
            draw.ellipse((88, y + 8, 98, y + 18), fill=ORANGE)
            draw.text((118, y), subline[:78], font=F20, fill=WHITE)
            y += 34
        y += 10
        if y > H - 190:
            break
    if not lines:
        draw.text((88, 430), "A publicação foi recebida, mas não contém dados estruturados.", font=F22, fill=MUTED)
    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / "boletim_cartola.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput(files=[path], kind="bulletin", title=title, caption="Boletim Cartola • Portal SimonSports")


def detect_kind(dados: Dict[str, Any]) -> str:
    kind = _safe(dados.get("tipo_publicacao") or dados.get("tipo") or dados.get("contexto")).lower()
    if any(token in kind for token in ("resultado", "placar", "partida", "live")):
        return "results"
    if any(token in kind for token in ("time", "campinho", "escalacao", "escalação", "econom", "intermedi", "pontua", "ideal")):
        return "team"
    if "top5" in kind or "top 5" in kind:
        return "top5"
    if _extract_matches(dados):
        return "results"
    if any(key in dados for key in ("jogadores", "time", "escalacao", "atletas")):
        return "team"
    items = dados.get("lista")
    if isinstance(items, list) and items:
        positions = {_normalize_pos(item.get("pos") or item.get("posicao")) for item in items if isinstance(item, dict)}
        if positions & set(POSITION_LABELS):
            counts = {
                pos: sum(
                    1
                    for item in items
                    if isinstance(item, dict)
                    and _normalize_pos(item.get("pos") or item.get("posicao")) == pos
                )
                for pos in POSITION_LABELS
            }
            if max(counts.values() or [0]) >= 4:
                return "top5"
            return "team"
    return "bulletin"


def render_publication(dados: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    kind = detect_kind(dados)
    if kind == "top5":
        return render_top5(dados, output_dir)
    if kind == "team":
        return render_team(dados, output_dir)
    if kind == "results":
        return render_results(dados, output_dir)
    return render_bulletin(dados, output_dir)
