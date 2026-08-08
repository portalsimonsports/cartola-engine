from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v9 as v9

VERSION = "cartola_dialogo_tecnico_v10_fases_2026_08_08"
ORIGINAL_BUILD = v9.build_dialogue_v9
ORIGINAL_CLOSING_CARD = v9.closing_card


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def replace_preclose(text: str) -> str:
    replacements = [
        ("análise inicial", "análise de pré-fechamento"),
        ("Análise inicial", "Análise de pré-fechamento"),
        ("seleção inicial", "seleção atualizada de pré-fechamento"),
        ("Seleção inicial", "Seleção atualizada de pré-fechamento"),
        ("três times publicados na seleção atualizada de pré-fechamento", "três times atualizados no pré-fechamento"),
        ("snapshot publicado da seleção atualizada de pré-fechamento", "snapshot publicado do pré-fechamento"),
        ("primeira fotografia", "fotografia de pré-fechamento"),
        ("próximo encontro no pré-fechamento", "pré-fechamento concluído"),
    ]
    result = text
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def build_dialogue_v10(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    segments = ORIGINAL_BUILD(round_value, data)
    if clean(data.get("fase_video")).upper() != "PRE_FECHAMENTO":
        return segments

    adapted: List[v3.Segment] = []
    for segment in segments:
        text = replace_preclose(clean(segment.text))
        onscreen = replace_preclose(clean(segment.onscreen))

        if "Está no ar a análise de pré-fechamento" in text:
            text = (
                f"Está no ar a análise de pré-fechamento da rodada {round_value} do Cartola. "
                "Agora os três modelos e o Top 5 já refletem as escolhas mais próximas do fechamento do mercado. "
                "Vamos revisar confrontos, indicadores, riscos e as escalações atualizadas."
            )
            onscreen = f"Pré-fechamento da rodada {round_value}: escolhas atualizadas e riscos finais."

        if "No pré-fechamento, uma nova edição" in text:
            text = (
                "Esta é a fotografia de pré-fechamento. As escolhas atuais ficam registradas para "
                "comparação posterior com as escalações confirmadas e com o desempenho final da rodada."
            )
            onscreen = "Fotografia de pré-fechamento registrada para comparação posterior."

        if "Encerramos a análise de pré-fechamento" in text or "Encerramos a análise inicial" in text:
            text = (
                f"Encerramos a análise de pré-fechamento da rodada {round_value}. "
                "Acompanhe o canal Dicas Cartola Portal SimonSports para as escalações confirmadas, "
                "o acompanhamento da rodada e a avaliação final dos modelos e do Top 5."
            )
            onscreen = f"Rodada {round_value} • pré-fechamento concluído • próximas: escalações confirmadas."

        adapted.append(
            v3.Segment(
                speaker=segment.speaker,
                voice=segment.voice,
                text=text,
                visual=segment.visual,
                onscreen=onscreen,
            )
        )
    return adapted


def closing_card_v10(data: Dict[str, Any], round_value: int, output: Path) -> None:
    ORIGINAL_CLOSING_CARD(data, round_value, output)
    if clean(data.get("fase_video")).upper() != "PRE_FECHAMENTO":
        return

    image = Image.open(output).convert("RGBA")
    draw = ImageDraw.Draw(image)
    # Substitui somente o banner inferior da V9. O restante do quadro aprovado é preservado.
    draw.rectangle((28, 666, 632, 760), fill=(3, 20, 39, 255))
    v3.rounded(draw, (35, 678, 625, 748), 20, (23, 14, 3), (255, 190, 55), 2)
    draw.text(
        (330, 702),
        "PRÓXIMO PASSO: ESCALAÇÕES CONFIRMADAS",
        font=base.font(16, True),
        fill=(255, 190, 55),
        anchor="mm",
    )
    draw.text(
        (330, 727),
        "Depois: acompanhamento e avaliação final da rodada.",
        font=base.font(13, True),
        fill=base.SILVER,
        anchor="mm",
    )
    image.convert("RGB").save(output, "PNG", optimize=True)


def update_manifest(output_path: Path, data: Dict[str, Any]) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    fase = clean(data.get("fase_video")).upper() or "INICIAL"
    payload["versao"] = VERSION
    payload["fase_video"] = fase
    payload["roteiro_por_fase"] = True
    if fase == "PRE_FECHAMENTO":
        spoken = " ".join(
            clean(item.get("texto_falado")) for item in payload.get("timeline") or []
        ).lower()
        if "pré-fechamento" not in spoken and "pre-fechamento" not in spoken:
            raise RuntimeError("Roteiro de pré-fechamento não identificado no áudio.")
        payload["pre_fechamento_identificado_no_audio"] = True
        payload["encerramento_pre_fechamento_corrigido"] = True
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    old_build = v9.build_dialogue_v9
    old_closing = v9.closing_card
    try:
        v9.build_dialogue_v9 = build_dialogue_v10
        v9.closing_card = closing_card_v10
        result = v9.generate(round_value, repo_root, output_path)
        update_manifest(output_path, data)
        return result
    finally:
        v9.build_dialogue_v9 = old_build
        v9.closing_card = old_closing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
