from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from PIL import ImageDraw

import render_live_cards_v2 as v2
from render_telegram_cards import RenderOutput


# Mantém a mesma família visual aprovada pelo workflow Live V3.
VISUAL_VERSION = "live_cards_v3_eventos_vetoriais_2026_07_23"


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _clean(value: Any) -> str:
    text = v2._clean_markdown(value)
    text = text.replace("📡 Portal SimonSports", "")
    text = re.sub(r"🔗\s*https?://t\.me/\S+", "", text, flags=re.I)
    text = re.sub(r"🔗\s*@\S+", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _kind(data: Dict[str, Any]) -> str:
    return " ".join(
        _safe(data.get(key)).lower()
        for key in ("tipo_publicacao", "contexto", "evento_programado", "titulo")
        if data.get(key)
    )


def is_notice_publication(data: Dict[str, Any]) -> bool:
    kind = _kind(data)
    return any(
        token in kind
        for token in (
            "aviso",
            "mercado",
            "lembrete",
            "abertura",
            "fechado",
            "trava_30",
            "resumo_rodada_anterior",
        )
    )


def _accent(data: Dict[str, Any]):
    kind = _kind(data)
    if "fechado" in kind or "trava_30" in kind:
        return v2.RED
    if "abertura" in kind:
        return (33, 210, 125)
    if "lembrete" in kind or "mercado" in kind:
        return v2.YELLOW
    return v2.CYAN


def _default_title(data: Dict[str, Any]) -> str:
    title = _clean(data.get("titulo"))
    if title:
        return title

    kind = _kind(data)
    rodada = v2._round_value(data)

    if "abertura" in kind:
        return f"MERCADO ABERTO • RODADA {rodada}"
    if "fechado" in kind:
        return f"MERCADO FECHADO • RODADA {rodada}"
    if "trava_30" in kind:
        return f"FECHAMENTO EM 30 MIN • RODADA {rodada}"
    if "lembrete" in kind:
        return f"LEMBRETE DE MERCADO • RODADA {rodada}"
    if "resumo_rodada_anterior" in kind:
        return f"RESUMO FINAL • RODADA {rodada}"
    return f"INFORME CARTOLA • RODADA {rodada}"


def _subtitle(data: Dict[str, Any]) -> str:
    kind = _kind(data)
    if "abertura" in kind:
        return "Mercado aberto e monitoramento automático ativado."
    if "fechado" in kind:
        return "Mercado encerrado. Acompanhe a rodada e as parciais."
    if "trava_30" in kind:
        return "Janela final: escalações congeladas para confirmação."
    if "lembrete" in kind:
        return "Contagem regressiva oficial do mercado."
    if "resumo_rodada_anterior" in kind:
        return "Desempenho consolidado da rodada anterior."
    return "Atualização automática do Portal SimonSports."


def _lines(data: Dict[str, Any]) -> List[str]:
    raw = data.get("linhas")
    lines: List[str] = []

    if isinstance(raw, list):
        for value in raw:
            text = _clean(value)
            if text:
                lines.extend([line.strip() for line in text.splitlines() if line.strip()])

    if not lines:
        message = _clean(data.get("mensagem_oficial"))
        if message:
            lines = [line.strip() for line in message.splitlines() if line.strip()]

    filtered: List[str] = []
    title_norm = re.sub(r"\W+", " ", _default_title(data)).upper().strip()
    for line in lines:
        clean = line.strip(" •-_")
        if not clean:
            continue
        upper = re.sub(r"\W+", " ", clean).upper().strip()
        if not upper:
            continue
        if "PORTAL SIMONSPORTS" == upper:
            continue
        if "DICAS CARTOLA PORTAL SIMONSPORTS" in upper:
            continue
        if upper == title_norm:
            continue
        if "ATUALIZAÇÃO AUTOMÁTICA" in upper and "SIMONSPORTS" in upper:
            continue
        filtered.append(clean)

    return filtered[:18]


def _wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int = 48, min_size: int = 28):
    words = text.split()
    if not words:
        return [], v2._font(max_size, "semibold", True)

    for size in range(max_size, min_size - 1, -2):
        font = v2._font(size, "semibold", True)
        lines: List[str] = []
        current = ""
        ok = True
        for word in words:
            candidate = word if not current else current + " " + word
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                bbox_word = draw.textbbox((0, 0), current, font=font)
                if bbox_word[2] - bbox_word[0] > max_width:
                    ok = False
                    break
        if current:
            lines.append(current)
        if ok:
            return lines, font

    return [text], v2._font(min_size, "semibold", True)


def render_notice_card(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    round_value = v2._round_value(data)
    title = _default_title(data)
    subtitle = _subtitle(data)
    accent = _accent(data)
    body_lines = _lines(data)

    image = v2._gradient_background(*v2.RESULT_SIZE)
    draw = ImageDraw.Draw(image)

    v2._header_team(image, title, subtitle, v2._badge(data))

    panel = (72, 390, 1528, 1760)
    v2._glow_outline(image, panel, accent, radius=38, blur=22, alpha=60)
    v2._shadow_panel(
        image,
        panel,
        radius=38,
        fill=(4, 15, 30),
        outline=accent,
        shadow_alpha=105,
        outline_width=3,
    )

    label_box = (120, 440, 1480, 555)
    v2._round(draw, label_box, 28, fill=(5, 28, 50), outline=accent, width=2)

    kind = _kind(data)
    if "abertura" in kind:
        label = "MERCADO ABERTO"
    elif "fechado" in kind:
        label = "MERCADO FECHADO"
    elif "trava_30" in kind:
        label = "JANELA FINAL • 30 MIN"
    elif "lembrete" in kind:
        label = "CONTAGEM REGRESSIVA"
    elif "resumo_rodada_anterior" in kind:
        label = "RESUMO CONSOLIDADO"
    else:
        label = "INFORMAÇÕES DA PUBLICAÇÃO"

    v2._centered_text(
        draw,
        label_box,
        label,
        v2._fit_text(draw, label, 1180, 38, 26, "bold", True),
        fill=v2.WHITE,
    )

    y = 630
    max_width = 1260
    for index, line in enumerate(body_lines):
        wrapped, font = _wrap(draw, line, max_width, 46 if len(body_lines) <= 10 else 38, 26)
        bullet_color = accent if index < 3 else v2.CYAN
        for sub_index, wrapped_line in enumerate(wrapped):
            if y > 1640:
                break
            if sub_index == 0:
                draw.ellipse((138, y + 16, 158, y + 36), fill=bullet_color)
            draw.text((188, y), wrapped_line, font=font, fill=v2.WHITE)
            bbox = draw.textbbox((0, 0), wrapped_line, font=font)
            y += max(56, (bbox[3] - bbox[1]) + 20)
        y += 12
        if y > 1640:
            break

    if not body_lines:
        fallback = "Publicação automática programada pelo Portal SimonSports."
        font = v2._fit_text(draw, fallback, 1180, 48, 30, "semibold", True)
        v2._centered_text(draw, (170, 760, 1430, 960), fallback, font, fill=v2.SILVER)

    footer_box = (210, 1645, 1390, 1725)
    v2._round(draw, footer_box, 26, fill=(5, 24, 43), outline=v2.LINE, width=2)
    footer_text = "PUBLICAÇÃO AUTOMÁTICA • SIMONSPORTS"
    v2._centered_text(draw, footer_box, footer_text, v2._font(27, "bold", True), fill=v2.SILVER)

    v2._footer(image, 1888)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"live_aviso_v3_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)

    caption = title.replace(" • RODADA", " • Rodada")
    return RenderOutput([path], "notice_v3", title, caption)
