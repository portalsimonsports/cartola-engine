from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import gerar_resultados_telegram as publisher
from render_telegram_cards import detect_kind


TEAM_FILES: List[Tuple[str, str, str]] = [
    (
        "data/times_atual_pontuacao.json",
        "time_pontuacao",
        "TIME PARA PONTUAR",
    ),
    (
        "data/times_atual_intermediario.json",
        "time_intermediario",
        "TIME INTERMEDIÁRIO",
    ),
    (
        "data/times_atual_economico.json",
        "time_economico",
        "TIME ECONÔMICO",
    ),
]


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _round_number(data: Dict[str, Any]) -> str:
    return _safe(data.get("rodada") or data.get("rodada_atual"))


def _load_json(path: str) -> Dict[str, Any] | None:
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        print(f"Arquivo complementar ausente: {path}")
        return None
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Arquivo complementar inválido ({path}): {exc}")
        return None
    return value if isinstance(value, dict) else None


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


def _team_publications_for_round(current_round: str) -> List[Dict[str, Any]]:
    publications: List[Dict[str, Any]] = []
    for path, publication_type, title in TEAM_FILES:
        raw = _load_json(path)
        if not raw:
            continue
        normalized = publisher.normalizar_dados_renderizacao(raw)
        file_round = _round_number(normalized)
        if current_round and file_round != current_round:
            print(
                f"Ignorado {path}: rodada {file_round or 'não informada'} "
                f"é diferente da rodada atual {current_round}."
            )
            continue

        normalized["tipo_publicacao"] = publication_type
        normalized["titulo"] = title
        publications.append(normalized)
    return publications


def executar_pacote() -> List[Dict[str, Any]]:
    payload_root = publisher.carregar_payload()
    primary = publisher.normalizar_dados_renderizacao(
        publisher.extrair_dados_publicacao(payload_root)
    )

    token, chat_id = publisher.obter_bot_token_chat_id()
    publisher.validar_bot_e_destino(token, chat_id)

    queue: List[Dict[str, Any]] = [primary]
    queue.extend(
        publisher.normalizar_dados_renderizacao(item)
        for item in _embedded(payload_root)
    )

    primary_kind = detect_kind(primary)
    current_round = _round_number(primary)
    if primary_kind == "top5":
        queue.extend(_team_publications_for_round(current_round))

    results: List[Dict[str, Any]] = []
    seen = set()
    for item in queue:
        normalized = publisher.normalizar_dados_renderizacao(item)
        fingerprint = (
            _safe(normalized.get("tipo_publicacao")),
            _round_number(normalized),
            _safe(normalized.get("titulo")),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        results.append(
            publisher.publicar_dados(normalized, payload_root=payload_root)
        )

    publisher._save_manifest(results)
    print(f"Pacote automático concluído: {len(results)} publicação(ões).")
    return results


if __name__ == "__main__":
    executar_pacote()
