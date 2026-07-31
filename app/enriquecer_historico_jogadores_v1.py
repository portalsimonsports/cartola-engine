from __future__ import annotations

import json
import re
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


def market_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("atletas") or []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "atleta_id": as_int(item.get("atleta_id") or item.get("id")),
            "clube_id": as_int(item.get("clube_id")),
        }
        for value in (item.get("apelido"), item.get("nome"), item.get("slug")):
            if clean(value):
                result[key_text(value)] = normalized
    return result


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


def enrich_history(round_value: int, repo_root: Path) -> None:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    paths = ["atletas/mercado"]
    paths += [f"partidas/{number}" for number in range(1, round_value + 1)]
    paths += [f"atletas/pontuados/{number}" for number in range(1, round_value)]
    payloads = fetch_many(paths)

    market_payload = payloads.get("atletas/mercado")
    if not market_payload:
        print("Aviso: mercado indisponível; vídeo seguirá sem médias por mando.")
        return
    market = market_index(market_payload)

    round_context: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for number in range(1, round_value + 1):
        payload = payloads.get(f"partidas/{number}")
        if payload:
            round_context[number] = match_context(payload)

    by_id: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
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
                by_id[athlete_id].append(record)
            for value in (item.get("apelido"), item.get("nome"), item.get("slug")):
                if clean(value):
                    by_name[key_text(value)].append(record)

    current = round_context.get(round_value, {})
    located = 0
    for name, player in (data.get("jogadores") or {}).items():
        if not isinstance(player, dict):
            continue
        official = market.get(key_text(name), {})
        athlete_id = as_int(official.get("atleta_id"))
        current_club = as_int(official.get("clube_id"))
        records = list(by_id.get(athlete_id, [])) if athlete_id else []
        if not records:
            records = list(by_name.get(key_text(name), []))
        records.sort(key=lambda item: as_int(item.get("rodada")))
        if not records:
            continue
        located += 1

        home = [item for item in records if item.get("mando") == "casa"]
        away = [item for item in records if item.get("mando") == "fora"]
        current_opponent = as_int(current.get(current_club, {}).get("adversario_id"))
        first_turn = [
            item
            for item in records
            if current_opponent
            and as_int(item.get("adversario_id")) == current_opponent
            and (not current_club or as_int(item.get("clube_id")) == current_club)
        ]
        previous = first_turn[-1] if first_turn else None
        player.update(
            {
                "media_casa": average(home),
                "jogos_casa": len(home),
                "media_fora": average(away),
                "jogos_fora": len(away),
                "media_ult5_cartola": average(records[-5:]),
                "pontuacao_primeiro_turno": (
                    as_float(previous.get("pontos")) if previous else None
                ),
                "rodada_primeiro_turno": (
                    as_int(previous.get("rodada")) if previous else 0
                ),
                "historico_cartola_localizado": True,
            }
        )

    data["historico_individual_enriquecido"] = True
    data["jogadores_com_historico"] = located
    data["fonte_historico_individual"] = (
        f"API Cartola: atletas/pontuados/1 até atletas/pontuados/{round_value - 1}"
    )
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Histórico individual localizado para {located} jogadores.")
