from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

import gerar_resultados_telegram as publisher
from render_telegram_cards import detect_kind


MODEL_TITLES = {
    "PONTUACAO": "TIME PARA PONTUAR",
    "INTERMEDIARIO": "TIME INTERMEDIÁRIO",
    "ECONOMICO": "TIME ECONÔMICO",
}


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFD", _safe(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def _round_number(data: Dict[str, Any]) -> str:
    return _safe(data.get("rodada") or data.get("rodada_atual"))


def _embedded(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    values: List[Dict[str, Any]] = []
    containers = [payload_root]
    if isinstance(payload_root.get("payload"), dict):
        containers.append(payload_root["payload"])

    for container in containers:
        for key in ("publicacoes", "publicações", "times"):
            items = container.get(key)
            if isinstance(items, list):
                values.extend(item for item in items if isinstance(item, dict))
    return values


def _detect_model(data: Dict[str, Any]) -> str:
    for value in (
        data.get("modelo"),
        data.get("nome_modelo"),
        data.get("tipo"),
    ):
        model = _slug(value)
        if model in MODEL_TITLES:
            return model

    blocks = data.get("blocos_topo") or []
    if isinstance(blocks, list):
        joined = " ".join(_safe(item) for item in blocks)
        normalized = _slug(joined)
        for model in MODEL_TITLES:
            if model in normalized:
                return model
    return ""


def _captain_name(data: Dict[str, Any]) -> str:
    snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    value = (
        data.get("capitao")
        or data.get("capitão")
        or snapshot.get("capitao")
        or snapshot.get("capitão")
        or meta.get("capitao")
        or meta.get("capitão")
        or ""
    )
    return re.sub(r"\s*\([^)]*\)\s*$", "", _safe(value)).strip()


def _prepare_team(data: Dict[str, Any]) -> Dict[str, Any]:
    model = _detect_model(data)
    model_slug = model.lower() if model else "geral"

    athletes = data.get("atletas")
    if not isinstance(athletes, list) or not athletes:
        athletes = data.get("jogadores")
    if not isinstance(athletes, list):
        athletes = []

    athletes = [item for item in athletes if isinstance(item, dict)]
    starters = [
        item
        for item in athletes
        if _safe(item.get("status") or "TITULAR").upper() != "RESERVA"
    ]
    reserves = [
        item
        for item in athletes
        if _safe(item.get("status")).upper() == "RESERVA"
    ]

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    blocks = data.get("blocos_topo") or []
    status_text = ""
    if isinstance(blocks, list) and len(blocks) >= 2:
        status_text = _safe(blocks[1])
    elif isinstance(blocks, list) and blocks:
        first = _safe(blocks[0])
        if "time" not in first.lower():
            status_text = first

    data["tipo_publicacao"] = f"time_{model_slug}"
    data["titulo"] = MODEL_TITLES.get(model, "TIME DA RODADA")
    data["jogadores"] = starters or athletes
    data["reservas"] = reserves
    data["formacao"] = _safe(
        data.get("formacao") or meta.get("esquema") or "4-3-3"
    )
    data["capitao"] = _captain_name(data)
    if status_text:
        data["blocos_topo"] = [status_text]

    # Mantém os dados oficiais enviados pelo GS para auditoria e uso visual futuro.
    if meta.get("custo_total") not in (None, ""):
        data["custo_total"] = meta.get("custo_total")
    if meta.get("pontos_total") not in (None, ""):
        data["pontos_total"] = meta.get("pontos_total")
    if model:
        data["modelo"] = model
        data["nome_modelo"] = MODEL_TITLES[model]
    return data


def _prepare_publication(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = publisher.normalizar_dados_renderizacao(raw)
    publication_type = _safe(data.get("tipo_publicacao")).lower()
    kind = detect_kind(data)

    if kind == "team" or publication_type == "times":
        return _prepare_team(data)
    return data


def _archive_payload(data: Dict[str, Any]) -> str:
    rodada = _round_number(data) or "atual"
    publication_type = _slug(data.get("tipo_publicacao") or detect_kind(data)).lower()
    archive_dir = Path("data/publicacoes_atuais")
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{publication_type}_rodada_{rodada}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Payload atual arquivado: {path}")
    return str(path)


def executar_pacote() -> List[Dict[str, Any]]:
    payload_root = publisher.carregar_payload()
    primary = publisher.extrair_dados_publicacao(payload_root)

    token, chat_id = publisher.obter_bot_token_chat_id()
    publisher.validar_bot_e_destino(token, chat_id)

    # Cada repository_dispatch do GS contém a publicação oficial daquela execução:
    # Econômico, Pontuação, Intermediário ou Top 5. Não usamos os antigos
    # data/times_atual_*.json, pois eles não são a fonte do dispatcher atual.
    queue: List[Dict[str, Any]] = [primary]
    queue.extend(_embedded(payload_root))

    results: List[Dict[str, Any]] = []
    seen = set()
    for item in queue:
        normalized = _prepare_publication(item)
        fingerprint = (
            _safe(normalized.get("tipo_publicacao")),
            _round_number(normalized),
            _safe(normalized.get("titulo")),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        _archive_payload(normalized)
        results.append(
            publisher.publicar_dados(normalized, payload_root=payload_root)
        )

    publisher._save_manifest(results)
    print(f"Disparo automático concluído: {len(results)} publicação(ões).")
    return results


if __name__ == "__main__":
    executar_pacote()
