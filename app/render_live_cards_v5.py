from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import render_live_cards_v2 as v2
import render_live_cards_v4 as v4
from render_live_aux_v1 import is_live_aux_event, render_live_aux
from render_telegram_cards import RenderOutput


# Mantém a assinatura visual esperada pelo workflow atual, mas troca
# definitivamente o modo de múltiplos jogos: 1 partida = 1 card completo.
VISUAL_VERSION = "live_cards_v5_auxiliares_2026_07_29"
RESULT_SIZE_V5 = v4.RESULT_SIZE_V4


def render_results_v5(data: Dict[str, Any], output_dir: str) -> RenderOutput:
    matches = v2._extract_matches(data)
    if not matches:
        raise RuntimeError("Payload de resultados sem partidas estruturadas; card vazio bloqueado.")

    round_value = v2._round_value(data)
    statuses = [v2._status_label(match)[0] for match in matches]
    live = any("AO VIVO" in status or "INTERVALO" in status for status in statuses)
    final = all(status == "ENCERRADO" for status in statuses)
    kind = v2._kind_text(data)

    if "placar" in kind or live:
        title = f"ATUALIZAÇÃO DE PLACAR • RODADA {round_value}"
        subtitle = "Acompanhe ao vivo os placares e eventos da partida."
    elif final:
        title = f"RESULTADOS DA RODADA • RODADA {round_value}"
        subtitle = "Resultados oficiais e eventos dos jogos."
    else:
        title = f"JOGOS DA RODADA • RODADA {round_value}"
        subtitle = "Agenda oficial e status das partidas."

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files: List[str] = []
    total = len(matches)

    # Regra V5: nunca comprimir duas ou mais partidas no mesmo card.
    # Cada jogo recebe o layout premium completo com escudos grandes,
    # placar central grande e marcadores legíveis.
    for index, match in enumerate(matches, start=1):
        image = v2._gradient_background(*RESULT_SIZE_V5)
        v4._draw_header_v4(image, title, subtitle, v2._badge(data))
        v4._draw_info_bar(image, match)
        v4._draw_single_match_v4(image, match)
        v4._draw_footer_v4(image, (index, total) if total > 1 else None)

        path = str(
            Path(output_dir)
            / f"live_jogo_v5_rodada_{round_value}_j{index:02d}.png"
        )
        image.convert("RGB").save(path, "PNG", optimize=True)
        files.append(path)

    caption = "Atualização de Placar" if live or "placar" in kind else "Resultados da Rodada"
    return RenderOutput(files, "results_v5", title, f"{caption} • Rodada {round_value}")


def render_live_publication_v5(data: Dict[str, Any], output_dir: str = "output") -> RenderOutput:
    # Eventos auxiliares devem ser roteados antes de qualquer verificação pela
    # palavra "live". Isso impede Mitos e Zicas, resumo e pontuação dos times de
    # serem tratados incorretamente como placar sem partidas.
    if is_live_aux_event(data):
        return render_live_aux(data, output_dir)

    kind = v2._kind_text(data)
    matches = v2._extract_matches(data)

    if matches or any(token in kind for token in ("placar", "resultado", "partida", "evento_partida")):
        return render_results_v5(data, output_dir)

    # Demais cards continuam usando o pipeline visual já aprovado.
    return v4.render_live_publication_v4(data, output_dir)
