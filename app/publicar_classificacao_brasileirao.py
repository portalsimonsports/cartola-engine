from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from gerar_resultados_telegram import enviar_foto
from render_classificacao_brasileirao import render_classificacao_brasileirao


PLANILHA_CLASSIFICACAO_ID = os.getenv(
    "PLANILHA_CLASSIFICACAO_ID",
    "1-A7w4kkE28iHRd61yiSoNOvSekrmmADzHxGCRDVrICI",
).strip()
ABA_CLASSIFICACAO = os.getenv("ABA_CLASSIFICACAO", "ESTATISTICAS_PROPRIA").strip()
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output").strip() or "output"
SNAPSHOT_PATH = Path(
    os.getenv(
        "SNAPSHOT_PATH",
        "data/publicacoes_atuais/classificacao_brasileirao_snapshot.json",
    ).strip()
)
TZ_NAME = os.getenv("TZ", "America/Sao_Paulo").strip() or "America/Sao_Paulo"
FECHAMENTO_HORA = int(os.getenv("FECHAMENTO_HORA", "23"))
FECHAMENTO_MINUTO = int(os.getenv("FECHAMENTO_MINUTO", "30"))


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _num(value: Any, default: int = 0) -> int:
    text = _safe(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        return int(round(float(text)))
    except Exception:
        return default


def _now() -> datetime:
    return datetime.now(ZoneInfo(TZ_NAME))


def _credentials_path() -> str:
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        parsed = json.loads(raw)
        Path(path).write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    if not Path(path).exists():
        raise RuntimeError("Credencial Google não encontrada para ler a classificação.")
    return path


def _sheets_service():
    credentials = Credentials.from_service_account_file(
        _credentials_path(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _read_rows() -> List[List[Any]]:
    response = (
        _sheets_service()
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=PLANILHA_CLASSIFICACAO_ID,
            range=f"'{ABA_CLASSIFICACAO}'!A:Z",
        )
        .execute()
    )
    rows = response.get("values") or []
    if len(rows) < 2:
        raise RuntimeError(f"Aba {ABA_CLASSIFICACAO!r} vazia ou sem dados suficientes.")
    return rows


def ler_classificacao() -> List[Dict[str, Any]]:
    rows = _read_rows()
    header = [_safe(value).lower() for value in rows[0]]
    indexes = {name: idx for idx, name in enumerate(header)}

    required = ("nome", "v", "e", "d", "gm", "gs", "saldo", "pts_geral")
    missing = [name for name in required if name not in indexes]
    if missing:
        raise RuntimeError("Colunas obrigatórias ausentes em ESTATISTICAS_PROPRIA: " + ", ".join(missing))

    def value(row: List[Any], key: str) -> Any:
        idx = indexes[key]
        return row[idx] if idx < len(row) else ""

    teams: List[Dict[str, Any]] = []
    for row in rows[1:]:
        nome = _safe(value(row, "nome"))
        if not nome or nome.lower() == "nome":
            continue

        v = _num(value(row, "v"))
        e = _num(value(row, "e"))
        d = _num(value(row, "d"))
        teams.append(
            {
                "clube_id": _num(value(row, "clube_id")) if "clube_id" in indexes else 0,
                "nome": nome,
                "v": v,
                "e": e,
                "d": d,
                "j": v + e + d,
                "gm": _num(value(row, "gm")),
                "gs": _num(value(row, "gs")),
                "saldo": _num(value(row, "saldo")),
                "pts": _num(value(row, "pts_geral")),
            }
        )

    # Critérios aplicáveis com os campos existentes na aba: pontos, vitórias,
    # saldo de gols, gols pró. Mantém nome como último critério estável.
    teams.sort(key=lambda t: (-t["pts"], -t["v"], -t["saldo"], -t["gm"], t["nome"]))
    for index, team in enumerate(teams, start=1):
        team["pos"] = index
    return teams[:20]


def _load_snapshot() -> Dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        loaded = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _save_snapshot(snapshot: Dict[str, Any]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _signature(teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "nome": team["nome"],
            "pos": team["pos"],
            "pts": team["pts"],
            "v": team["v"],
            "saldo": team["saldo"],
        }
        for team in teams
    ]


def _apply_variation(teams: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> None:
    previous = snapshot.get("positions") if isinstance(snapshot.get("positions"), dict) else {}
    for team in teams:
        old = previous.get(team["nome"])
        team["variacao"] = None if old is None else int(old) - int(team["pos"])


def _guess_round(teams: List[Dict[str, Any]]) -> str:
    # A classificação pode conter jogos atrasados, então não existe uma rodada
    # única garantida. Usa o maior número de jogos como referência visual.
    if not teams:
        return ""
    return str(max(int(team.get("j") or 0) for team in teams))


def _after_closing_time(now: datetime) -> bool:
    return (now.hour, now.minute) >= (FECHAMENTO_HORA, FECHAMENTO_MINUTO)


def _determine_mode(teams: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> str:
    now = _now()
    today = now.strftime("%Y-%m-%d")
    signature = _signature(teams)
    previous_signature = snapshot.get("signature") or []

    # Mudança real da tabela = publicação automática após atualização dos jogos.
    if previous_signature and signature != previous_signature:
        return "apos_jogos"

    # Na primeira execução, cria a referência sem despejar uma publicação histórica.
    if not previous_signature:
        return "baseline"

    # Fechamento diário somente uma vez por dia.
    if _after_closing_time(now) and snapshot.get("last_closing_date") != today:
        return "fechamento"

    return "none"


def _caption(modo: str) -> str:
    title = "Classificação final do dia" if modo == "fechamento" else "Classificação após os jogos"
    return (
        f"<b>Classificação do Brasileirão • {title}</b>\n\n"
        "📡 Portal SimonSports\n"
        "🔗 @dicascartolaportalsimonsports"
    )


def main() -> None:
    teams = ler_classificacao()
    if len(teams) < 10:
        raise RuntimeError(f"Classificação incompleta: apenas {len(teams)} clubes encontrados.")

    snapshot = _load_snapshot()
    _apply_variation(teams, snapshot)
    mode = _determine_mode(teams, snapshot)
    now = _now()

    if mode == "baseline":
        _save_snapshot(
            {
                "updated_at": now.isoformat(),
                "signature": _signature(teams),
                "positions": {team["nome"]: team["pos"] for team in teams},
                "last_closing_date": snapshot.get("last_closing_date", ""),
            }
        )
        print("Baseline da classificação criada; nenhuma publicação histórica enviada.")
        return

    if mode == "none":
        print("Classificação sem alteração e sem fechamento pendente.")
        return

    path = render_classificacao_brasileirao(
        teams,
        OUTPUT_DIR,
        mode,
        now.strftime("%d/%m/%Y - %H:%M"),
        _guess_round(teams),
    )
    enviar_foto(path, _caption(mode))

    new_snapshot = {
        "updated_at": now.isoformat(),
        "last_publication_mode": mode,
        "signature": _signature(teams),
        "positions": {team["nome"]: team["pos"] for team in teams},
        "last_closing_date": (
            now.strftime("%Y-%m-%d")
            if mode == "fechamento"
            else snapshot.get("last_closing_date", "")
        ),
    }
    _save_snapshot(new_snapshot)
    print(f"Classificação publicada automaticamente: {mode}; arquivo={path}")


if __name__ == "__main__":
    main()
