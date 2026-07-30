from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw

import gerar_video_dialogo_cartola_v1 as base
import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v4 as v4


VERSION = "cartola_analise_tecnica_v5_2026_07_30_debate_reforcado"
TITLE = "ANÁLISE"
V4_BUILD_DIALOGUE_ORIGINAL = v4.build_dialogue_v4
V4_FRAME_ORIGINAL = v4.create_frame_v4


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def number(value, digits: int = 2) -> str:
    return f"{safe_float(value):.{digits}f}".replace(".", ",")


def percent(value, digits: int = 1) -> str:
    return f"{safe_float(value) * 100:.{digits}f}%".replace(".", ",")


def team_stats(team: str) -> Dict[str, int]:
    games = v4.HISTORY.get(team, [])
    wins = draws = losses = goals_for = goals_against = 0
    for item in games:
        if item["casa"] == team:
            gf, ga = int(item["pc"]), int(item["pf"])
        else:
            gf, ga = int(item["pf"]), int(item["pc"])
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf < ga:
            losses += 1
        else:
            draws += 1
    return {
        "jogos": len(games),
        "vitorias": wins,
        "empates": draws,
        "derrotas": losses,
        "pontos": wins * 3 + draws,
        "gols_pro": goals_for,
        "gols_contra": goals_against,
        "saldo": goals_for - goals_against,
    }


def seg(speaker: str, text: str, visual: str, onscreen: str) -> v3.Segment:
    return v4.seg(speaker, text, visual, onscreen)


def richer_reaction(segment: v3.Segment, data: dict) -> v3.Segment:
    players = data.get("jogadores", {})
    text = segment.text

    if text.startswith("Nesse caso eu concordo com a lógica das defesas"):
        p = players.get("Lucas Arcanjo", {})
        text = (
            f"Eu concordo com a lógica das defesas, mas não compraria a ideia de segurança. "
            f"A probabilidade de seis ou mais aparece em {percent(p.get('prob_6'))}, enquanto o Poisson de pontos fica em apenas "
            f"{number(p.get('poisson_pontos', 1.67))}. Essa divergência é exatamente o risco que precisa aparecer na análise."
        )
    elif text.startswith("Aqui aparece uma divergência interessante"):
        p = players.get("Matheuzinho", {})
        media = number(p.get("media_ult5")) if p else "não consolidada"
        text = (
            f"Aqui eu discordo de uma leitura defensiva simples. O mando ajuda o Corinthians, mas o Athletico somou treze pontos "
            f"nos últimos cinco jogos. Matheuzinho tem média recente de {media}; portanto, a indicação deve vir pelos scouts laterais, não por saldo de gol presumido."
        )
    elif text.startswith("Arias é consenso"):
        p = players.get("Arias", {})
        text = (
            f"Arias é consenso, mas custa {number(p.get('preco'))} cartoletas, tem variância de {number(p.get('variancia_ult5'))} "
            f"e índice de confiança de apenas {percent(p.get('indice_confianca'))}. A probabilidade de oito ou mais, em {percent(p.get('prob_8'))}, "
            f"sustenta o teto; não elimina o risco do investimento."
        )
    elif text.startswith("Viveros tem o melhor momento recente"):
        p = players.get("Viveros", {})
        text = (
            f"Viveros tem média de {number(p.get('media_ult5'))} nas últimas cinco, mas média esperada de {number(p.get('media_esperada'))} "
            f"e fator de confronto de {number(p.get('fator_confronto', 0.924), 3)}. É capitão pelo teto probabilístico; não porque o jogo seja confortável."
        )
    elif text.startswith("Entre Samuel Lino e Pedro"):
        pedro = players.get("Pedro", {})
        samuel = players.get("Samuel Lino", {})
        text = (
            f"Entre Samuel Lino e Pedro, o preço pesa: {number(samuel.get('preco'))} contra {number(pedro.get('preco'))} cartoletas. "
            f"Mas a variância também é alta nos dois, {number(samuel.get('variancia_ult5'))} e {number(pedro.get('variancia_ult5'))}. "
            f"Usar a dupla é uma decisão agressiva e precisa ser assumida como tal."
        )

    if text == segment.text:
        return segment
    return seg(segment.speaker, text, segment.visual, text)


def build_dialogue_v5(round_value: int, data: dict) -> List[v3.Segment]:
    original = V4_BUILD_DIALOGUE_ORIGINAL(round_value, data)
    players = data.get("jogadores", {})

    result: List[v3.Segment] = [
        seg(
            "FRANCISCA",
            f"Está no ar a análise completa da rodada {round_value}. Seis jogos, três modelos e vinte jogadores sob avaliação. Hoje ninguém vai se esconder atrás de uma lista de nomes: cada escolha terá de sobreviver aos números e ao contraditório.",
            "rodada",
            "Seis jogos, três modelos e vinte escolhas sob análise.",
        ),
        seg(
            "ANTÔNIO",
            "E eu já deixo o aviso: probabilidade alta, isoladamente, não me convence. Vou cobrar forma recente, força do adversário, mando de campo, custo e coerência entre os indicadores.",
            "rodada",
            "Probabilidade sem contexto não basta.",
        ),
        seg(
            "THALITA",
            "Perfeito. E quando a escalação concentrar atletas de um mesmo confronto, eu vou questionar o risco de correlação. O objetivo é mostrar onde o modelo é forte e onde ele pode estar se expondo demais.",
            "rodada",
            "Teto, risco, correlação e custo serão confrontados.",
        ),
        seg(
            "FRANCISCA",
            "Então vamos começar pelos jogos. A tabela mostra a fotografia do campeonato; os últimos cinco resultados mostram a direção do momento. Quando os dois sinais discordarem, haverá debate.",
            "rodada",
            "Tabela e momento recente: sinais que podem divergir.",
        ),
    ]

    # Descarta a abertura anterior e preserva todo o conteúdo técnico do V4.
    for segment in original[2:]:
        current = richer_reaction(segment, data)
        result.append(current)

        # Réplicas adicionais: naturais, incisivas e sustentadas por números.
        if (
            current.visual == "jogo_0"
            and current.speaker == "FRANCISCA"
            and "empilhar muitos atletas do Remo" in current.text
        ):
            mir = team_stats("MIR")
            rem = team_stats("REM")
            result.append(
                seg(
                    "ANTÔNIO",
                    f"Eu acho essa cautela excessiva. O Remo fez {rem['pontos']} pontos e marcou {rem['gols_pro']} gols nas últimas cinco; "
                    f"o Mirassol fez {mir['pontos']} pontos e marcou {mir['gols_pro']}. Se o preço dos atletas do Remo é menor, por que o Econômico não deveria explorar essa diferença?",
                    "jogo_0",
                    f"Debate: Remo {rem['pontos']} pontos no recorte; Mirassol {mir['pontos']}.",
                )
            )

        if (
            current.visual == "jogo_1"
            and current.speaker == "ANTÔNIO"
            and current.text.startswith("Concordo. Para um time conservador")
        ):
            inter = team_stats("INT")
            fla = team_stats("FLA")
            result.append(
                seg(
                    "FRANCISCA",
                    f"Eu seria ainda mais firme: o Flamengo marcou {fla['gols_pro']} e sofreu {fla['gols_contra']} gols no recorte, enquanto o Internacional sofreu {inter['gols_contra']}. "
                    f"Os números justificam exposição ofensiva, mas não obrigam a dobradinha. Um atacante preserva o cenário favorável e reduz a correlação.",
                    "jogo_1",
                    f"Flamengo: {fla['gols_pro']} gols pró; Internacional: {inter['gols_contra']} sofridos.",
                )
            )

        if (
            current.visual == "jogo_4"
            and current.speaker == "ANTÔNIO"
            and "não concentraria defesa e ataque" in current.text
        ):
            cor = team_stats("COR")
            cap = team_stats("CAP")
            result.append(
                seg(
                    "THALITA",
                    f"Mas aí eu vou contestar: o Athletico somou {cap['pontos']} pontos, marcou {cap['gols_pro']} e sofreu apenas {cap['gols_contra']} gols. "
                    f"O Corinthians fez {cor['pontos']} pontos. Se Viveros é capitão dos três modelos, o sistema já escolheu um lado para buscar teto, mesmo que a fala tente parecer neutra.",
                    "jogo_4",
                    f"Athletico: {cap['pontos']} pontos e saldo {cap['saldo']:+d} no recorte.",
                )
            )

        if current.visual == "Arias" and current.text.startswith("Arias é consenso"):
            p = players.get("Arias", {})
            result.append(
                seg(
                    "ANTÔNIO",
                    f"E é justamente aí que eu discordo. Pagar {number(p.get('preco'))} cartoletas em um atleta com confiança de {percent(p.get('indice_confianca'))} "
                    f"é aceitar muita oscilação. Francisca, a probabilidade de {percent(p.get('prob_8'))} para oito ou mais compensa esse preço?",
                    "Arias",
                    "Arias: teto forte, preço alto e confiança baixa.",
                )
            )
            result.append(
                seg(
                    "FRANCISCA",
                    f"Compensa apenas para quem busca teto. A média recente de {number(p.get('media_ult5'))} e a liderança do Palmeiras sustentam a escolha, "
                    f"mas eu não chamaria Arias de peça de segurança. Em um modelo conservador, esse preço precisa ser comparado com duas opções mais baratas da posição.",
                    "Arias",
                    "Arias compensa pelo teto; não deve ser vendido como segurança.",
                )
            )

        if current.visual == "Viveros" and current.text.startswith("Viveros tem média"):
            p = players.get("Viveros", {})
            result.append(
                seg(
                    "THALITA",
                    f"Eu ainda quero uma resposta mais direta: média recente de {number(p.get('media_ult5'))}, média esperada de {number(p.get('media_esperada'))} "
                    f"e confiança de {percent(p.get('indice_confianca'))}. Esses indicadores não contam a mesma história. Por que ele recebe a braçadeira?",
                    "Viveros",
                    "Capitão sob contestação: forma, expectativa e confiança divergem.",
                )
            )
            result.append(
                seg(
                    "ANTÔNIO",
                    f"Porque o capitão é uma escolha de teto. A probabilidade de oito ou mais chega a {percent(p.get('prob_8'))}, e o Athletico fez treze pontos no recorte. "
                    f"Mas eu concordo com a ressalva: quem busca estabilidade não deve interpretar essa braçadeira como garantia.",
                    "Viveros",
                    f"Braçadeira pelo teto: probabilidade 8+ de {percent(p.get('prob_8'))}.",
                )
            )

    return result


def create_frame_v5(
    visual_path: Path | None,
    collage_paths: List[Path],
    speaker: str,
    text: str,
    round_value: int,
    output: Path,
) -> None:
    # Reutiliza o layout sem sobreposição já aprovado no V4.
    V4_FRAME_ORIGINAL(visual_path, collage_paths, speaker, text, round_value, output)

    # Cobre integralmente o cabeçalho anterior e remove a palavra "dialogada".
    image = Image.open(output).convert("RGBA")
    draw = ImageDraw.Draw(image)
    v3.rounded(draw, (20, 18, 700, 76), 24, (3, 20, 39, 255), base.LINE, 2)
    header = f"{TITLE} • RODADA {round_value}"
    hb = draw.textbbox((0, 0), header, font=base.font(25, True))
    draw.text(((base.WIDTH - (hb[2] - hb[0])) / 2, 32), header, font=base.font(25, True), fill=base.WHITE)
    image.convert("RGB").save(output, "PNG", optimize=True)


def update_manifest(output_path: Path) -> None:
    manifest_path = output_path.with_suffix(".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "versao": VERSION,
            "titulo_visual": TITLE,
            "palavra_dialogada_removida": True,
            "abertura_reforcada": True,
            "debate_reforcado": True,
            "replicas_adicionais": 7,
            "criterios_adicionais": [
                "pontos nos últimos cinco jogos",
                "gols marcados e sofridos",
                "saldo recente",
                "posição no campeonato",
                "mando de campo",
                "probabilidades de pontuação",
                "média recente e média esperada",
                "variância",
                "índice de confiança",
                "custo em cartoletas",
                "correlação entre atletas do mesmo confronto",
            ],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    original_version = v4.VERSION
    original_frame = v4.create_frame_v4
    original_dialogue = v4.build_dialogue_v4
    try:
        v4.VERSION = VERSION
        v4.create_frame_v4 = create_frame_v5
        v4.build_dialogue_v4 = build_dialogue_v5
        result = v4.generate(round_value, repo_root, output_path)
        update_manifest(result)
        return result
    finally:
        v4.VERSION = original_version
        v4.create_frame_v4 = original_frame
        v4.build_dialogue_v4 = original_dialogue


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o vídeo V5 com debate técnico reforçado.")
    parser.add_argument("--rodada", type=int, default=21)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/piloto_analise_tecnica_rodada_21_v5.mp4")
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
