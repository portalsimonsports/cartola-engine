from __future__ import annotations

from typing import Any, Dict

import render_live_cards_v2 as v2
import render_live_cards_v4 as v4
from render_live_aux_v1 import is_live_aux_event, render_live_aux
from render_live_cobertura_v3 import (
    is_coverage_event,
    render_coverage_event,
    render_match_cards,
)
from render_telegram_cards import RenderOutput


VISUAL_VERSION = "live_cards_v5_cobertura_gc_2026_07_30"
RESULT_SIZE_V5 = v4.RESULT_SIZE_V4


def render_results_v5(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    # Preserva o layout aprovado, acrescenta gols contra e mantém uma partida
    # por card para as atualizações ao vivo.
    return render_match_cards(data, output_dir)


def render_live_publication_v5(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    # Abertura do Live e resumo completo da noite carregam partidas, mas devem
    # usar layouts próprios antes da detecção genérica de placar.
    if is_coverage_event(data):
        return render_coverage_event(data, output_dir)

    # Mitos e Zicas, resumo e pontuação dos times também têm prioridade.
    if is_live_aux_event(data):
        return render_live_aux(data, output_dir)

    kind = v2._kind_text(data)
    matches = v2._extract_matches(data)

    if matches or any(token in kind for token in ("placar", "resultado", "partida", "evento_partida")):
        return render_results_v5(data, output_dir)

    return v4.render_live_publication_v4(data, output_dir)
