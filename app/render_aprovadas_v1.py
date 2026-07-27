from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

import render_live_cards_v2 as v2
import render_live_cards_v3 as v3
from render_telegram_cards import RenderOutput, _logo_ps


VISUAL_VERSION = "approved_cards_v1_2026_07_27"
CANVAS = (1600, 2000)

APPROVED_EVENTS = {
    "ABERTURA",
    "LEMBRETE_MERCADO_6H",
    "AVISO_30_MIN",
    "MERCADO_FECHADO",
    "FECHAMENTO_FINAL_TIMES",
    "RESUMO_FINAL_RODADA",
}


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", _safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def event_name(data: Dict[str, Any]) -> str:
    values = [
        data.get("evento_programado"),
        data.get("evento"),
        data.get("tipo_publicacao"),
        data.get("contexto"),
        data.get("titulo"),
    ]
    joined = " ".join(_norm(value) for value in values if value)
    aliases = (
        ("FECHAMENTO_FINAL_TIMES", ("FECHAMENTO_FINAL_TIMES", "DESEMPENHO_FINAL_DOS_TIMES", "RESUMO_RODADA_ANTERIOR")),
        ("RESUMO_FINAL_RODADA", ("RESUMO_FINAL_RODADA", "RESUMO_FINAL_DA_RODADA")),
        ("LEMBRETE_MERCADO_6H", ("LEMBRETE_MERCADO_6H", "LEMBRETE_DE_MERCADO", "LEMBRETE_MERCADO")),
        ("AVISO_30_MIN", ("AVISO_30_MIN", "AVISO_DE_FECHAMENTO", "TRAVA_30", "FECHAMENTO_EM_30")),
        ("MERCADO_FECHADO", ("MERCADO_FECHADO", "MERCADO_ENCERRADO")),
        ("ABERTURA", ("ABERTURA", "MERCADO_ABERTO")),
    )
    for canonical, tokens in aliases:
        if any(token in joined for token in tokens):
            return canonical
    return _norm(data.get("evento_programado"))


def is_approved_event(data: Dict[str, Any]) -> bool:
    return event_name(data) in APPROVED_EVENTS


def _round_value(data: Dict[str, Any]) -> str:
    value = data.get("rodada") or data.get("rodada_atual") or data.get("round")
    try:
        return str(int(float(value)))
    except Exception:
        return _safe(value, "ATUAL")


def _value(data: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if data.get(key) not in (None, ""):
            return data.get(key)
        lower = key.lower()
        if data.get(lower) not in (None, ""):
            return data.get(lower)
        upper = key.upper()
        if data.get(upper) not in (None, ""):
            return data.get(upper)
    return default


def _fmt_datetime(value: Any) -> str:
    text = _safe(value)
    if not text:
        return "A confirmar"
    match = re.search(r"(\d{2})[/-](\d{2})(?:[/-]\d{2,4})?[^0-9]*(\d{1,2}):(\d{2})", text)
    if match:
        return f"{match.group(1)}/{match.group(2)} • {int(match.group(3)):02d}:{match.group(4)}"
    return text.replace("T", " ")[:28]


def _closing_text(data: Dict[str, Any]) -> str:
    return _fmt_datetime(
        _value(
            data,
            "fechamento_mercado",
            "data_fechamento",
            "data_limite",
            "fechamento",
            "mercado_fecha_em",
            default="",
        )
    )


def _remaining_minutes(data: Dict[str, Any], fallback: int) -> int:
    for key in ("minutos_restantes", "restante_minutos", "tempo_restante_minutos", "diff_min"):
        raw = _value(data, key, default=None)
        if raw not in (None, ""):
            try:
                return max(0, int(round(float(str(raw).replace(",", ".")))))
            except Exception:
                pass
    text = " ".join(
        _safe(_value(data, key, default=""))
        for key in ("tempo_restante", "mensagem_oficial", "mensagem", "linhas")
    )
    hours = re.search(r"(\d+)\s*h", text, re.I)
    minutes = re.search(r"(\d+)\s*min", text, re.I)
    if hours or minutes:
        return (int(hours.group(1)) if hours else 0) * 60 + (int(minutes.group(1)) if minutes else 0)
    return fallback


def _format_countdown(minutes: int) -> Tuple[str, str]:
    hours, mins = divmod(max(0, minutes), 60)
    return f"{hours}h", f"{mins:02d}min"


def _background() -> Image.Image:
    image = v2._gradient_background(*CANVAS, stadium=False)
    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for x in range(-500, 2100, 260):
        draw.line((x, 0, x + 900, 2000), fill=(23, 111, 255, 18), width=4)
    layer = layer.filter(ImageFilter.GaussianBlur(6))
    image.alpha_composite(layer)
    return image


def _header(image: Image.Image, title: str, subtitle: str, round_value: str) -> None:
    draw = ImageDraw.Draw(image)
    _logo_ps(image, (64, 34, 202, 165))
    draw.text((232, 38), "PORTAL", font=v2._font(32, "bold", True), fill=v2.WHITE)
    draw.text((232, 76), "SIMON", font=v2._font(51, "bold", True), fill=v2.WHITE)
    draw.text((407, 76), "SPORTS", font=v2._font(51, "bold", True), fill=v2.BLUE)
    draw.text((234, 136), "CARTOLA • DADOS • ANÁLISE", font=v2._font(20, "semibold"), fill=v2.SILVER)

    badge = (1240, 42, 1535, 138)
    v2._glow_outline(image, badge, v2.CYAN, radius=30, blur=14, alpha=80)
    v2._round(draw, badge, 30, fill=(4, 17, 35), outline=v2.CYAN, width=3)
    v2._centered_text(draw, badge, f"RODADA {round_value}", v2._font(39, "bold", True), fill=v2.WHITE, y_offset=-3)

    font = v2._fit_text(draw, title, 1500, 76, 48, "bold", True)
    if "•" in title:
        prefix, suffix = [part.strip() for part in title.split("•", 1)]
        left = prefix + " • "
        lb = draw.textbbox((0, 0), left, font=font)
        rb = draw.textbbox((0, 0), suffix, font=font)
        total = (lb[2] - lb[0]) + (rb[2] - rb[0])
        x = (1600 - total) / 2
        draw.text((x, 190), left, font=font, fill=v2.WHITE)
        draw.text((x + lb[2] - lb[0], 190), suffix, font=font, fill=v2.BLUE)
    else:
        box = draw.textbbox((0, 0), title, font=font)
        draw.text(((1600 - (box[2] - box[0])) / 2, 190), title, font=font, fill=v2.WHITE)

    subfont = v2._fit_text(draw, subtitle, 1450, 31, 23, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=subfont)
    draw.text(((1600 - (sb[2] - sb[0])) / 2, 278), subtitle, font=subfont, fill=v2.MUTED)


def _footer(image: Image.Image, page: Tuple[int, int] | None = None) -> None:
    draw = ImageDraw.Draw(image)
    y = 1888
    draw.line((64, y, 1536, y), fill=(32, 91, 142), width=3)
    draw.ellipse((64, y + 18, 116, y + 70), fill=(28, 163, 227))
    v2._centered_text(draw, (64, y + 18, 116, y + 70), "➤", v2._font(26, "bold"), fill=v2.WHITE)
    draw.text((132, y + 25), "@dicascartolaportalsimonsports", font=v2._font(25, "semibold", True), fill=v2.WHITE)
    brand = "PORTAL SIMONSPORTS"
    bf = v2._font(32, "bold", True)
    bb = draw.textbbox((0, 0), brand, font=bf)
    draw.text((1536 - (bb[2] - bb[0]), y + 20), brand, font=bf, fill=v2.WHITE)
    if page:
        pf = v2._font(24, "bold", True)
        ptext = f"{page[0]}/{page[1]}"
        pb = draw.textbbox((0, 0), ptext, font=pf)
        draw.text(((1600 - (pb[2] - pb[0])) / 2, y + 29), ptext, font=pf, fill=v2.MUTED)


def _model_card(image: Image.Image, box: Tuple[int, int, int, int], title: str, accent: Tuple[int, int, int], icon: str, status: str) -> None:
    draw = ImageDraw.Draw(image)
    v2._glow_outline(image, box, accent, radius=28, blur=16, alpha=60)
    v2._shadow_panel(image, box, radius=28, fill=(4, 15, 30), outline=accent, shadow_alpha=100, outline_width=3)
    x1, y1, x2, y2 = box
    v2._centered_text(draw, (x1 + 12, y1 + 22, x2 - 12, y1 + 88), title, v2._fit_text(draw, title, x2 - x1 - 30, 28, 20, "bold", True), fill=accent)
    icon_box = ((x1 + x2) // 2 - 65, y1 + 100, (x1 + x2) // 2 + 65, y1 + 230)
    draw.ellipse(icon_box, outline=accent, width=6)
    v2._centered_text(draw, icon_box, icon, v2._font(65, "bold", True), fill=accent, y_offset=-4)
    draw.line((x1 + 60, y1 + 255, x2 - 60, y1 + 255), fill=accent, width=3)
    v2._centered_text(draw, (x1 + 20, y1 + 270, x2 - 20, y2 - 20), status, v2._fit_text(draw, status, x2 - x1 - 40, 38, 25, "bold", True), fill=v2.WHITE)


def render_abertura(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    image = _background()
    _header(image, f"ABERTURA DA RODADA • RODADA {r}", "Mercado aberto para a nova rodada do Cartola.", r)
    draw = ImageDraw.Draw(image)

    hero = (62, 355, 1538, 1025)
    v2._glow_outline(image, hero, v2.CYAN, radius=42, blur=25, alpha=85)
    v2._shadow_panel(image, hero, radius=42, fill=(3, 13, 28), outline=v2.CYAN, shadow_alpha=130, outline_width=4)
    door = (155, 485, 435, 900)
    draw.rectangle(door, outline=(65, 190, 255), width=15)
    draw.polygon([(185, 505), (405, 540), (405, 875), (185, 900)], outline=v2.CYAN, fill=(4, 20, 40))
    draw.ellipse((370, 690, 390, 710), fill=v2.WHITE)
    glow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rectangle((145, 475, 445, 910), outline=(31, 143, 255, 130), width=22)
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(24)))

    v2._centered_text(draw, (475, 430, 1455, 585), "MERCADO", v2._font(85, "bold", True), fill=v2.WHITE)
    v2._centered_text(draw, (475, 535, 1455, 760), "ABERTO!", v2._font(145, "bold", True), fill=v2.BLUE)
    msg = "Monte seu time, escale os titulares e busque a melhor pontuação."
    v2._centered_text(draw, (520, 780, 1420, 925), msg, v2._fit_text(draw, msg, 850, 42, 29, "semibold", True), fill=v2.SILVER)

    _model_card(image, (62, 1060, 520, 1515), "TIME ECONÔMICO", v2.GREEN, "$", "SELEÇÃO LIBERADA")
    _model_card(image, (571, 1060, 1029, 1515), "TIME INTERMEDIÁRIO", v2.CYAN, "↗", "SELEÇÃO LIBERADA")
    _model_card(image, (1080, 1060, 1538, 1515), "TIME PARA PONTUAR", v2.PURPLE, "◎", "SELEÇÃO LIBERADA")

    info = (62, 1550, 1538, 1848)
    v2._shadow_panel(image, info, radius=32, fill=(4, 17, 34), outline=v2.CYAN, shadow_alpha=95, outline_width=3)
    columns = [
        ("▣", "MERCADO", "ABERTO"),
        ("◷", "FECHAMENTO", _closing_text(data)),
        ("♢", "PUBLICAÇÕES", "PROGRAMADAS AO LONGO DO DIA"),
    ]
    for index, (icon, label, value) in enumerate(columns):
        x1 = 82 + index * 485
        if index:
            draw.line((x1 - 18, 1590, x1 - 18, 1810), fill=v2.LINE, width=3)
        draw.text((x1 + 10, 1610), icon, font=v2._font(63, "bold"), fill=v2.CYAN)
        draw.text((x1 + 100, 1608), label, font=v2._font(29, "bold", True), fill=v2.WHITE)
        vf = v2._fit_text(draw, value, 335, 34, 22, "bold", True)
        draw.text((x1 + 100, 1660), value, font=vf, fill=v2.BLUE)

    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"aprovada_abertura_rodada_{r}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "approved_abertura", f"Abertura da Rodada • Rodada {r}", f"Mercado Aberto • Rodada {r}")


def render_lembrete(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    minutes = _remaining_minutes(data, 360)
    hours_text, mins_text = _format_countdown(minutes)
    image = _background()
    _header(image, f"LEMBRETE DE MERCADO • RODADA {r}", "Tempo restante para o fechamento do mercado.", r)
    draw = ImageDraw.Draw(image)

    panel = (52, 370, 1548, 1310)
    v2._glow_outline(image, panel, v2.YELLOW, radius=42, blur=25, alpha=90)
    v2._shadow_panel(image, panel, radius=42, fill=(4, 14, 28), outline=v2.YELLOW, shadow_alpha=130, outline_width=4)
    bell = (690, 405, 910, 625)
    draw.ellipse(bell, outline=v2.YELLOW, width=8)
    v2._centered_text(draw, bell, "!", v2._font(120, "bold", True), fill=v2.YELLOW, y_offset=-10)

    hf = v2._font(225, "bold", True)
    mf = v2._font(130, "bold", True)
    hbox = draw.textbbox((0, 0), hours_text, font=hf)
    mbox = draw.textbbox((0, 0), mins_text, font=mf)
    total = (hbox[2] - hbox[0]) + 45 + (mbox[2] - mbox[0])
    x = (1600 - total) / 2
    draw.text((x, 610), hours_text, font=hf, fill=v2.YELLOW)
    draw.text((x + hbox[2] - hbox[0] + 45, 690), mins_text, font=mf, fill=v2.YELLOW)
    v2._centered_text(draw, (180, 930, 1420, 1020), "TEMPO RESTANTE PARA O FECHAMENTO", v2._font(39, "bold", True), fill=v2.SILVER)

    date_box = (175, 1055, 1425, 1205)
    v2._round(draw, date_box, 30, fill=(6, 20, 35), outline=v2.YELLOW, width=3)
    v2._centered_text(draw, date_box, f"DATA LIMITE   {_closing_text(data)}", v2._fit_text(draw, f"DATA LIMITE   {_closing_text(data)}", 1170, 54, 34, "bold", True), fill=v2.WHITE)

    lower = [(70, 1350, 780, 1710, "REVISE SUA ESCALAÇÃO", "Ajuste seu time e faça as melhores escolhas."), (820, 1350, 1530, 1710, "CONFIRA AS SELEÇÕES DO DIA", "Curadoria completa dos modelos SimonSports.")]
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
    return RenderOutput([path], "approved_lembrete_6h", f"Lembrete de Mercado • Rodada {r}", f"Lembrete de Mercado • Rodada {r}")


def render_aviso_30(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    minutes = _remaining_minutes(data, 30)
    image = _background()
    _header(image, f"AVISO DE FECHAMENTO • RODADA {r}", "O mercado fecha em 30 minutos.", r)
    draw = ImageDraw.Draw(image)

    panel = (58, 370, 1542, 1595)
    v2._glow_outline(image, panel, v2.ORANGE, radius=42, blur=25, alpha=100)
    v2._shadow_panel(image, panel, radius=42, fill=(7, 14, 25), outline=v2.ORANGE, shadow_alpha=140, outline_width=4)
    tri = [(800, 430), (720, 570), (880, 570)]
    draw.polygon(tri, outline=v2.RED, fill=(30, 10, 12))
    v2._centered_text(draw, (735, 450, 865, 555), "!", v2._font(86, "bold", True), fill=v2.RED)
    countdown = f"00:{max(0, min(59, minutes)):02d}"
    v2._centered_text(draw, (140, 585, 1460, 1020), countdown, v2._font(260, "bold", True), fill=v2.YELLOW)

    banner = (150, 1050, 1450, 1195)
    v2._round(draw, banner, 28, fill=(35, 20, 3), outline=v2.ORANGE, width=3)
    v2._centered_text(draw, banner, "ÚLTIMOS AJUSTES NA ESCALAÇÃO", v2._fit_text(draw, "ÚLTIMOS AJUSTES NA ESCALAÇÃO", 1180, 53, 35, "bold", True), fill=v2.WHITE)

    info = (150, 1230, 1450, 1390)
    v2._round(draw, info, 28, fill=(5, 20, 39), outline=v2.CYAN, width=3)
    info_text = f"DATA LIMITE: {_closing_text(data)}   •   LEMBRETE FINAL AUTOMÁTICO"
    v2._centered_text(draw, info, info_text, v2._fit_text(draw, info_text, 1190, 42, 28, "bold", True), fill=v2.WHITE)

    alert = (105, 1430, 1495, 1550)
    v2._round(draw, alert, 26, fill=(45, 7, 7), outline=v2.RED, width=3)
    v2._centered_text(draw, alert, "ATENÇÃO! FAÇA SEUS AJUSTES AGORA", v2._fit_text(draw, "ATENÇÃO! FAÇA SEUS AJUSTES AGORA", 1280, 53, 34, "bold", True), fill=v2.RED)

    bottom = (105, 1630, 1495, 1835)
    v2._shadow_panel(image, bottom, radius=30, fill=(4, 15, 30), outline=v2.ORANGE, shadow_alpha=100, outline_width=3)
    v2._centered_text(draw, bottom, "GARANTA SUA MELHOR PONTUAÇÃO!", v2._fit_text(draw, "GARANTA SUA MELHOR PONTUAÇÃO!", 1280, 56, 36, "bold", True), fill=v2.YELLOW)
    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"aprovada_aviso_30_min_rodada_{r}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "approved_aviso_30", f"Aviso de Fechamento • Rodada {r}", f"Mercado fecha em 30 minutos • Rodada {r}")


def render_mercado_fechado(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    image = _background()
    _header(image, f"MERCADO FECHADO • RODADA {r}", "Escalações travadas e rodada pronta para começar.", r)
    draw = ImageDraw.Draw(image)

    status = (55, 365, 1545, 575)
    v2._glow_outline(image, status, v2.RED, radius=35, blur=22, alpha=90)
    v2._shadow_panel(image, status, radius=35, fill=(20, 5, 8), outline=v2.RED, shadow_alpha=130, outline_width=4)
    draw.ellipse((90, 405, 230, 545), outline=v2.RED, width=8)
    v2._centered_text(draw, (90, 405, 230, 545), "×", v2._font(90, "bold", True), fill=v2.RED)
    draw.text((270, 405), "MERCADO ENCERRADO", font=v2._font(65, "bold", True), fill=v2.WHITE)
    draw.text((272, 485), "Todas as alterações foram bloqueadas com sucesso.", font=v2._font(29, "semibold", True), fill=v2.SILVER)
    close_badge = (1180, 415, 1495, 525)
    v2._round(draw, close_badge, 30, fill=v2.RED)
    v2._centered_text(draw, close_badge, "FECHADO", v2._font(45, "bold", True), fill=v2.WHITE)

    cards = [
        ((55, 615, 515, 1040), v2.GREEN, "TIMES CONFIRMADOS", "12/12", "Todas as escalações estão confirmadas."),
        ((570, 615, 1030, 1040), v2.CYAN, "PRONTO PARA A RODADA", "100%", "Elencos definidos e prontos para pontuar."),
        ((1085, 615, 1545, 1040), v2.ORANGE, "AGUARDANDO INÍCIO DOS JOGOS", "EM BREVE", "Monitoramento Live será iniciado automaticamente."),
    ]
    for box, accent, title, value, subtitle in cards:
        v2._shadow_panel(image, box, radius=30, fill=(4, 15, 30), outline=accent, shadow_alpha=100, outline_width=3)
        x1, y1, x2, y2 = box
        v2._centered_text(draw, (x1 + 25, y1 + 35, x2 - 25, y1 + 145), title, v2._fit_text(draw, title, x2 - x1 - 50, 38, 27, "bold", True), fill=v2.WHITE)
        v2._centered_text(draw, (x1 + 20, y1 + 150, x2 - 20, y1 + 290), value, v2._fit_text(draw, value, x2 - x1 - 40, 84, 48, "bold", True), fill=accent)
        v2._centered_text(draw, (x1 + 35, y1 + 300, x2 - 35, y2 - 30), subtitle, v2._fit_text(draw, subtitle, x2 - x1 - 70, 28, 21, "semibold", True), fill=v2.SILVER)

    draw.text((660, 1070), "OS TRÊS MODELOS", font=v2._font(35, "bold", True), fill=v2.WHITE)
    _model_card(image, (55, 1125, 515, 1595), "TIME ECONÔMICO", v2.GREEN, "✓", "ESCALAÇÃO CONFIRMADA")
    _model_card(image, (570, 1125, 1030, 1595), "TIME INTERMEDIÁRIO", v2.CYAN, "✓", "ESCALAÇÃO CONFIRMADA")
    _model_card(image, (1085, 1125, 1545, 1595), "TIME PARA PONTUAR", v2.PURPLE, "✓", "ESCALAÇÃO CONFIRMADA")

    banner = (55, 1640, 1545, 1840)
    v2._shadow_panel(image, banner, radius=30, fill=(35, 5, 7), outline=v2.RED, shadow_alpha=110, outline_width=3)
    v2._centered_text(draw, (80, 1660, 1520, 1750), f"RODADA {r} VEM FORTE!", v2._font(64, "bold", True), fill=v2.RED)
    v2._centered_text(draw, (80, 1750, 1520, 1820), "BONS TIMES, BONS MITOS E BOA SORTE A TODOS!", v2._font(34, "bold", True), fill=v2.WHITE)
    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"aprovada_mercado_fechado_rodada_{r}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "approved_mercado_fechado", f"Mercado Fechado • Rodada {r}", f"Mercado Fechado • Rodada {r}")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("C$", "").replace("pts", "").replace(",", ".").strip())
    except Exception:
        return default


def _model_key(value: Any) -> str:
    norm = _norm(value)
    if "ECON" in norm:
        return "ECONOMICO"
    if "INTER" in norm:
        return "INTERMEDIARIO"
    if "PONT" in norm or "IDEAL" in norm:
        return "PONTUACAO"
    return norm


def _parse_performance_lines(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    text_parts: List[str] = []
    raw_lines = data.get("linhas")
    if isinstance(raw_lines, list):
        text_parts.extend(_safe(line) for line in raw_lines)
    for key in ("mensagem_oficial", "mensagem", "texto"):
        if data.get(key):
            text_parts.append(_safe(data.get(key)))
    text = "\n".join(text_parts)
    result: Dict[str, Dict[str, Any]] = {}
    sections = re.split(r"(?=Sele[cç][aã]o\s+(?:ECON[OÔ]MICO|INTERMEDIARIO|INTERMEDIÁRIO|PONTUACAO|PONTUAÇÃO))", text, flags=re.I)
    for section in sections:
        match = re.search(r"Sele[cç][aã]o\s+([A-ZÀ-Ú]+)", section, re.I)
        if not match:
            continue
        key = _model_key(match.group(1))
        sem = re.search(r"Sem\s*C\)?\s*:\s*([-+\d.,]+)", section, re.I)
        com = re.search(r"Com\s*C\)?\s*:\s*([-+\d.,]+)", section, re.I)
        part = re.search(r"Participa[cç][aã]o\s*:\s*(\d+\s*/\s*\d+)", section, re.I)
        val = re.search(r"Valoriza[cç][aã]o\s*:\s*C\$?\s*([-+\d.,]+)", section, re.I)
        result[key] = {
            "pontos_sem_c": _float(sem.group(1) if sem else 0),
            "pontos_com_c": _float(com.group(1) if com else 0),
            "participacao": part.group(1).replace(" ", "") if part else "0/12",
            "valorizacao": _float(val.group(1) if val else 0),
        }
    return result


def _performance_data(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    candidates = data.get("times") or data.get("modelos") or data.get("desempenho") or data.get("resumo_times")
    result: Dict[str, Dict[str, Any]] = {}
    if isinstance(candidates, dict):
        iterable: Iterable[Tuple[Any, Any]] = candidates.items()
    elif isinstance(candidates, list):
        iterable = ((item.get("modelo") or item.get("tipo") or item.get("nome"), item) for item in candidates if isinstance(item, dict))
    else:
        iterable = []
    for raw_key, raw in iterable:
        if not isinstance(raw, dict):
            continue
        key = _model_key(raw_key)
        result[key] = {
            "pontos_sem_c": _float(_value(raw, "pontos_sem_c", "pontos_sem_capitao", "pontos", default=0)),
            "pontos_com_c": _float(_value(raw, "pontos_com_c", "pontos_com_capitao", "pontos_capitao", default=0)),
            "participacao": _safe(_value(raw, "participacao", "participação", default="0/12")),
            "valorizacao": _float(_value(raw, "valorizacao", "valorização", default=0)),
        }
    if not result:
        result = _parse_performance_lines(data)
    required = {"ECONOMICO", "INTERMEDIARIO", "PONTUACAO"}
    if not required.issubset(result):
        missing = sorted(required - set(result))
        raise RuntimeError("Resumo final dos times incompleto. Modelos ausentes: " + ", ".join(missing))
    return result


def _metric(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], label: str, value: str, accent: Tuple[int, int, int], icon: str) -> None:
    x1, y1, x2, y2 = box
    draw.ellipse((x1 + 22, y1 + 26, x1 + 92, y1 + 96), outline=accent, width=4)
    v2._centered_text(draw, (x1 + 22, y1 + 26, x1 + 92, y1 + 96), icon, v2._font(35, "bold", True), fill=accent)
    draw.text((x1 + 110, y1 + 24), label, font=v2._font(25, "bold", True), fill=v2.WHITE)
    vf = v2._fit_text(draw, value, x2 - x1 - 45, 55, 34, "bold", True)
    v2._centered_text(draw, (x1 + 15, y1 + 98, x2 - 15, y2 - 5), value, vf, fill=accent)


def render_desempenho_final(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    r = _round_value(data)
    performance = _performance_data(data)
    image = _background()
    _header(image, f"DESEMPENHO FINAL DOS TIMES • RODADA {r}", "Fechamento oficial da rodada anterior.", r)
    draw = ImageDraw.Draw(image)
    configs = [
        ("ECONOMICO", "TIME ECONÔMICO", v2.GREEN, "$"),
        ("INTERMEDIARIO", "TIME INTERMEDIÁRIO", v2.CYAN, "◇"),
        ("PONTUACAO", "TIME PARA PONTUAR", v2.PURPLE, "◎"),
    ]
    y = 360
    for key, title, accent, icon in configs:
        values = performance[key]
        box = (60, y, 1540, y + 430)
        v2._glow_outline(image, box, accent, radius=35, blur=20, alpha=65)
        v2._shadow_panel(image, box, radius=35, fill=(4, 15, 30), outline=accent, shadow_alpha=110, outline_width=3)
        draw.ellipse((105, y + 42, 215, y + 152), outline=accent, width=5)
        v2._centered_text(draw, (105, y + 42, 215, y + 152), icon, v2._font(58, "bold", True), fill=accent)
        draw.text((260, y + 48), title, font=v2._fit_text(draw, title, 800, 62, 44, "bold", True), fill=accent)
        final_box = (1210, y + 45, 1490, y + 145)
        v2._round(draw, final_box, 28, fill=tuple(max(0, c // 4) for c in accent), outline=accent, width=3)
        v2._centered_text(draw, final_box, "FINAL", v2._font(46, "bold", True), fill=v2.WHITE)
        metric_y = y + 180
        metric_w = 355
        metrics = [
            ("PONTOS (SEM C)", f"{values['pontos_sem_c']:.2f} pts", "▥"),
            ("PONTOS (COM C)", f"{values['pontos_com_c']:.2f} pts", "♛"),
            ("PARTICIPAÇÃO", _safe(values["participacao"], "0/12"), "●"),
            ("VALORIZAÇÃO", f"C$ {values['valorizacao']:.2f}", "↗"),
        ]
        for idx, (label, value, mic) in enumerate(metrics):
            x1 = 75 + idx * 370
            if idx:
                draw.line((x1 - 8, metric_y + 15, x1 - 8, metric_y + 205), fill=accent, width=2)
            _metric(draw, (x1, metric_y, x1 + metric_w, metric_y + 220), label, value, accent, mic)
        y += 455

    banner = (60, 1730, 1540, 1850)
    v2._round(draw, banner, 30, fill=(4, 20, 42), outline=v2.BLUE, width=3)
    v2._centered_text(draw, banner, "RESUMO FINAL AUTOMÁTICO • SIMONSPORTS", v2._font(44, "bold", True), fill=v2.WHITE)
    _footer(image)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"aprovada_desempenho_final_times_rodada_{r}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "approved_desempenho_final", f"Desempenho Final dos Times • Rodada {r}", f"Desempenho Final • Rodada {r}")


def _team_name(match: Dict[str, Any], home: bool) -> str:
    keys = ("mandante", "home", "time_casa", "casa", "equipe_mandante") if home else ("visitante", "away", "time_fora", "fora", "equipe_visitante")
    return _safe(v2._value(match, *keys, default="Mandante" if home else "Visitante"))


def _team_code(match: Dict[str, Any], home: bool) -> str:
    keys = ("mandante_abrev", "home_abbr", "clube_mandante", "codigo_mandante") if home else ("visitante_abrev", "away_abbr", "clube_visitante", "codigo_visitante")
    value = _safe(v2._value(match, *keys, default=""))
    if value:
        return value.upper()
    name = _team_name(match, home)
    words = re.findall(r"[A-Za-zÀ-ÿ]+", name)
    return ("".join(word[0] for word in words[:3]) if len(words) > 1 else name[:3]).upper()


def _score(match: Dict[str, Any], home: bool) -> str:
    keys = ("placar_mandante", "gols_mandante", "home_score", "gm", "placar_casa") if home else ("placar_visitante", "gols_visitante", "away_score", "gv", "placar_fora")
    value = v2._value(match, *keys, default="–")
    try:
        return str(int(float(value)))
    except Exception:
        return _safe(value, "–")


def _date_line(match: Dict[str, Any]) -> str:
    date = _safe(v2._value(match, "data", "data_jogo", default=""))
    time = _safe(v2._value(match, "hora", "horario", "hora_jogo", default=""))
    stadium = _safe(v2._value(match, "estadio", "estádio", "local", default=""))
    combined = _safe(v2._value(match, "data_hora", "inicio", default=""))
    parts = [part for part in (date or combined[:10], time or (combined[11:16] if "T" in combined else ""), stadium) if part]
    return " • ".join(parts)[:70]


def _draw_scorers(image: Image.Image, events: Sequence[v3.Event], box: Tuple[int, int, int, int], accent: Tuple[int, int, int], align_right: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    y = y1
    for event in list(events)[:3]:
        v3._draw_event_row(draw, x2 if align_right else x1, y, x2 - x1, event, accent, align_right=align_right, max_font=30, min_font=21)
        y += 48
        if y > y2 - 35:
            break


def _draw_summary_match(image: Image.Image, match: Dict[str, Any], box: Tuple[int, int, int, int], index: int) -> None:
    draw = ImageDraw.Draw(image)
    v2._glow_outline(image, box, v2.CYAN, radius=28, blur=12, alpha=35)
    v2._shadow_panel(image, box, radius=28, fill=(4, 15, 30), outline=v2.CYAN, shadow_alpha=95, outline_width=2)
    x1, y1, x2, y2 = box
    draw.text((x1 + 25, y1 + 18), f"JOGO {index:02d}", font=v2._font(24, "bold", True), fill=v2.BLUE)
    date_line = _date_line(match)
    if date_line:
        font = v2._fit_text(draw, date_line, 740, 25, 18, "semibold", True)
        v2._centered_text(draw, (x1 + 330, y1 + 8, x2 - 330, y1 + 60), date_line, font, fill=v2.MUTED)
    status = (x2 - 250, y1 + 16, x2 - 22, y1 + 72)
    v2._round(draw, status, 22, fill=(46, 202, 104))
    v2._centered_text(draw, status, "ENCERRADO", v2._font(21, "bold", True), fill=(3, 20, 20))

    home = _team_name(match, True)
    away = _team_name(match, False)
    hc, ac = _team_code(match, True), _team_code(match, False)
    v2._paste_crest(image, hc, (x1 + 120, y1 + 190), 140)
    v2._paste_crest(image, ac, (x2 - 120, y1 + 190), 140)
    hf = v2._fit_text(draw, home.upper(), 365, 38, 24, "bold", True)
    af = v2._fit_text(draw, away.upper(), 365, 38, 24, "bold", True)
    draw.text((x1 + 205, y1 + 135), home.upper(), font=hf, fill=v2.WHITE)
    ab = draw.textbbox((0, 0), away.upper(), font=af)
    draw.text((x2 - 205 - (ab[2] - ab[0]), y1 + 135), away.upper(), font=af, fill=v2.WHITE)

    score_box = ((x1 + x2) // 2 - 175, y1 + 105, (x1 + x2) // 2 + 175, y1 + 235)
    v2._round(draw, score_box, 28, fill=(3, 20, 40), outline=v2.CYAN, width=3)
    v2._centered_text(draw, score_box, f"{_score(match, True)}  ×  {_score(match, False)}", v2._font(72, "bold", True), fill=v2.WHITE)
    _draw_scorers(image, v3._events(match, True), (x1 + 205, y1 + 245, x1 + 570, y2 - 18), v2.CYAN)
    _draw_scorers(image, v3._events(match, False), (x2 - 570, y1 + 245, x2 - 205, y2 - 18), v2.BLUE, align_right=True)


def render_resumo_final_rodada(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Resumo final da rodada sem partidas estruturadas.")
    r = _round_value(data)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    pages = max(1, math.ceil(len(matches) / 4))
    files: List[str] = []
    for page in range(pages):
        image = _background()
        _header(image, f"RESUMO FINAL DA RODADA • RODADA {r}", "Placares oficiais e marcadores dos jogos.", r)
        y = 350
        chunk = matches[page * 4:(page + 1) * 4]
        for local_index, match in enumerate(chunk, start=1):
            global_index = page * 4 + local_index
            _draw_summary_match(image, match, (55, y, 1545, y + 350), global_index)
            y += 370
        _footer(image, (page + 1, pages))
        path = str(Path(output_dir) / f"aprovada_resumo_final_rodada_{r}_p{page + 1}.png")
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)
    return RenderOutput(files, "approved_resumo_final", f"Resumo Final da Rodada • Rodada {r}", f"Resumo Final da Rodada • Rodada {r}")


def render_approved_event(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    event = event_name(data)
    if event == "ABERTURA":
        return render_abertura(data, output_dir)
    if event == "LEMBRETE_MERCADO_6H":
        return render_lembrete(data, output_dir)
    if event == "AVISO_30_MIN":
        return render_aviso_30(data, output_dir)
    if event == "MERCADO_FECHADO":
        return render_mercado_fechado(data, output_dir)
    if event == "FECHAMENTO_FINAL_TIMES":
        return render_desempenho_final(data, output_dir)
    if event == "RESUMO_FINAL_RODADA":
        return render_resumo_final_rodada(data, output_dir)
    raise RuntimeError(f"Evento aprovado não suportado: {event!r}")
