from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import publicar_mitou_rodada as base

LIMITE = 100.0
TIPOS_VALIDOS = {"ECONOMICO", "INTERMEDIARIO", "PONTUACAO"}


def _tipo_simples(value: Any) -> str:
    return base.norm(value).replace("TIME_", "")


def _pontos(row: List[Any], h: Dict[str, int]) -> float:
    return base.num(base.getv(
        row,
        h,
        "PONTOS_COM_CAPITAO",
        "PONTOS_TOTAL",
        "PONTOS COM C",
        "PONTOS_COM_C",
        "PONTOS",
    ))


def equipes_mitadas_todas() -> List[Dict[str, Any]]:
    h, rows = base.rows_by_header(base.values("HIST_TIMES"))
    if not h:
        raise RuntimeError("HIST_TIMES sem cabeçalho")

    # Para cada rodada+modelo, a última ocorrência é a base consolidada.
    # Publica TODOS os 3 Times Simples que fecharem com 100 pontos ou mais.
    ultimos: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in rows:
        rodada = int(base.num(base.getv(row, h, "RODADA")))
        if rodada <= 0:
            continue

        tipo = _tipo_simples(base.getv(row, h, "TIPO_TIME", "TIPO", "ORIGEM"))
        if tipo not in TIPOS_VALIDOS:
            continue

        ultimos[(rodada, tipo)] = {
            "rodada": rodada,
            "tipo": tipo,
            "pontos": _pontos(row, h),
            "capitao": base.limpar_capitao(base.getv(row, h, "CAPITAO_SUGERIDO", "CAPITAO", "CAPITÃO")),
            "esquema": str(base.getv(row, h, "OBS", "ESQUEMA") or "").strip(),
        }

    encontrados = [item for item in ultimos.values() if float(item.get("pontos") or 0) >= LIMITE]
    encontrados.sort(key=lambda x: (int(x["rodada"]), x["tipo"]))
    print("Times Simples >=100:", [(x["rodada"], x["tipo"], x["pontos"]) for x in encontrados])
    return encontrados


def flag_tipo(item: Dict[str, Any]) -> Path:
    tipo = _tipo_simples(item["tipo"]).lower()
    return Path("data/flags") / f"mitou_rodada_{int(item['rodada'])}_{tipo}.publicado.json"


def flag_legacy(rodada: int) -> Path:
    return Path("data/flags") / f"mitou_rodada_{rodada}.publicado.json"


def _legacy_ja_publicou_mesmo_tipo(item: Dict[str, Any]) -> bool:
    path = flag_legacy(int(item["rodada"]))
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return _tipo_simples(data.get("tipo")) == _tipo_simples(item.get("tipo"))


def _registrar_flag(item: Dict[str, Any], path: Path, migrado: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "status": "PUBLICADO_COM_SUCESSO",
        "rodada": int(item["rodada"]),
        "tipo": _tipo_simples(item["tipo"]),
        "pontos": round(float(item["pontos"]), 2),
        "telegram_enviado": True,
        "migrado_de_flag_legacy": bool(migrado),
        "publicado_em": datetime.now(timezone.utc).isoformat(),
        "regra": "TODOS_OS_3_TIMES_SIMPLES_COM_100_OU_MAIS",
        "limite": LIMITE,
        "modelo": "MITOU_NA_RODADA_V2_TODOS_APROVADO",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def publicar(item: Dict[str, Any], force: bool = False) -> bool:
    fp = flag_tipo(item)
    if fp.exists() and not force:
        print(f"R{item['rodada']} {item['tipo']} já publicado. Pulando.")
        return False

    # Migra a flag antiga sem republicar o mesmo time que já saiu.
    if not force and _legacy_ja_publicou_mesmo_tipo(item):
        _registrar_flag(item, fp, migrado=True)
        print(f"R{item['rodada']} {item['tipo']} migrado da flag legacy sem duplicar Telegram.")
        return False

    players = base.jogadores(int(item["rodada"]), _tipo_simples(item["tipo"]))
    if not players:
        raise RuntimeError(f"HIST_JOGADORES sem escalação para R{item['rodada']} {item['tipo']}")

    original = base.render_card(item, players)
    tipo_slug = _tipo_simples(item["tipo"]).lower()
    destino = Path(base.OUTPUT_DIR) / f"mitou_na_rodada_{int(item['rodada'])}_{tipo_slug}.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if Path(original) != destino:
        if destino.exists():
            destino.unlink()
        Path(original).replace(destino)

    caption = (
        f"🏆 <b>MITOU NA RODADA {int(item['rodada'])}</b>\n"
        f"{base.nome_modelo(item['tipo']).title()} • {float(item['pontos']):.2f} pontos\n\n"
        f"📡 Portal SimonSports\n"
        f"🔗 @dicascartolaportalsimonsports"
    )
    base.enviar_foto(str(destino), caption)
    _registrar_flag(item, fp)
    print(f"MITOU R{item['rodada']} enviado: {item['tipo']} {float(item['pontos']):.2f}")
    return True


def registrar_processamento(rodada: int, elegiveis: List[Dict[str, Any]]) -> None:
    path = Path("data/flags") / f"mitou_rodada_{rodada}.processado.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "status": "PUBLICADO_COM_SUCESSO",
        "rodada": rodada,
        "limite": LIMITE,
        "quantidade_mitou": len(elegiveis),
        "times": [
            {"tipo": _tipo_simples(x["tipo"]), "pontos": round(float(x["pontos"]), 2)}
            for x in elegiveis
        ],
        "regra": "PUBLICAR_TODOS_OS_TIMES_SIMPLES_COM_100_OU_MAIS",
        "processado_em": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, default=0)
    parser.add_argument("--retroativo", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    todos = equipes_mitadas_todas()
    if args.rodada:
        rodadas = [args.rodada]
    elif args.retroativo:
        rodadas = sorted({int(x["rodada"]) for x in todos})
    else:
        rodadas = [max(int(x["rodada"]) for x in todos)] if todos else []

    publicados = 0
    for rodada in rodadas:
        elegiveis = [x for x in todos if int(x["rodada"]) == rodada]
        for item in elegiveis:
            if publicar(item, args.force):
                publicados += 1
        registrar_processamento(rodada, elegiveis)

    print(f"Publicações Mitou concluídas: {publicados}")


if __name__ == "__main__":
    main()
