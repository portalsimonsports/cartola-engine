from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests

API_BASE = "https://api.cartola.globo.com"

CLUBE_NOME_POR_SIGLA = {
    "FLA": "Flamengo",
    "BOT": "Botafogo",
    "COR": "Corinthians",
    "BAH": "Bahia",
    "FLU": "Fluminense",
    "VAS": "Vasco da Gama",
    "PAL": "Palmeiras",
    "SAO": "São Paulo",
    "SAN": "Santos",
    "RBB": "Red Bull Bragantino",
    "CAM": "Atlético Mineiro",
    "CRU": "Cruzeiro",
    "GRE": "Grêmio",
    "INT": "Internacional",
    "VIT": "Vitória",
    "CAP": "Athletico Paranaense",
    "CFC": "Coritiba",
    "CHA": "Chapecoense",
    "REM": "Remo",
    "MIR": "Mirassol",
}

POSICAO_NOME = {
    "GOL": "goleiro",
    "LAT": "lateral",
    "ZAG": "zagueiro",
    "MEI": "meia",
    "ATA": "atacante",
    "TEC": "técnico",
}


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


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


def key_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", safe(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida da API Cartola em {path}.")
    return payload


def score_from_match(match: Dict[str, Any]) -> Tuple[int, int] | None:
    home = match.get("placar_oficial_mandante")
    away = match.get("placar_oficial_visitante")
    if home in (None, ""):
        home = match.get("placar_casa")
    if away in (None, ""):
        away = match.get("placar_vis")
    if home in (None, "") or away in (None, ""):
        return None
    return as_int(home), as_int(away)


def club_id(match: Dict[str, Any], home: bool) -> int:
    keys = (
        ("clube_casa_id", "casa_id")
        if home
        else ("clube_visitante_id", "visitante_id")
    )
    for key in keys:
        value = as_int(match.get(key))
        if value:
            return value
    return 0


def load_round(round_value: int) -> Dict[str, Any]:
    return api_get(f"partidas/{round_value}")


def normalize_clubs(payloads: Iterable[Dict[str, Any]]) -> Tuple[Dict[int, str], Dict[int, str]]:
    sigla_by_id: Dict[int, str] = {}
    name_by_id: Dict[int, str] = {}
    for payload in payloads:
        clubs = payload.get("clubes") or {}
        if not isinstance(clubs, dict):
            continue
        for raw_id, item in clubs.items():
            if not isinstance(item, dict):
                continue
            cid = as_int(item.get("id") or raw_id)
            sigla = safe(item.get("abreviacao") or item.get("nome")).upper()
            if not cid or not sigla:
                continue
            sigla_by_id[cid] = sigla
            name_by_id[cid] = CLUBE_NOME_POR_SIGLA.get(sigla, safe(item.get("nome") or sigla))
    return sigla_by_id, name_by_id


def classification_and_form(
    round_value: int,
) -> Tuple[
    Dict[int, Dict[str, Any]],
    Dict[int, List[Dict[str, Any]]],
    Dict[int, str],
    Dict[int, str],
    Dict[str, Any],
]:
    payloads: List[Dict[str, Any]] = []
    for number in range(1, round_value + 1):
        payloads.append(load_round(number))

    sigla_by_id, name_by_id = normalize_clubs(payloads)
    current = payloads[-1]
    current_matches = [m for m in (current.get("partidas") or []) if isinstance(m, dict)]

    current_ids = set()
    for match in current_matches:
        current_ids.add(club_id(match, True))
        current_ids.add(club_id(match, False))
    current_ids.discard(0)

    table: Dict[int, Dict[str, Any]] = {
        cid: {
            "id": cid,
            "sigla": sigla_by_id.get(cid, str(cid)),
            "nome": name_by_id.get(cid, sigla_by_id.get(cid, str(cid))),
            "jogos": 0,
            "pontos": 0,
            "vitorias": 0,
            "empates": 0,
            "derrotas": 0,
            "gols_pro": 0,
            "gols_contra": 0,
            "saldo": 0,
            "posicao": 0,
        }
        for cid in current_ids
    }
    history: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for round_number, payload in enumerate(payloads[:-1], start=1):
        for match in payload.get("partidas") or []:
            if not isinstance(match, dict):
                continue
            result = score_from_match(match)
            if result is None:
                continue
            home_id = club_id(match, True)
            away_id = club_id(match, False)
            if home_id not in table or away_id not in table:
                continue
            home_goals, away_goals = result
            home = table[home_id]
            away = table[away_id]

            home["jogos"] += 1
            away["jogos"] += 1
            home["gols_pro"] += home_goals
            home["gols_contra"] += away_goals
            away["gols_pro"] += away_goals
            away["gols_contra"] += home_goals

            if home_goals > away_goals:
                home["vitorias"] += 1
                home["pontos"] += 3
                away["derrotas"] += 1
                home_letter, away_letter = "V", "D"
            elif home_goals < away_goals:
                away["vitorias"] += 1
                away["pontos"] += 3
                home["derrotas"] += 1
                home_letter, away_letter = "D", "V"
            else:
                home["empates"] += 1
                away["empates"] += 1
                home["pontos"] += 1
                away["pontos"] += 1
                home_letter = away_letter = "E"

            history[home_id].append(
                {
                    "rodada": round_number,
                    "resultado": home_letter,
                    "gols_pro": home_goals,
                    "gols_contra": away_goals,
                    "adversario_id": away_id,
                }
            )
            history[away_id].append(
                {
                    "rodada": round_number,
                    "resultado": away_letter,
                    "gols_pro": away_goals,
                    "gols_contra": home_goals,
                    "adversario_id": home_id,
                }
            )

    for item in table.values():
        item["saldo"] = item["gols_pro"] - item["gols_contra"]

    ordered = sorted(
        table.values(),
        key=lambda x: (
            -x["pontos"],
            -x["vitorias"],
            -x["saldo"],
            -x["gols_pro"],
            x["nome"],
        ),
    )
    for position, item in enumerate(ordered, start=1):
        item["posicao"] = position

    return table, history, sigla_by_id, name_by_id, current


def recent_summary(
    cid: int,
    table: Dict[int, Dict[str, Any]],
    history: Dict[int, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    recent = sorted(history.get(cid, []), key=lambda x: x["rodada"])[-5:]
    letters = [item["resultado"] for item in recent]
    wins = letters.count("V")
    draws = letters.count("E")
    losses = letters.count("D")
    goals_for = sum(as_int(item["gols_pro"]) for item in recent)
    goals_against = sum(as_int(item["gols_contra"]) for item in recent)
    points = wins * 3 + draws
    team = table[cid]
    form = " ".join(letters)
    spoken = (
        f"{team['nome']} ocupa a {team['posicao']}ª posição, com {team['pontos']} pontos em "
        f"{team['jogos']} jogos. Nos últimos {len(recent)} jogos, somou {wins} vitória"
        f"{'' if wins == 1 else 's'}, {draws} empate{'' if draws == 1 else 's'} e "
        f"{losses} derrota{'' if losses == 1 else 's'}, marcou {goals_for} e sofreu "
        f"{goals_against} gols."
    )
    return {
        "forma": form,
        "falado": spoken,
        "vitorias": wins,
        "empates": draws,
        "derrotas": losses,
        "pontos": points,
        "gols_pro": goals_for,
        "gols_contra": goals_against,
    }


def parse_match_datetime(match: Dict[str, Any]) -> Tuple[str, str]:
    value = safe(match.get("partida_data") or match.get("data"))
    if not value:
        return "Data a confirmar", "Horário a confirmar"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%d/%m"), parsed.strftime("%H:%M")
    except Exception:
        return value, "Horário a confirmar"


def enrich_games(
    round_value: int,
    data: Dict[str, Any],
    table: Dict[int, Dict[str, Any]],
    history: Dict[int, List[Dict[str, Any]]],
    sigla_by_id: Dict[int, str],
    name_by_id: Dict[int, str],
    current: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    matches = [m for m in (current.get("partidas") or []) if isinstance(m, dict)]
    enriched: List[Dict[str, Any]] = []
    context_by_sigla: Dict[str, Dict[str, Any]] = {}

    for match in matches:
        home_id = club_id(match, True)
        away_id = club_id(match, False)
        if home_id not in table or away_id not in table:
            raise RuntimeError(f"Clube da rodada {round_value} ausente da classificação: {home_id} x {away_id}")

        home = table[home_id]
        away = table[away_id]
        home_recent = recent_summary(home_id, table, history)
        away_recent = recent_summary(away_id, table, history)
        date_text, time_text = parse_match_datetime(match)
        stadium = safe(match.get("local"), "Local a confirmar")

        if home_recent["pontos"] > away_recent["pontos"]:
            reading = (
                f"{home['nome']} chega em momento recente superior e ainda tem o mando, mas a "
                "escolha individual deve considerar os scouts e o preço de cada atleta."
            )
        elif away_recent["pontos"] > home_recent["pontos"]:
            reading = (
                f"{away['nome']} apresenta desempenho recente superior, embora atue fora de casa. "
                "O confronto pede equilíbrio entre momento coletivo e risco do mando adversário."
            )
        else:
            reading = (
                "As equipes têm rendimento recente semelhante. O diferencial para o Cartola deve "
                "vir de preço, média individual, scouts e função tática."
            )

        game = {
            "mandante": home["nome"],
            "mandante_sigla": home["sigla"],
            "visitante": away["nome"],
            "visitante_sigla": away["sigla"],
            "data": date_text,
            "hora": time_text,
            "estadio": stadium,
            "pos_mandante": home["posicao"],
            "pos_visitante": away["posicao"],
            "forma_mandante": home_recent["forma"],
            "forma_visitante": away_recent["forma"],
            "historico_mandante_falado": home_recent["falado"],
            "historico_visitante_falado": away_recent["falado"],
            "resumo_mandante": home_recent["falado"],
            "resumo_visitante": away_recent["falado"],
            "leitura": reading,
            "destaque_cartola": (
                f"Na tabela, {home['nome']} é o {home['posicao']}º colocado e "
                f"{away['nome']} é o {away['posicao']}º colocado."
            ),
        }
        enriched.append(game)

        context_by_sigla[home["sigla"]] = {
            "clube_nome": home["nome"],
            "clube_posicao": home["posicao"],
            "adversario": away["nome"],
            "adversario_sigla": away["sigla"],
            "adversario_posicao": away["posicao"],
            "mando": "em casa",
            "forma": home_recent["forma"],
        }
        context_by_sigla[away["sigla"]] = {
            "clube_nome": away["nome"],
            "clube_posicao": away["posicao"],
            "adversario": home["nome"],
            "adversario_sigla": home["sigla"],
            "adversario_posicao": home["posicao"],
            "mando": "fora de casa",
            "forma": away_recent["forma"],
        }

    data["jogos"] = enriched
    return context_by_sigla


def market_players() -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    payload = api_get("atletas/mercado")
    by_id: Dict[int, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("atletas") or []:
        if not isinstance(item, dict):
            continue
        aid = as_int(item.get("atleta_id") or item.get("id"))
        nickname = safe(item.get("apelido") or item.get("nome"))
        normalized = {
            "atleta_id": aid,
            "nome": nickname,
            "media": as_float(item.get("media_num")),
            "jogos": as_int(item.get("jogos_num")),
            "ultima_pontuacao": as_float(item.get("pontos_num")),
            "variacao": as_float(item.get("variacao_num")),
            "preco": as_float(item.get("preco_num")),
            "status_id": as_int(item.get("status_id")),
        }
        if aid:
            by_id[aid] = normalized
        if nickname:
            by_name[key_text(nickname)] = normalized
    return by_id, by_name


def enrich_players(
    data: Dict[str, Any],
    context_by_sigla: Dict[str, Dict[str, Any]],
) -> None:
    by_id, by_name = market_players()
    top5_rows = ((data.get("top5") or {}).get("dados") or [])
    top5_by_name: Dict[str, Dict[str, Any]] = {}

    for row in top5_rows:
        if not isinstance(row, dict):
            continue
        name = safe(row.get("NOME") or row.get("nome"))
        if not name:
            continue
        top5_by_name[key_text(name)] = row
        sigla = safe(row.get("CLUBE") or row.get("clube")).upper()
        context = context_by_sigla.get(sigla, {})
        official = by_id.get(as_int(row.get("ATLETA_ID") or row.get("atleta_id"))) or by_name.get(key_text(name), {})
        row.update(
            {
                "CLUBE_NOME": context.get("clube_nome", CLUBE_NOME_POR_SIGLA.get(sigla, sigla)),
                "CLUBE_POSICAO": as_int(context.get("clube_posicao")),
                "ADVERSARIO": context.get("adversario", ""),
                "MANDO": context.get("mando", ""),
                "MEDIA": as_float(official.get("media")),
                "JOGOS": as_int(official.get("jogos")),
                "ULTIMA_PONTUACAO": as_float(official.get("ultima_pontuacao")),
                "VARIACAO": as_float(official.get("variacao")),
            }
        )

    players = data.get("jogadores") or {}
    for name, player in players.items():
        if not isinstance(player, dict):
            continue
        sigla = safe(player.get("clube")).upper()
        context = context_by_sigla.get(sigla, {})
        official = by_name.get(key_text(name), {})
        top5 = top5_by_name.get(key_text(name), {})
        pos = safe(player.get("posicao")).upper()
        player.update(
            {
                "posicao_extenso": POSICAO_NOME.get(pos, pos.lower()),
                "clube_nome": context.get("clube_nome", CLUBE_NOME_POR_SIGLA.get(sigla, sigla)),
                "pos_clube": as_int(context.get("clube_posicao")),
                "adversario": context.get("adversario", ""),
                "pos_adversario": as_int(context.get("adversario_posicao")),
                "mando": context.get("mando", ""),
                "forma_clube": context.get("forma", ""),
                "media": as_float(official.get("media")),
                "jogos": as_int(official.get("jogos")),
                "ultima_pontuacao": as_float(official.get("ultima_pontuacao")),
                "variacao": as_float(official.get("variacao")),
                "exp_score": as_float(top5.get("EXP_SCORE") or top5.get("exp_score")),
                "factor": as_float(top5.get("FACTOR") or top5.get("factor")),
            }
        )


def enrich_team_models(data: Dict[str, Any], root: Path, round_value: int) -> None:
    file_names = {
        "economico": "time_economico",
        "intermediario": "time_intermediario",
        "pontuacao": "time_pontuacao",
    }
    for key, base_name in file_names.items():
        path = root / "data" / "publicacoes_atuais" / f"{base_name}_rodada_{round_value}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        team = (data.get("times") or {}).get(key)
        if not isinstance(team, dict):
            continue
        team["formacao"] = safe(payload.get("formacao") or (payload.get("meta") or {}).get("esquema"))
        team["capitao"] = safe(payload.get("capitao") or (payload.get("meta") or {}).get("capitao"))
        team["custo"] = as_float(payload.get("custo_total") or (payload.get("meta") or {}).get("custo_total"))
        team["titulares"] = [
            safe(item.get("nome"))
            for item in (payload.get("jogadores") or payload.get("atletas") or [])
            if isinstance(item, dict) and safe(item.get("status"), "TITULAR").upper() != "RESERVA"
        ]


def validate_enriched(data: Dict[str, Any]) -> None:
    games = data.get("jogos") or []
    if len(games) != 10:
        raise RuntimeError(f"Esperados 10 jogos; encontrados {len(games)}.")
    for game in games:
        if as_int(game.get("pos_mandante")) <= 0 or as_int(game.get("pos_visitante")) <= 0:
            raise RuntimeError(f"Classificação inválida: {game}")
        if len(safe(game.get("forma_mandante")).split()) < 3:
            raise RuntimeError(f"Forma recente inválida para {game.get('mandante')}.")
        if len(safe(game.get("forma_visitante")).split()) < 3:
            raise RuntimeError(f"Forma recente inválida para {game.get('visitante')}.")
        if safe(game.get("mandante")) == safe(game.get("mandante_sigla")):
            raise RuntimeError(f"Nome completo ausente para {game.get('mandante_sigla')}.")
        if safe(game.get("visitante")) == safe(game.get("visitante_sigla")):
            raise RuntimeError(f"Nome completo ausente para {game.get('visitante_sigla')}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    path = root / "data" / f"analise_tecnica_rodada_{args.rodada}_v3.json"
    if not path.exists():
        raise RuntimeError(f"Base técnica não encontrada: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    table, history, sigla_by_id, name_by_id, current = classification_and_form(args.rodada)
    context = enrich_games(
        args.rodada,
        data,
        table,
        history,
        sigla_by_id,
        name_by_id,
        current,
    )
    enrich_players(data, context)
    enrich_team_models(data, root, args.rodada)
    validate_enriched(data)

    data["contexto_real_validado"] = True
    data["fonte_classificacao"] = f"API Cartola: partidas/1 até partidas/{args.rodada - 1}"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Base enriquecida com classificação, forma e desempenho reais: {path}")


if __name__ == "__main__":
    main()
