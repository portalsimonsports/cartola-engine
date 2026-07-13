"""Ajuste visual carregado automaticamente pelo Python.

Aumenta moderadamente a tipografia das artes premium sem alterar o layout,
os dados, os escudos, as camisas ou a estrutura dos cards.
"""

from __future__ import annotations

import render_telegram_cards as _cards

_ORIGINAL_FONT = _cards._font
_ORIGINAL_TOP5 = _cards.render_top5
_ORIGINAL_TEAM = _cards.render_team


def _scaled_font_factory(scale: float):
    def _scaled_font(size: int, weight: str = "regular", condensed: bool = False):
        scaled_size = max(1, int(round(size * scale)))
        return _ORIGINAL_FONT(scaled_size, weight, condensed)

    return _scaled_font


def _render_with_scale(renderer, scale: float, *args, **kwargs):
    previous = _cards._font
    _cards._font = _scaled_font_factory(scale)
    try:
        return renderer(*args, **kwargs)
    finally:
        _cards._font = previous


def _render_top5_larger(*args, **kwargs):
    # Aumento de 14%: nomes, preços, posições, medalhas, título e rodapé.
    return _render_with_scale(_ORIGINAL_TOP5, 1.14, *args, **kwargs)


def _render_team_larger(*args, **kwargs):
    # Aumento menor para preservar o encaixe dos 11 titulares e reservas.
    return _render_with_scale(_ORIGINAL_TEAM, 1.08, *args, **kwargs)


_cards.render_top5 = _render_top5_larger
_cards.render_team = _render_team_larger
