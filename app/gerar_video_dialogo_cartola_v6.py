from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v4 as v4

VERSION = "cartola_dialogo_tecnico_v6_abertura_direta_2026_07_31"
ORIGINAL_FRAME = v4.create_frame_v4
ORIGINAL_DIALOGUE = v4.build_dialogue_v4

POSICOES = {
    "GOL": "goleiro",
    "LAT": "lateral",
    "ZAG": "zagueiro",
    "MEI": "meia",
    "ATA": "atacante",
    "TEC": "técnico",
}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def number(value: Any, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f}".replace(".", ",")
    except Exception:
        return "0,00"


def ordinal(position: Any) -> str:
    try:
        value = int(float(position))
    except Exception:
        value = 0
    if value <= 0:
        raise RuntimeError("Posição de clube inválida no roteiro.")
    return f"{value}º colocado"


def segment(
    items: List[v3.Segment],
    speaker: str,
    text: str,
    visual: str,
    onscreen: str,
) -> None:
    v4.add_segment(items, speaker, text, visual, onscreen)


def game_dialogue(
    segments: List[v3.Segment],
    game: Dict[str, Any],
    index: int,
) -> None:
    speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    speaker_a = speakers[index % 3]
    speaker_b = speakers[(index + 1) % 3]
    visual = f"jogo_{index}"

    home = clean(game.get("mandante"))
    away = clean(game.get("visitante"))
    home_pos = ordinal(game.get("pos_mandante"))
    away_pos = ordinal(game.get("pos_visitante"))
    home_form = clean(game.get("forma_mandante"))
    away_form = clean(game.get("forma_visitante"))

    segment(
        segments,
        speaker_a,
        (
            f"Vamos a {home} contra {away}. O {home} é o {home_pos} da competição e "
            f"o {away} é o {away_pos}. A partida será no {clean(game.get('estadio'))}, "
            f"com mando do {home}."
        ),
        visual,
        f"{home} ({home_pos}) x {away} ({away_pos}).",
    )
    segment(
        segments,
        speaker_b,
        (
            f"{clean(game.get('historico_mandante_falado'))} "
            f"{clean(game.get('historico_visitante_falado'))} "
            f"A sequência visual é {home_form} para o {home} e {away_form} para o {away}."
        ),
        visual,
        f"Forma recente: {home_form} x {away_form}.",
    )
    segment(
        segments,
        speakers[(index + 2) % 3],
        clean(game.get("leitura")),
        visual,
        clean(game.get("destaque_cartola")),
    )


def team_dialogue(
    segments: List[v3.Segment],
    teams: Dict[str, Dict[str, Any]],
) -> None:
    segment(
        segments,
        "FRANCISCA",
        (
            "Agora vamos aos três times publicados na seleção inicial. "
            "A comparação considera formação, custo, capitão e distribuição dos atletas."
        ),
        "pontuacoes",
        "Três modelos publicados: formação, custo e capitão.",
    )
    speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    for index, team in enumerate(teams.values()):
        titulares = [clean(name) for name in (team.get("titulares") or []) if clean(name)]
        captain = clean(team.get("capitao")).split(" (", 1)[0]
        names = ", ".join(titulares[:5])
        remaining = max(0, len(titulares) - 5)
        complement = f", além de outros {remaining} titulares" if remaining else ""
        segment(
            segments,
            speakers[index % 3],
            (
                f"O {clean(team.get('nome'))} utiliza a formação {clean(team.get('formacao'))}, "
                f"custa {number(team.get('custo'))} cartoletas e tem {captain} como capitão. "
                f"Entre as primeiras escolhas aparecem {names}{complement}."
            ),
            "pontuacoes",
            (
                f"{clean(team.get('nome'))}: {clean(team.get('formacao'))} • "
                f"{number(team.get('custo'))} cartoletas • capitão {captain}."
            ),
        )


def player_dialogue(
    segments: List[v3.Segment],
    players: Dict[str, Dict[str, Any]],
) -> None:
    segment(
        segments,
        "ANTÔNIO",
        (
            "Na sequência, os principais atletas dos modelos, com posição, clube, "
            "confronto, preço e desempenho disponível."
        ),
        next(iter(players)) if players else "rodada",
        "Principais escolhas e contexto de cada atleta.",
    )

    speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    for index, (name, player) in enumerate(players.items()):
        position = clean(player.get("posicao_extenso")) or POSICOES.get(
            clean(player.get("posicao")).upper(),
            clean(player.get("posicao")).lower(),
        )
        club = clean(player.get("clube_nome"))
        club_position = ordinal(player.get("pos_clube"))
        opponent = clean(player.get("adversario"))
        mando = clean(player.get("mando"))
        models = [clean(item) for item in (player.get("modelos") or []) if clean(item)]
        model_text = (
            f" aparece nos modelos {', '.join(models)}"
            if models
            else " aparece na seleção publicada"
        )

        metrics: List[str] = []
        if int(player.get("jogos") or 0) > 0:
            metrics.append(
                f"média de {number(player.get('media'))} pontos em "
                f"{int(player.get('jogos'))} jogos"
            )
            metrics.append(f"última pontuação de {number(player.get('ultima_pontuacao'))}")
        if float(player.get("exp_score") or 0) > 0:
            metrics.append(f"projeção de {number(player.get('exp_score'))} pontos no Top 5")
        performance = ", ".join(metrics)
        if not performance:
            performance = "desempenho individual ainda sem amostra suficiente na temporada"

        segment(
            segments,
            speakers[index % 3],
            (
                f"{name} é {position} do {club}, clube que ocupa a {club_position}. "
                f"Nesta rodada enfrenta o {opponent}, {mando}. Custa "
                f"{number(player.get('preco'))} cartoletas, tem {performance} e{model_text}. "
                f"{clean(player.get('racional'))}"
            ),
            name,
            (
                f"{name} • {position} • {club} • {club_position} • "
                f"{number(player.get('preco'))} cartoletas."
            ),
        )


def top5_dialogue(
    segments: List[v3.Segment],
    top5: Dict[str, Any],
) -> None:
    rows = [row for row in (top5.get("dados") or []) if isinstance(row, dict)]
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[clean(row.get("POS")).upper()].append(row)

    segment(
        segments,
        "THALITA",
        (
            "Fechamos com o Top 5 publicado. A comparação por posição considera preço, média "
            "na temporada, última pontuação, projeção e o contexto do clube na tabela."
        ),
        "top5",
        "Top 5 publicado com indicadores reais.",
    )

    speakers = ["FRANCISCA", "ANTÔNIO", "THALITA"]
    order = ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]
    for index, position in enumerate(order):
        group = grouped.get(position, [])
        if not group:
            continue
        descriptions: List[str] = []
        for row in group[:5]:
            name = clean(row.get("NOME"))
            club = clean(row.get("CLUBE_NOME") or row.get("CLUBE"))
            price = number(row.get("PRECO"))
            expected = number(row.get("EXP_SCORE"))
            average = number(row.get("MEDIA"))
            descriptions.append(
                f"{name}, do {club}, custa {price}, tem média {average} e projeção {expected}"
            )
        segment(
            segments,
            speakers[index % 3],
            (
                f"Entre os {POSICOES.get(position, position.lower())}s, o Top 5 é formado por "
                + "; ".join(descriptions)
                + "."
            ),
            "top5",
            f"Top 5 de {POSICOES.get(position, position.lower())}: cinco alternativas comparadas.",
        )


def build_dialogue_v6(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    if data.get("contexto_real_validado") is not True:
        raise RuntimeError("A base não foi validada com classificação e forma reais.")

    segments: List[v3.Segment] = []
    segment(
        segments,
        "FRANCISCA",
        (
            f"Está no ar a análise inicial da rodada {round_value} do Cartola. "
            "Vamos aos confrontos, aos três modelos publicados e ao Top 5."
        ),
        "rodada",
        f"Rodada {round_value}: confrontos, times e Top 5.",
    )

    games = list(data.get("jogos") or [])
    for index, game in enumerate(games):
        game_dialogue(segments, game, index)

    team_dialogue(segments, dict(data.get("times") or {}))
    player_dialogue(segments, dict(data.get("jogadores") or {}))
    top5_dialogue(segments, dict(data.get("top5") or {}))

    segment(
        segments,
        "FRANCISCA",
        (
            f"Esta foi a análise inicial da rodada {round_value}. No pré-fechamento, uma nova "
            "edição comparará alterações nos times, no capitão e no Top 5 antes do mercado fechar."
        ),
        "final",
        "Portal SimonSports • análise inicial concluída.",
    )
    return segments


def create_frame_v6(
    visual_path: Path | None,
    collage_paths: List[Path],
    speaker: str,
    text: str,
    round_value: int,
    output: Path,
) -> None:
    ORIGINAL_FRAME(visual_path, collage_paths, speaker, text, round_value, output)
    image = Image.open(output).convert("RGBA")
    draw = ImageDraw.Draw(image)
    v3.rounded(draw, (20, 18, 700, 76), 24, (3, 20, 39, 255), base.LINE, 2)
    title = f"ANÁLISE • RODADA {round_value}"
    box = draw.textbbox((0, 0), title, font=base.font(25, True))
    draw.text(
        ((base.WIDTH - (box[2] - box[0])) / 2, 32),
        title,
        font=base.font(25, True),
        fill=base.WHITE,
    )
    image.convert("RGB").save(output, "PNG", optimize=True)


def update_manifest(output_path: Path) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        {
            "versao": VERSION,
            "contexto_real_validado": True,
            "zero_colocado_bloqueado": True,
            "texto_provisorio_bloqueado": True,
            "clubes_por_extenso_no_audio": True,
            "abertura_direta_na_analise": True,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    original_version = v4.VERSION
    original_frame = v4.create_frame_v4
    original_dialogue = v4.build_dialogue_v4
    try:
        v4.VERSION = VERSION
        v4.create_frame_v4 = create_frame_v6
        v4.build_dialogue_v4 = build_dialogue_v6
        result = v4.generate(round_value, repo_root, output_path)
        update_manifest(output_path)
        return result
    finally:
        v4.VERSION = original_version
        v4.create_frame_v4 = original_frame
        v4.build_dialogue_v4 = original_dialogue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
