from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

import render_live_cards_v2 as v2
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "live_aux_v1_2026_07_29"
AUX_EVENTS = {
    "LIVE_MITOS_ZICAS",
    "LIVE_RESUMO_TIMES",
    "LIVE_RANKING_PARCIAL",
    "LIVE_PONTUACAO_TIME",
    "LIVE_DELTA_15",
}


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", _safe(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def event_name(data: Dict[str, Any]) -> str:
    values = [data.get(key) for key in ("evento_programado", "tipo_publicacao", "contexto", "titulo")]
    joined = " ".join(_norm(value) for value in values if value)

    if any(token in joined for token in ("LIVE_MITOS_ZICAS", "MITOS_E_ZICAS", "MITOS", "ZICAS")):
        return "LIVE_MITOS_ZICAS"
    if any(token in joined for token in ("LIVE_PONTUACAO_TIME", "PONTUACAO_TIME", "TIME_DELTA_15", "LIVE_DELTA_15")):
        return "LIVE_PONTUACAO_TIME"
    if any(token in joined for token in ("LIVE_RESUMO_TIMES", "LIVE_RANKING_PARCIAL", "RESUMO_GERAL", "PARCIAIS_DOS_TIMES")):
        return "LIVE_RESUMO_TIMES"
    return _norm(data.get("evento_programado"))


def is_live_aux_event(data: Dict[str, Any]) -> bool:
    return event_name(data) in AUX_EVENTS or event_name(data) in {
        "LIVE_RESUMO_TIMES",
        "LIVE_PONTUACAO_TIME",
    }


def _round_value(data: Dict[str, Any]) -> str:
    return v2._round_value(data)


def _team_type(data: Dict[str, Any]) -> str:
    raw = _safe(v2._value(data, "tipo_time", "tipo", "modelo", default="PONTUACAO"))
    key = _norm(raw).replace("TIME_", "")
    aliases = {
        "ECONOMICO": "ECONOMICO",
        "ECONOMICO_": "ECONOMICO",
        "INTERMEDIARIO": "INTERMEDIARIO",
        "PONTUACAO": "PONTUACAO",
    }
    return aliases.get(key, key or "PONTUACAO")


def _team_label(team_type: str) -> str:
    return {
        "ECONOMICO": "TIME ECONÔMICO",
        "INTERMEDIARIO": "TIME INTERMEDIÁRIO",
        "PONTUACAO": "TIME PARA PONTUAR",
    }.get(team_type, f"TIME {team_type}")


def _accent(team_type: str) -> Tuple[int, int, int]:
    return {
        "ECONOMICO": v2.GREEN,
        "INTERMEDIARIO": v2.CYAN,
        "PONTUACAO": v2.PURPLE,
    }.get(team_type, v2.CYAN)


def _normalize_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    tipos = data.get("tipos")
    if not isinstance(tipos, list):
        tipos = []

    normalized: List[Dict[str, Any]] = []
    for item in tipos:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "tipo": _norm(item.get("tipo")).replace("TIME_", ""),
                "pontos_sem_capitao": item.get("pontos_sem_capitao", item.get("pontosSemCap", 0)),
                "pontos_com_capitao": item.get("pontos_com_capitao", item.get("pontosComCap", 0)),
                "participacao": item.get("participacao", item.get("participaram", 0)),
                "total": item.get("total", 12),
                "valorizacao": item.get("valorizacao", 0),
            }
        )

    copied = dict(data)
    copied["tipos"] = normalized
    return copied


def _parse_player_rows(message: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    starters: List[Dict[str, Any]] = []
    reserves: List[Dict[str, Any]] = []
    target = starters

    for raw in _safe(message).splitlines():
        line = raw.replace("*", "").strip()
        if not line:
            continue
        upper = _norm(line)
        if "RESERVAS" in upper:
            target = reserves
            continue

        match = re.search(
            r"(?:©|▪️|▫️|[-•])?\s*(GOL|LAT|ZAG|MEI|ATA|TEC)\s*:\s*(.*?)\s*[—-]\s*(.+)$",
            line,
            re.I,
        )
        if not match:
            continue

        position = match.group(1).upper()
        name = match.group(2).strip()
        score_text = match.group(3).strip()
        captain = "©" in line
        score_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:→\s*(-?\d+(?:[.,]\d+)?))?", score_text)
        score = 0.0
        final_score = None
        if score_match:
            score = float(score_match.group(1).replace(",", "."))
            if score_match.group(2):
                final_score = float(score_match.group(2).replace(",", "."))
        target.append(
            {
                "posicao": position,
                "nome": name,
                "pontos": score,
                "pontos_capitao": final_score,
                "capitao": captain,
                "aguardando": "⏳" in score_text,
            }
        )

    return starters[:12], reserves[:5]


def _metric(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], label: str, value: str, accent: Tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = box
    v2._round(draw, box, 24, fill=(4, 19, 36), outline=accent, width=2)
    v2._centered_text(draw, (x1 + 15, y1 + 14, x2 - 15, y1 + 58), label, v2._fit_text(draw, label, x2 - x1 - 30, 22, 16, "bold", True), fill=v2.SILVER)
    v2._centered_text(draw, (x1 + 15, y1 + 58, x2 - 15, y2 - 10), value, v2._fit_text(draw, value, x2 - x1 - 30, 45, 28, "bold", True), fill=accent)


def _draw_player(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], item: Dict[str, Any], accent: Tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = box
    v2._round(draw, box, 18, fill=(5, 18, 34), outline=(28, 69, 104), width=2)
    badge = (x1 + 12, y1 + 17, x1 + 78, y2 - 17)
    v2._round(draw, badge, 16, fill=tuple(max(0, c // 5) for c in accent), outline=accent, width=2)
    v2._centered_text(draw, badge, _safe(item.get("posicao"), "--"), v2._font(20, "bold", True), fill=accent)

    name = _safe(item.get("nome"), "Atleta")
    if item.get("capitao"):
        name = "C  " + name
    draw.text((x1 + 94, y1 + 18), name, font=v2._fit_text(draw, name, x2 - x1 - 235, 28, 19, "bold", True), fill=v2.WHITE)

    if item.get("aguardando"):
        points = "AGUARDANDO"
    elif item.get("pontos_capitao") is not None:
        points = f"{float(item['pontos']):.1f} → {float(item['pontos_capitao']):.1f} pts"
    else:
        points = f"{float(item.get('pontos') or 0):.1f} pts"
    pf = v2._fit_text(draw, points, 190, 27, 18, "bold", True)
    pb = draw.textbbox((0, 0), points, font=pf)
    draw.text((x2 - 18 - (pb[2] - pb[0]), y1 + 19), points, font=pf, fill=accent)


def render_team_points(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    team_type = _team_type(data)
    team_label = _team_label(team_type)
    accent = _accent(team_type)
    round_value = _round_value(data)
    starters, reserves = _parse_player_rows(_safe(data.get("mensagem_oficial")))

    image = v2._gradient_background(*v2.RESULT_SIZE)
    v2._header_team(
        image,
        f"PONTUAÇÃO DO TIME • RODADA {round_value}",
        f"Parcial atual do {team_label.title()}.",
        v2._badge(data),
    )
    draw = ImageDraw.Draw(image)

    main = (55, 335, 1545, 1760)
    v2._glow_outline(image, main, accent, radius=34, blur=18, alpha=65)
    v2._shadow_panel(image, main, radius=34, fill=v2.PANEL, outline=accent, shadow_alpha=110, outline_width=3)
    draw.text((95, 375), team_label, font=v2._font(55, "bold", True), fill=accent)
    context = _safe(data.get("contexto"), "PARCIAL AO VIVO").replace("_", " ").upper()
    pill = (1135, 370, 1490, 445)
    v2._round(draw, pill, 24, fill=tuple(max(0, c // 4) for c in accent), outline=accent, width=2)
    v2._centered_text(draw, pill, context[:24], v2._fit_text(draw, context[:24], 320, 22, 16, "bold", True), fill=v2.WHITE)

    metrics = [
        ("PONTOS SEM C", f"{float(data.get('pontos_sem_capitao') or 0):.2f} pts"),
        ("PONTOS COM C", f"{float(data.get('pontos_com_capitao') or 0):.2f} pts"),
        ("PARTICIPAÇÃO", f"{int(float(data.get('participacao') or 0))}/12"),
    ]
    metric_y = 485
    for index, (label, value) in enumerate(metrics):
        x1 = 85 + index * 490
        _metric(draw, (x1, metric_y, x1 + 445, metric_y + 135), label, value, accent)

    draw.text((90, 665), "TITULARES", font=v2._font(31, "bold", True), fill=v2.WHITE)
    rows = starters or [{"posicao": "--", "nome": "Dados dos atletas aguardando atualização", "pontos": 0, "aguardando": True}]
    for index, item in enumerate(rows[:12]):
        row, col = divmod(index, 2)
        x1 = 85 + col * 730
        y1 = 720 + row * 125
        _draw_player(draw, (x1, y1, x1 + 690, y1 + 98), item, accent)

    if reserves:
        y_res = 1495
        draw.text((90, y_res), "RESERVAS", font=v2._font(29, "bold", True), fill=v2.SILVER)
        for index, item in enumerate(reserves[:4]):
            x1 = 85 + (index % 2) * 730
            y1 = y_res + 52 + (index // 2) * 100
            _draw_player(draw, (x1, y1, x1 + 690, y1 + 82), item, accent)

    v2._footer(image, 1888)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(output_dir) / f"live_pontuacao_{team_type.lower()}_rodada_{round_value}.png")
    image.convert("RGB").save(path, "PNG", optimize=True)
    return RenderOutput([path], "live_pontuacao_time", f"Pontuação do {team_label} • Rodada {round_value}", f"{team_label.title()} • Rodada {round_value}")


def render_live_aux(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    event = event_name(data)
    if event == "LIVE_MITOS_ZICAS":
        return v2.render_ranking_v2(data, output_dir)
    if event == "LIVE_RESUMO_TIMES":
        return v2.render_summary_v2(_normalize_summary(data), output_dir)
    if event == "LIVE_PONTUACAO_TIME":
        return render_team_points(data, output_dir)
    raise RuntimeError(f"Evento Live auxiliar não suportado: {event!r}")
