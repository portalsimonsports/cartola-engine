from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests

API_BASE = "https://api.cartola.globo.com"
REPO = os.getenv("GITHUB_REPOSITORY", "portalsimonsports/cartola-engine").strip()
TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

MODELOS = (
    ("ECONOMICO", "economico", "Time Econômico"),
    ("INTERMEDIARIO", "intermediario", "Time Intermediário"),
    ("PONTUACAO", "pontuacao", "Time para Pontuar"),
)


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
    text = unicodedata.normalize("NFD", safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def api_get(path: str) -> Dict[str, Any]:
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


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Snapshot obrigatório ausente: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Snapshot inválido: {path}")
    return payload


def atletas_time(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    values = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    rows = [item for item in values if isinstance(item, dict)]
    return [
        item
        for item in rows
        if safe(item.get("status"), "TITULAR").upper() != "RESERVA"
    ]


def pontuados(rodada: int) -> Dict[str, Dict[str, Any]]:
    payload = api_get(f"atletas/pontuados/{rodada}")
    raw = payload.get("atletas") or payload
    iterable: Iterable[Any]
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []

    result: Dict[str, Dict[str, Any]] = {}
    for item in iterable:
        if not isinstance(item, dict):
            continue
        registro = {
            "pontos": as_float(item.get("pontuacao") if item.get("pontuacao") is not None else item.get("pontos")),
            "variacao": as_float(
                item.get("variacao_num")
                if item.get("variacao_num") is not None
                else item.get("variacao")
            ),
            "dados": item,
        }
        for value in (
            item.get("apelido"),
            item.get("nome"),
            item.get("slug"),
            item.get("nome_completo"),
        ):
            key = norm(value)
            if key:
                result[key] = registro
    return result


def localizar(atleta: Dict[str, Any], mapa: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    for value in (
        atleta.get("nome"),
        atleta.get("apelido"),
        atleta.get("slug"),
        atleta.get("nome_completo"),
    ):
        key = norm(value)
        if key and key in mapa:
            return mapa[key]
    return None


def desempenho_modelo(
    rodada: int,
    modelo: str,
    slug: str,
    nome: str,
    mapa: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    path = Path("data/publicacoes_atuais") / f"time_{slug}_rodada_{rodada}.json"
    payload = load_json(path)
    if as_int(payload.get("rodada")) != rodada:
        raise RuntimeError(f"{path}: rodada incorreta")

    atletas = atletas_time(payload)
    if len(atletas) != 12:
        raise RuntimeError(f"{path}: esperado 12 titulares, encontrados {len(atletas)}")

    capitao = norm(payload.get("capitao") or (payload.get("snapshot") or {}).get("capitao"))
    total = 0.0
    bonus_capitao = 0.0
    valorizacao = 0.0
    encontrados = 0
    ausentes: List[str] = []

    for atleta in atletas:
        score = localizar(atleta, mapa)
        if score is None:
            ausentes.append(safe(atleta.get("nome"), "SEM_NOME"))
            continue
        encontrados += 1
        pontos = as_float(score.get("pontos"))
        total += pontos
        valorizacao += as_float(score.get("variacao"))
        if capitao and capitao == norm(atleta.get("nome")):
            bonus_capitao = pontos

    if encontrados != 12:
        raise RuntimeError(
            f"{nome}: pontuação incompleta ({encontrados}/12). Ausentes: {', '.join(ausentes)}"
        )

    return {
        "modelo": modelo,
        "nome": nome,
        "pontos_sem_c": round(total, 2),
        "bonus_capitao": round(bonus_capitao, 2),
        "pontos_com_c": round(total + bonus_capitao, 2),
        "participacao": "12/12",
        "valorizacao": round(valorizacao, 2),
        "capitao": safe(payload.get("capitao") or (payload.get("snapshot") or {}).get("capitao")),
        "snapshot": str(path),
    }


def build_payload(rodada: int) -> Dict[str, Any]:
    mapa = pontuados(rodada)
    if not mapa:
        raise RuntimeError(f"API sem atletas pontuados para a rodada {rodada}")

    times: Dict[str, Dict[str, Any]] = {}
    for modelo, slug, nome in MODELOS:
        times[modelo] = desempenho_modelo(rodada, modelo, slug, nome, mapa)

    ranking = sorted(
        (
            {
                "modelo": modelo,
                "nome": dados["nome"],
                "pontos": dados["pontos_com_c"],
            }
            for modelo, dados in times.items()
        ),
        key=lambda item: item["pontos"],
        reverse=True,
    )

    payload = {
        "origem": "cartola_live_desempenho_times_guard",
        "evento_github": "cartola_live_publish",
        "workflow_destino": "gerar.resultados.yml",
        "evento_programado": "FECHAMENTO_FINAL_TIMES",
        "tipo_publicacao": "DESEMPENHO_FINAL_DOS_TIMES",
        "contexto": "RODADA_FINALIZADA",
        "rodada": rodada,
        "rodada_finalizada": rodada,
        "times": times,
        "ranking_times": ranking,
        "payload": {
            "rodada": rodada,
            "rodada_finalizada": rodada,
            "times": times,
            "ranking_times": ranking,
            "evento_programado": "FECHAMENTO_FINAL_TIMES",
            "tipo_publicacao": "DESEMPENHO_FINAL_DOS_TIMES",
            "contexto": "RODADA_FINALIZADA",
        },
    }
    return payload


def dispatch(payload: Dict[str, Any]) -> None:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN não disponível")
    response = requests.post(
        f"https://api.github.com/repos/{REPO}/dispatches",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"event_type": "cartola_live_publish", "client_payload": payload},
        timeout=45,
    )
    if response.status_code not in (200, 201, 202, 204):
        raise RuntimeError(
            f"Falha no dispatch: HTTP {response.status_code} - {response.text}"
        )
    print(f"Dispatch aceito: FECHAMENTO_FINAL_TIMES rodada {payload['rodada']}")


def rodada_anterior_atual() -> int:
    status = api_get("mercado/status")
    atual = as_int(status.get("rodada_atual") or status.get("rodada"))
    if atual <= 1:
        raise RuntimeError(f"Rodada atual inválida: {atual}")
    return atual - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, default=0)
    parser.add_argument("--payload-output", default="")
    parser.add_argument("--nao-disparar", action="store_true")
    args = parser.parse_args()

    rodada = args.rodada or rodada_anterior_atual()
    imagem = Path("output") / f"aprovada_desempenho_final_times_rodada_{rodada}.png"
    if imagem.exists() and not args.rodada:
        print(f"Resumo da rodada {rodada} já existe: {imagem}")
        return

    payload = build_payload(rodada)
    output = Path(args.payload_output or f"data/publicacoes_atuais/desempenho_times_rodada_{rodada}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Payload validado: {output}")

    if not args.nao_disparar:
        dispatch(payload)


if __name__ == "__main__":
    main()
