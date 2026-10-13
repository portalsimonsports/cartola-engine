from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw

import publicar_mitou_rodada as base


def celula(row, heads, name):
    idx = heads.get(base.norm(name), -1)
    return row[idx] if 0 <= idx < len(row) else ""


def linhas(aba):
    matriz = base.values(aba)
    if not matriz:
        raise RuntimeError(f"Aba sem dados: {aba}")
    cab = {base.norm(v): i for i, v in enumerate(matriz[0])}
    return cab, matriz[1:]


def rodada_encerrada():
    resposta = requests.get(
        "https://api.cartola.globo.com/mercado/status",
        headers={"User-Agent": "PortalSimonSports-CartolaEngine/2026"},
        timeout=45,
    )
    resposta.raise_for_status()
    status = resposta.json()
    atual = int(status.get("rodada_atual") or status.get("rodada") or 0)
    if int(status.get("status_mercado") or 0) != 1 or atual < 2:
        return 0
    return atual - 1


def dados_da_selecao(rodada):
    hc, corpos = linhas("Seleção da Rodada Resumo")
    obrigatorios = ("RODADA", "ESQUEMA_VENCEDOR", "TOTAL_COM_CAPITAO")
    if not all(base.norm(n) in hc for n in obrigatorios):
        raise RuntimeError("Cabeçalho da aba de resumo não corresponde ao esperado")
    resumo = next(
        (r for r in reversed(corpos) if int(base.num(celula(r, hc, "RODADA"))) == rodada),
        None,
    )
    if not resumo:
        print(f"Seleção Fantástica R{rodada}: resumo indisponível")
        return None
    hp, linhas_atletas = linhas("Seleção da Rodada")
    obrigatorios_p = ("RODADA", "POSICAO", "APELIDO", "PONTOS", "ORDEM")
    if not all(base.norm(n) in hp for n in obrigatorios_p):
        raise RuntimeError("Cabeçalho da aba da seleção não corresponde ao esperado")
    por_ordem = {}
    for r in linhas_atletas:
        if int(base.num(celula(r, hp, "RODADA"))) != rodada:
            continue
        ordem = int(base.num(celula(r, hp, "ORDEM")))
        if ordem not in range(1, 13):
            continue
        por_ordem[ordem] = {
            "pos": str(celula(r, hp, "POSICAO")).strip(),
            "nome": str(celula(r, hp, "APELIDO")).strip(),
            "pontos": base.num(celula(r, hp, "PONTOS")),
            "capitao": base.norm(celula(r, hp, "IS_CAPITAO")) == "SIM",
        }
    if len(por_ordem) != 12 or any(not p["nome"] or not p["pos"] for p in por_ordem.values()):
        print(f"Seleção Fantástica R{rodada}: escalação incompleta, {len(por_ordem)}/12")
        return None
    pontos = base.num(celula(resumo, hc, "TOTAL_COM_CAPITAO"))
    esquema = str(celula(resumo, hc, "ESQUEMA_VENCEDOR")).strip()
    if pontos <= 0 or not esquema:
        return None
    return {"rodada": rodada, "total": pontos, "esquema": esquema,
            "jogadores": [por_ordem[k] for k in sorted(por_ordem)]}


def desenhar(dados):
    w, h = 1080, 1350
    im = Image.new("RGB", (w, h), (4, 16, 39))
    d = ImageDraw.Draw(im)
    f = base.fnt
    white, gold, cyan = (242, 246, 252), (255, 191, 38), (54, 170, 255)
    d.rounded_rectangle((32, 30, 1048, 1315), radius=26, outline=cyan, width=4)
    d.text((70, 65), "PORTAL SIMONSPORTS  •  CARTOLA", font=f(29, True), fill=white)
    d.text((70, 134), "SELEÇÃO FANTÁSTICA", font=f(53, True), fill=gold)
    d.text((70, 210), "TIME DOS SONHOS", font=f(39, True), fill=white)
    d.text((70, 285), f"RODADA {dados['rodada']}   |   ESQUEMA {dados['esquema']}",
           font=f(31, True), fill=cyan)
    d.rounded_rectangle((70, 357, 1010, 483), radius=18, fill=(15, 48, 93))
    d.text((100, 380), "PONTUAÇÃO IDEAL DA RODADA", font=f(26, True), fill=white)
    d.text((100, 420), f"{dados['total']:.2f} PONTOS".replace(".", ","),
           font=f(43, True), fill=gold)
    d.text((75, 532), "POS  |  ATLETA                                      PTS", font=f(24, True), fill=cyan)
    for i, p in enumerate(dados["jogadores"]):
        y = 585 + i * 52
        if i % 2 == 0:
            d.rounded_rectangle((65, y - 5, 1015, y + 46), radius=8, fill=(13, 38, 73))
        nome = p["nome"][:25] + ("  (C)" if p["capitao"] else "")
        d.text((85, y), p["pos"][:4], font=f(23, True), fill=gold)
        d.text((200, y), nome, font=f(25), fill=white)
        d.text((873, y), f"{p['pontos']:.2f}".replace(".", ","), font=f(24, True), fill=gold)
    d.text((80, 1248), "@dicascartolaportalsimonsports", font=f(23), fill=white)
    out = Path("output") / f"selecao_fantastica_rodada_{dados['rodada']}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def main():
    rodada = rodada_encerrada()
    if not rodada:
        print("Mercado não aberto para próxima rodada; sem publicação antecipada")
        return
    flag = Path("data/flags") / f"selecao_fantastica_rodada_{rodada}.publicado.json"
    if flag.exists():
        print(f"Seleção Fantástica R{rodada} já publicada")
        return
    dados = dados_da_selecao(rodada)
    if not dados:
        return
    arquivo = desenhar(dados)
    legenda = (
        f"🏆 <b>SELEÇÃO FANTÁSTICA — R{rodada}</b>\n"
        f"✨ Time dos Sonhos | {dados['esquema']}\n"
        f"⭐ {dados['total']:.2f} pontos\n"
        "📡 Portal SimonSports"
    )
    base.enviar_foto(str(arquivo), legenda)
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(json.dumps({
        "rodada": rodada, "status": "PUBLICADO_COM_SUCESSO",
        "total": dados["total"], "esquema": dados["esquema"],
        "publicado_em": datetime.now(timezone.utc).isoformat()
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Seleção Fantástica R{rodada}: enviada")


if __name__ == "__main__":
    main()
