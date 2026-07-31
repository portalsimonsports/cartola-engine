from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v6_base as v6
import gerar_video_dialogo_cartola_v7 as v7

VERSION = "cartola_dialogo_tecnico_v8_graficos_top5_2026_07_31"
ORIGINAL_CREATE_VISUALS = v3.create_visuals
ORIGINAL_PLAYER_CARD = v3.player_card
ORIGINAL_TOP5_DIALOGUE = v6.top5_dialogue

POSITION_LABELS = {
    "GOL": "GOLEIROS",
    "LAT": "LATERAIS",
    "ZAG": "ZAGUEIROS",
    "MEI": "MEIAS",
    "ATA": "ATACANTES",
    "TEC": "TÉCNICOS",
}
POSITION_SINGULAR = {
    "GOL": "goleiro",
    "LAT": "lateral",
    "ZAG": "zagueiro",
    "MEI": "meia",
    "ATA": "atacante",
    "TEC": "técnico",
}
POSITION_COLORS = {
    "GOL": (255, 190, 55),
    "LAT": (32, 196, 255),
    "ZAG": (71, 111, 255),
    "MEI": (181, 86, 255),
    "ATA": (237, 71, 96),
    "TEC": (205, 218, 230),
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def number(value: Any, digits: int = 2) -> str:
    return f"{as_float(value):.{digits}f}".replace(".", ",")


def percent(value: Any, digits: int = 0) -> str:
    return f"{as_float(value) * 100:.{digits}f}%".replace(".", ",")


def top5_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        row
        for row in ((data.get("top5") or {}).get("dados") or [])
        if isinstance(row, dict)
    ]


def metric(row: Dict[str, Any], *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value is not None:
            return as_float(value)
    return 0.0


def validate_metrics(data: Dict[str, Any]) -> None:
    rows = top5_rows(data)
    if len(rows) != 30:
        raise RuntimeError(f"Top 5 incompleto: esperados 30 atletas; encontrados {len(rows)}.")

    missing: List[str] = []
    for row in rows:
        name = clean(row.get("NOME") or row.get("nome"))
        required = {
            "média recente": row.get("MEDIA_ULT5") if row.get("MEDIA_ULT5") is not None else row.get("media_ult5"),
            "chance 8+": row.get("PROB_8") if row.get("PROB_8") is not None else row.get("prob_8"),
            "eficiência": row.get("EFICIENCIA") if row.get("EFICIENCIA") is not None else row.get("eficiencia"),
            "confiança": row.get("INDICE_CONFIANCA") if row.get("INDICE_CONFIANCA") is not None else row.get("indice_confianca"),
        }
        absent = [label for label, value in required.items() if value is None]
        if absent:
            missing.append(f"{name}: {', '.join(absent)}")

    if missing:
        raise RuntimeError(
            "O vídeo não será publicado com indicadores ausentes no Top 5: "
            + " | ".join(missing)
        )

    players = data.get("jogadores") or {}
    player_missing: List[str] = []
    for name, player in players.items():
        if not isinstance(player, dict):
            continue
        if any(
            player.get(field) is None
            for field in ("media_ult5", "prob_8", "eficiencia", "indice_confianca")
        ):
            player_missing.append(name)
    if player_missing:
        raise RuntimeError(
            "Jogadores sem gráficos históricos: " + ", ".join(player_missing)
        )


def bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    value: float,
    color: Tuple[int, int, int],
) -> None:
    value = max(0.0, min(1.0, value))
    v3.rounded(draw, (x, y, x + width, y + 12), 6, (8, 28, 50), (23, 63, 94), 1)
    filled = max(4, int((width - 4) * value))
    v3.rounded(draw, (x + 2, y + 2, x + 2 + filled, y + 10), 4, color)


def player_card_v8(name: str, player: Dict[str, Any], output: Path) -> None:
    image = v3.gradient()
    draw = ImageDraw.Draw(image)
    v3.card_header(
        draw,
        "POR QUE FOI ESCALADO?",
        "Eficiência, chance estimada, média recente e risco do confronto.",
    )

    v3.rounded(draw, (28, 185, 632, 262), 20, (5, 27, 52), (32, 196, 255), 2)
    draw.text(
        (48, 198),
        name.upper(),
        font=v3.fit_text(draw, name.upper(), 390, 27, 18, True),
        fill=base.WHITE,
    )
    draw.text(
        (48, 230),
        f"{clean(player.get('posicao'))} • {clean(player.get('clube_nome') or player.get('clube'))} • {number(player.get('preco'))} cartoletas",
        font=base.font(15, True),
        fill=(255, 190, 55),
    )

    v3.rounded(draw, (28, 278, 632, 350), 20, (5, 24, 45), (53, 210, 122), 2)
    draw.text(
        (48, 292),
        f"{clean(player.get('clube_nome'))} {as_int(player.get('pos_clube'))}º x {clean(player.get('adversario'))} {as_int(player.get('pos_adversario'))}º",
        font=v3.fit_text(
            draw,
            f"{clean(player.get('clube_nome'))} {as_int(player.get('pos_clube'))}º x {clean(player.get('adversario'))} {as_int(player.get('pos_adversario'))}º",
            550,
            20,
            14,
            True,
        ),
        fill=base.WHITE,
    )
    draw.text(
        (48, 322),
        f"Mando: {clean(player.get('mando'))} • Última: {number(player.get('ultima_pontuacao'))} • Projeção: {number(player.get('exp_score'))}",
        font=base.font(14, True),
        fill=base.SILVER,
    )

    metrics = [
        (
            "EFICIÊNCIA",
            f"{number(player.get('eficiencia'))} pt/cartoleta",
            min(1.0, as_float(player.get("eficiencia")) / 1.10),
            (32, 196, 255),
        ),
        (
            "CHANCE ESTIMADA DE 8+",
            percent(player.get("prob_8")),
            as_float(player.get("prob_8")),
            (181, 86, 255),
        ),
        (
            "MÉDIA DAS ÚLTIMAS 5",
            f"{number(player.get('media_ult5'))} pts",
            min(1.0, as_float(player.get("media_ult5")) / 12.0),
            (255, 190, 55),
        ),
        (
            "CONFIANÇA DO HISTÓRICO",
            percent(player.get("indice_confianca")),
            as_float(player.get("indice_confianca")),
            (53, 210, 122),
        ),
    ]

    y = 374
    for label, display, normalized, color in metrics:
        draw.text((48, y), label, font=base.font(13, True), fill=base.SILVER)
        draw.text((610, y), display, font=base.font(15, True), fill=color, anchor="ra")
        bar(draw, 48, y + 22, 564, normalized, color)
        y += 48

    v3.rounded(draw, (32, 580, 628, 750), 22, (4, 20, 39), (255, 190, 55), 2)
    draw.text((52, 596), "ANÁLISE DA ESCALAÇÃO", font=base.font(18, True), fill=(255, 190, 55))
    rationale = clean(player.get("racional"))
    font = base.font(15, True)
    for index, line in enumerate(v3.wrap(draw, rationale, 540, font)[:6]):
        draw.text((52, 626 + index * 20), line, font=font, fill=base.WHITE)

    image.save(output, "PNG", optimize=True)


def top5_summary_card(data: Dict[str, Any], output: Path) -> None:
    image = v3.gradient()
    draw = ImageDraw.Draw(image)
    v3.card_header(
        draw,
        "TOP 5 • RESUMO TÉCNICO",
        "Líder de projeção por posição com eficiência e chance estimada de 8+.",
    )
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in top5_rows(data):
        grouped[clean(row.get("POS")).upper()].append(row)

    y = 190
    for position in ("GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"):
        rows = grouped[position]
        leader = max(rows, key=lambda row: metric(row, "EXP_SCORE", "exp_score"))
        color = POSITION_COLORS[position]
        v3.rounded(draw, (28, y, 632, y + 82), 18, (5, 24, 45), color, 2)
        draw.text((45, y + 12), POSITION_LABELS[position], font=base.font(17, True), fill=color)
        draw.text(
            (45, y + 39),
            clean(leader.get("NOME")),
            font=v3.fit_text(draw, clean(leader.get("NOME")), 250, 20, 14, True),
            fill=base.WHITE,
        )
        draw.text(
            (610, y + 16),
            f"Proj. {number(leader.get('EXP_SCORE'))}",
            font=base.font(15, True),
            fill=base.SILVER,
            anchor="ra",
        )
        draw.text(
            (610, y + 43),
            f"Ef. {number(metric(leader, 'EFICIENCIA', 'eficiencia'))} • 8+ {percent(metric(leader, 'PROB_8', 'prob_8'))}",
            font=base.font(14, True),
            fill=color,
            anchor="ra",
        )
        y += 91

    image.save(output, "PNG", optimize=True)


def top5_position_card(position: str, rows: List[Dict[str, Any]], output: Path) -> None:
    image = v3.gradient()
    draw = ImageDraw.Draw(image)
    color = POSITION_COLORS[position]
    v3.card_header(
        draw,
        f"TOP 5 • {POSITION_LABELS[position]}",
        "Eficiência por cartoleta, chance estimada de 8+ e projeção do modelo.",
    )

    max_efficiency = max(metric(row, "EFICIENCIA", "eficiencia") for row in rows) or 1.0
    y = 184
    for index, row in enumerate(rows[:5], start=1):
        name = clean(row.get("NOME"))
        club = clean(row.get("CLUBE_NOME") or row.get("CLUBE"))
        price = metric(row, "PRECO", "preco")
        efficiency = metric(row, "EFICIENCIA", "eficiencia")
        chance = metric(row, "PROB_8", "prob_8")
        projection = metric(row, "EXP_SCORE", "exp_score")
        recent = metric(row, "MEDIA_ULT5", "media_ult5")

        v3.rounded(draw, (28, y, 632, y + 105), 18, (5, 24, 45), color, 2)
        v3.rounded(draw, (42, y + 12, 76, y + 46), 12, (8, 35, 60), color, 2)
        draw.text((59, y + 20), str(index), font=base.font(17, True), fill=color, anchor="mm")
        draw.text(
            (91, y + 11),
            name.upper(),
            font=v3.fit_text(draw, name.upper(), 285, 19, 13, True),
            fill=base.WHITE,
        )
        draw.text(
            (91, y + 38),
            f"{club} • {number(price)} cartoletas • média 5: {number(recent)}",
            font=base.font(13, True),
            fill=base.SILVER,
        )
        draw.text(
            (610, y + 13),
            f"Proj. {number(projection)}",
            font=base.font(14, True),
            fill=color,
            anchor="ra",
        )

        draw.text((91, y + 64), f"Ef. {number(efficiency)}", font=base.font(12, True), fill=(32, 196, 255))
        bar(draw, 166, y + 68, 155, efficiency / max_efficiency, (32, 196, 255))
        draw.text((342, y + 64), f"8+ {percent(chance)}", font=base.font(12, True), fill=(181, 86, 255))
        bar(draw, 423, y + 68, 175, chance, (181, 86, 255))
        y += 113

    draw.text(
        (330, 754),
        "CHANCE DE 8+ = ESTIMATIVA BASEADA NO HISTÓRICO • NÃO É GARANTIA",
        font=base.font(11, True),
        fill=base.SILVER,
        anchor="mm",
    )
    image.save(output, "PNG", optimize=True)


def create_visuals_v8(
    data: Dict[str, Any],
    temp: Path,
    repo_root: Path,
    round_value: int,
) -> Dict[str, Path | None]:
    visuals = ORIGINAL_CREATE_VISUALS(data, temp, repo_root, round_value)

    summary = temp / "top5_resumo_v8.png"
    top5_summary_card(data, summary)
    visuals["top5_resumo"] = summary
    visuals["top5"] = summary

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in top5_rows(data):
        grouped[clean(row.get("POS")).upper()].append(row)

    for position in ("GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"):
        rows = sorted(
            grouped[position],
            key=lambda row: metric(row, "EXP_SCORE", "exp_score"),
            reverse=True,
        )
        path = temp / f"top5_{position.lower()}_v8.png"
        top5_position_card(position, rows, path)
        visuals[f"top5_{position}"] = path

    return visuals


def top5_dialogue_v8(
    segments: List[v3.Segment],
    top5: Dict[str, Any],
) -> None:
    rows = [row for row in (top5.get("dados") or []) if isinstance(row, dict)]
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[clean(row.get("POS")).upper()].append(row)

    v6.segment(
        segments,
        "THALITA",
        (
            "Agora o Top 5 deixa de ser uma imagem estática e passa a ser comparado por "
            "eficiência, média recente, projeção e chance estimada de superar oito pontos."
        ),
        "top5_resumo",
        "Top 5 com eficiência, média recente, projeção e chance estimada de 8+.",
    )

    pairs = [
        ("FRANCISCA", "ANTÔNIO"),
        ("THALITA", "FRANCISCA"),
        ("ANTÔNIO", "THALITA"),
    ]
    for index, position in enumerate(("GOL", "LAT", "ZAG", "MEI", "ATA", "TEC")):
        group = grouped[position]
        projection_leader = max(group, key=lambda row: metric(row, "EXP_SCORE", "exp_score"))
        efficiency_leader = max(group, key=lambda row: metric(row, "EFICIENCIA", "eficiencia"))
        chance_leader = max(group, key=lambda row: metric(row, "PROB_8", "prob_8"))
        questioner, responder = pairs[index % len(pairs)]
        singular = POSITION_SINGULAR[position]

        v6.segment(
            segments,
            questioner,
            (
                f"Entre os {POSITION_LABELS[position].lower()}, quem lidera a projeção e quem "
                "entrega a melhor relação entre custo e histórico?"
            ),
            f"top5_{position}",
            f"Top 5 de {singular}: projeção, eficiência e chance estimada de 8+.",
        )

        parts = [
            (
                f"{clean(projection_leader.get('NOME'))} lidera a projeção, com "
                f"{number(metric(projection_leader, 'EXP_SCORE', 'exp_score'))} pontos esperados"
            ),
            (
                f"{clean(efficiency_leader.get('NOME'))} apresenta a maior eficiência, com "
                f"{number(metric(efficiency_leader, 'EFICIENCIA', 'eficiencia'))} ponto por cartoleta"
            ),
            (
                f"e {clean(chance_leader.get('NOME'))} tem a maior chance histórica estimada de "
                f"oito ou mais, em {percent(metric(chance_leader, 'PROB_8', 'prob_8'))}"
            ),
        ]
        v6.segment(
            segments,
            responder,
            ". ".join(parts)
            + ". Esses indicadores ajudam a comparar perfis, mas não garantem a pontuação da rodada.",
            f"top5_{position}",
            (
                f"Projeção: {clean(projection_leader.get('NOME'))} • "
                f"Eficiência: {clean(efficiency_leader.get('NOME'))} • "
                f"8+: {clean(chance_leader.get('NOME'))}."
            ),
        )


def update_manifest(output_path: Path, data: Dict[str, Any]) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    timeline = payload.get("timeline") or []
    visuals = {clean(item.get("visual")) for item in timeline}
    required_visuals = {"top5_resumo", "top5_GOL", "top5_LAT", "top5_ZAG", "top5_MEI", "top5_ATA", "top5_TEC"}
    missing = sorted(required_visuals - visuals)
    if missing:
        raise RuntimeError("Visuais comparativos do Top 5 ausentes: " + ", ".join(missing))

    payload.update(
        {
            "versao": VERSION,
            "graficos_eficiencia_prob8": True,
            "top5_visual_dinamico": True,
            "top5_sem_imagem_vazia": True,
            "chance_8_identificada_como_estimativa": True,
            "top5_atletas_com_historico": as_int(data.get("top5_com_historico")),
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    validate_metrics(data)

    old_create_visuals = v3.create_visuals
    old_player_card = v3.player_card
    old_top5_dialogue = v6.top5_dialogue
    try:
        v3.create_visuals = create_visuals_v8
        v3.player_card = player_card_v8
        v6.top5_dialogue = top5_dialogue_v8
        result = v7.generate(round_value, repo_root, output_path)
        update_manifest(output_path, data)
        return result
    finally:
        v3.create_visuals = old_create_visuals
        v3.player_card = old_player_card
        v6.top5_dialogue = old_top5_dialogue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
