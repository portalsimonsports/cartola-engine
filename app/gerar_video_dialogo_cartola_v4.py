from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFilter

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3


VERSION = "cartola_dialogo_tecnico_v4_2026_07_30_historico"
WIDTH = base.WIDTH
HEIGHT = base.HEIGHT
V3_BUILD_DIALOGUE_ORIGINAL = v3.build_dialogue
V3_GAME_CARD_ORIGINAL = v3.game_card

# Recorte obtido das abas HIST_PARTIDAS e HIST_CLUBES da planilha
# Cartola — Sugestões PRO (Automático). Ordem cronológica: rodadas 16 a 20.
HISTORY: Dict[str, List[dict]] = {
    "MIR": [
        {"r": 16, "casa": "CAM", "fora": "MIR", "pc": 3, "pf": 1},
        {"r": 17, "casa": "MIR", "fora": "FLU", "pc": 1, "pf": 0},
        {"r": 18, "casa": "CAP", "fora": "MIR", "pc": 1, "pf": 0},
        {"r": 19, "casa": "MIR", "fora": "GRE", "pc": 2, "pf": 1},
        {"r": 20, "casa": "VAS", "fora": "MIR", "pc": 1, "pf": 1},
    ],
    "REM": [
        {"r": 16, "casa": "CHA", "fora": "REM", "pc": 2, "pf": 3},
        {"r": 17, "casa": "REM", "fora": "CAP", "pc": 1, "pf": 2},
        {"r": 18, "casa": "REM", "fora": "SAO", "pc": 1, "pf": 0},
        {"r": 19, "casa": "COR", "fora": "REM", "pc": 3, "pf": 0},
        {"r": 20, "casa": "REM", "fora": "VIT", "pc": 2, "pf": 0},
    ],
    "INT": [
        {"r": 16, "casa": "INT", "fora": "VAS", "pc": 4, "pf": 1},
        {"r": 17, "casa": "VIT", "fora": "INT", "pc": 2, "pf": 0},
        {"r": 18, "casa": "RBB", "fora": "INT", "pc": 3, "pf": 1},
        {"r": 19, "casa": "INT", "fora": "CRU", "pc": 1, "pf": 2},
        {"r": 20, "casa": "CAP", "fora": "INT", "pc": 2, "pf": 0},
    ],
    "FLA": [
        {"r": 16, "casa": "CAP", "fora": "FLA", "pc": 1, "pf": 1},
        {"r": 17, "casa": "FLA", "fora": "PAL", "pc": 0, "pf": 3},
        {"r": 18, "casa": "FLA", "fora": "CFC", "pc": 3, "pf": 0},
        {"r": 19, "casa": "CHA", "fora": "FLA", "pc": 0, "pf": 4},
        {"r": 20, "casa": "FLA", "fora": "SAO", "pc": 1, "pf": 1},
    ],
    "VIT": [
        {"r": 16, "casa": "RBB", "fora": "VIT", "pc": 2, "pf": 0},
        {"r": 17, "casa": "VIT", "fora": "INT", "pc": 2, "pf": 0},
        {"r": 18, "casa": "SAN", "fora": "VIT", "pc": 3, "pf": 1},
        {"r": 19, "casa": "VIT", "fora": "VAS", "pc": 1, "pf": 0},
        {"r": 20, "casa": "REM", "fora": "VIT", "pc": 2, "pf": 0},
    ],
    "PAL": [
        {"r": 16, "casa": "PAL", "fora": "CRU", "pc": 1, "pf": 1},
        {"r": 17, "casa": "FLA", "fora": "PAL", "pc": 0, "pf": 3},
        {"r": 18, "casa": "PAL", "fora": "CHA", "pc": 1, "pf": 0},
        {"r": 19, "casa": "CFC", "fora": "PAL", "pc": 1, "pf": 3},
        {"r": 20, "casa": "PAL", "fora": "CAM", "pc": 1, "pf": 2},
    ],
    "FLU": [
        {"r": 16, "casa": "FLU", "fora": "SAO", "pc": 2, "pf": 1},
        {"r": 17, "casa": "MIR", "fora": "FLU", "pc": 1, "pf": 0},
        {"r": 18, "casa": "CRU", "fora": "FLU", "pc": 1, "pf": 1},
        {"r": 19, "casa": "FLU", "fora": "RBB", "pc": 1, "pf": 1},
        {"r": 20, "casa": "GRE", "fora": "FLU", "pc": 1, "pf": 1},
    ],
    "BAH": [
        {"r": 16, "casa": "BAH", "fora": "GRE", "pc": 1, "pf": 1},
        {"r": 17, "casa": "CFC", "fora": "BAH", "pc": 3, "pf": 2},
        {"r": 18, "casa": "BAH", "fora": "BOT", "pc": 2, "pf": 1},
        {"r": 19, "casa": "CAM", "fora": "BAH", "pc": 1, "pf": 1},
        {"r": 20, "casa": "BAH", "fora": "COR", "pc": 1, "pf": 1},
    ],
    "COR": [
        {"r": 16, "casa": "BOT", "fora": "COR", "pc": 3, "pf": 1},
        {"r": 17, "casa": "COR", "fora": "CAM", "pc": 1, "pf": 0},
        {"r": 18, "casa": "GRE", "fora": "COR", "pc": 1, "pf": 3},
        {"r": 19, "casa": "COR", "fora": "REM", "pc": 3, "pf": 0},
        {"r": 20, "casa": "BAH", "fora": "COR", "pc": 1, "pf": 1},
    ],
    "CAP": [
        {"r": 16, "casa": "CAP", "fora": "FLA", "pc": 1, "pf": 1},
        {"r": 17, "casa": "REM", "fora": "CAP", "pc": 1, "pf": 2},
        {"r": 18, "casa": "CAP", "fora": "MIR", "pc": 1, "pf": 0},
        {"r": 19, "casa": "SAO", "fora": "CAP", "pc": 1, "pf": 2},
        {"r": 20, "casa": "CAP", "fora": "INT", "pc": 2, "pf": 0},
    ],
    "CFC": [
        {"r": 16, "casa": "SAN", "fora": "CFC", "pc": 0, "pf": 3},
        {"r": 17, "casa": "CFC", "fora": "BAH", "pc": 3, "pf": 2},
        {"r": 18, "casa": "FLA", "fora": "CFC", "pc": 3, "pf": 0},
        {"r": 19, "casa": "CFC", "fora": "PAL", "pc": 1, "pf": 3},
        {"r": 20, "casa": "RBB", "fora": "CFC", "pc": 0, "pf": 0},
    ],
    "CRU": [
        {"r": 16, "casa": "PAL", "fora": "CRU", "pc": 1, "pf": 1},
        {"r": 17, "casa": "CRU", "fora": "CHA", "pc": 2, "pf": 1},
        {"r": 18, "casa": "CRU", "fora": "FLU", "pc": 1, "pf": 1},
        {"r": 19, "casa": "INT", "fora": "CRU", "pc": 1, "pf": 2},
        {"r": 20, "casa": "CRU", "fora": "BOT", "pc": 0, "pf": 1},
    ],
}

GAME_DIALOGUE = [
    {
        "q": ("THALITA", "Antônio, Mirassol e Remo estão separados por apenas uma posição. Mas a sequência recente conta uma história mais clara. O que pesa mais aqui: o mando do Mirassol ou a recuperação do Remo?"),
        "a": ("ANTÔNIO", "O Mirassol venceu Fluminense e Grêmio, perdeu para Atlético Mineiro e Athletico e empatou com o Vasco. Já o Remo ganhou três das últimas cinco, contra Chapecoense, São Paulo e Vitória. Para mim, o momento do Remo equilibra um jogo em que o mando favorece o Mirassol."),
        "f": ("FRANCISCA", "Então eu evitaria chamar qualquer lado de seguro. Marcelo Rangel pode pontuar por defesas, mas empilhar muitos atletas do Remo aumenta demais a dependência de um único confronto."),
    },
    {
        "q": ("FRANCISCA", "Thalita, o Internacional perdeu quatro das últimas cinco, enquanto o Flamengo venceu duas, empatou duas e perdeu uma. Você escalaria Pedro e Samuel Lino juntos fora de casa?"),
        "a": ("THALITA", "Em uma escalação agressiva, sim. O Flamengo marcou sete gols nas duas vitórias recentes, contra Coritiba e Chapecoense. Mas usar os dois atacantes concentra o risco: se o jogo travar no Beira-Rio, duas vagas ofensivas ficam comprometidas."),
        "f": ("ANTÔNIO", "Concordo. Para um time conservador, eu escolheria um dos dois. Samuel Lino custa menos; Pedro oferece maior referência de área. A decisão depende do orçamento e do perfil da escalação."),
    },
    {
        "q": ("ANTÔNIO", "Francisca, o Palmeiras vinha de três vitórias seguidas, mas perdeu para o Atlético Mineiro na rodada anterior. O Vitória alternou vitória e derrota nas cinco últimas. Essa derrota recente reduz a confiança em Arias?"),
        "a": ("FRANCISCA", "Reduz um pouco, mas não elimina a indicação. O Palmeiras venceu Flamengo, Chapecoense e Coritiba nesse recorte. Arias continua apoiado pelo desempenho coletivo, enquanto Lucas Arcanjo é uma aposta oposta: pode fazer muitas defesas, mas corre risco alto de gols sofridos."),
        "f": ("THALITA", "Eu separaria bem os perfis: Arias busca teto e participação ofensiva; Lucas Arcanjo busca scouts de goleiro. Não são escolhas que dependem da mesma leitura do jogo."),
    },
    {
        "q": ("THALITA", "Antônio, o Fluminense empatou três jogos seguidos, e o Bahia também empatou três das últimas cinco. Isso aponta para um duelo travado ou apenas mostra equipes difíceis de vencer?"),
        "a": ("ANTÔNIO", "Vejo mais equilíbrio do que falta de qualidade. O Fluminense venceu o São Paulo e depois somou empates com Cruzeiro, Bragantino e Grêmio. O Bahia perdeu apenas para o Coritiba nesse período. Por isso, eu valorizaria atletas com scouts próprios em vez de depender de goleada ou saldo de gol."),
        "f": ("FRANCISCA", "Nesse confronto, regularidade vale mais que favoritismo. É um jogo em que o jogador pode pontuar bem mesmo sem o clube dominar completamente."),
    },
    {
        "q": ("FRANCISCA", "Thalita, Corinthians e Athletico chegam em ótima fase: o Corinthians venceu três e empatou uma das últimas quatro; o Athletico venceu quatro seguidas. Quem oferece o melhor teto?"),
        "a": ("THALITA", "O Athletico tem a sequência mais forte, com vitórias sobre Remo, Mirassol, São Paulo e Internacional. Viveros ganha força por esse momento. Mas o Corinthians venceu Atlético Mineiro, Grêmio e Remo antes de empatar com o Bahia, então não vejo um visitante confortável."),
        "f": ("ANTÔNIO", "É justamente o jogo para aceitar divergência. Viveros tem teto alto; Matheuzinho e Gabriel Paulista contam com mando e fase competitiva. Eu não concentraria defesa e ataque dos dois lados no mesmo time."),
    },
    {
        "q": ("ANTÔNIO", "Francisca, o Coritiba venceu duas, perdeu duas e empatou uma; o Cruzeiro venceu duas, empatou duas e perdeu a última. Em um jogo tão parelho, onde está o diferencial?"),
        "a": ("FRANCISCA", "O diferencial está no tipo de scout. O Coritiba venceu Santos e Bahia, depois sofreu contra Flamengo e Palmeiras. O Cruzeiro pontuou fora contra Palmeiras e Internacional e tem Matheus Pereira como principal criador. Eu confiaria mais em scouts individuais do que no resultado final."),
        "f": ("THALITA", "Por isso Thiago Santos e Jacy entram pelo custo, enquanto Matheus Pereira entra por criação e teto. São escolhas com objetivos diferentes dentro da mesma partida."),
    },
]


def concise_onscreen(text: str, limit: int = 150) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def result_for(team: str, item: dict) -> str:
    gf = item["pc"] if item["casa"] == team else item["pf"]
    ga = item["pf"] if item["casa"] == team else item["pc"]
    return "V" if gf > ga else "D" if gf < ga else "E"


def summary(team: str) -> str:
    values = [result_for(team, item) for item in HISTORY.get(team, [])]
    return f"{values.count('V')} vitórias, {values.count('E')} empates e {values.count('D')} derrotas"


def historical_game_card(game: dict, output: Path) -> None:
    image = v3.gradient()
    draw = ImageDraw.Draw(image)
    home = game["mandante_sigla"]
    away = game["visitante_sigla"]
    v3.card_header(draw, f"{home} x {away}", "Últimos cinco jogos, adversários, placares e mando de campo.")

    columns = [(28, 320, home), (340, 632, away)]
    colors = {"V": (53, 210, 122), "E": (255, 190, 55), "D": (237, 71, 96)}
    for left, right, team in columns:
        v3.rounded(draw, (left, 190, right, 730), 22, (5, 24, 45), (32, 196, 255), 2)
        draw.text((left + 18, 208), team, font=base.font(25, True), fill=base.WHITE)
        draw.text((left + 18, 242), summary(team), font=base.font(14, True), fill=base.SILVER)
        y = 285
        for item in HISTORY.get(team, []):
            result = result_for(team, item)
            color = colors[result]
            v3.rounded(draw, (left + 14, y, right - 14, y + 72), 14, (7, 29, 50), color, 2)
            draw.text((left + 27, y + 10), f"R{item['r']}  {item['casa']} {item['pc']} x {item['pf']} {item['fora']}", font=base.font(16, True), fill=base.WHITE)
            mando = "casa" if item["casa"] == team else "fora"
            draw.text((left + 27, y + 40), f"{result} • {mando}", font=base.font(14, True), fill=color)
            y += 82
    image.save(output, "PNG", optimize=True)


def create_frame_v4(visual_path: Path | None, collage_paths: List[Path], speaker: str, text: str, round_value: int, output: Path) -> None:
    if visual_path is None:
        foreground = base.fit_image(base.make_collage(collage_paths), 620, 720)
    else:
        foreground = base.fit_image(Image.open(visual_path), 620, 720)
    background = foreground.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(25)).convert("RGBA")
    frame = Image.alpha_composite(background, Image.new("RGBA", (WIDTH, HEIGHT), (0, 8, 22, 190)))
    draw = ImageDraw.Draw(frame)
    v3.rounded(draw, (20, 18, 700, 76), 24, (3, 20, 39, 238), base.LINE, 2)
    header = f"ANÁLISE DIALOGADA • RODADA {round_value}"
    hb = draw.textbbox((0, 0), header, font=base.font(25, True))
    draw.text(((WIDTH - (hb[2] - hb[0])) / 2, 32), header, font=base.font(25, True), fill=base.WHITE)
    frame.alpha_composite(foreground.convert("RGBA"), ((WIDTH - foreground.width) // 2, 92))
    v3.rounded(draw, (28, 824, 692, 850), 12, (2, 12, 27, 255), base.LINE, 1)
    accent = base.SPEAKER_COLORS[speaker]
    v3.rounded(draw, (22, 862, 698, 1238), 30, (4, 18, 36, 252), accent, 3)
    v3.rounded(draw, (48, 884, 275, 942), 20, (accent[0] // 5, accent[1] // 5, accent[2] // 5, 255), accent, 2)
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
    footer = "@dicascartolaportalsimonsports  •  PORTAL SIMONSPORTS"
    fb = draw.textbbox((0, 0), footer, font=base.font(16, True))
    draw.text(((WIDTH - (fb[2] - fb[0])) / 2, 1253), footer, font=base.font(16, True), fill=base.SILVER)
    frame.convert("RGB").save(output, "PNG", optimize=True)


def seg(speaker: str, text: str, visual: str, onscreen: str) -> v3.Segment:
    return v3.Segment(speaker, v3.speaker_voice(speaker), v3.sanitize_tts(text), visual, concise_onscreen(onscreen))


def build_dialogue_v4(round_value: int, data: dict) -> List[v3.Segment]:
    original = V3_BUILD_DIALOGUE_ORIGINAL(round_value, data)
    result: List[v3.Segment] = [
        seg("FRANCISCA", f"Começa agora a análise da rodada {round_value}. Vamos direto aos jogos, ao momento das equipes e às escolhas que podem fazer diferença na escalação.", "rodada", "Rodada, momento dos times e escolhas recomendadas."),
        seg("ANTÔNIO", "São seis confrontos válidos. Em vez de resumir a fase recente apenas com letras, vamos mostrar adversários, placares, mando e o que cada sequência realmente indica.", "rodada", "Últimos cinco jogos completos de cada equipe."),
    ]

    for index, dialogue in enumerate(GAME_DIALOGUE):
        visual = f"jogo_{index}"
        for key in ("q", "a", "f"):
            speaker, text = dialogue[key]
            result.append(seg(speaker, text, visual, text))

    # Mantém as pontuações dos três modelos.
    for segment in original[15:19]:
        result.append(seg(segment.speaker, segment.text, segment.visual, segment.onscreen))

    # Mantém a abertura curta da análise individual e remove perguntas mecânicas ao fim de cada atleta.
    result.append(seg("ANTÔNIO", "Agora vamos aos jogadores. Em cada posição, a análise considera preço, últimos jogos, adversário e o papel daquele atleta dentro do modelo.", "Marcelo Rangel", "Jogadores: preço, fase, confronto e função no modelo."))
    player_segments = [s for s in original if s.visual in data.get("jogadores", {}) and s.text.startswith("Sobre")]
    reactions = {
        "Lucas Arcanjo": ("FRANCISCA", "Nesse caso eu concordo com a lógica das defesas, mas não trataria o saldo de gol como provável."),
        "Matheuzinho": ("ANTÔNIO", "Aqui aparece uma divergência interessante: o mando ajuda o Corinthians, mas a fase do Athletico impede uma escolha defensiva confortável."),
        "Arias": ("THALITA", "Arias é consenso, mas consenso não significa ausência de risco. O preço exige que ele participe diretamente da pontuação."),
        "Viveros": ("FRANCISCA", "Viveros tem o melhor momento recente entre os atacantes, embora enfrente um Corinthians competitivo em casa."),
        "Samuel Lino": ("ANTÔNIO", "Entre Samuel Lino e Pedro, a diferença de preço pode decidir. Usar os dois juntos é opção agressiva, não obrigatória."),
    }
    for segment in player_segments:
        text = re.sub(r"\s+(Francisca|Antônio|Thalita), qual é o ponto decisivo na escolha de .+\?$", "", segment.text)
        result.append(seg(segment.speaker, text, segment.visual, segment.onscreen))
        if segment.visual in reactions:
            speaker, reaction = reactions[segment.visual]
            result.append(seg(speaker, reaction, segment.visual, reaction))

    for segment in original[-5:]:
        if "próxima rodada poderá usar" in segment.text:
            continue
        result.append(seg(segment.speaker, segment.text, segment.visual, segment.onscreen))
    return result


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    original_version = v3.VERSION
    original_frame = v3.create_frame_v3
    original_dialogue = v3.build_dialogue
    original_game_card = v3.game_card
    try:
        v3.VERSION = VERSION
        v3.create_frame_v3 = create_frame_v4
        v3.build_dialogue = build_dialogue_v4
        v3.game_card = historical_game_card
        return v3.generate(round_value, repo_root, output_path)
    finally:
        v3.VERSION = original_version
        v3.create_frame_v3 = original_frame
        v3.build_dialogue = original_dialogue
        v3.game_card = original_game_card


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o vídeo V4 com histórico e diálogo real.")
    parser.add_argument("--rodada", type=int, default=21)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/piloto_analise_tecnica_dialogada_rodada_21_v4.mp4")
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
