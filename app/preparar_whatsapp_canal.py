from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

OUTPUT_DIR = Path("output")
MANIFEST_PATH = OUTPUT_DIR / "ultima_publicacao.json"
OUTBOX_DIR = Path("data") / "whatsapp_outbox"
CURRENT_PATH = OUTBOX_DIR / "current.json"


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_text(publication: Dict[str, Any]) -> str:
    title = _safe(publication.get("titulo"), "Portal SimonSports")
    caption = _safe(publication.get("legenda"))
    parts = [title]
    if caption and caption.lower() != title.lower():
        parts.extend(["", caption])
    parts.extend(["", "📡 Portal SimonSports"])
    return "\n".join(parts).strip()


def _publication_key(publication: Dict[str, Any], files: List[Dict[str, str]]) -> str:
    fingerprint = {
        "tipo_detectado": publication.get("tipo_detectado"),
        "tipo_publicacao": publication.get("tipo_publicacao"),
        "evento_programado": publication.get("evento_programado"),
        "rodada": publication.get("rodada"),
        "files": files,
    }
    raw = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def preparar() -> Dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"Manifesto não encontrado: {MANIFEST_PATH}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    publications = manifest.get("publicacoes") or []
    if not isinstance(publications, list) or not publications:
        raise RuntimeError("Manifesto sem publicações para o WhatsApp.")

    items: List[Dict[str, Any]] = []
    for publication in publications:
        raw_files = publication.get("arquivos") or []
        files: List[Dict[str, str]] = []
        for raw_path in raw_files:
            path = Path(str(raw_path))
            if not path.exists():
                raise RuntimeError(f"Arquivo da publicação não encontrado: {path}")
            files.append(
                {
                    "path": path.as_posix(),
                    "sha256": _file_sha256(path),
                }
            )

        if not files:
            raise RuntimeError("Publicação sem mídia; espelhamento do canal foi bloqueado.")

        publication_id = _publication_key(publication, files)
        items.append(
            {
                "id": publication_id,
                "status": "PENDENTE_BRIDGE",
                "destino": "whatsapp_channel",
                "canal": "Portal SimonSports",
                "texto": _build_text(publication),
                "midias": files,
                "tipo_detectado": publication.get("tipo_detectado"),
                "tipo_publicacao": publication.get("tipo_publicacao"),
                "evento_programado": publication.get("evento_programado"),
                "rodada": publication.get("rodada"),
                "versao_visual": publication.get("versao_visual"),
                "pipeline_visual": publication.get("pipeline_visual"),
                "base_visual": publication.get("base_visual"),
            }
        )

    payload = {
        "schema": "portalsimonsports.whatsapp_channel_outbox.v1",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "origem": "telegram_approved_cards_pipeline",
        "politica": {
            "telegram_intacto": True,
            "falha_whatsapp_nao_bloqueia_telegram": True,
            "antiduplicidade_por_hash_de_conteudo": True,
        },
        "publicacoes": items,
    }

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Também persiste uma cópia imutável por hash para o bridge poder controlar reenvios.
    for item in items:
        unique_path = OUTBOX_DIR / f"{item['id']}.json"
        if not unique_path.exists():
            unique_path.write_text(
                json.dumps(
                    {
                        "schema": payload["schema"],
                        "gerado_em": payload["gerado_em"],
                        "origem": payload["origem"],
                        "politica": payload["politica"],
                        "publicacao": item,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    print(
        "WhatsApp outbox preparada: "
        f"{len(items)} publicação(ões); Telegram não foi alterado; "
        "status=PENDENTE_BRIDGE."
    )
    return payload


if __name__ == "__main__":
    preparar()
