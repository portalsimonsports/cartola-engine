from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import gerar_resultados_telegram as publisher
import publicar_times_top5_automatico as base
import render_telegram_cards as rtc


PIPELINE_VERSION = "times_top5_aprovados_v2_2026_08_27_capitao_reservas"

MODEL_ORDER = ("ECONOMICO", "INTERMEDIARIO", "PONTUACAO")
MODEL_TITLES = {
    "ECONOMICO": "TIME ECONÔMICO",
    "INTERMEDIARIO": "TIME INTERMEDIÁRIO",
    "PONTUACAO": "TIME PARA PONTUAR",
}
MODEL_FILES = {
    "ECONOMICO": Path("data/times_atual_economico.json"),
    "INTERMEDIARIO": Path("data/times_atual_intermediario.json"),
    "PONTUACAO": Path("data/times_atual_pontuacao.json"),
}
TOP5_FILE = Path("data/top5_atual.json")


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _event(payload_root: Dict[str, Any]) -> str:
    inner = payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {}
    return _safe(payload_root.get("evento_programado") or inner.get("evento_programado")).upper()


def _round(payload_root: Dict[str, Any]) -> int:
    inner = payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {}
    value = payload_root.get("rodada") or inner.get("rodada") or 0
    try:
        return int(float(value))
    except Exception:
        return 0


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Arquivo obrigatório ausente: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"JSON inválido em {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Conteúdo inválido em {path}: esperado objeto JSON")
    return data


def _validate_round(data: Dict[str, Any], rodada: int, path: Path) -> None:
    current = data.get("rodada") or data.get("RODADA") or 0
    try:
        current = int(float(current))
    except Exception:
        current = 0
    if current != rodada:
        raise RuntimeError(f"Rodada divergente em {path}: esperado R{rodada}, encontrado R{current}")


def _normalized_player(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rodada": item.get("rodada") if item.get("rodada") is not None else item.get("RODADA"),
        "tipo": _safe(item.get("tipo") or item.get("TIPO")),
        "status": _safe(item.get("status") or item.get("STATUS") or "TITULAR").upper(),
        "pos": _safe(item.get("pos") or item.get("POS")).upper(),
        "nome": _safe(item.get("nome") or item.get("NOME")),
        "clube": _safe(item.get("clube") or item.get("CLUBE")).upper(),
        "preco": item.get("preco") if item.get("preco") is not None else item.get("PRECO"),
        "exp_score": item.get("exp_score") if item.get("exp_score") is not None else item.get("EXP_SCORE"),
        "atleta_id": item.get("atleta_id") if item.get("atleta_id") is not None else item.get("ATLETA_ID"),
    }


def _captain_from_data(data: Dict[str, Any], starters: List[Dict[str, Any]]) -> str:
    explicit = _safe(data.get("capitao") or data.get("capitão"))
    if explicit:
        return explicit

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    explicit = _safe(meta.get("capitao") or meta.get("capitão"))
    if explicit:
        return explicit.split("(", 1)[0].strip()

    scored = []
    for player in starters:
        try:
            score = float(player.get("exp_score") or 0)
        except Exception:
            score = 0.0
        if player.get("nome"):
            scored.append((score, player["nome"]))
    if scored:
        scored.sort(key=lambda value: value[0], reverse=True)
        return scored[0][1]
    return ""


def _team_publication(model: str, rodada: int) -> Dict[str, Any]:
    path = MODEL_FILES[model]
    data = _read_json(path)
    _validate_round(data, rodada, path)

    raw_players = data.get("dados") or data.get("atletas") or data.get("jogadores") or []
    players = [_normalized_player(item) for item in raw_players if isinstance(item, dict)]
    starters = [item for item in players if item.get("status") != "RESERVA"]
    reserves = [item for item in players if item.get("status") == "RESERVA"]

    if not starters:
        raise RuntimeError(f"Time {model} R{rodada} sem titulares válidos em {path}")
    if not reserves:
        raise RuntimeError(f"Time {model} R{rodada} sem reservas válidos em {path}")

    captain = _captain_from_data(data, starters)
    if not captain:
        raise RuntimeError(f"Time {model} R{rodada} sem capitão identificável em {path}")

    starter_names = {_safe(item.get("nome")).upper() for item in starters}
    if captain.upper() not in starter_names:
        raise RuntimeError(
            f"Capitão inválido no {model} R{rodada}: {captain!r} não está entre os titulares"
        )

    payload = dict(data)
    payload.update(
        {
            "tipo_publicacao": "times",
            "tipo": model,
            "modelo": model,
            "nome_modelo": MODEL_TITLES[model],
            "titulo": f"{MODEL_TITLES[model]} • RODADA {rodada}",
            "rodada": rodada,
            "atletas": players,
            "jogadores": starters,
            "reservas": reserves,
            "capitao": captain,
            "formacao": _safe(data.get("formacao") or "4-3-3"),
        }
    )
    return payload


def _top5_publication(rodada: int) -> Dict[str, Any]:
    data = _read_json(TOP5_FILE)
    _validate_round(data, rodada, TOP5_FILE)
    payload = dict(data)
    payload.update(
        {
            "tipo_publicacao": "top5",
            "titulo": "TOP 5 DA RODADA",
            "rodada": rodada,
        }
    )
    return payload


def _package_root(original: Dict[str, Any], event: str, rodada: int) -> Dict[str, Any]:
    if rodada <= 0:
        raise RuntimeError("Rodada não informada no dispatch.")

    publications: List[Dict[str, Any]] = []
    if event in {"SELECAO_INICIAL", "ATUALIZACAO_20H", "CONFIRMADOS"}:
        publications.extend(_team_publication(model, rodada) for model in MODEL_ORDER)
        publications.append(_top5_publication(rodada))
    elif event == "PRE_FECHAMENTO_TIMES":
        publications.extend(_team_publication(model, rodada) for model in MODEL_ORDER)
    elif event == "PRE_FECHAMENTO_TOP5":
        publications.append(_top5_publication(rodada))
    else:
        return original

    if not publications:
        raise RuntimeError(f"Pacote vazio para evento {event} R{rodada}")

    return {
        "origem": "publicador_unico_github",
        "pipeline": "jobtelegram",
        "evento_programado": event,
        "rodada": rodada,
        "tipo_publicacao": "pacote_times_top5",
        "payload": publications[0],
        "publicacoes": publications[1:],
    }


def _event_title(event: str, round_value: str, kind: str, model_name: str = "") -> tuple[str, str]:
    if event == "SELECAO_INICIAL":
        if kind == "top5":
            return f"TOP 5 INICIAL DA RODADA • RODADA {round_value}", "Mercado aberto • Seleção inicial do Top 5"
        return f"SELEÇÃO INICIAL • RODADA {round_value}", "Mercado aberto • Seleção inicial da rodada"
    if event == "ATUALIZACAO_20H":
        return (
            f"{model_name} • RODADA {round_value}" if kind == "team" else f"TOP 5 DA RODADA • RODADA {round_value}",
            "Atualização programada das 20h",
        )
    if event == "PRE_FECHAMENTO_TIMES":
        return f"{model_name} • RODADA {round_value}", "Pré-fechamento dos times"
    if event == "PRE_FECHAMENTO_TOP5":
        return f"TOP 5 DA RODADA • RODADA {round_value}", "Pré-fechamento do Top 5"
    if event == "CONFIRMADOS":
        if kind == "top5":
            return f"TOP 5 CONFIRMADO • RODADA {round_value}", "Versão final confirmada para a rodada"
        return f"{model_name} CONFIRMADO • RODADA {round_value}", "Escalação final confirmada para a rodada"
    return (
        f"{model_name} • RODADA {round_value}" if kind == "team" else f"TOP 5 DA RODADA • RODADA {round_value}",
        "Publicação programada do Portal SimonSports",
    )


def _custom_top5_header(image, badge: str, subtitle: str, title: str) -> None:
    draw = rtc.ImageDraw.Draw(image)
    width, _ = image.size
    rtc._logo_ps(image, (640, 25, 780, 155))
    draw.text((815, 37), "PORTAL", font=rtc._font(29, "bold", True), fill=rtc.WHITE)
    draw.text((815, 76), "SIMON", font=rtc._font(44, "bold", True), fill=rtc.WHITE)
    draw.text((960, 76), "SPORTS", font=rtc._font(44, "bold", True), fill=rtc.CYAN)
    draw.text((816, 130), "CARTOLA • DADOS • ANÁLISE", font=rtc._font(18, "semibold"), fill=rtc.SILVER)
    badge_box = (1260, 38, 1532, 128)
    rtc._glow_outline(image, badge_box, rtc.CYAN, radius=28, blur=14, alpha=80)
    rtc._round(draw, badge_box, 28, fill=(4, 18, 36), outline=rtc.CYAN, width=3)
    rtc._centered_text(draw, badge_box, badge, rtc._font(38, "bold", True), fill=rtc.WHITE)

    font = rtc._fit_text(draw, title, 1500, 92, 50, "bold", True)
    if "•" in title:
        prefix, suffix = [part.strip() for part in title.split("•", 1)]
        left = prefix + " • "
        lb = draw.textbbox((0, 0), left, font=font)
        rb = draw.textbbox((0, 0), suffix, font=font)
        total = (lb[2] - lb[0]) + (rb[2] - rb[0])
        x = (width - total) / 2
        draw.text((x, 170), left, font=font, fill=rtc.WHITE)
        draw.text((x + lb[2] - lb[0], 170), suffix, font=font, fill=rtc.BLUE)
    else:
        box = draw.textbbox((0, 0), title, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, 170), title, font=font, fill=rtc.WHITE)
    sub_font = rtc._fit_text(draw, subtitle, 1400, 31, 22, "semibold", True)
    sb = draw.textbbox((0, 0), subtitle, font=sub_font)
    draw.text(((width - (sb[2] - sb[0])) / 2, 292), subtitle, font=sub_font, fill=rtc.CYAN)


def executar_pacote_aprovado():
    original_payload = publisher.carregar_payload()
    event = _event(original_payload)
    rodada = _round(original_payload)
    payload_root = _package_root(original_payload, event, rodada)

    original_load = publisher.carregar_payload
    original_prepare = base._prepare_publication
    original_render = publisher.render_publication

    publisher.carregar_payload = lambda *args, **kwargs: payload_root

    def prepare(raw: Dict[str, Any]) -> Dict[str, Any]:
        data = original_prepare(raw)
        data["evento_programado"] = event
        blocks = data.get("blocos_topo")
        if not isinstance(blocks, list):
            blocks = []
        data["blocos_topo"] = blocks
        data["pipeline_visual"] = PIPELINE_VERSION
        return data

    def render(data: Dict[str, Any], output_dir: str):
        kind = rtc.detect_kind(data)
        round_value = _safe(data.get("rodada") or data.get("rodada_atual") or "ATUAL")
        model_name = _safe(data.get("nome_modelo") or data.get("titulo") or "TIME DA RODADA")
        title, subtitle = _event_title(event, round_value, kind, model_name)

        old_team_header = rtc._header_team
        old_top5_header = rtc._header_top5

        def team_header(image, _title, _subtitle, badge):
            return old_team_header(image, title, subtitle, badge)

        def top5_header(image, badge, _subtitle):
            return _custom_top5_header(image, badge, subtitle, title)

        rtc._header_team = team_header
        rtc._header_top5 = top5_header
        try:
            return rtc.render_publication(data, output_dir)
        finally:
            rtc._header_team = old_team_header
            rtc._header_top5 = old_top5_header

    base._prepare_publication = prepare
    publisher.render_publication = render
    try:
        results = base.executar_pacote()
        expected = 4 if event in {"SELECAO_INICIAL", "ATUALIZACAO_20H", "CONFIRMADOS"} else (3 if event == "PRE_FECHAMENTO_TIMES" else 1)
        if event in {"SELECAO_INICIAL", "ATUALIZACAO_20H", "CONFIRMADOS", "PRE_FECHAMENTO_TIMES", "PRE_FECHAMENTO_TOP5"} and len(results) != expected:
            raise RuntimeError(f"Pacote incompleto: evento={event} esperado={expected} publicado={len(results)}")
        return results
    finally:
        publisher.carregar_payload = original_load
        base._prepare_publication = original_prepare
        publisher.render_publication = original_render


if __name__ == "__main__":
    executar_pacote_aprovado()
