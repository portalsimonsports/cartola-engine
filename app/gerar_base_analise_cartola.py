from __future__ import annotations

import argparse
import json
import os
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

API_BASE = "https://api.cartola.globo.com"
PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def materialize_credentials() -> str:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        Path(CREDENTIALS_PATH).write_text(
            json.dumps(json.loads(raw), ensure_ascii=False), encoding="utf-8"
        )
    if not Path(CREDENTIALS_PATH).exists():
        raise RuntimeError("Credencial Google não encontrada.")
    return CREDENTIALS_PATH


def sheets_service():
    if not PLANILHA_ID:
        raise RuntimeError("PLANILHA_ID não definido.")
    credentials = Credentials.from_service_account_file(
        materialize_credentials(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def sheet_values(service, sheet: str, cell_range: str) -> List[List[Any]]:
    return (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=PLANILHA_ID, range=f"'{sheet}'!{cell_range}")
        .execute()
        .get("values", [])
    )


def table(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    headers = [safe(value).lower() for value in rows[0]]
    output: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not any(safe(value) for value in row):
            continue
        item = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
        output.append(item)
    return output


def cartola_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Resposta inválida da API: {path}")
    return payload


def market_status() -> Dict[str, Any]:
    return cartola_get("mercado/status")


def round_matches(round_value: int) -> Dict[str, Any]:
    return cartola_get(f"partidas/{round_value}")


def result_for(club_id: int, match: Dict[str, Any]) -> str:
    home = as_int(match.get("casa_id"))
    away = as_int(match.get("visitante_id"))
    hg = as_int(match.get("placar_casa"), -999)
    ag = as_int(match.get("placar_vis"), -999)
    if hg == -999 or ag == -999:
        return ""
    own = hg if club_id == home else ag
    rival = ag if club_id == home else hg
    return "V" if own > rival else "D" if own < rival else "E"


def recent_matches(club_id: int, history: List[Dict[str, Any]], before_round: int) -> List[Dict[str, Any]]:
    valid = []
    for match in history:
        round_number = as_int(match.get("rodada"))
        if round_number >= before_round:
            continue
        home = as_int(match.get("casa_id"))
        away = as_int(match.get("visitante_id"))
        if club_id not in (home, away):
            continue
        if safe(match.get("placar_casa")) == "" or safe(match.get("placar_vis")) == "":
            continue
        valid.append(match)
    valid.sort(key=lambda item: as_int(item.get("rodada")), reverse=True)
    return list(reversed(valid[:5]))


def plural(value: int, singular: str, plural_word: str) -> str:
    return f"{value} {singular if value == 1 else plural_word}"


def history_summary(
    club_id: int,
    sigla: str,
    recent: List[Dict[str, Any]],
    clubs: Dict[int, Dict[str, Any]],
) -> Tuple[str, str]:
    results = [result_for(club_id, item) for item in recent]
    counts = Counter(results)
    form = " ".join(results) if results else "recorte indisponível"
    if not recent:
        return form, f"O {sigla} não possui cinco partidas finalizadas disponíveis no recorte histórico."

    games = []
    for item in recent:
        home = as_int(item.get("casa_id"))
        away = as_int(item.get("visitante_id"))
        hg = as_int(item.get("placar_casa"))
        ag = as_int(item.get("placar_vis"))
        rival_id = away if club_id == home else home
        rival = safe(clubs.get(rival_id, {}).get("abreviacao"), str(rival_id))
        mando = "em casa" if club_id == home else "fora"
        games.append(f"{mando}, contra {rival}, placar {hg} a {ag}")

    campaign = (
        f"{plural(counts.get('V', 0), 'vitória', 'vitórias')}, "
        f"{plural(counts.get('E', 0), 'empate', 'empates')} e "
        f"{plural(counts.get('D', 0), 'derrota', 'derrotas')}"
    )
    detail = "; ".join(games)
    return form, f"Nos últimos cinco jogos, o {sigla} registrou {campaign}: {detail}."


def normalize_api_clubs(payload: Dict[str, Any], fallback: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    result = dict(fallback)
    raw = payload.get("clubes") or {}
    iterable: Iterable[Tuple[Any, Any]] = raw.items() if isinstance(raw, dict) else []
    for key, value in iterable:
        if not isinstance(value, dict):
            continue
        club_id = as_int(value.get("id") or key)
        result[club_id] = {
            "id": club_id,
            "nome": safe(value.get("nome") or value.get("nome_fantasia") or value.get("abreviacao")),
            "abreviacao": safe(value.get("abreviacao") or value.get("nome")),
            "escudo": safe(
                value.get("escudos", {}).get("60x60") if isinstance(value.get("escudos"), dict) else value.get("escudo")
            ),
            "posicao": as_int(value.get("posicao")),
        }
    return result


def normalize_games(
    round_value: int,
    api_payload: Dict[str, Any],
    history: List[Dict[str, Any]],
    clubs: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    raw_games = api_payload.get("partidas") or []
    if not raw_games:
        raw_games = [item for item in history if as_int(item.get("rodada")) == round_value]

    games: List[Dict[str, Any]] = []
    for item in raw_games:
        home_id = as_int(item.get("clube_casa_id") or item.get("casa_id"))
        away_id = as_int(item.get("clube_visitante_id") or item.get("visitante_id"))
        if not home_id or not away_id:
            continue
        home = clubs.get(home_id, {"nome": str(home_id), "abreviacao": str(home_id), "posicao": 0})
        away = clubs.get(away_id, {"nome": str(away_id), "abreviacao": str(away_id), "posicao": 0})
        recent_home = recent_matches(home_id, history, round_value)
        recent_away = recent_matches(away_id, history, round_value)
        form_home, spoken_home = history_summary(home_id, safe(home.get("abreviacao")), recent_home, clubs)
        form_away, spoken_away = history_summary(away_id, safe(away.get("abreviacao")), recent_away, clubs)
        date_value = safe(item.get("partida_data") or item.get("data"))
        date_label = date_value
        time_label = safe(item.get("hora"))
        if date_value:
            try:
                parsed = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
                date_label = parsed.strftime("%d/%m")
                time_label = parsed.strftime("%H:%M")
            except ValueError:
                pass
        reading = (
            f"O mando favorece {safe(home.get('nome'))}, mas a sequência recente precisa ser comparada antes de definir favoritismo. "
            "Para o Cartola, o mais seguro é separar atletas que dependem do resultado coletivo daqueles que produzem scouts próprios."
        )
        games.append(
            {
                "mandante_id": home_id,
                "visitante_id": away_id,
                "mandante": safe(home.get("nome")),
                "visitante": safe(away.get("nome")),
                "mandante_sigla": safe(home.get("abreviacao")),
                "visitante_sigla": safe(away.get("abreviacao")),
                "pos_mandante": as_int(home.get("posicao")),
                "pos_visitante": as_int(away.get("posicao")),
                "forma_mandante": form_home,
                "forma_visitante": form_away,
                "historico_mandante_falado": spoken_home,
                "historico_visitante_falado": spoken_away,
                "data": date_label or "Data a confirmar",
                "hora": time_label or "Horário a confirmar",
                "estadio": safe(item.get("local"), "Local a confirmar"),
                "leitura": reading,
                "destaque_cartola": (
                    "O contraponto é evitar concentração excessiva no mesmo jogo: preço baixo não transforma automaticamente um atleta em escolha segura."
                ),
            }
        )
    return games


def load_team(repo_root: Path, round_value: int, slug: str) -> Dict[str, Any]:
    candidates = [
        repo_root / "data" / "publicacoes_atuais" / f"time_{slug}_rodada_{round_value}.json",
        repo_root / "data" / f"times_atual_{slug}.json",
    ]
    for path in candidates:
        payload = read_json(path)
        if payload:
            return payload
    return {}


def team_players(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    return [item for item in raw if isinstance(item, dict) and safe(item.get("status"), "TITULAR").upper() != "RESERVA"]


def score_from(payload: Dict[str, Any]) -> float:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    for value in (
        meta.get("pontos_total"),
        payload.get("pontos_total"),
        payload.get("pontuacao"),
        payload.get("pontos"),
    ):
        if value not in (None, ""):
            return as_float(value)
    return 0.0


def build_players(teams: Dict[str, Dict[str, Any]], games: List[Dict[str, Any]]) -> OrderedDict[str, Dict[str, Any]]:
    opponent: Dict[str, Tuple[str, int, int, str, str]] = {}
    for game in games:
        opponent[game["mandante_sigla"]] = (
            game["visitante_sigla"],
            game["pos_mandante"],
            game["pos_visitante"],
            game["forma_mandante"],
            game["forma_visitante"],
        )
        opponent[game["visitante_sigla"]] = (
            game["mandante_sigla"],
            game["pos_visitante"],
            game["pos_mandante"],
            game["forma_visitante"],
            game["forma_mandante"],
        )

    merged: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for model, payload in teams.items():
        for athlete in team_players(payload):
            name = safe(athlete.get("nome"))
            if not name:
                continue
            club = safe(athlete.get("clube"))
            entry = merged.setdefault(
                name,
                {
                    "posicao": safe(athlete.get("pos") or athlete.get("posicao")),
                    "clube": club,
                    "preco": as_float(athlete.get("preco")),
                    "modelos": [],
                },
            )
            if model not in entry["modelos"]:
                entry["modelos"].append(model)

    final: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for name, player in list(merged.items())[:24]:
        club = player["clube"]
        rival, club_pos, rival_pos, club_form, rival_form = opponent.get(club, ("", 0, 0, "", ""))
        consensus = len(player["modelos"])
        role = {
            "GOL": "defesas e possibilidade de saldo de gol",
            "LAT": "scouts defensivos e participação pelos lados",
            "ZAG": "desarmes, segurança defensiva e custo",
            "MEI": "criação, finalizações e participação ofensiva",
            "ATA": "teto por gols, assistências e finalizações",
            "TEC": "resultado coletivo e custo da montagem",
        }.get(player["posicao"], "equilíbrio entre custo e potencial")
        player.update(
            {
                "adversario": rival,
                "pos_clube": club_pos,
                "pos_adversario": rival_pos,
                "forma_clube": club_form,
                "forma_adversario": rival_form,
                "racional": (
                    f"{name} aparece em {consensus} modelo{'s' if consensus != 1 else ''}. A escolha considera {role}. "
                    f"O confronto de {club} contra {rival or 'adversário ainda não identificado'} exige avaliar o teto sem ignorar o risco coletivo"
                ),
            }
        )
        final[name] = player
    return final


def build(round_value: int, repo_root: Path) -> Path:
    service = sheets_service()
    history_rows = table(sheet_values(service, "HIST_PARTIDAS", "A:F"))
    club_rows = table(sheet_values(service, "HIST_CLUBES", "A:D"))
    clubs = {
        as_int(item.get("id")): {
            "id": as_int(item.get("id")),
            "nome": safe(item.get("nome")),
            "abreviacao": safe(item.get("abreviacao")),
            "escudo": safe(item.get("escudo")),
            "posicao": 0,
        }
        for item in club_rows
        if as_int(item.get("id"))
    }

    try:
        api_matches = round_matches(round_value)
    except Exception as exc:
        print(f"Aviso: API de partidas indisponível, usando HIST_PARTIDAS: {exc}")
        api_matches = {}
    clubs = normalize_api_clubs(api_matches, clubs)
    games = normalize_games(round_value, api_matches, history_rows, clubs)

    team_payloads = {
        "Econômico": load_team(repo_root, round_value, "economico"),
        "Intermediário": load_team(repo_root, round_value, "intermediario"),
        "Para Pontuar": load_team(repo_root, round_value, "pontuacao"),
    }
    if not any(team_payloads.values()):
        raise RuntimeError(f"Nenhum time da rodada {round_value} foi encontrado no repositório.")

    previous = {
        key: load_team(repo_root, round_value - 1, slug)
        for key, slug in (
            ("Econômico", "economico"),
            ("Intermediário", "intermediario"),
            ("Para Pontuar", "pontuacao"),
        )
    }
    times = OrderedDict()
    for key, payload in team_payloads.items():
        last = previous.get(key) or payload
        participants = len(team_players(last))
        times[key.lower().replace("ô", "o").replace("á", "a").replace(" ", "_")] = {
            "nome": key,
            "ultima_pontuacao": score_from(last),
            "participacao": f"{participants}/12" if participants else "",
            "tipo_pontuacao": "Último resultado disponível do modelo",
        }

    players = build_players(team_payloads, games)
    payload = {
        "versao": "analise_tecnica_automatica_v4",
        "rodada": round_value,
        "gerado_em": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "fontes": ["API Cartola", "HIST_PARTIDAS", "HIST_CLUBES", "times e Top 5 do repositório"],
        "jogos": games,
        "times": times,
        "jogadores": players,
    }
    path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    build(args.rodada, Path(args.repo_root).resolve())


if __name__ == "__main__":
    main()
