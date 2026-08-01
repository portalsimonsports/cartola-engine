from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from PIL import ImageDraw

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v6_base as v6
import gerar_video_dialogo_cartola_v8 as v8

VERSION = "cartola_dialogo_tecnico_v9_encerramento_reforcado_2026_07_31"
ORIGINAL_BUILD_DIALOGUE = v6.build_dialogue_v6
ORIGINAL_CREATE_VISUALS_V8 = v8.create_visuals_v8


def highlights(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = v8.top5_rows(data)
    if not rows:
        raise RuntimeError("Top 5 ausente para o encerramento.")
    return {
        "projecao": max(
            rows,
            key=lambda row: v8.metric(row, "EXP_SCORE", "exp_score"),
        ),
        "eficiencia": max(
            rows,
            key=lambda row: v8.metric(row, "EFICIENCIA", "eficiencia"),
        ),
        "chance": max(
            rows,
            key=lambda row: v8.metric(row, "PROB_8", "prob_8"),
        ),
    }


def closing_card(data: Dict[str, Any], round_value: int, output: Path) -> None:
    leaders = highlights(data)
    projection = leaders["projecao"]
    efficiency = leaders["eficiencia"]
    chance = leaders["chance"]

    image = v3.gradient()
    draw = ImageDraw.Draw(image)
    v3.card_header(
        draw,
        f"ENCERRAMENTO • RODADA {round_value}",
        "Síntese dos indicadores e próximo passo antes do fechamento do mercado.",
    )

    items = [
        (
            "MAIOR PROJEÇÃO",
            v8.clean(projection.get("NOME")),
            f"{v8.number(v8.metric(projection, 'EXP_SCORE', 'exp_score'))} pontos esperados",
            (32, 196, 255),
        ),
        (
            "MAIOR EFICIÊNCIA",
            v8.clean(efficiency.get("NOME")),
            f"{v8.number(v8.metric(efficiency, 'EFICIENCIA', 'eficiencia'))} ponto por cartoleta",
            (255, 190, 55),
        ),
        (
            "MAIOR CHANCE ESTIMADA DE 8+",
            v8.clean(chance.get("NOME")),
            v8.percent(v8.metric(chance, "PROB_8", "prob_8")),
            (181, 86, 255),
        ),
    ]

    y = 205
    for label, name, value, color in items:
        v3.rounded(draw, (28, y, 632, y + 130), 22, (5, 24, 45), color, 2)
        draw.text((48, y + 16), label, font=base.font(16, True), fill=color)
        draw.text(
            (48, y + 50),
            name.upper(),
            font=v3.fit_text(draw, name.upper(), 360, 24, 16, True),
            fill=base.WHITE,
        )
        draw.text(
            (610, y + 53),
            value,
            font=base.font(16, True),
            fill=base.SILVER,
            anchor="ra",
        )
        draw.text(
            (48, y + 92),
            "Indicador de apoio à decisão; não representa garantia de pontuação.",
            font=base.font(13, True),
            fill=base.SILVER,
        )
        y += 148

    v3.rounded(draw, (35, 678, 625, 748), 20, (23, 14, 3), (255, 190, 55), 2)
    draw.text(
        (330, 702),
        "PRÓXIMO VÍDEO: COMPARAÇÃO DO PRÉ-FECHAMENTO",
        font=base.font(16, True),
        fill=(255, 190, 55),
        anchor="mm",
    )
    draw.text(
        (330, 727),
        "Mudanças nos times, capitão, Top 5 e riscos finais.",
        font=base.font(13, True),
        fill=base.SILVER,
        anchor="mm",
    )
    image.save(output, "PNG", optimize=True)


def create_visuals_v9(
    data: Dict[str, Any],
    temp: Path,
    repo_root: Path,
    round_value: int,
) -> Dict[str, Path | None]:
    visuals = ORIGINAL_CREATE_VISUALS_V8(data, temp, repo_root, round_value)
    path = temp / "encerramento_v9.png"
    closing_card(data, round_value, path)
    visuals["encerramento"] = path
    visuals["final"] = path
    return visuals


def build_dialogue_v9(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    segments = ORIGINAL_BUILD_DIALOGUE(round_value, data)

    while segments and (
        v8.clean(segments[-1].visual) == "final"
        or "esta foi a análise" in v8.clean(segments[-1].text).lower()
    ):
        segments.pop()

    leaders = highlights(data)
    projection = leaders["projecao"]
    efficiency = leaders["eficiencia"]
    chance = leaders["chance"]

    v6.segment(
        segments,
        "ANTÔNIO",
        (
            "Antes de encerrar, ficam três destaques objetivos. "
            f"{v8.clean(projection.get('NOME'))} lidera a projeção, com "
            f"{v8.number(v8.metric(projection, 'EXP_SCORE', 'exp_score'))} pontos esperados. "
            f"{v8.clean(efficiency.get('NOME'))} apresenta a maior eficiência, com "
            f"{v8.number(v8.metric(efficiency, 'EFICIENCIA', 'eficiencia'))} ponto por cartoleta. "
            f"E {v8.clean(chance.get('NOME'))} registra a maior chance histórica estimada de "
            f"oito ou mais, em {v8.percent(v8.metric(chance, 'PROB_8', 'prob_8'))}."
        ),
        "encerramento",
        "Resumo: maior projeção, eficiência e chance estimada de 8+.",
    )
    v6.segment(
        segments,
        "THALITA",
        (
            "Esses números ajudam a comparar as escolhas, mas não garantem pontuação. "
            "A seleção inicial fica registrada e será confrontada no pré-fechamento com as "
            "mudanças dos três modelos, do capitão, do Top 5 e dos riscos finais da rodada."
        ),
        "encerramento",
        "Próxima análise: mudanças dos times, capitão, Top 5 e riscos finais.",
    )
    v6.segment(
        segments,
        "FRANCISCA",
        (
            f"Encerramos a análise inicial da rodada {round_value}. "
            "Acompanhe o canal Dicas Cartola Portal SimonSports para receber a análise de "
            "pré-fechamento e as seleções atualizadas antes do mercado fechar. "
            "Portal SimonSports: dados, contexto e análise para acompanhar cada rodada."
        ),
        "encerramento",
        f"Rodada {round_value} analisada • próximo encontro no pré-fechamento.",
    )
    return segments


def update_manifest(output_path: Path) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    timeline = payload.get("timeline") or []
    closing = [item for item in timeline if v8.clean(item.get("visual")) == "encerramento"]
    if len(closing) < 3:
        raise RuntimeError("Encerramento reforçado incompleto.")
    payload.update(
        {
            "versao": VERSION,
            "encerramento_reforcado": True,
            "encerramento_com_sintese": True,
            "chamada_pre_fechamento": True,
            "quadro_final_exclusivo": True,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    old_build = v6.build_dialogue_v6
    old_visuals = v8.create_visuals_v8
    try:
        v6.build_dialogue_v6 = build_dialogue_v9
        v8.create_visuals_v8 = create_visuals_v9
        result = v8.generate(round_value, repo_root, output_path)
        update_manifest(output_path)
        return result
    finally:
        v6.build_dialogue_v6 = old_build
        v8.create_visuals_v8 = old_visuals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
