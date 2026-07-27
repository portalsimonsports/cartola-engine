from __future__ import annotations

from typing import Any, Dict

import gerar_resultados_telegram as publisher
import publicar_times_top5_automatico as base
import render_telegram_cards as rtc


PIPELINE_VERSION = "times_top5_aprovados_v2_2026_07_27"


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _event(payload_root: Dict[str, Any]) -> str:
    inner = payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {}
    return _safe(payload_root.get("evento_programado") or inner.get("evento_programado")).upper()


def _event_title(event: str, round_value: str, kind: str, model_name: str = "") -> tuple[str, str]:
    if event == "SELECAO_INICIAL":
        if kind == "top5":
            return f"TOP 5 INICIAL DA RODADA • RODADA {round_value}", "Mercado aberto • Primeira fotografia do Top 5"
        return f"SELEÇÃO INICIAL • RODADA {round_value}", "Mercado aberto • Seleção inicial da rodada"
    if event == "ATUALIZACAO_20H":
        return (f"{model_name} • RODADA {round_value}" if kind == "team" else f"TOP 5 DA RODADA • RODADA {round_value}", "Atualização programada das 20h")
    if event == "PRE_FECHAMENTO_TIMES":
        return f"{model_name} • RODADA {round_value}", "Pré-fechamento dos times"
    if event == "PRE_FECHAMENTO_TOP5":
        return f"TOP 5 DA RODADA • RODADA {round_value}", "Pré-fechamento do Top 5"
    if event == "CONFIRMADOS":
        if kind == "top5":
            return f"TOP 5 CONFIRMADO • RODADA {round_value}", "Versão final confirmada para a rodada"
        return f"{model_name} CONFIRMADO • RODADA {round_value}", "Escalação final confirmada para a rodada"
    return (f"{model_name} • RODADA {round_value}" if kind == "team" else f"TOP 5 DA RODADA • RODADA {round_value}", "Publicação programada do Portal SimonSports")


def _custom_top5_header(image, badge: str, subtitle: str, title: str) -> None:
    draw = rtc.ImageDraw.Draw(image)
    width, _ = image.size
    rtc._logo_ps(image, (640, 25, 780, 155))
    draw.text((815, 37), "PORTAL", font=rtc._font(29, "bold", True), fill=rtc.WHITE)
    draw.text((815, 76), "SIMON", font=rtc._font(44, "bold", True), fill=rtc.WHITE)
    draw.text((960, 76), "SPORTS", font=rtc._font(44, "bold", True), fill=rtc.CYAN)
    draw.text((816, 130), "CARTOLA • DADOS • ANÁLISE", font=rtc._font(18, "semibold"), fill=rtc.SILVER)
    badge_box = (1260, 38, 1532, 128)
    rtc._glow_outline(image, badge_box, rtc.CYAN, radius=28, blur=14, alpha=80)
    rtc._round(draw, badge_box, 28, fill=(4, 18, 36), outline=rtc.CYAN, width=3)
    rtc._centered_text(draw, badge_box, badge, rtc._font(38, "bold", True), fill=rtc.WHITE)

    font = rtc._fit_text(draw, title, 1500, 92, 50, "bold", True)
    if "•" in title:
        prefix, suffix = [part.strip() for part in title.split("•", 1)]
        left = prefix + " • "
        lb = draw.textbbox((0, 0), left, font=font)
        rb = draw.textbbox((0, 0), suffix, font=font)
        total = (lb[2] - lb[0]) + (rb[2] - rb[0])
        x = (width - total) / 2
        draw.text((x, 170), left, font=font, fill=rtc.WHITE)
        draw.text((x + lb[2] - lb[0], 170), suffix, font=font, fill=rtc.BLUE)
    else:
        box = draw.textbbox((0, 0), title, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, 170), title, font=font, fill=rtc.WHITE)
    sub_font = rtc._fit_text(draw, subtitle, 1400, 31, 22, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=sub_font)
    draw.text(((width - (sb[2] - sb[0])) / 2, 292), subtitle, font=sub_font, fill=rtc.CYAN)


def executar_pacote_aprovado():
    payload_root = publisher.carregar_payload()
    event = _event(payload_root)

    original_load = publisher.carregar_payload
    original_prepare = base._prepare_publication
    original_render = publisher.render_publication

    publisher.carregar_payload = lambda *args, **kwargs: payload_root

    def prepare(raw: Dict[str, Any]) -> Dict[str, Any]:
        data = original_prepare(raw)
        data["evento_programado"] = event
        blocks = data.get("blocos_topo")
        if not isinstance(blocks, list):
            blocks = []
        data["blocos_topo"] = blocks
        data["pipeline_visual"] = PIPELINE_VERSION
        return data

    def render(data: Dict[str, Any], output_dir: str):
        kind = rtc.detect_kind(data)
        round_value = _safe(data.get("rodada") or data.get("rodada_atual") or "ATUAL")
        model_name = _safe(data.get("nome_modelo") or data.get("titulo") or "TIME DA RODADA")
        title, subtitle = _event_title(event, round_value, kind, model_name)

        old_team_header = rtc._header_team
        old_top5_header = rtc._header_top5

        def team_header(image, _title, _subtitle, badge):
            return old_team_header(image, title, subtitle, badge)

        def top5_header(image, badge, _subtitle):
            return _custom_top5_header(image, badge, subtitle, title)

        rtc._header_team = team_header
        rtc._header_top5 = top5_header
        try:
            return rtc.render_publication(data, output_dir)
        finally:
            rtc._header_team = old_team_header
            rtc._header_top5 = old_top5_header

    base._prepare_publication = prepare
    publisher.render_publication = render
    try:
        return base.executar_pacote()
    finally:
        publisher.carregar_payload = original_load
        base._prepare_publication = original_prepare
        publisher.render_publication = original_render


if __name__ == "__main__":
    executar_pacote_aprovado()
