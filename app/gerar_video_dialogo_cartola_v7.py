from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v6_base as v6

VERSION = "cartola_dialogo_tecnico_v7_analise_individual_2026_07_31"


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def number(value: Any) -> str:
    return f"{as_float(value):.2f}".replace(".", ",")


def parse_goals(text: Any) -> tuple[int, int]:
    match = re.search(
        r"marcou\s+(\d+)\s+e\s+sofreu\s+(\d+)",
        clean(text),
        flags=re.IGNORECASE,
    )
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def game_context(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for game in data.get("jogos") or []:
        home = clean(game.get("mandante_sigla")).upper()
        away = clean(game.get("visitante_sigla")).upper()
        home_for, home_against = parse_goals(game.get("historico_mandante_falado"))
        away_for, away_against = parse_goals(game.get("historico_visitante_falado"))
        result[home] = {
            "forma_adversario": clean(game.get("forma_visitante")),
            "gols_pro_ult5": home_for,
            "gols_contra_ult5": home_against,
            "rival_gols_pro_ult5": away_for,
            "rival_gols_contra_ult5": away_against,
        }
        result[away] = {
            "forma_adversario": clean(game.get("forma_mandante")),
            "gols_pro_ult5": away_for,
            "gols_contra_ult5": away_against,
            "rival_gols_pro_ult5": home_for,
            "rival_gols_contra_ult5": home_against,
        }
    return result


def model_text(models: List[str]) -> str:
    values = [clean(item) for item in models if clean(item)]
    if not values:
        return "na seleção publicada"
    if len(values) == 1:
        return f"no {values[0]}"
    return "nos modelos " + " e ".join(values)


def role_analysis(player: Dict[str, Any]) -> str:
    pos = clean(player.get("posicao")).upper()
    club = clean(player.get("clube_nome"))
    rival = clean(player.get("adversario"))
    own_for = as_int(player.get("gols_pro_ult5"))
    own_against = as_int(player.get("gols_contra_ult5"))
    rival_for = as_int(player.get("rival_gols_pro_ult5"))
    rival_against = as_int(player.get("rival_gols_contra_ult5"))

    if pos == "GOL":
        return (
            f"O {rival} marcou {rival_for} gols nos últimos cinco jogos. "
            "Isso equilibra possibilidade de defesas com o risco de perder o saldo."
        )
    if pos in {"LAT", "ZAG"}:
        if own_against <= 5 and rival_for <= 5:
            return (
                f"O {club} sofreu {own_against} gols e o {rival} marcou {rival_for} "
                "nos últimos cinco jogos, cenário que favorece a busca pelo saldo."
            )
        return (
            f"O {club} sofreu {own_against} gols nos últimos cinco jogos. "
            "A escolha precisa de scouts defensivos e não pode depender apenas do saldo."
        )
    if pos in {"MEI", "ATA"}:
        return (
            f"O {club} marcou {own_for} gols e o {rival} sofreu {rival_against} "
            "nos últimos cinco jogos. A escolha busca participação ofensiva nesse confronto."
        )
    if pos == "TEC":
        return (
            f"A escolha acompanha o contexto coletivo do {club}, que enfrenta o {rival} "
            f"ocupando a {as_int(player.get('pos_adversario'))}ª posição."
        )
    return "A escolha combina preço, desempenho individual e contexto do confronto."


def enrich_players(data: Dict[str, Any]) -> None:
    context = game_context(data)
    for name, player in (data.get("jogadores") or {}).items():
        if not isinstance(player, dict):
            continue
        player.update(context.get(clean(player.get("clube")).upper(), {}))
        models = model_text(player.get("modelos") or [])
        club = clean(player.get("clube_nome"))
        rival = clean(player.get("adversario"))
        mando = clean(player.get("mando"))
        media = as_float(player.get("media"))
        jogos = as_int(player.get("jogos"))
        ultima = as_float(player.get("ultima_pontuacao"))
        projecao = as_float(player.get("exp_score"))
        preco = as_float(player.get("preco"))
        posicao = clean(player.get("posicao_extenso"))
        variant = sum(ord(char) for char in name) % 4

        questions = [
            f"{name} está {models} contra o {rival}. O que sustenta essa escolha?",
            f"Por que {name} ganhou espaço {models} para este confronto?",
            f"Os números de {name} justificam a escalação diante do {rival}?",
            f"Em {name}, a aposta é segurança, teto ou custo-benefício?",
        ]
        openings = [
            f"O primeiro argumento é o confronto {mando} e o preço de {number(preco)} cartoletas.",
            f"A escolha não vem apenas do nome. {name} custa {number(preco)} e joga {mando}.",
            f"A leitura é de custo-benefício: {name} enfrenta o {rival} {mando}.",
            f"O ponto central é comparar o desempenho de {name} com o momento do {club}.",
        ]

        metrics = [f"média de {number(media)} em {jogos} jogos"] if jogos else []
        if player.get("media_casa") is not None and "casa" in mando:
            metrics.append(f"média em casa de {number(player.get('media_casa'))}")
        if player.get("media_fora") is not None and "fora" in mando:
            metrics.append(f"média fora de casa de {number(player.get('media_fora'))}")
        metrics.append(f"última pontuação de {number(ultima)}")
        if player.get("pontuacao_primeiro_turno") is not None:
            metrics.append(
                f"{number(player.get('pontuacao_primeiro_turno'))} pontos no primeiro turno"
            )
        if projecao > 0:
            metrics.append(f"projeção de {number(projecao)}")

        specific = role_analysis(player)
        risk: List[str] = []
        if "fora" in mando and as_int(player.get("pos_adversario")) <= 5:
            risk.append("atua fora contra uma equipe do bloco superior")
        if jogos and ultima + 2 < media:
            risk.append("vem de pontuação abaixo da própria média")
        if not risk:
            risk.append("o bom contexto não garante pontuação")

        audio = (
            f"{openings[variant]} Os dados mostram {', '.join(metrics)}. "
            f"{specific} O ponto de atenção é que {' e '.join(risk)}."
        )

        card_metrics: List[str] = []
        if player.get("media_casa") is not None and "casa" in mando:
            card_metrics.append(f"média em casa {number(player.get('media_casa'))}")
        elif player.get("media_fora") is not None and "fora" in mando:
            card_metrics.append(f"média fora {number(player.get('media_fora'))}")
        else:
            card_metrics.append(f"média geral {number(media)}")
        card_metrics.append(f"última {number(ultima)}")
        if player.get("pontuacao_primeiro_turno") is not None:
            card_metrics.append(
                f"1º turno {number(player.get('pontuacao_primeiro_turno'))}"
            )
        elif projecao > 0:
            card_metrics.append(f"projeção {number(projecao)}")

        rationales = [
            f"{models.capitalize()} • {' • '.join(card_metrics)}. {specific}",
            f"Motivo: {' • '.join(card_metrics)}. {specific}",
            f"Leitura do confronto: {' • '.join(card_metrics)}. {specific}",
            f"Custo de {number(preco)} • {' • '.join(card_metrics)}. {specific}",
        ]
        player.update(
            {
                "pergunta_analise": questions[variant],
                "analise_escalacao_audio": audio,
                "racional": rationales[variant],
                "analise_individual_especifica": True,
                "posicao_extenso": posicao,
            }
        )


def player_dialogue_v7(
    segments: List[v3.Segment],
    players: Dict[str, Dict[str, Any]],
) -> None:
    v6.segment(
        segments,
        "ANTÔNIO",
        "Agora vamos discutir o motivo de cada escolha individual.",
        next(iter(players)) if players else "rodada",
        "Escolhas individuais: perguntas, respostas e riscos.",
    )
    pairs = [
        ("FRANCISCA", "ANTÔNIO"),
        ("THALITA", "FRANCISCA"),
        ("ANTÔNIO", "THALITA"),
    ]
    for index, (name, player) in enumerate(players.items()):
        questioner, responder = pairs[index % len(pairs)]
        question = clean(player.get("pergunta_analise"))
        answer = clean(player.get("analise_escalacao_audio"))
        if not question or not answer:
            raise RuntimeError(f"Análise específica ausente para {name}.")
        v6.segment(segments, questioner, question, name, f"Por que {name} foi escalado?")
        v6.segment(segments, responder, answer, name, clean(player.get("racional")))


def update_manifest(output_path: Path) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    spoken = " ".join(
        clean(item.get("texto_falado")) for item in payload.get("timeline") or []
    ).lower()
    prohibited = [
        "aparece em 1 modelo do snapshot",
        "aparece em 2 modelos do snapshot",
        "preserva exatamente a seleção enviada",
    ]
    found = [term for term in prohibited if term in spoken]
    if found:
        raise RuntimeError("Justificativa genérica ainda presente: " + ", ".join(found))
    if not any(term in spoken for term in ("o que sustenta", "por que", "justificam")):
        raise RuntimeError("O diálogo individual não contém questionamentos.")
    payload.update(
        {
            "versao": VERSION,
            "dialogo_individual_real": True,
            "justificativas_repetidas_bloqueadas": True,
            "media_por_mando_quando_disponivel": True,
            "primeiro_turno_quando_disponivel": True,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    enrich_players(data)
    data["analise_individual_especifica"] = True
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    old_version = v6.VERSION
    old_dialogue = v6.player_dialogue
    try:
        v6.VERSION = VERSION
        v6.player_dialogue = player_dialogue_v7
        result = v6.generate(round_value, repo_root, output_path)
        update_manifest(output_path)
        return result
    finally:
        v6.VERSION = old_version
        v6.player_dialogue = old_dialogue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
