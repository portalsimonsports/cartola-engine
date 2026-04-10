# -*- coding: utf-8 -*-
"""
Portal SimonSports
Gerador de artes de resultados para Telegram

Fluxo:
- Lê PAYLOAD_JSON (enviado pelo GitHub Actions) OU arquivos em /data
- Gera arte PNG em /output/resultados
- Evita duplicidade por hash em data/resultados_publicados.json
- Se houver bot_token/chat_id no payload, publica direto no Telegram

Estrutura esperada do payload (exemplo):
{
  "tipo": "resultados_resumos",
  "telegram_bot_token": "123:ABC",
  "telegram_chat_id": "-1001234567890",
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
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
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


def slugify(text: Any) -> str:
    s = normalize_text(text).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


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
    align: str = "left"
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
    pontuados: List[Dict[str, Any]]
) -> Tuple[Path, List[str], List[str]]:
    home_id = str(match.get("casa_id"))
    away_id = str(match.get("visitante_id"))

    home = clubes_map.get(home_id, {"nome": home_id, "abreviacao": home_id, "escudo": ""})
    away = clubes_map.get(away_id, {"nome": away_id, "abreviacao": away_id, "escudo": ""})

    scorers_home = extract_goal_scorers(pontuados, home_id)
    scorers_away = extract_goal_scorers(pontuados, away_id)

    img = make_bg()
    rounded_card(img, (70, 340, 954, 1130))
    draw = ImageDraw.Draw(img)

    # Topo
    top_text = f"📅 {normalize_text(match.get('data'))} • 🕒 {normalize_text(match.get('hora'))}"
    draw_centered(draw, top_text, FONT_40_B, 390, WHITE)

    stadium_text = f"🏟 {normalize_text(match.get('local', 'Estádio'))}"
    draw_centered(draw, stadium_text, FONT_36_B, 500, WHITE)

    # Escudos
    paste_shield_or_text(img, home, (120, 560, 350, 790))
    paste_shield_or_text(img, away, (674, 560, 904, 790))

    # Placar
    score = f"{match.get('placar_casa', 0)} x {match.get('placar_visitante', 0)}"
    draw_centered(draw, score, FONT_64_B, 660, WHITE)

    # Linha horizontal
    draw.line((110, 825, 914, 825), fill=DIVIDER, width=2)

    # Nomes dos times
    home_name = normalize_text(home.get("nome") or home.get("abreviacao") or home_id).upper()
    away_name = normalize_text(away.get("nome") or away.get("abreviacao") or away_id).upper()

    draw.text((115, 860), home_name, font=FONT_28_B, fill=WHITE)
    aw_w, _ = text_bbox(draw, away_name, FONT_28_B)
    draw.text((909 - aw_w, 860), away_name, font=FONT_28_B, fill=WHITE)

    # Divisória vertical
    draw.line((512, 920, 512, 1080), fill=DIVIDER, width=2)

    # Goleadores
    home_text = "\n".join(scorers_home) if scorers_home else ""
    away_text = "\n".join(scorers_away) if scorers_away else ""

    draw_multiline(draw, home_text, (115, 940, 470, 1080), FONT_24_B, WHITE_SOFT, 14, "left")
    draw_multiline(draw, away_text, (560, 940, 909, 1080), FONT_24_B, WHITE_SOFT, 14, "left")

    # Rodapé
    draw_centered(draw, "📺 Veja como foi", FONT_40_B, 1090, LINK_BLUE)

    filename = (
        f"resultado_{sanitize_filename(home_name)}_x_{sanitize_filename(away_name)}_"
        f"{sanitize_filename(normalize_text(match.get('data')))}_{sanitize_filename(normalize_text(match.get('hora')))}.png"
    )
    out_path = OUTPUT_DIR / filename
    img.convert("RGB").save(out_path, "PNG", optimize=True)

    return out_path, scorers_home, scorers_away


def send_telegram_photo(
    bot_token: str,
    chat_id: str,
    file_path: Path,
    caption_html: str
) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with file_path.open("rb") as fh:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": caption_html,
                "parse_mode": "HTML",
            },
            files={"photo": fh},
            timeout=REQUEST_TIMEOUT,
        )
    resp.raise_for_status()
    return resp.json()


def payload_or_fallback() -> Dict[str, Any]:
    env_payload = os.getenv("PAYLOAD_JSON", "").strip()
    if env_payload:
        try:
            return json.loads(env_payload)
        except Exception:
            pass

    file_payload = safe_read_json(PAYLOAD_FILE, {})
    if file_payload:
        return file_payload

    return {
        "tipo": "resultados_resumos",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "caption_link": "",
        "partidas": safe_read_json(DATA_DIR / "partidas_live.json", []),
        "clubes": safe_read_json(DATA_DIR / "clubes_resultados.json", []),
        "pontuados": safe_read_json(DATA_DIR / "pontuados_resultados.json", []),
    }


def ensure_state_file() -> Dict[str, Any]:
    state = safe_read_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("publicados", {})
    return state


def normalize_payload_lists(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    partidas = payload.get("partidas", [])
    clubes = payload.get("clubes", [])
    pontuados = payload.get("pontuados", [])

    if isinstance(partidas, dict):
        partidas = [partidas]
    if not isinstance(partidas, list):
        partidas = []

    if not isinstance(clubes, list):
        clubes = []
    if not isinstance(pontuados, list):
        pontuados = []

    return partidas, clubes, pontuados


def build_caption(match: Dict[str, Any], link: str) -> str:
    casa = normalize_text(match.get("casa_nome") or match.get("casa") or "")
    fora = normalize_text(match.get("visitante_nome") or match.get("visitante") or "")
    placar = f"{match.get('placar_casa', 0)} x {match.get('placar_visitante', 0)}"
    base = f"<b>{casa} {placar} {fora}</b>"
    if link:
        return f'{base}\n<a href="{link}">📺 Veja como foi</a>'
    return base


def main() -> None:
    payload = payload_or_fallback()
    partidas, clubes, pontuados = normalize_payload_lists(payload)

    if not partidas:
        print("Nenhuma partida encontrada no payload ou em data/partidas_live.json")
        return

    clubes_map = build_club_map(clubes)
    state = ensure_state_file()
    published = state.get("publicados", {})

    bot_token = normalize_text(
        payload.get("telegram_bot_token")
        or payload.get("bot_token")
        or payload.get("telegram", {}).get("bot_token")
    )
    chat_id = normalize_text(
        payload.get("telegram_chat_id")
        or payload.get("chat_id")
        or payload.get("telegram", {}).get("chat_id")
    )
    caption_link_default = normalize_text(
        payload.get("caption_link")
        or payload.get("link")
        or payload.get("telegram", {}).get("caption_link")
    )

    total_generated = 0
    total_sent = 0

    for match in partidas:
        output_path, scorers_home, scorers_away = render_match_card(match, clubes_map, pontuados)
        total_generated += 1

        match_id = str(
            match.get("id")
            or f"{match.get('casa_id')}x{match.get('visitante_id')}_{match.get('data')}_{match.get('hora')}"
        )

        current_hash = compute_hash(match, scorers_home, scorers_away)
        last_hash = published.get(match_id, "")

        if current_hash == last_hash:
            print(f"Sem alteração para {match_id}. Nada publicado.")
            continue

        published[match_id] = current_hash

        link = normalize_text(match.get("link_resumo") or match.get("url") or caption_link_default)
        caption_html = build_caption(match, link)

        if bot_token and chat_id:
            try:
                send_telegram_photo(bot_token, chat_id, output_path, caption_html)
                total_sent += 1
                print(f"Publicado no Telegram: {output_path.name}")
            except Exception as e:
                print(f"Falha ao publicar no Telegram ({match_id}): {e}")
        else:
            print(f"Arte gerada sem envio ao Telegram: {output_path.name}")

    state["publicados"] = published
    safe_write_json(STATE_FILE, state)

    print(f"Artes geradas: {total_generated}")
    print(f"Artes enviadas: {total_sent}")


if __name__ == "__main__":
    main()