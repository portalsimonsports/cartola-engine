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
from render_live_cards_v2 import render_live_publication_v2


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _caption(rendered, data: Dict[str, Any]) -> str:
    caption = html.escape(_safe(rendered.caption or rendered.title, "Portal SimonSports"))
    lines = [
        f"<b>{caption}</b>",
        "",
        "📡 Portal SimonSports",
        "🔗 @dicascartolaportalsimonsports",
    ]
    return "\n".join(lines)[:1024]


def _save_manifest(publications: List[Dict[str, Any]]) -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR, "ultima_publicacao.json").write_text(
        json.dumps(
            {
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "versao_visual": "live_cards_v2",
                "publicacoes": publications,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def executar_publicacao_v2() -> List[Dict[str, Any]]:
    payload_root = carregar_payload()
    token, chat_id = obter_bot_token_chat_id()
    validar_bot_e_destino(token, chat_id)

    raw_data = extrair_dados_publicacao(payload_root)
    data = normalizar_dados_renderizacao(raw_data)
    rendered = render_live_publication_v2(data, output_dir=OUTPUT_DIR)

    if not rendered.files:
        raise RuntimeError("O renderizador Live V2 não produziu imagens.")

    caption = _caption(rendered, data)
    if len(rendered.files) == 1:
        enviar_foto(rendered.files[0], caption)
    else:
        enviar_album(rendered.files, caption)

    publication = {
        "tipo_detectado": rendered.kind,
        "tipo_publicacao": data.get("tipo_publicacao") or payload_root.get("tipo_publicacao"),
        "rodada": data.get("rodada") or payload_root.get("rodada"),
        "arquivos": rendered.files,
        "titulo": rendered.title,
        "legenda": rendered.caption,
        "versao_visual": "live_cards_v2",
    }
    _save_manifest([publication])
    print(
        f"Publicação Live V2 concluída: tipo={rendered.kind}; "
        f"imagens={len(rendered.files)}"
    )
    return [publication]


if __name__ == "__main__":
    executar_publicacao_v2()
