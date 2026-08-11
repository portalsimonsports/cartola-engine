from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from gerar_resultados_telegram import (
    OUTPUT_DIR,
    carregar_payload,
    enviar_album,
    enviar_foto,
    extrair_dados_publicacao,
    normalizar_dados_renderizacao,
    obter_bot_token_chat_id,
    validar_bot_e_destino,
)
from preparar_desempenho_rodada_anterior_v2 import (
    build_team_payload,
    build_top5_payload,
    club_index,
    score_records,
)
from render_aprovadas_v1 import VISUAL_VERSION, is_approved_event, render_approved_event
from render_desempenho_top5_v1 import is_top5_performance_event, render_top5_performance
from render_live_cards_v5 import render_live_publication_v5
from render_live_cobertura_v3 import is_coverage_event
from render_mercado_aberto_v2 import is_market_open_v2_event, render_market_open_v2
from render_notice_cards import is_notice_publication, render_notice_card

RENDERER_VERSION = "approved_cards_v1"
PIPELINE_VERSION = "approved_cards_v6_desempenho_times_top5_2026_08_11"


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _caption(rendered, data: Dict[str, Any]) -> str:
    caption = html.escape(_safe(rendered.caption or rendered.title, "Portal SimonSports"))
    return "\n".join(
        [
            f"<b>{caption}</b>",
            "",
            "📡 Portal SimonSports",
            "🔗 @dicascartolaportalsimonsports",
        ]
    )[:1024]


def _save_manifest(publications: List[Dict[str, Any]]) -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR, "ultima_publicacao.json").write_text(
        json.dumps(
            {
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "versao_visual": RENDERER_VERSION,
                "pipeline_visual": PIPELINE_VERSION,
                "base_visual": VISUAL_VERSION,
                "publicacoes": publications,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _joined_event(data: Dict[str, Any], payload_root: Dict[str, Any]) -> str:
    inner = payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {}
    values = [
        data.get("evento_programado"),
        data.get("tipo_publicacao"),
        payload_root.get("evento_programado"),
        payload_root.get("tipo_publicacao"),
        inner.get("evento_programado"),
        inner.get("tipo_publicacao"),
    ]
    return " ".join(_safe(value).upper() for value in values if value)


def _round_from_payload(data: Dict[str, Any], payload_root: Dict[str, Any]) -> int:
    inner = payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {}
    value = (
        data.get("rodada")
        or payload_root.get("rodada")
        or payload_root.get("rodada_finalizada")
        or inner.get("rodada")
        or inner.get("rodada_finalizada")
    )
    try:
        return int(float(value))
    except Exception as exc:
        raise RuntimeError(f"Desempenho sem rodada válida: {value!r}") from exc


def _team_performance_event(data: Dict[str, Any], payload_root: Dict[str, Any]) -> bool:
    joined = _joined_event(data, payload_root)
    return any(
        token in joined
        for token in (
            "DESEMPENHO_TIMES",
            "FECHAMENTO_FINAL_TIMES",
            "DESEMPENHO_FINAL_DOS_TIMES",
            "RESUMO_RODADA_ANTERIOR",
        )
    )


def _top5_performance_event(data: Dict[str, Any], payload_root: Dict[str, Any]) -> bool:
    joined = _joined_event(data, payload_root)
    return any(
        token in joined
        for token in (
            "DESEMPENHO_TOP5",
            "FECHAMENTO_FINAL_TOP5",
            "DESEMPENHO_FINAL_TOP5",
            "DESEMPENHO_DO_TOP5",
            "TOP5_FINAL",
        )
    )


def _hydrate_performance(data: Dict[str, Any], payload_root: Dict[str, Any]) -> Dict[str, Any]:
    is_team = _team_performance_event(data, payload_root)
    is_top5 = _top5_performance_event(data, payload_root)
    if not is_team and not is_top5:
        return data

    if is_team and isinstance(data.get("times"), dict) and data.get("times"):
        return data
    if is_top5 and isinstance(data.get("lista"), list) and data.get("lista"):
        return data

    rodada = _round_from_payload(data, payload_root)
    records = score_records(rodada)
    clubs = club_index(rodada)

    if is_team:
        enriched = build_team_payload(rodada, records, clubs)
        print(
            f"DESEMPENHO_TIMES enriquecido: rodada={rodada}; "
            f"modelos={len(enriched.get('times') or {})}"
        )
    else:
        enriched = build_top5_payload(rodada, records, clubs)
        print(
            f"DESEMPENHO_TOP5 enriquecido: rodada={rodada}; "
            f"localizados={enriched.get('pontuacoes_localizadas')}/"
            f"{enriched.get('total_top5')}"
        )

    result = dict(data)
    result.update(enriched)
    return result


def _render(data: Dict[str, Any]):
    if is_market_open_v2_event(data):
        return render_market_open_v2(data, output_dir=OUTPUT_DIR)
    if is_top5_performance_event(data):
        return render_top5_performance(data, output_dir=OUTPUT_DIR)
    if is_coverage_event(data):
        return render_live_publication_v5(data, output_dir=OUTPUT_DIR)
    if is_approved_event(data):
        return render_approved_event(data, output_dir=OUTPUT_DIR)
    if is_notice_publication(data):
        return render_notice_card(data, output_dir=OUTPUT_DIR)
    return render_live_publication_v5(data, output_dir=OUTPUT_DIR)


def executar_publicacao_aprovada() -> List[Dict[str, Any]]:
    payload_root = carregar_payload()
    token, chat_id = obter_bot_token_chat_id()
    validar_bot_e_destino(token, chat_id)

    raw_data = extrair_dados_publicacao(payload_root)
    data = normalizar_dados_renderizacao(raw_data)

    for key in (
        "evento_programado",
        "evento_github",
        "contexto",
        "tipo_publicacao",
        "rodada",
        "times",
        "lista",
        "partidas",
        "jogos",
    ):
        if not data.get(key) and payload_root.get(key) not in (None, ""):
            data[key] = payload_root.get(key)

    data = _hydrate_performance(data, payload_root)

    rendered = _render(data)
    if not rendered.files:
        raise RuntimeError("O renderizador aprovado não produziu imagens.")

    caption = _caption(rendered, data)
    if len(rendered.files) == 1:
        enviar_foto(rendered.files[0], caption)
    else:
        enviar_album(rendered.files, caption)

    publication = {
        "tipo_detectado": rendered.kind,
        "tipo_publicacao": data.get("tipo_publicacao") or payload_root.get("tipo_publicacao"),
        "evento_programado": data.get("evento_programado") or payload_root.get("evento_programado"),
        "rodada": data.get("rodada") or payload_root.get("rodada"),
        "arquivos": rendered.files,
        "titulo": rendered.title,
        "legenda": rendered.caption,
        "versao_visual": RENDERER_VERSION,
        "pipeline_visual": PIPELINE_VERSION,
        "base_visual": VISUAL_VERSION,
    }
    _save_manifest([publication])
    print(
        f"Publicação aprovada concluída: tipo={rendered.kind}; "
        f"imagens={len(rendered.files)}; base={VISUAL_VERSION}; pipeline={PIPELINE_VERSION}"
    )
    return [publication]


if __name__ == "__main__":
    executar_publicacao_aprovada()
