from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

API_BASE = "https://api.cartola.globo.com"


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


def key_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def first_value(item: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida em {path}.")
    return payload


def fetch_many(paths: List[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(api_get, path): path for path in paths}
        for future in as_completed(futures):
            path = futures[future]
            try:
                result[path] = future.result()
            except Exception as exc:
                print(f"Aviso: histórico indisponível em {path}: {exc}")
    return result


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


def match_context(payload: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    context: Dict[int, Dict[str, Any]] = {}
    for match in payload.get("partidas") or []:
        if not isinstance(match, dict):
            continue
        home = club_id(match, True)
        away = club_id(match, False)
        if home and away:
            context[home] = {"mando": "casa", "adversario_id": away}
            context[away] = {"mando": "fora", "adversario_id": home}
    return context


def market_index(payload: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    by_name: Dict[str, Dict[str, Any]] = {}
    by_id: Dict[int, Dict[str, Any]] = {}
    for item in payload.get("atletas") or []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "atleta_id": as_int(item.get("atleta_id") or item.get("id")),
            "clube_id": as_int(item.get("clube_id")),
            "media": as_float(item.get("media_num")),
            "jogos": as_int(item.get("jogos_num")),
            "ultima_pontuacao": as_float(item.get("pontos_num")),
            "preco": as_float(item.get("preco_num")),
        }
        if normalized["atleta_id"]:
            by_id[normalized["atleta_id"]] = normalized
        for value in (item.get("apelido"), item.get("nome"), item.get("slug")):
            if clean(value):
                by_name[key_text(value)] = normalized
    return by_name, by_id


def score_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("atletas") or payload
    if isinstance(raw, dict):
        return [item for item in raw.values() if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def average(records: List[Dict[str, Any]]) -> Optional[float]:
    if not records:
        return None
    return sum(as_float(item.get("pontos")) for item in records) / len(records)


def historical_metrics(
    records: List[Dict[str, Any]],
    price: float,
    current_mando: str,
    current_opponent: int,
    current_club: int,
) -> Dict[str, Any]:
    records = sorted(records, key=lambda item: as_int(item.get("rodada")))
    if not records:
        return {
            "historico_cartola_localizado": False,
            "metodo_prob_8": "frequencia_historica_suavizada",
        }

    scores = [as_float(item.get("pontos")) for item in records]
    recent = records[-5:]
    recent_scores = [as_float(item.get("pontos")) for item in recent]
    media_recent = sum(recent_scores) / len(recent_scores)
    desvio_recent = statistics.pstdev(recent_scores) if len(recent_scores) > 1 else 0.0
    teto_recent = max(recent_scores)

    successes_8 = sum(1 for score in scores if score >= 8.0)
    successes_6 = sum(1 for score in scores if score >= 6.0)
    # Frequência histórica com suavização de Laplace. Evita transformar
    # amostras pequenas em 0% ou 100% e deixa claro que é estimativa.
    prob_8 = (successes_8 + 1) / (len(scores) + 2)
    prob_6 = (successes_6 + 1) / (len(scores) + 2)

    sample_factor = min(1.0, len(scores) / 10.0)
    regularity = 1.0 / (1.0 + desvio_recent / (abs(media_recent) + 3.0))
    confidence = max(0.0, min(1.0, sample_factor * regularity))
    efficiency = media_recent / price if price > 0 else 0.0

    home = [item for item in records if item.get("mando") == "casa"]
    away = [item for item in records if item.get("mando") == "fora"]
    first_turn = [
        item
        for item in records
        if current_opponent
        and as_int(item.get("adversario_id")) == current_opponent
        and (not current_club or as_int(item.get("clube_id")) == current_club)
    ]
    previous = first_turn[-1] if first_turn else None

    return {
        "historico_cartola_localizado": True,
        "jogos_historico": len(scores),
        "media_temporada_historica": sum(scores) / len(scores),
        "media_ult5": media_recent,
        "media_ult5_cartola": media_recent,
        "teto_ult5": teto_recent,
        "desvio_ult5": desvio_recent,
        "prob_6": prob_6,
        "prob_8": prob_8,
        "indice_confianca": confidence,
        "eficiencia": efficiency,
        "eficiencia_pontos_por_cartoleta": efficiency,
        "media_casa": average(home),
        "jogos_casa": len(home),
        "media_fora": average(away),
        "jogos_fora": len(away),
        "media_mando_atual": average(home if current_mando == "casa" else away),
        "pontuacao_primeiro_turno": (
            as_float(previous.get("pontos")) if previous else None
        ),
        "rodada_primeiro_turno": (
            as_int(previous.get("rodada")) if previous else 0
        ),
        "metodo_prob_8": "frequencia_historica_suavizada",
    }


def resolve_records(
    name: str,
    athlete_id: int,
    by_score_id: Dict[int, List[Dict[str, Any]]],
    by_score_name: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if athlete_id and by_score_id.get(athlete_id):
        return list(by_score_id[athlete_id])
    return list(by_score_name.get(key_text(name), []))


def enrich_history(round_value: int, repo_root: Path) -> None:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    paths = ["atletas/mercado"]
    paths += [f"partidas/{number}" for number in range(1, round_value + 1)]
    paths += [f"atletas/pontuados/{number}" for number in range(1, round_value)]
    payloads = fetch_many(paths)

    market_payload = payloads.get("atletas/mercado")
    if not market_payload:
        raise RuntimeError("Mercado indisponível; não é possível calcular os indicadores históricos.")
    market_by_name, market_by_id = market_index(market_payload)

    round_context: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for number in range(1, round_value + 1):
        payload = payloads.get(f"partidas/{number}")
        if payload:
            round_context[number] = match_context(payload)

    by_score_id: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    by_score_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for number in range(1, round_value):
        payload = payloads.get(f"atletas/pontuados/{number}")
        if not payload:
            continue
        context = round_context.get(number, {})
        for item in score_items(payload):
            raw_points = first_value(item, ("pontuacao", "pontos", "pontos_num"))
            if raw_points in (None, ""):
                continue
            athlete_id = as_int(item.get("atleta_id") or item.get("id"))
            club = as_int(item.get("clube_id"))
            game = context.get(club, {})
            record = {
                "rodada": number,
                "pontos": as_float(raw_points),
                "clube_id": club,
                "mando": clean(game.get("mando")),
                "adversario_id": as_int(game.get("adversario_id")),
            }
            if athlete_id:
                by_score_id[athlete_id].append(record)
            for value in (item.get("apelido"), item.get("nome"), item.get("slug")):
                if clean(value):
                    by_score_name[key_text(value)].append(record)

    current = round_context.get(round_value, {})
    players_located = 0
    for name, player in (data.get("jogadores") or {}).items():
        if not isinstance(player, dict):
            continue
        official = market_by_name.get(key_text(name), {})
        athlete_id = as_int(official.get("atleta_id"))
        current_club = as_int(official.get("clube_id"))
        current_game = current.get(current_club, {})
        records = resolve_records(
            name,
            athlete_id,
            by_score_id,
            by_score_name,
        )
        metrics = historical_metrics(
            records=records,
            price=as_float(player.get("preco") or official.get("preco")),
            current_mando=clean(current_game.get("mando")),
            current_opponent=as_int(current_game.get("adversario_id")),
            current_club=current_club,
        )
        player.update(metrics)
        if metrics.get("historico_cartola_localizado"):
            players_located += 1

    top5_rows = ((data.get("top5") or {}).get("dados") or [])
    top5_located = 0
    for row in top5_rows:
        if not isinstance(row, dict):
            continue
        name = clean(row.get("NOME") or row.get("nome"))
        athlete_id = as_int(row.get("ATLETA_ID") or row.get("atleta_id"))
        official = market_by_id.get(athlete_id) or market_by_name.get(key_text(name), {})
        athlete_id = athlete_id or as_int(official.get("atleta_id"))
        current_club = as_int(official.get("clube_id"))
        current_game = current.get(current_club, {})
        records = resolve_records(
            name,
            athlete_id,
            by_score_id,
            by_score_name,
        )
        metrics = historical_metrics(
            records=records,
            price=as_float(row.get("PRECO") or row.get("preco") or official.get("preco")),
            current_mando=clean(current_game.get("mando")),
            current_opponent=as_int(current_game.get("adversario_id")),
            current_club=current_club,
        )
        row.update(metrics)
        row.update(
            {
                "MEDIA_ULT5": metrics.get("media_ult5"),
                "TETO_ULT5": metrics.get("teto_ult5"),
                "PROB_8": metrics.get("prob_8"),
                "PROB_6": metrics.get("prob_6"),
                "EFICIENCIA": metrics.get("eficiencia"),
                "INDICE_CONFIANCA": metrics.get("indice_confianca"),
                "MEDIA_CASA": metrics.get("media_casa"),
                "MEDIA_FORA": metrics.get("media_fora"),
            }
        )
        if metrics.get("historico_cartola_localizado"):
            top5_located += 1

    data["historico_individual_enriquecido"] = True
    data["jogadores_com_historico"] = players_located
    data["top5_com_historico"] = top5_located
    data["metricas_graficas_calculadas"] = True
    data["metodo_chance_8"] = "frequencia_historica_suavizada"
    data["fonte_historico_individual"] = (
        f"API Cartola: atletas/pontuados/1 até atletas/pontuados/{round_value - 1}"
    )
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Histórico localizado: {players_located} jogadores dos times; "
        f"{top5_located} atletas do Top 5."
    )
