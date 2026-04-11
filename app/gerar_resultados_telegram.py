# -*- coding: utf-8 -*-
"""
Portal SimonSports
Gerador de artes de resultados para Telegram

Fluxo:
- Lê PAYLOAD_JSON (enviado pelo GitHub Actions) OU arquivos em /data
- Lê a planilha Google via service account
- Busca a aba Telegram_Cartola para obter TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID
- Gera arte PNG em /output/resultados
- Evita duplicidade por hash em data/resultados_publicados.json
- Publica direto no Telegram

Variáveis de ambiente esperadas:
- GOOGLE_APPLICATION_CREDENTIALS = caminho do JSON da service account
- PLANILHA_ID = ID da planilha Google
- PAYLOAD_JSON = payload do repository_dispatch (opcional)

Estrutura esperada do payload (exemplo):
{
  "tipo": "resultados_resumos",
  "caption_link": "https://exemplo.com",
  "partidas": [...],
  "clubes": [...],
  "pontuados": [...]
}
"""

from __future__ import annotations

import os
import io
import re
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output" / "resultados"
STATE_FILE = DATA_DIR / "resultados_publicados.json"
PAYLOAD_FILE = DATA_DIR / "payload_dispatch.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CARD_W = 1024
CARD_H = 1536

BG_COLOR = (8, 20, 48)
CARD_COLOR = (36, 59, 97, 215)
WHITE = (255, 255, 255)
WHITE_SOFT = (235, 240, 248)
DIVIDER = (114, 132, 167, 130)
LINK_BLUE = (103, 166, 255)

REQUEST_TIMEOUT = 20


def safe_read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(text: Any) -> str:
    s = str(text or "").strip()
    return re.sub(r"\s+", " ", s)


def abbreviate_player(name: str) -> str:
    name = normalize_text(name)
    if not name:
        return ""
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0]
    if len(parts[0]) <= 2:
        return name
    return f"{parts[0][0]}. {parts[-1]}"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_18 = load_font(18, False)
FONT_20 = load_font(20, False)
FONT_22_B = load_font(22, True)
FONT_24_B = load_font(24, True)
FONT_28_B = load_font(28, True)
FONT_36_B = load_font(36, True)
FONT_40_B = load_font(40, True)
FONT_64_B = load_font(64, True)


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, y: int, fill=WHITE) -> None:
    w, _ = text_bbox(draw, text, font)
    x = int((CARD_W - w) / 2)
    draw.text((x, y), text, font=font, fill=fill)


def fetch_image(url: str) -> Optional[Image.Image]:
    url = normalize_text(url)
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None


def make_bg() -> Image.Image:
    bg = Image.new("RGBA", (CARD_W, CARD_H), BG_COLOR)
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    for i in range(0, CARD_H, 32):
        alpha = 18 if (i // 32) % 2 == 0 else 10
        od.rectangle((0, i, CARD_W, i + 16), fill=(20, 40, 90, alpha))

    bg = Image.alpha_composite(bg, overlay)

    grain = Image.effect_noise((CARD_W, CARD_H), 12).convert("L")
    grain = grain.filter(ImageFilter.GaussianBlur(0.3))
    grain_rgba = Image.new("RGBA", (CARD_W, CARD_H), (255, 255, 255, 0))
    grain_rgba.putalpha(grain.point(lambda p: int(p * 0.12)))
    bg = Image.alpha_composite(bg, grain_rgba)
    return bg


def rounded_card(base: Image.Image, box: Tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    card = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((0, 0, x2 - x1, y2 - y1), radius=36, fill=CARD_COLOR)

    shadow = Image.new("RGBA", (x2 - x1 + 30, y2 - y1 + 30), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((15, 15, x2 - x1 + 5, y2 - y1 + 5), radius=40, fill=(0, 0, 0, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))

    base.alpha_composite(shadow, (x1 - 15, y1 - 15))
    base.alpha_composite(card, (x1, y1))


def paste_shield_or_text(
    base: Image.Image,
    club: Dict[str, Any],
    box: Tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    shield = fetch_image(club.get("escudo", ""))

    if shield:
        shield.thumbnail((x2 - x1, y2 - y1), Image.LANCZOS)
        sx = x1 + int(((x2 - x1) - shield.width) / 2)
        sy = y1 + int(((y2 - y1) - shield.height) / 2)
        base.alpha_composite(shield, (sx, sy))
        return

    draw = ImageDraw.Draw(base)
    txt = normalize_text(club.get("abreviacao") or club.get("nome") or "TIME")[:12].upper()
    font = FONT_36_B
    tw, th = text_bbox(draw, txt, font)
    tx = x1 + int(((x2 - x1) - tw) / 2)
    ty = y1 + int(((y2 - y1) - th) / 2)
    draw.text((tx, ty), txt, font=font, fill=WHITE)


def draw_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    fill=WHITE_SOFT,
    line_spacing: int = 10,
    align: str = "left"
) -> None:
    x1, y1, x2, y2 = box
    lines = [line for line in text.split("\n") if normalize_text(line)]
    yy = y1

    for line in lines:
        if yy > y2:
            break

        lw, lh = text_bbox(draw, line, font)

        if align == "center":
            xx = x1 + int(((x2 - x1) - lw) / 2)
        elif align == "right":
            xx = x2 - lw
        else:
            xx = x1

        draw.text((xx, yy), line, font=font, fill=fill)
        yy += lh + line_spacing


def compute_hash(match: Dict[str, Any], scorers_home: List[str], scorers_away: List[str]) -> str:
    payload = {
        "id": match.get("id") or f"{match.get('casa_id')}x{match.get('visitante_id')}_{match.get('data')}_{match.get('hora')}",
        "placar_casa": match.get("placar_casa"),
        "placar_visitante": match.get("placar_visitante"),
        "status": match.get("status"),
        "goleadores_casa": scorers_home,
        "goleadores_visitante": scorers_away,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_goal_scorers(pontuados: List[Dict[str, Any]], club_id: Any) -> List[str]:
    target = str(club_id)
    out = []

    for item in pontuados:
        if str(item.get("clube_id")) != target:
            continue

        gols = int(item.get("gols", 0) or 0)
        if gols <= 0:
            continue

        nome = abbreviate_player(str(item.get("apelido", "")))
        out.append(f"{nome} ({gols}⚽)")

    return out


def build_club_map(clubes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for clube in clubes:
        cid = str(clube.get("id", "")).strip()
        if cid:
            out[cid] = clube
    return out


def sanitize_filename(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE)
    return text.strip("_")


def render_match_card(
    match: Dict[str, Any],
    clubes_map: Dict[str, Dict[str, Any]],
    pontuados: List[Dict[str, Any
