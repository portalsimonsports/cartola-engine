from __future__ import annotations

import argparse
from pathlib import Path

from enriquecer_historico_jogadores_v1 import enrich_history
from gerar_video_dialogo_cartola_v7 import VERSION, generate as generate_v7

__all__ = ["VERSION", "generate", "main"]


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    enrich_history(round_value, repo_root)
    return generate_v7(round_value, repo_root, output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(
        generate(
            args.rodada,
            Path(args.repo_root).resolve(),
            Path(args.output),
        )
    )


if __name__ == "__main__":
    main()
