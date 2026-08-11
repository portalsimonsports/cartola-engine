from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

API_BASE = "https://api.cartola.globo.com"

MODELOS = (
    ("ECONOMICO", "economico", "Time Econômico"),
    ("INTERMEDIARIO", "intermediario", "Time Intermediário"),
    ("PONTUACAO", "pontuacao", "Time para Pontuar"),
)
POS_IDS = {"GOL": 1, "LAT": 2, "ZAG": 3, "MEI": 4, "ATA": 5, "TEC": 6}


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


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida da API: {path}")
    return payload


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Snapshot obrigatório ausente: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Snapshot inválido: {path}")
    return payload


def score_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("atletas") or payload
    if isinstance(raw, dict):
        return [item for item in raw.values() if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def aliases_for(item: Dict[str, Any]) -> set[str]:
    return {
        norm(value)
        for value in (
            item.get("apelido"),
            item.get("nome"),
            item.get("slug"),
            item.get("nome_completo"),
        )
        if norm(value)
    }


def club_index(round_value: int) -> Dict[str, int]:
    payload = api_get(f"partidas/{round_value}")
    clubs = payload.get("clubes") or {}
    result: Dict[str, int] = {}
    if isinstance(clubs, dict):
        for key, value in clubs.items():
            if not isinstance(value, dict):
                continue
            club_id = as_int(value.get("id") or key)
            for alias in (value.get("abreviacao"), value.get("nome"), value.get("slug")):
                if club_id and norm(alias):
                    result[norm(alias)] = club_id
    return result


def score_records(round_value: int) -> List[Dict[str, Any]]:
    payload = api_get(f"atletas/pontuados/{round_value}")
    records: List[Dict[str, Any]] = []
    for item in score_items(payload):
        aliases = aliases_for(item)
        if not aliases:
            continue
        points_raw = item.get("pontuacao")
        if points_raw is None:
            points_raw = item.get("pontos")
        records.append(
            {
                "aliases": aliases,
                "atleta_id": as_int(item.get("atleta_id") or item.get("id")),
                "clube_id": as_int(item.get("clube_id")),
                "posicao_id": as_int(item.get("posicao_id")),
                "pontos": as_float(points_raw),
                "raw": item,
            }
        )
    if not records:
        raise RuntimeError(f"API sem atletas pontuados para a rodada {round_value}")
    return records


def market_records() -> List[Dict[str, Any]]:
    payload = api_get("atletas/mercado")
    raw = payload.get("atletas") or []
    if not isinstance(raw, list):
        raise RuntimeError("API atletas/mercado sem lista de atletas.")

    records: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        aliases = aliases_for(item)
        if not aliases:
            continue
        variation_raw = item.get("variacao_num")
        if variation_raw is None:
            variation_raw = item.get("variacao")
        records.append(
            {
                "aliases": aliases,
                "atleta_id": as_int(item.get("atleta_id") or item.get("id")),
                "clube_id": as_int(item.get("clube_id")),
                "posicao_id": as_int(item.get("posicao_id")),
                "variacao": as_float(variation_raw),
                "preco_atual": as_float(item.get("preco_num") or item.get("preco")),
                "raw": item,
            }
        )
    if not records:
        raise RuntimeError("API atletas/mercado sem dados para calcular valorização.")
    return records


def _filter_context(
    records: List[Dict[str, Any]],
    club_id: int,
    pos_id: int,
) -> List[Dict[str, Any]]:
    current = records
    if club_id:
        same_club = [item for item in current if as_int(item.get("clube_id")) == club_id]
        if same_club:
            current = same_club
    if pos_id:
        same_pos = [item for item in current if as_int(item.get("posicao_id")) == pos_id]
        if same_pos:
            current = same_pos
    return current


def locate_record(
    athlete: Dict[str, Any],
    records: List[Dict[str, Any]],
    clubs: Dict[str, int],
) -> Tuple[Optional[Dict[str, Any]], str]:
    name = norm(athlete.get("nome") or athlete.get("NOME") or athlete.get("apelido"))
    if not name:
        return None, "SEM_NOME"
    club = norm(athlete.get("clube") or athlete.get("CLUBE"))
    club_id = clubs.get(club, 0)
    pos = safe(athlete.get("pos") or athlete.get("POS") or athlete.get("posicao")).upper()
    pos_id = POS_IDS.get(pos, 0)

    exact = [record for record in records if name in record.get("aliases", set())]
    exact = _filter_context(exact, club_id, pos_id)
    if len(exact) == 1:
        return exact[0], "EXATO"
    if len(exact) > 1:
        return exact[0], "EXATO_MULTIPLO"

    contextual = _filter_context(records, club_id, pos_id)
    fuzzy: List[Tuple[float, Dict[str, Any]]] = []
    for record in contextual:
        best = 0.0
        for alias in record.get("aliases", set()):
            if name in alias or alias in name:
                best = max(best, 0.95)
            else:
                best = max(best, difflib.SequenceMatcher(None, name, alias).ratio())
        if best >= 0.72:
            fuzzy.append((best, record))
    fuzzy.sort(key=lambda item: item[0], reverse=True)
    if fuzzy:
        if len(fuzzy) == 1 or fuzzy[0][0] - fuzzy[1][0] >= 0.08:
            return fuzzy[0][1], f"FLEXIVEL_{fuzzy[0][0]:.2f}"
    return None, "NAO_LOCALIZADO"


def team_athletes(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    rows = [item for item in raw if isinstance(item, dict)]
    return [
        item
        for item in rows
        if safe(item.get("status"), "TITULAR").upper() != "RESERVA"
    ]


def build_team_payload(
    round_value: int,
    scores: List[Dict[str, Any]],
    market: List[Dict[str, Any]],
    clubs: Dict[str, int],
) -> Dict[str, Any]:
    times: Dict[str, Dict[str, Any]] = {}
    for model, slug, title in MODELOS:
        path = Path("data/publicacoes_atuais") / f"time_{slug}_rodada_{round_value}.json"
        source = load_json(path)
        if as_int(source.get("rodada")) != round_value:
            raise RuntimeError(f"{path}: rodada incorreta")
        athletes = team_athletes(source)
        if len(athletes) != 12:
            raise RuntimeError(f"{path}: esperado 12 titulares; encontrados {len(athletes)}")

        captain = norm(source.get("capitao") or (source.get("snapshot") or {}).get("capitao"))
        total = 0.0
        bonus = 0.0
        appreciation = 0.0
        score_located = 0
        variation_located = 0
        not_scored: List[str] = []
        not_valued: List[str] = []
        match_methods: Dict[str, str] = {}
        variation_methods: Dict[str, str] = {}

        for athlete in athletes:
            name = safe(athlete.get("nome"), "SEM_NOME")

            score, score_method = locate_record(athlete, scores, clubs)
            match_methods[name] = score_method
            if score is None:
                not_scored.append(name)
            else:
                score_located += 1
                points = as_float(score.get("pontos"))
                total += points
                if captain and captain == norm(name):
                    bonus = points

            market_item, variation_method = locate_record(athlete, market, clubs)
            variation_methods[name] = variation_method
            if market_item is None:
                not_valued.append(name)
            else:
                variation_located += 1
                appreciation += as_float(market_item.get("variacao"))

        if score_located < 9:
            raise RuntimeError(
                f"{title}: apenas {score_located}/12 atletas com pontuação localizada; publicação bloqueada."
            )
        if variation_located != 12:
            raise RuntimeError(
                f"{title}: valorização incompleta ({variation_located}/12). "
                f"Ausentes: {', '.join(not_valued)}"
            )

        times[model] = {
            "modelo": model,
            "nome": title,
            "pontos_sem_c": round(total, 2),
            "bonus_capitao": round(bonus, 2),
            "pontos_com_c": round(total + bonus, 2),
            "participacao": f"{score_located}/12",
            "valorizacao": round(appreciation, 2),
            "valorizacao_localizada": f"{variation_located}/12",
            "fonte_valorizacao": "API Cartola atletas/mercado variacao_num após processamento da rodada",
            "capitao": safe(source.get("capitao") or (source.get("snapshot") or {}).get("capitao")),
            "nao_pontuaram_ou_nao_localizados": not_scored,
            "nao_localizados_valorizacao": not_valued,
            "metodos_localizacao": match_methods,
            "metodos_localizacao_valorizacao": variation_methods,
            "snapshot": str(path),
        }

    ranking = sorted(
        (
            {"modelo": key, "nome": value["nome"], "pontos": value["pontos_com_c"]}
            for key, value in times.items()
        ),
        key=lambda item: item["pontos"],
        reverse=True,
    )
    return {
        "origem": "cartola_desempenho_rodada_anterior_v3_valorizacao_mercado",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "FECHAMENTO_FINAL_TIMES",
        "tipo_publicacao": "DESEMPENHO_FINAL_DOS_TIMES",
        "contexto": "RODADA_FINALIZADA",
        "rodada": round_value,
        "rodada_finalizada": round_value,
        "fonte_pontuacao": f"API Cartola atletas/pontuados/{round_value}",
        "fonte_valorizacao": "API Cartola atletas/mercado variacao_num da abertura seguinte",
        "times": times,
        "ranking_times": ranking,
        "payload": {
            "rodada": round_value,
            "times": times,
            "ranking_times": ranking,
            "evento_programado": "FECHAMENTO_FINAL_TIMES",
            "tipo_publicacao": "DESEMPENHO_FINAL_DOS_TIMES",
            "contexto": "RODADA_FINALIZADA",
        },
    }


def build_top5_payload(
    round_value: int,
    records: List[Dict[str, Any]],
    clubs: Dict[str, int],
) -> Dict[str, Any]:
    path = Path("data/publicacoes_atuais") / f"top5_rodada_{round_value}.json"
    source = load_json(path)
    raw = source.get("lista") or source.get("dados") or []
    rows = [item for item in raw if isinstance(item, dict)]
    if len(rows) < 30:
        raise RuntimeError(f"Top 5 R{round_value} incompleto: {len(rows)} registros")

    players: List[Dict[str, Any]] = []
    located = 0
    for item in rows:
        score, method = locate_record(item, records, clubs)
        copy = dict(item)
        copy["pontos"] = round(as_float(score.get("pontos")), 2) if score else 0.0
        copy["pontuacao_localizada"] = score is not None
        copy["status_resultado"] = "PONTUOU" if score is not None else "NÃO PONTUOU"
        copy["metodo_localizacao"] = method
        if score is not None:
            located += 1
        players.append(copy)

    if located < 20:
        raise RuntimeError(
            f"Top 5 R{round_value}: somente {located}/{len(players)} pontuações localizadas; publicação bloqueada."
        )

    return {
        "origem": "cartola_desempenho_rodada_anterior_v3_valorizacao_mercado",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "FECHAMENTO_FINAL_TOP5",
        "tipo_publicacao": "DESEMPENHO_FINAL_TOP5",
        "contexto": "RODADA_FINALIZADA",
        "rodada": round_value,
        "rodada_finalizada": round_value,
        "lista": players,
        "pontuacoes_localizadas": located,
        "total_top5": len(players),
        "payload": {
            "rodada": round_value,
            "lista": players,
            "evento_programado": "FECHAMENTO_FINAL_TOP5",
            "tipo_publicacao": "DESEMPENHO_FINAL_TOP5",
            "contexto": "RODADA_FINALIZADA",
        },
    }


def build_payloads(round_value: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    scores = score_records(round_value)
    market = market_records()
    clubs = club_index(round_value)
    return (
        build_team_payload(round_value, scores, market, clubs),
        build_top5_payload(round_value, scores, clubs),
    )


def write_payloads(round_value: int) -> Tuple[Path, Path]:
    teams, top5 = build_payloads(round_value)
    base = Path("data/publicacoes_atuais")
    base.mkdir(parents=True, exist_ok=True)
    teams_path = base / f"desempenho_times_rodada_{round_value}.json"
    top5_path = base / f"desempenho_top5_rodada_{round_value}.json"
    teams_path.write_text(json.dumps(teams, ensure_ascii=False, indent=2), encoding="utf-8")
    top5_path.write_text(json.dumps(top5, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Desempenho preparado: R{round_value}; times={teams_path}; "
        f"top5={top5_path}; localizados_top5={top5['pontuacoes_localizadas']}/{top5['total_top5']}"
    )
    for model, item in teams.get("times", {}).items():
        print(
            f"Valorização {model}: C$ {as_float(item.get('valorizacao')):.2f} "
            f"({item.get('valorizacao_localizada')})"
        )
    return teams_path, top5_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    args = parser.parse_args()
    write_payloads(args.rodada)


if __name__ == "__main__":
    main()
