from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v4 as v4

VERSION = "cartola_dialogo_tecnico_v5_desempenho_colocacao_2026_07_31"
API_BASE = "https://api.cartola.globo.com"

POSICOES = {
    "GOL": "goleiro",
    "LAT": "lateral",
    "ZAG": "zagueiro",
    "MEI": "meia",
    "ATA": "atacante",
    "TEC": "técnico",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def number(value: Any, decimals: int = 2) -> str:
    try:
        return f"{float(value):.{decimals}f}".replace(".", ",")
    except Exception:
        return "0,00"


def integer(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def key_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def api_get(path: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_BASE}/{path.lstrip('/')}",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def ordinal(position: int) -> str:
    return f"{position}º colocado" if position > 0 else ""


def result_for(club_id: int, match: Dict[str, Any]) -> str:
    home = integer(match.get("clube_casa_id") or match.get("casa_id"))
    away = integer(match.get("clube_visitante_id") or match.get("visitante_id"))
    home_goals = match.get("placar_oficial_mandante")
    away_goals = match.get("placar_oficial_visitante")
    if home_goals is None:
        home_goals = match.get("placar_casa")
    if away_goals is None:
        away_goals = match.get("placar_vis")
    if home_goals in (None, "") or away_goals in (None, ""):
        return ""
    hg = integer(home_goals)
    ag = integer(away_goals)
    own = hg if club_id == home else ag
    rival = ag if club_id == home else hg
    return "vitória" if own > rival else "derrota" if own < rival else "empate"


def load_official_context(round_value: int) -> Dict[str, Any]:
    current = api_get(f"partidas/{round_value}")
    market = api_get("atletas/mercado")

    clubs_by_id: Dict[int, Dict[str, Any]] = {}
    clubs_by_abbr: Dict[str, Dict[str, Any]] = {}
    raw_clubs = current.get("clubes") or market.get("clubes") or {}
    if isinstance(raw_clubs, dict):
        for raw_id, item in raw_clubs.items():
            if not isinstance(item, dict):
                continue
            club_id = integer(item.get("id") or raw_id)
            abbr = clean(item.get("abreviacao"))
            normalized = {
                "id": club_id,
                "nome": clean(item.get("nome") or item.get("nome_fantasia") or abbr),
                "abreviacao": abbr,
                "posicao": integer(item.get("posicao")),
            }
            clubs_by_id[club_id] = normalized
            if abbr:
                clubs_by_abbr[abbr.upper()] = normalized

    matches = [item for item in (current.get("partidas") or []) if isinstance(item, dict)]
    opponent: Dict[str, Dict[str, Any]] = {}
    for match in matches:
        home_id = integer(match.get("clube_casa_id") or match.get("casa_id"))
        away_id = integer(match.get("clube_visitante_id") or match.get("visitante_id"))
        home = clubs_by_id.get(home_id, {})
        away = clubs_by_id.get(away_id, {})
        home_abbr = clean(home.get("abreviacao")).upper()
        away_abbr = clean(away.get("abreviacao")).upper()
        if home_abbr:
            opponent[home_abbr] = {"adversario": away, "mando": "em casa"}
        if away_abbr:
            opponent[away_abbr] = {"adversario": home, "mando": "fora de casa"}

    history: List[Dict[str, Any]] = []
    for previous_round in range(max(1, round_value - 5), round_value):
        try:
            payload = api_get(f"partidas/{previous_round}")
            history.extend([item for item in (payload.get("partidas") or []) if isinstance(item, dict)])
        except Exception as error:
            print(f"Aviso: histórico da rodada {previous_round} indisponível: {error}")

    recent_form: Dict[int, List[str]] = {}
    for club_id in clubs_by_id:
        results: List[str] = []
        for match in history:
            home = integer(match.get("clube_casa_id") or match.get("casa_id"))
            away = integer(match.get("clube_visitante_id") or match.get("visitante_id"))
            if club_id not in (home, away):
                continue
            result = result_for(club_id, match)
            if result:
                results.append(result)
        recent_form[club_id] = results[-5:]

    athletes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for athlete in market.get("atletas") or []:
        if not isinstance(athlete, dict):
            continue
        club_id = integer(athlete.get("clube_id"))
        club = clubs_by_id.get(club_id, {})
        abbr = clean(club.get("abreviacao")).upper()
        for athlete_name in (athlete.get("apelido"), athlete.get("nome"), athlete.get("slug")):
            normalized_name = key_text(athlete_name)
            if normalized_name:
                athletes[(normalized_name, abbr)] = athlete
                athletes.setdefault((normalized_name, ""), athlete)

    return {
        "clubs_by_abbr": clubs_by_abbr,
        "opponent": opponent,
        "recent_form": recent_form,
        "athletes": athletes,
    }


def form_sentence(club: Dict[str, Any], results: List[str]) -> str:
    name = clean(club.get("nome") or club.get("abreviacao"))
    if not results:
        return f"O {name} não tem cinco resultados finalizados disponíveis no recorte oficial."
    return (
        f"Nos últimos {len(results)} jogos, o {name} somou {results.count('vitória')} vitórias, "
        f"{results.count('empate')} empates e {results.count('derrota')} derrotas."
    )


def top5_map(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    payload = data.get("top5") if isinstance(data.get("top5"), dict) else {}
    rows = payload.get("dados") or payload.get("atletas") or payload.get("jogadores") or []
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            name = row.get("NOME") or row.get("nome")
            if name:
                result[key_text(name)] = row
    return result


def build_dialogue_v5(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    segments: List[v3.Segment] = []
    context = load_official_context(round_value)
    clubs = context["clubs_by_abbr"]
    opponents = context["opponent"]
    recent = context["recent_form"]
    athlete_market = context["athletes"]
    top5 = top5_map(data)

    games = list(data.get("jogos") or [])
    players = dict(data.get("jogadores") or {})
    teams = dict(data.get("times") or {})

    v4.add_segment(
        segments,
        "FRANCISCA",
        f"Começa agora a análise inicial da rodada {round_value}. A imagem preserva exatamente os times e o Top 5 publicados no canal. No áudio, vamos detalhar colocação dos clubes, desempenho recente, média dos atletas, preço e contexto de cada escolha.",
        "rodada",
        "Snapshot publicado com análise completa de desempenho.",
    )

    for index, game in enumerate(games):
        visual = f"jogo_{index}"
        home_abbr = clean(game.get("mandante_sigla")).upper()
        away_abbr = clean(game.get("visitante_sigla")).upper()
        home = clubs.get(home_abbr, {"nome": clean(game.get("mandante")), "abreviacao": home_abbr})
        away = clubs.get(away_abbr, {"nome": clean(game.get("visitante")), "abreviacao": away_abbr})
        home_name = clean(home.get("nome") or home_abbr)
        away_name = clean(away.get("nome") or away_abbr)
        home_position = integer(home.get("posicao"))
        away_position = integer(away.get("posicao"))
        position_text = ""
        if home_position and away_position:
            position_text = (
                f"Na classificação, o {home_name} é o {ordinal(home_position)}, "
                f"enquanto o {away_name} aparece como {ordinal(away_position)}. "
            )
        v4.add_segment(
            segments,
            ["ANTÔNIO", "THALITA", "FRANCISCA"][index % 3],
            f"O confronto é {home_name} contra {away_name}. {position_text}"
            f"{form_sentence(home, recent.get(integer(home.get('id')), []))} "
            f"{form_sentence(away, recent.get(integer(away.get('id')), []))} "
            f"O mando é do {home_name}, mas a escalação deve separar força coletiva de produção individual de scouts.",
            visual,
            f"{home_name} x {away_name} • classificação e últimos jogos.",
        )

    if teams:
        v4.add_segment(
            segments,
            "THALITA",
            "Agora entram os três modelos exatamente como foram publicados na seleção inicial. Como a rodada ainda não começou, não vamos chamar zero ponto de desempenho. O correto é apresentar custo, capitão e proposta de montagem.",
            "pontuacoes",
            "Seleção inicial: custo, capitão e proposta de cada modelo.",
        )
        for index, team in enumerate(teams.values()):
            name = clean(team.get("nome")) or "Modelo"
            cost = number(team.get("custo"))
            captain = clean(team.get("capitao")) or "não informado"
            v4.add_segment(
                segments,
                ["ANTÔNIO", "FRANCISCA", "THALITA"][index % 3],
                f"O {name} foi publicado com custo de {cost} cartoletas e capitão {captain}. Essa é a fotografia inicial; o desempenho será medido somente depois que os atletas pontuarem na rodada.",
                "pontuacoes",
                f"{name}: C$ {cost} • capitão {captain}.",
            )

    v4.add_segment(
        segments,
        "FRANCISCA",
        "Vamos às escolhas individuais. Cada atleta será apresentado pela posição, clube por extenso, colocação da equipe, adversário, preço e desempenho disponível no mercado do Cartola.",
        next(iter(players), "top5"),
        "Atletas: posição, clube, classificação, confronto e desempenho.",
    )

    for index, (name, player) in enumerate(players.items()):
        abbr = clean(player.get("clube")).upper()
        club = clubs.get(abbr, {"nome": abbr, "abreviacao": abbr, "posicao": 0})
        club_name = clean(club.get("nome") or abbr)
        position_code = clean(player.get("posicao")).upper()
        position_name = POSICOES.get(position_code, position_code.lower() or "atleta")
        club_position = integer(club.get("posicao"))
        rival_info = opponents.get(abbr, {})
        rival = rival_info.get("adversario") if isinstance(rival_info.get("adversario"), dict) else {}
        rival_name = clean(rival.get("nome") or rival.get("abreviacao"))
        rival_position = integer(rival.get("posicao"))
        mando = clean(rival_info.get("mando"))

        athlete = athlete_market.get((key_text(name), abbr)) or athlete_market.get((key_text(name), "")) or {}
        top = top5.get(key_text(name), {})

        spoken = f"{name} é {position_name} do {club_name}"
        if club_position:
            spoken += f", clube que ocupa a condição de {ordinal(club_position)}"
        spoken += f", e custa {number(player.get('preco'))} cartoletas."

        if rival_name:
            spoken += f" Nesta rodada enfrenta o {rival_name}"
            if rival_position:
                spoken += f", {ordinal(rival_position)}"
            if mando:
                spoken += f", jogando {mando}"
            spoken += "."

        performance: List[str] = []
        if athlete.get("media_num") is not None:
            performance.append(f"média de {number(athlete.get('media_num'))} pontos")
        if integer(athlete.get("jogos_num")):
            performance.append(f"em {integer(athlete.get('jogos_num'))} jogos")
        if athlete.get("pontos_num") is not None:
            performance.append(f"última pontuação de {number(athlete.get('pontos_num'))}")
        if athlete.get("variacao_num") is not None:
            performance.append(f"variação de preço de {number(athlete.get('variacao_num'))} cartoletas")
        expected = top.get("EXP_SCORE") if top else None
        if expected is not None:
            performance.append(f"projeção do Top 5 de {number(expected)} pontos")
        if performance:
            spoken += " O desempenho disponível mostra " + ", ".join(performance) + "."

        rationale = clean(player.get("racional")) or "A escolha deve equilibrar preço, confronto e capacidade de produzir scouts próprios."
        spoken += " " + rationale

        v4.add_segment(
            segments,
            ["ANTÔNIO", "THALITA", "FRANCISCA"][index % 3],
            spoken,
            name,
            f"{name} • {position_name} • {club_name} • C$ {number(player.get('preco'))}.",
        )

    v4.add_segment(
        segments,
        "THALITA",
        "O Top 5 deve ser entendido pelo desempenho esperado de cada posição. A lista preservada no snapshot permite comparar alternativas sem trocar retroativamente os nomes publicados no canal.",
        "top5",
        "Top 5 preservado: alternativas e projeções por posição.",
    )
    v4.add_segment(
        segments,
        "ANTÔNIO",
        "No pré-fechamento, essa estrutura será refeita com os snapshots próprios do pré-fechamento: mudanças nos times, atletas mantidos, retirados, dúvidas e desempenho atualizado.",
        "top5",
        "Pré-fechamento: nova análise com os times atualizados.",
    )
    v4.add_segment(
        segments,
        "FRANCISCA",
        f"Esta foi a análise inicial da rodada {round_value}. Portal SimonSports: a imagem mostra a seleção publicada e o áudio explica classificação, desempenho e risco de cada escolha.",
        "final",
        "Portal SimonSports • seleção preservada e análise completa.",
    )
    return segments


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    original_version = v3.VERSION
    original_frame = v3.create_frame_v3
    original_dialogue = v3.build_dialogue
    try:
        v3.VERSION = VERSION
        v3.create_frame_v3 = v4.create_frame_v4
        v3.build_dialogue = build_dialogue_v5
        return v3.generate(round_value, repo_root, output_path)
    finally:
        v3.VERSION = original_version
        v3.create_frame_v3 = original_frame
        v3.build_dialogue = original_dialogue


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera vídeo Cartola com classificação e desempenho no áudio.")
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
