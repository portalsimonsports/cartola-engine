from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import gerar_resultados_telegram as publisher
from render_telegram_cards import render_publication


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


CURRENT_FILES = (
    ("top5_atual.json", "top5", "TOP 5 DA RODADA"),
    ("times_atual_economico.json", "time_economico", "TIME ECONÔMICO"),
    ("times_atual_intermediario.json", "time_intermediario", "TIME INTERMEDIÁRIO"),
    ("times_atual_pontuacao.json", "time_pontuacao", "TIME PARA PONTUAR"),
)


def carregar_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        print(f"Arquivo não encontrado ou vazio: {path}")
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def preparar_base(data: Dict[str, Any], publication_type: str, title: str) -> Dict[str, Any]:
    normalized = publisher.normalizar_dados_renderizacao(data)
    normalized["tipo_publicacao"] = publication_type
    normalized["titulo"] = title

    if publication_type.startswith("time_"):
        entries = normalized.get("dados")
        if isinstance(entries, list):
            starters = [
                item
                for item in entries
                if isinstance(item, dict)
                and str(item.get("status") or "TITULAR").upper() != "RESERVA"
            ]
            reserves = [
                item
                for item in entries
                if isinstance(item, dict)
                and str(item.get("status") or "").upper() == "RESERVA"
            ]
            normalized["jogadores"] = starters
            normalized["reservas"] = reserves
    return normalized


def main() -> None:
    generated = []
    for filename, publication_type, title in CURRENT_FILES:
        raw = carregar_json(DATA_DIR / filename)
        if not raw:
            continue
        data = preparar_base(raw, publication_type, title)
        rendered = render_publication(data, output_dir=str(OUTPUT_DIR))
        generated.extend(rendered.files)
        print(
            f"Arte profissional gerada: {publication_type} → "
            f"{', '.join(rendered.files)}"
        )

    if not generated:
        raise SystemExit("Nenhuma arte foi gerada.")
    print(f"Concluído: {len(generated)} imagem(ns) profissional(is).")


if __name__ == "__main__":
    main()
