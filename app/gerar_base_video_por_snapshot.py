from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests

API_BASE = "https://api.cartola.globo.com"


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Snapshot obrigatório não encontrado: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Snapshot inválido: {path}")
    return payload


def snapshot_path(root: Path, rodada: int, nome: str) -> Path:
    return root / "data" / "publicacoes_atuais" / f"{nome}_rodada_{rodada}.json"


def athletes(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("jogadores") or payload.get("atletas") or payload.get("dados") or []
    return [item for item in raw if isinstance(item, dict)]


def starters(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        item for item in athletes(payload)
        if safe(item.get("status"), "TITULAR").upper() != "RESERVA"
    ]


def validate_snapshot(payload: Dict[str, Any], rodada: int, label: str, minimum: int) -> None:
    if as_int(payload.get("rodada")) != rodada:
        raise RuntimeError(
            f"Snapshot {label} pertence à rodada {payload.get('rodada')}, não à rodada {rodada}."
        )
    if safe(payload.get("evento_programado")).upper() != "SELECAO_INICIAL":
        raise RuntimeError(
            f"Snapshot {label} não é da SELECAO_INICIAL: {payload.get('evento_programado')}"
        )
    if len(athletes(payload)) < minimum:
        raise RuntimeError(f"Snapshot {label} incompleto: {len(athletes(payload))} registros.")


def cartola_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def normalize_games(rodada: int) -> List[Dict[str, Any]]:
    payload = cartola_get(f"partidas/{rodada}")
    clubes = payload.get("clubes") or {}

    def clube(clube_id: Any) -> Dict[str, Any]:
        if not isinstance(clubes, dict):
            return {}
        value = clubes.get(str(clube_id))
        if value is None:
            value = clubes.get(as_int(clube_id))
        return value if isinstance(value, dict) else {}

    jogos: List[Dict[str, Any]] = []
    for partida in payload.get("partidas") or []:
        if not isinstance(partida, dict):
            continue
        casa_id = partida.get("clube_casa_id") or partida.get("casa_id")
        fora_id = partida.get("clube_visitante_id") or partida.get("visitante_id")
        casa = clube(casa_id)
        fora = clube(fora_id)
        data_raw = safe(partida.get("partida_data") or partida.get("data"))
        data = "Data a confirmar"
        hora = "Horário a confirmar"
        if data_raw:
            try:
                parsed = datetime.fromisoformat(data_raw.replace("Z", "+00:00"))
                data = parsed.strftime("%d/%m")
                hora = parsed.strftime("%H:%M")
            except ValueError:
                data = data_raw
        mandante = safe(casa.get("nome") or casa.get("abreviacao") or casa_id)
        visitante = safe(fora.get("nome") or fora.get("abreviacao") or fora_id)
        mandante_sigla = safe(casa.get("abreviacao") or mandante)
        visitante_sigla = safe(fora.get("abreviacao") or visitante)
        jogos.append({
            "mandante": mandante,
            "mandante_sigla": mandante_sigla,
            "visitante": visitante,
            "visitante_sigla": visitante_sigla,
            "data": data,
            "hora": hora,
            "estadio": safe(partida.get("local"), "Local a confirmar"),
            "pos_mandante": as_int(casa.get("posicao")),
            "pos_visitante": as_int(fora.get("posicao")),
            "forma_mandante": "recorte histórico preservado fora do snapshot",
            "forma_visitante": "recorte histórico preservado fora do snapshot",
            "leitura": (
                f"{mandante} enfrenta {visitante}. A análise considera o confronto oficial "
                "e, principalmente, os atletas registrados no snapshot publicado da seleção inicial."
            ),
        })
    if not jogos:
        raise RuntimeError(f"A API não retornou partidas válidas para a rodada {rodada}.")
    return jogos


def build_players(times: Dict[str, Dict[str, Any]]) -> OrderedDict[str, Dict[str, Any]]:
    result: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    names = {
        "economico": "Econômico",
        "intermediario": "Intermediário",
        "pontuacao": "Para Pontuar",
    }
    for slug, payload in times.items():
        for atleta in starters(payload):
            nome = safe(atleta.get("nome"))
            if not nome:
                continue
            item = result.setdefault(nome, {
                "posicao": safe(atleta.get("pos") or atleta.get("posicao")),
                "clube": safe(atleta.get("clube")),
                "preco": as_float(atleta.get("preco")),
                "modelos": [],
            })
            modelo = names[slug]
            if modelo not in item["modelos"]:
                item["modelos"].append(modelo)
    for nome, item in result.items():
        qtd = len(item["modelos"])
        item["racional"] = (
            f"{nome} aparece em {qtd} modelo{'s' if qtd != 1 else ''} do snapshot publicado. "
            "A avaliação preserva exatamente a seleção enviada ao canal, sem substituir pelos dados dinâmicos posteriores."
        )
        item.update({
            "adversario": "",
            "pos_clube": 0,
            "pos_adversario": 0,
            "forma_clube": "",
            "forma_adversario": "",
        })
    return result


def team_summary(payload: Dict[str, Any], nome: str) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        "nome": nome,
        "custo": as_float(payload.get("custo_total") or meta.get("custo_total")),
        "capitao": safe(payload.get("capitao") or meta.get("capitao")),
        "ultima_pontuacao": as_float(meta.get("pontos_total")),
        "participacao": f"{len(starters(payload))}/12",
        "tipo_pontuacao": "snapshot publicado da seleção inicial",
    }


def build(rodada: int, root: Path) -> Path:
    times = {
        "economico": read_json(snapshot_path(root, rodada, "time_economico")),
        "intermediario": read_json(snapshot_path(root, rodada, "time_intermediario")),
        "pontuacao": read_json(snapshot_path(root, rodada, "time_pontuacao")),
    }
    top5 = read_json(snapshot_path(root, rodada, "top5"))

    for slug, payload in times.items():
        validate_snapshot(payload, rodada, slug, 12)
    validate_snapshot(top5, rodada, "top5", 30)

    output = {
        "rodada": rodada,
        "status": "SNAPSHOT_PUBLICADO_SELECAO_INICIAL",
        "publicacao_automatica": True,
        "duracao_alvo_minutos": [10, 15],
        "moeda_falada": "cartoletas",
        "fontes": [
            f"data/publicacoes_atuais/time_economico_rodada_{rodada}.json",
            f"data/publicacoes_atuais/time_intermediario_rodada_{rodada}.json",
            f"data/publicacoes_atuais/time_pontuacao_rodada_{rodada}.json",
            f"data/publicacoes_atuais/top5_rodada_{rodada}.json",
            f"API Cartola: partidas/{rodada}",
        ],
        "times": {
            "economico": team_summary(times["economico"], "Time Econômico"),
            "intermediario": team_summary(times["intermediario"], "Time Intermediário"),
            "pontuacao": team_summary(times["pontuacao"], "Time para Pontuar"),
        },
        "jogos": normalize_games(rodada),
        "jogadores": build_players(times),
        "top5": top5,
        "snapshot_evento": "SELECAO_INICIAL",
        "gerado_em": datetime.utcnow().isoformat() + "Z",
    }

    target = root / "data" / f"analise_tecnica_rodada_{rodada}_v3.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Base gerada exclusivamente pelos snapshots publicados: {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    build(args.rodada, Path(args.repo_root).resolve())


if __name__ == "__main__":
    main()
