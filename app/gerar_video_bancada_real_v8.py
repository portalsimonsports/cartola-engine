from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "cartola_bancada_real_v8_2026_07_31"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Correção V8 não aplicada; trecho ausente: {label}")
    return text.replace(old, new, 1)


def build_patched_source(source: str) -> str:
    source = replace_once(
        source,
        'VERSION = "cartola_bancada_real_v7_2026_07_31"',
        f'VERSION = "{VERSION}"',
        "versão",
    )
    source = replace_once(
        source,
        'image = Image.new("RGBA", (WIDTH, HEIGHT), (2, 10, 15, 255))\n    draw = ImageDraw.Draw(image)\n    accent = PRESENTERS[segment.speaker]["accent"]',
        'image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))\n    draw = ImageDraw.Draw(image)\n    accent = PRESENTERS[segment.speaker]["accent"]',
        "overlay transparente",
    )
    source = replace_once(
        source,
        'draw.rounded_rectangle((24, 88, 936, 608), radius=18, fill=(0, 0, 0, 255), outline=accent + (255,), width=3)',
        'draw.rounded_rectangle((24, 88, 936, 608), radius=18, fill=None, outline=accent + (255,), width=3)',
        "área dos apresentadores sem preenchimento",
    )
    source = replace_once(
        source,
        'y_expr = "(ih-ih/{z})/2"',
        'y_expr = "(ih-ih/{z})/2".format(z=zoom)',
        "expressão vertical",
    )
    source = replace_once(
        source,
        'video_filter = shot_filter(segment.shot, index)',
        'video_filter = shot_filter("wide", index)',
        "plano geral consistente",
    )
    source = replace_once(
        source,
        'stock = stock_files[segment.source_index % len(stock_files)]',
        'stock = stock_files[0]',
        "mesmo trio em todas as cenas",
    )
    source = replace_once(
        source,
        '"plano": segment.shot,',
        '"plano": "wide",',
        "manifesto do plano",
    )
    source = replace_once(
        source,
        '"filmagem": STOCK_SOURCES[segment.source_index % len(STOCK_SOURCES)]["id"],',
        '"filmagem": STOCK_SOURCES[0]["id"],',
        "manifesto da filmagem",
    )
    source = replace_once(
        source,
        '''run([\n            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),\n            "-c", "copy", "-movflags", "+faststart", str(output_path),\n        ])''',
        '''run([\n            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),\n            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",\n            "-af", "aresample=async=1:first_pts=0",\n            "-movflags", "+faststart", str(output_path),\n        ])''',
        "concatenação com áudio completo",
    )
    return source


def run_v8(round_value: int, repo_root: Path, output: Path) -> None:
    source_path = Path(__file__).with_name("gerar_video_bancada_real_v7.py")
    source = build_patched_source(source_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="cartola_bancada_v8_") as temp_name:
        patched = Path(temp_name) / "gerar_video_bancada_real_v8_runtime.py"
        patched.write_text(source, encoding="utf-8")
        command = [
            sys.executable,
            str(patched),
            "--rodada",
            str(round_value),
            "--repo-root",
            str(repo_root.resolve()),
            "--output",
            str(output.resolve()),
        ]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera o vídeo de bancada real V8.")
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run_v8(args.rodada, Path(args.repo_root), Path(args.output))
