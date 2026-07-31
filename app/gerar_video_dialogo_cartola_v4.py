from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFilter

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3

VERSION = "cartola_dialogo_tecnico_v4_generico_2026_07_31"
WIDTH = base.WIDTH
HEIGHT = base.HEIGHT


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def concise_onscreen(text: str, limit: int = 150) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def voice_for(speaker: str) -> str:
    return {
        "FRANCISCA": base.VOICE_FRANCISCA,
        "ANTÔNIO": base.VOICE_ANTONIO,
        "THALITA": base.VOICE_THALITA,
    }[speaker]


def add_segment(items: List[v3.Segment], speaker: str, text: str, visual: str, onscreen: str) -> None:
    items.append(
        v3.Segment(
            speaker=speaker,
            voice=voice_for(speaker),
            text=v3.sanitize_tts(clean_text(text)),
            visual=visual,
            onscreen=concise_onscreen(onscreen),
        )
    )


def create_frame_v4(
    visual_path: Path | None,
    collage_paths: List[Path],
    speaker: str,
    text: str,
    round_value: int,
    output: Path,
) -> None:
    if visual_path is None:
        foreground = base.make_collage(collage_paths)
        foreground = base.fit_image(foreground, 620, 720)
    else:
        foreground = base.fit_image(Image.open(visual_path), 620, 720)

    background_source = foreground.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    background = background_source.filter(ImageFilter.GaussianBlur(25)).convert("RGBA")
    frame = Image.alpha_composite(
        background,
        Image.new("RGBA", (WIDTH, HEIGHT), (0, 8, 22, 190)),
    )
    draw = ImageDraw.Draw(frame)

    v3.rounded(draw, (20, 18, 700, 76), 24, (3, 20, 39, 238), base.LINE, 2)
    header = f"ANÁLISE DIALOGADA • RODADA {round_value}"
    hb = draw.textbbox((0, 0), header, font=base.font(25, True))
    draw.text(
        ((WIDTH - (hb[2] - hb[0])) / 2, 32),
        header,
        font=base.font(25, True),
        fill=base.WHITE,
    )

    x = (WIDTH - foreground.width) // 2
    frame.alpha_composite(foreground.convert("RGBA"), (x, 92))
    v3.rounded(draw, (28, 824, 692, 850), 12, (2, 12, 27, 255), base.LINE, 1)

    accent = base.SPEAKER_COLORS[speaker]
    v3.rounded(draw, (22, 862, 698, 1238), 30, (4, 18, 36, 252), accent, 3)
    v3.rounded(
        draw,
        (48, 884, 275, 942),
        20,
        (accent[0] // 5, accent[1] // 5, accent[2] // 5, 255),
        accent,
        2,
    )
    draw.text((70, 897), speaker, font=base.font(26, True), fill=accent)

    short_text = concise_onscreen(text)
    text_font, lines = base.wrap_text(draw, short_text, 610, 27, 20)
    while len(lines) > 6 and text_font.size > 18:
        text_font = base.font(text_font.size - 1, False)
        lines = v3.wrap(draw, short_text, 610, text_font)

    y = 967
    for line in lines[:6]:
        draw.text((52, y), line, font=text_font, fill=base.WHITE)
        y += text_font.size + 9

    draw.text(
        (52, 1192),
        "RESUMO VISUAL • A FALA COMPLETA PERMANECE SOMENTE NO ÁUDIO",
        font=base.font(12, True),
        fill=base.SILVER,
    )
    footer = "@dicascartolaportalsimonsports  •  PORTAL SIMONSPORTS"
    fb = draw.textbbox((0, 0), footer, font=base.font(16, True))
    draw.text(
        ((WIDTH - (fb[2] - fb[0])) / 2, 1253),
        footer,
        font=base.font(16, True),
        fill=base.SILVER,
    )
    frame.convert("RGB").save(output, "PNG", optimize=True)


def build_dialogue_v4(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    segments: List[v3.Segment] = []
    games = list(data.get("jogos") or [])
    players = dict(data.get("jogadores") or {})
    teams = dict(data.get("times") or {})

    add_segment(
        segments,
        "FRANCISCA",
        f"Começa agora a análise da rodada {round_value}. Vamos direto aos jogos, ao momento das equipes e às escolhas que podem fazer diferença na escalação.",
        "rodada",
        "Rodada, momento dos times e escolhas recomendadas.",
    )
    add_segment(
        segments,
        "ANTÔNIO",
        f"A rodada reúne {len(games)} confrontos considerados na base atual. Primeiro vamos comparar mando, classificação e os cinco resultados mais recentes de cada equipe; depois entramos nos jogadores.",
        "rodada",
        f"{len(games)} confrontos analisados antes das escolhas individuais.",
    )

    questioners = ["THALITA", "FRANCISCA", "ANTÔNIO"]
    responders = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    complements = ["FRANCISCA", "ANTÔNIO", "THALITA"]

    for index, game in enumerate(games):
        visual = f"jogo_{index}"
        mandante = clean_text(game.get("mandante"))
        visitante = clean_text(game.get("visitante"))
        sigla_m = clean_text(game.get("mandante_sigla"))
        sigla_v = clean_text(game.get("visitante_sigla"))
        hist_m = clean_text(game.get("historico_mandante_falado") or game.get("resumo_mandante"))
        hist_v = clean_text(game.get("historico_visitante_falado") or game.get("resumo_visitante"))
        leitura = clean_text(game.get("leitura")) or "O confronto exige equilíbrio entre potencial e risco."
        destaque = clean_text(game.get("destaque_cartola"))

        q = questioners[index % len(questioners)]
        a = responders[index % len(responders)]
        c = complements[index % len(complements)]

        add_segment(
            segments,
            q,
            f"{a.title()}, vamos a {mandante} contra {visitante}. O que os últimos cinco jogos mostram além da posição na tabela?",
            visual,
            f"{sigla_m} x {sigla_v} • últimos cinco jogos e contexto do confronto.",
        )
        answer = " ".join(part for part in (hist_m, hist_v, leitura) if part)
        add_segment(
            segments,
            a,
            answer,
            visual,
            leitura,
        )
        complement = destaque or (
            "Eu não trataria nenhum lado como garantia. A escalação deve considerar mando, sequência, preço e a quantidade de atletas concentrados no mesmo jogo."
        )
        add_segment(
            segments,
            c,
            complement,
            visual,
            "Contraponto: teto, segurança e concentração no mesmo confronto.",
        )

    if teams:
        add_segment(
            segments,
            "FRANCISCA",
            "Agora vamos comparar a última pontuação disponível dos três modelos. Quando o número ainda for parcial, ele será apresentado como parcial e nunca como resultado definitivo.",
            "pontuacoes",
            "Última pontuação disponível dos modelos.",
        )
        speakers = ["ANTÔNIO", "THALITA", "FRANCISCA"]
        for idx, team in enumerate(teams.values()):
            name = clean_text(team.get("nome")) or "Modelo"
            score = team.get("ultima_pontuacao", 0)
            participation = clean_text(team.get("participacao"))
            suffix = f", com participação de {participation}" if participation else ""
            add_segment(
                segments,
                speakers[idx % 3],
                f"O {name} aparece com {v3.number(score)} pontos{suffix}. O dado serve para acompanhar a evolução e precisa ser lido conforme o estágio da rodada.",
                "pontuacoes",
                f"{name}: {v3.number(score)} pontos{(' • ' + participation) if participation else ''}.",
            )

    if players:
        add_segment(
            segments,
            "ANTÔNIO",
            "Passamos agora às escolhas individuais. Em vez de apenas anunciar nomes, vamos explicar preço, confronto, função no modelo e o principal risco de cada atleta.",
            next(iter(players)),
            "Análise individual: preço, confronto, papel e risco.",
        )

    cycle = ["ANTÔNIO", "THALITA", "FRANCISCA"]
    for idx, (name, player) in enumerate(players.items()):
        speaker = cycle[idx % 3]
        rationale = clean_text(player.get("racional")) or (
            f"{name} foi escolhido pelo equilíbrio entre preço, posição e contexto do confronto."
        )
        metrics = []
        if player.get("media_ult5") is not None:
            metrics.append(f"média recente de {v3.number(player.get('media_ult5'))} pontos")
        if player.get("prob_8") is not None:
            metrics.append(f"probabilidade de oito ou mais em {v3.percent(player.get('prob_8'))}")
        if metrics:
            rationale += ". Os indicadores mostram " + " e ".join(metrics)
        add_segment(
            segments,
            speaker,
            rationale,
            name,
            f"{name}: {clean_text(player.get('posicao'))} • {clean_text(player.get('clube'))} • {v3.cartoletas(player.get('preco', 0))}.",
        )

    add_segment(
        segments,
        "FRANCISCA",
        "O Top 5 entra como comparação por posição. Uma troca só faz sentido quando melhora eficiência por cartoleta, teto, estabilidade ou reduz exposição excessiva ao mesmo confronto.",
        "top5",
        "Top 5: alternativas por preço, teto e estabilidade.",
    )
    add_segment(
        segments,
        "THALITA",
        "No pré-fechamento, a segunda análise deve destacar alterações nos times, mudanças no Top 5, dúvidas de escalação e riscos que surgiram após a seleção inicial.",
        "top5",
        "Segundo vídeo: mudanças e escolhas definitivas.",
    )
    add_segment(
        segments,
        "ANTÔNIO",
        f"Esta foi a análise da rodada {round_value}. Portal SimonSports: dados para entender a escalação e diálogo para confrontar as escolhas.",
        "final",
        "Portal SimonSports • Cartola • Dados • Análise.",
    )
    return segments


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    original_version = v3.VERSION
    original_frame = v3.create_frame_v3
    original_dialogue = v3.build_dialogue
    try:
        v3.VERSION = VERSION
        v3.create_frame_v3 = create_frame_v4
        v3.build_dialogue = build_dialogue_v4
        return v3.generate(round_value, repo_root, output_path)
    finally:
        v3.VERSION = original_version
        v3.create_frame_v3 = original_frame
        v3.build_dialogue = original_dialogue


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera vídeo dialogado genérico do Cartola.")
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
