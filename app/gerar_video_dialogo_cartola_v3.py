from __future__ import annotations

import argparse
import asyncio
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

import gerar_video_dialogo_cartola_v1 as base


VERSION = "cartola_dialogo_tecnico_v3_2026_07_30"
WIDTH = base.WIDTH
HEIGHT = base.HEIGHT
CARD_W = 660
CARD_H = 770


@dataclass(frozen=True)
class Segment:
    speaker: str
    voice: str
    text: str
    visual: str
    onscreen: str


def safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}".replace(".", ",")
    except Exception:
        return "0"


def percent(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%".replace(".", ",")
    except Exception:
        return "0%"


def cartoletas(value: Any) -> str:
    return f"{number(value)} cartoletas"


def sanitize_tts(text: str) -> str:
    cleaned = re.sub(r"\bC\s*\$\s*", "", safe(text), flags=re.IGNORECASE)
    cleaned = re.sub(r"d[oó]lar(?:es)? canadense(?:s)?", "cartoletas", cleaned, flags=re.IGNORECASE)
    return cleaned


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, font) -> List[str]:
    words = safe(text).split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int, min_size: int, bold: bool = False):
    for size in range(max_size, min_size - 1, -1):
        font = base.font(size, bold)
        if draw.textbbox((0, 0), safe(text), font=font)[2] <= max_width:
            return font
    return base.font(min_size, bold)


def gradient() -> Image.Image:
    image = Image.new("RGB", (CARD_W, CARD_H), base.BG)
    pixels = image.load()
    for y in range(CARD_H):
        for x in range(CARD_W):
            glow = max(0.0, 1.0 - (((x - 520) ** 2 + (y - 110) ** 2) ** 0.5) / 650)
            pixels[x, y] = (int(2 + 4 * glow), int(12 + 25 * glow), int(27 + 48 * glow))
    return image


def card_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((28, 20), "PS  PORTAL SIMONSPORTS", font=base.font(22, True), fill=base.WHITE)
    draw.text((28, 52), "CARTOLA • DADOS • ANÁLISE", font=base.font(13, True), fill=base.SILVER)
    draw.line((28, 84, 632, 84), fill=base.LINE, width=2)
    draw.text((28, 104), title, font=fit_text(draw, title, 600, 29, 21, True), fill=(32, 196, 255))
    for index, line in enumerate(wrap(draw, subtitle, 600, base.font(17))[:2]):
        draw.text((28, 142 + index * 23), line, font=base.font(17), fill=base.SILVER)


def draw_form(draw: ImageDraw.ImageDraw, form: str, x: int, y: int) -> None:
    values = safe(form).split()
    colors = {"V": (53, 210, 122), "E": (255, 190, 55), "D": (237, 71, 96)}
    for index, value in enumerate(values[:5]):
        color = colors.get(value.upper(), (100, 120, 140))
        rounded(draw, (x + index * 45, y, x + index * 45 + 34, y + 34), 10, (7, 24, 43), color, 2)
        font = base.font(16, True)
        bbox = draw.textbbox((0, 0), value, font=font)
        draw.text((x + index * 45 + (34 - (bbox[2]-bbox[0]))/2, y + 7), value, font=font, fill=color)


def methodology_card(output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    card_header(draw, "ANÁLISE V3: MAIS PROFUNDIDADE", "Confrontos, histórico, última pontuação e justificativa de cada escolha.")
    items = [
        ("1", "JOGOS DA RODADA", "Tabela, mando e forma recente dos seis confrontos válidos."),
        ("2", "ÚLTIMA PONTUAÇÃO", "Recorte mais recente dos três modelos, com participação real."),
        ("3", "CADA ESCOLHA", "Preço, função no modelo, confronto, teto, risco e correlação."),
        ("4", "DIÁLOGO REAL", "Perguntas, respostas e contrapontos entre os apresentadores."),
    ]
    colors = [(32,196,255),(255,190,55),(181,86,255),(53,210,122)]
    y = 205
    for (num,title,desc), color in zip(items, colors):
        rounded(draw, (28,y,632,y+112), 22, (5,24,45), color, 2)
        rounded(draw, (45,y+25,101,y+81), 18, (8,35,60), color, 2)
        draw.text((66,y+38), num, font=base.font(24,True), fill=color, anchor="mm")
        draw.text((125,y+18), title, font=base.font(20,True), fill=base.WHITE)
        for i,line in enumerate(wrap(draw, desc, 470, base.font(16))[:2]):
            draw.text((125,y+52+i*21), line, font=base.font(16), fill=base.SILVER)
        y += 126
    rounded(draw, (35,710,625,755), 18, (23,14,3), (255,190,55), 2)
    draw.text((330,733), "SEM PROMESSA DE PONTUAÇÃO", font=base.font(19,True), fill=(255,190,55), anchor="mm")
    image.save(output, "PNG", optimize=True)


def round_overview_card(data: Dict[str, Any], output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    card_header(draw, "SEIS JOGOS VÁLIDOS", "Quatro partidas foram adiadas e não integraram a rodada do fantasy game.")
    y = 200
    for game in data["jogos"]:
        rounded(draw, (28,y,632,y+78), 18, (5,24,45), (32,196,255), 2)
        draw.text((45,y+13), f"{game['mandante_sigla']}  x  {game['visitante_sigla']}", font=base.font(22,True), fill=base.WHITE)
        draw.text((230,y+16), f"{game['data']} • {game['hora']}", font=base.font(17,True), fill=(255,190,55))
        draw.text((45,y+48), f"{game['pos_mandante']}º x {game['pos_visitante']}º • {game['estadio']}", font=base.font(15), fill=base.SILVER)
        y += 88
    image.save(output, "PNG", optimize=True)


def game_card(game: Dict[str, Any], output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    card_header(draw, f"{game['mandante_sigla']} x {game['visitante_sigla']}", f"{game['data']} • {game['hora']} • {game['estadio']}")
    rounded(draw, (28,200,632,320), 24, (5,25,47), (32,196,255), 2)
    draw.text((52,218), game["mandante"].upper(), font=fit_text(draw, game["mandante"].upper(), 215, 25, 18, True), fill=base.WHITE)
    draw.text((330,260), "X", font=base.font(38,True), fill=(32,196,255), anchor="mm")
    right_font = fit_text(draw, game["visitante"].upper(), 215, 25, 18, True)
    rb = draw.textbbox((0,0), game["visitante"].upper(), font=right_font)
    draw.text((608-(rb[2]-rb[0]),218), game["visitante"].upper(), font=right_font, fill=base.WHITE)
    draw.text((52,270), f"{game['pos_mandante']}º colocado", font=base.font(17,True), fill=(255,190,55))
    txt=f"{game['pos_visitante']}º colocado"
    tb=draw.textbbox((0,0),txt,font=base.font(17,True))
    draw.text((608-(tb[2]-tb[0]),270), txt, font=base.font(17,True), fill=(255,190,55))

    draw.text((40,350), "FORMA RECENTE", font=base.font(18,True), fill=base.SILVER)
    draw.text((40,385), game["mandante_sigla"], font=base.font(18,True), fill=base.WHITE)
    draw_form(draw, game["forma_mandante"], 105, 380)
    draw.text((40,430), game["visitante_sigla"], font=base.font(18,True), fill=base.WHITE)
    draw_form(draw, game["forma_visitante"], 105, 425)

    rounded(draw, (32,500,628,735), 24, (4,20,39), (181,86,255), 2)
    draw.text((52,520), "LEITURA TÉCNICA", font=base.font(20,True), fill=(181,86,255))
    for i,line in enumerate(wrap(draw, game["leitura"], 540, base.font(18))[:7]):
        draw.text((52,558+i*25), line, font=base.font(18), fill=base.WHITE)
    image.save(output, "PNG", optimize=True)


def team_scores_card(data: Dict[str, Any], output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    card_header(draw, "ÚLTIMA PONTUAÇÃO DISPONÍVEL", "Parciais do recorte usado no piloto; não são apresentadas como resultado final.")
    colors = [(53,210,122),(32,196,255),(181,86,255)]
    y = 205
    for (_, team), color in zip(data["times"].items(), colors):
        rounded(draw, (28,y,632,y+150), 24, (5,24,45), color, 2)
        draw.text((48,y+18), team["nome"].upper(), font=base.font(22,True), fill=base.WHITE)
        draw.text((48,y+60), f"{number(team['ultima_pontuacao'])} pts", font=base.font(36,True), fill=color)
        draw.text((350,y+70), f"Participação: {team['participacao']}", font=base.font(18,True), fill=base.SILVER)
        draw.text((48,y+112), team["tipo_pontuacao"], font=base.font(15), fill=base.SILVER)
        y += 170
    rounded(draw,(35,720,625,755),16,(23,14,3),(255,190,55),2)
    draw.text((330,737),"RECORTE IDENTIFICADO • SEM CONFUNDIR PARCIAL COM FINAL",font=base.font(15,True),fill=(255,190,55),anchor="mm")
    image.save(output, "PNG", optimize=True)


def player_card(name: str, player: Dict[str, Any], output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    card_header(draw, "POR QUE FOI ESCALADO?", "Preço, papel no modelo e contexto do confronto.")
    rounded(draw,(28,190,632,275),22,(5,27,52),(32,196,255),2)
    draw.text((48,207), name.upper(), font=fit_text(draw,name.upper(),390,29,19,True), fill=base.WHITE)
    draw.text((48,242), f"{player['posicao']} • {player['clube']} • {cartoletas(player['preco'])}", font=base.font(17,True), fill=(255,190,55))
    model_text = " • ".join(player.get("modelos",[]))
    draw.text((610,242), model_text, font=fit_text(draw,model_text,245,15,11,True), fill=(32,196,255), anchor="ra")

    rounded(draw,(28,295,632,420),22,(5,24,45),(53,210,122),2)
    draw.text((48,313), f"{player['clube']} {player.get('pos_clube','?')}º  x  {player.get('adversario','')} {player.get('pos_adversario','?')}º", font=base.font(22,True), fill=base.WHITE)
    draw.text((48,352),"Forma do clube",font=base.font(15,True),fill=base.SILVER)
    draw_form(draw,player.get("forma_clube",""),180,345)
    draw.text((48,390),"Forma do rival",font=base.font(15,True),fill=base.SILVER)
    draw_form(draw,player.get("forma_adversario",""),180,383)

    metrics = []
    if "media_ult5" in player:
        metrics = [
            ("Média últimas 5", f"{number(player['media_ult5'])} pts", min(1, player["media_ult5"]/14), (32,196,255)),
            ("Probabilidade 8+", percent(player.get("prob_8",0)), player.get("prob_8",0), (181,86,255)),
            ("Confiança", percent(player.get("indice_confianca",0)), player.get("indice_confianca",0), (53,210,122)),
        ]
    y=445
    for label,display,norm,color in metrics:
        draw.text((48,y),label.upper(),font=base.font(15,True),fill=base.SILVER)
        draw.text((610,y),display,font=base.font(17,True),fill=color,anchor="ra")
        rounded(draw,(48,y+26,612,y+44),9,(8,28,50),(23,63,94),1)
        rounded(draw,(50,y+28,50+int(560*max(.02,min(1,norm))),y+42),7,color)
        y+=65

    insight_top = 645 if metrics else 455
    rounded(draw,(32,insight_top,628,748),22,(4,20,39),(255,190,55),2)
    draw.text((52,insight_top+16),"JUSTIFICATIVA",font=base.font(17,True),fill=(255,190,55))
    max_lines = 3 if metrics else 9
    font = base.font(16 if metrics else 18, True)
    for i,line in enumerate(wrap(draw,player["racional"],540,font)[:max_lines]):
        draw.text((52,insight_top+45+i*(21 if metrics else 25)),line,font=font,fill=base.WHITE)
    image.save(output,"PNG",optimize=True)


def create_frame_v3(visual_path: Path | None, collage_paths: List[Path], speaker: str, text: str, round_value: int, output: Path) -> None:
    if visual_path is None:
        foreground = base.make_collage(collage_paths)
        foreground = base.fit_image(foreground, 660, 770)
    else:
        foreground = base.fit_image(Image.open(visual_path), 660, 770)

    background_source = foreground.resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS)
    background = background_source.filter(ImageFilter.GaussianBlur(25)).convert("RGBA")
    frame = Image.alpha_composite(background, Image.new("RGBA",(WIDTH,HEIGHT),(0,8,22,185)))
    draw=ImageDraw.Draw(frame)

    rounded(draw,(20,18,700,76),24,(3,20,39,235),base.LINE,2)
    header=f"ANÁLISE DIALOGADA • RODADA {round_value}"
    hb=draw.textbbox((0,0),header,font=base.font(25,True))
    draw.text(((WIDTH-(hb[2]-hb[0]))/2,32),header,font=base.font(25,True),fill=base.WHITE)

    x=(WIDTH-foreground.width)//2
    frame.alpha_composite(foreground.convert("RGBA"),(x,90))

    accent=base.SPEAKER_COLORS[speaker]
    panel=(22,880,698,1245)
    rounded(draw,panel,30,(4,18,36,248),accent,3)
    rounded(draw,(48,902,275,960),20,(accent[0]//5,accent[1]//5,accent[2]//5,255),accent,2)
    draw.text((70,915),speaker,font=base.font(26,True),fill=accent)

    # Texto fica em uma área exclusiva abaixo do visual: não há sobreposição.
    text_font, lines = base.wrap_text(draw,text,610,28,19)
    while len(lines)>8 and text_font.size>17:
        text_font=base.font(text_font.size-1,False)
        lines=wrap(draw,text,610,text_font)
    line_height=text_font.size+8
    y=985
    for line in lines[:9]:
        draw.text((52,y),line,font=text_font,fill=base.WHITE)
        y+=line_height

    footer="@dicascartolaportalsimonsports  •  PORTAL SIMONSPORTS"
    fb=draw.textbbox((0,0),footer,font=base.font(16,True))
    draw.text(((WIDTH-(fb[2]-fb[0]))/2,1255),footer,font=base.font(16,True),fill=base.SILVER)
    frame.convert("RGB").save(output,"PNG",optimize=True)


def speaker_voice(speaker: str) -> str:
    return {"FRANCISCA":base.VOICE_FRANCISCA,"ANTÔNIO":base.VOICE_ANTONIO,"THALITA":base.VOICE_THALITA}[speaker]


def metric_sentence(player: Dict[str, Any]) -> str:
    if "media_ult5" not in player:
        return ""
    return (
        f" A média das últimas cinco é {number(player['media_ult5'])} pontos, "
        f"a probabilidade de superar oito é {percent(player.get('prob_8',0))}, "
        f"e o índice de confiança está em {percent(player.get('indice_confianca',0))}."
    )


def build_dialogue(round_value: int, data: Dict[str, Any]) -> List[Segment]:
    segments: List[Segment] = []
    def add(speaker: str, text: str, visual: str, onscreen: str) -> None:
        segments.append(Segment(speaker,speaker_voice(speaker),sanitize_tts(text),visual,onscreen))

    add("FRANCISCA",f"Olá! Começa agora a terceira versão do piloto técnico da rodada {round_value}. A proposta foi ampliada: vamos analisar os seis jogos válidos, mostrar a última pontuação disponível dos três modelos e explicar, atleta por atleta, o motivo de cada escolha.","metodologia","V3: jogos, última pontuação e justificativa de cada atleta.")
    add("ANTÔNIO","E desta vez a conversa não ficará presa à leitura da escalação. Nós vamos questionar as escolhas, confrontar teto e risco, e dizer quando os próprios indicadores não permitem uma conclusão segura.","metodologia","Perguntas e contrapontos reais — sem tratar projeção como certeza.")
    add("THALITA","Também corrigimos a apresentação visual. A caixa de fala agora ocupa uma área exclusiva abaixo dos gráficos. Nenhum texto do apresentador deve esconder a última métrica do jogador analisado.","metodologia","Layout corrigido: indicadores e fala em áreas separadas.")

    add("FRANCISCA","Antes dos jogadores, precisamos entender a rodada. Apenas seis confrontos foram válidos para o fantasy game, enquanto quatro partidas ficaram adiadas. Antônio, por que isso muda tanto a montagem?","rodada","Seis jogos válidos reduzem o universo de escolhas.")
    add("ANTÔNIO","Porque doze clubes concentram todo o mercado. Quando vários modelos repetem atletas do mesmo confronto, a correlação aumenta: um bom jogo pode impulsionar tudo, mas uma atuação ruim também atinge várias posições ao mesmo tempo.","rodada","Menos jogos: maior repetição e maior correlação entre escolhas.")

    speakers=[("THALITA","ANTÔNIO"),("FRANCISCA","THALITA"),("ANTÔNIO","FRANCISCA"),("THALITA","ANTÔNIO"),("FRANCISCA","THALITA"),("ANTÔNIO","FRANCISCA")]
    for i,game in enumerate(data["jogos"]):
        q,a=speakers[i]
        add(q,f"{a.title()}, vamos ao confronto entre {game['mandante']} e {game['visitante']}. A tabela mostra {game['pos_mandante']}º contra {game['pos_visitante']}º, e os recortes recentes são {game['forma_mandante']} e {game['forma_visitante']}. Qual é a leitura correta para o Cartola?",f"jogo_{i}",f"{game['mandante_sigla']} x {game['visitante_sigla']} • tabela e forma recente.")
        add(a,game["leitura"]+ " O ponto central é usar o contexto para explicar a escolha, sem transformar posição de tabela em promessa de scout.",f"jogo_{i}",game["leitura"])

    add("FRANCISCA","Agora vamos registrar a fotografia mais recente dos três modelos. Atenção: esses números são a última parcial disponível no recorte do piloto, e não o fechamento definitivo da rodada.","pontuacoes","Última pontuação disponível, claramente identificada como parcial.")
    econ=data["times"]["economico"]; inter=data["times"]["intermediario"]; pont=data["times"]["pontuacao"]
    add("ANTÔNIO",f"O Econômico aparece com {number(econ['ultima_pontuacao'])} pontos e participação de {econ['participacao']}. O dado ajuda a avaliar a evolução, mas não pode ser comparado como resultado final enquanto ainda houver atletas por jogar.","pontuacoes",f"Econômico: {number(econ['ultima_pontuacao'])} pts • {econ['participacao']}.")
    add("THALITA",f"O Intermediário registra {number(inter['ultima_pontuacao'])} pontos, com {inter['participacao']} atletas contabilizados. A diferença de participação explica por que uma parcial menor não significa necessariamente desempenho final inferior.","pontuacoes",f"Intermediário: {number(inter['ultima_pontuacao'])} pts • {inter['participacao']}.")
    add("FRANCISCA",f"O Time para Pontuar está em {number(pont['ultima_pontuacao'])} pontos e {pont['participacao']} de participação. Assim, os três números ganham contexto e deixam de parecer uma comparação fechada antes da hora.","pontuacoes",f"Para Pontuar: {number(pont['ultima_pontuacao'])} pts • {pont['participacao']}.")

    order=[
        "Marcelo Rangel","Lucas Arcanjo","Marcelinho","Mayk","Matheuzinho",
        "Thiago Santos","Jacy","Gabriel Paulista","Arias","Patrick","Zé Ricardo",
        "Matheus Pereira","Josué","Viveros","Jajá","Alef Manga","Pedro",
        "Samuel Lino","Rafael Guanaes","Leonardo Jardim"
    ]
    cycle=["ANTÔNIO","THALITA","FRANCISCA"]
    add("ANTÔNIO","Vamos agora atleta por atleta. Thalita, começamos pelos goleiros: o que sustenta Marcelo Rangel no Econômico?","Marcelo Rangel","Análise individual: preço, confronto, papel e risco.")
    for idx,name in enumerate(order):
        p=data["jogadores"][name]
        speaker=cycle[idx%3]
        text=f"Sobre {name}: {p['racional']}{metric_sentence(p)}"
        if idx < len(order)-1:
            nxt=order[idx+1]
            next_speaker=cycle[(idx+1)%3].title()
            text += f" {next_speaker}, qual é o ponto decisivo na escolha de {nxt}?"
        add(speaker,text,name,f"{name}: {p['posicao']} • {p['clube']} • {cartoletas(p['preco'])}.")

    add("FRANCISCA","Depois de analisar cada titular, o Top 5 deve funcionar como comparação, não como uma lista para ser lida. Ele apresenta alternativas por posição para quem deseja trocar preço, teto ou exposição a determinado confronto.","top5","Top 5: alternativas por perfil, e não simples leitura de nomes.")
    add("ANTÔNIO","A pergunta técnica é sempre a mesma: a substituição melhora a eficiência por cartoleta, aumenta o teto ou apenas troca um risco por outro? Sem essa resposta, citar o ranking não acrescenta análise.","top5","Comparar eficiência, teto, estabilidade e correlação.")
    add("THALITA","E a próxima rodada poderá usar este mesmo formato de forma automática, desde que as bases entreguem escalações, métricas recentes, confrontos e a última pontuação dos modelos. Quando um dado estiver ausente, o vídeo deve declarar a limitação em vez de inventar uma conclusão.","top5","Automação com transparência: dado ausente não vira afirmação.")

    add("FRANCISCA",f"Esta foi a análise técnica ampliada da rodada {round_value}. A seleção é explicada por preço, desempenho recente, contexto coletivo, risco e proposta de cada modelo. Nada disso garante pontuação, mas torna a decisão mais transparente.","final","Análise informativa: critério e transparência, sem garantia.")
    add("ANTÔNIO","Portal SimonSports: dados para entender a escalação, diálogo para confrontar as escolhas e entretenimento responsável para acompanhar a rodada.","final","Portal SimonSports • Cartola • Dados • Análise.")
    return segments


def create_visuals(data: Dict[str, Any], temp: Path, repo_root: Path, round_value: int) -> Dict[str, Path | None]:
    visuals: Dict[str, Path | None] = {}
    visuals["metodologia"]=temp/"metodologia_v3.png"; methodology_card(visuals["metodologia"])
    visuals["rodada"]=temp/"rodada_v3.png"; round_overview_card(data,visuals["rodada"])
    visuals["pontuacoes"]=temp/"pontuacoes_v3.png"; team_scores_card(data,visuals["pontuacoes"])
    for i,game in enumerate(data["jogos"]):
        path=temp/f"jogo_{i}.png"; game_card(game,path); visuals[f"jogo_{i}"]=path
    for name,player in data["jogadores"].items():
        path=temp/(re.sub(r"[^a-z0-9]+","_",name.lower()).strip("_")+".png")
        player_card(name,player,path); visuals[name]=path
    output=repo_root/"output"
    visuals["top5"]=output/f"top5_rodada_{round_value}.png"
    visuals["final"]=None
    return visuals


async def synthesize(segment: Segment, output: Path) -> None:
    settings=base.VOICE_SETTINGS[segment.voice]
    communicator=base.edge_tts.Communicate(text=sanitize_tts(segment.text),voice=segment.voice,rate=settings["rate"],pitch=settings["pitch"],volume=settings["volume"])
    await communicator.save(str(output))


async def synthesize_all(segments: List[Segment], directory: Path) -> List[Path]:
    files=[]
    for index,segment in enumerate(segments):
        path=directory/f"fala_v3_{index:02d}.mp3"
        await synthesize(segment,path)
        files.append(path)
    return files


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data=load_json(repo_root/"data"/f"analise_tecnica_rodada_{round_value}_v3.json")
    segments=build_dialogue(round_value,data)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    required=[
        repo_root/"output"/f"time_economico_rodada_{round_value}.png",
        repo_root/"output"/f"time_intermediario_rodada_{round_value}.png",
        repo_root/"output"/f"time_pontuacao_rodada_{round_value}.png",
        repo_root/"output"/f"top5_rodada_{round_value}.png",
    ]
    missing=[str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"Imagens obrigatórias ausentes: {missing}")

    with tempfile.TemporaryDirectory(prefix="cartola-dialogo-v3-") as temp_name:
        temp=Path(temp_name)
        visuals=create_visuals(data,temp,repo_root,round_value)
        try:
            audio_files=asyncio.run(synthesize_all(segments,temp))
        except Exception as exc:
            raise RuntimeError("Falha ao gerar as três vozes aprovadas; nenhuma voz genérica foi usada.") from exc

        clips=[]; timeline=[]; elapsed=0.0
        for index,(segment,audio) in enumerate(zip(segments,audio_files)):
            duration=base.ffprobe_duration(audio)
            frame=temp/f"frame_v3_{index:02d}.png"
            clip=temp/f"clip_v3_{index:02d}.mp4"
            create_frame_v3(visuals.get(segment.visual),required,segment.speaker,segment.onscreen,round_value,frame)
            base.segment_video(frame,audio,clip,duration)
            clip_duration=duration+0.38
            timeline.append({
                "indice":index+1,"inicio":round(elapsed,3),"fim":round(elapsed+clip_duration,3),
                "apresentador":segment.speaker,"voz":segment.voice,"texto_falado":sanitize_tts(segment.text),
                "texto_tela":segment.onscreen,"visual":segment.visual
            })
            elapsed+=clip_duration; clips.append(clip)

        concat=temp/"concat_v3.txt"
        concat.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips),encoding="utf-8")
        base.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(output_path)])

    duration=base.ffprobe_duration(output_path)
    manifest=output_path.with_suffix(".json")
    manifest.write_text(json.dumps({
        "versao":VERSION,"status":"PILOTO_PARA_APROVACAO","publicacao_automatica":False,
        "rodada":round_value,"arquivo":str(output_path),"duracao_segundos":round(duration,3),
        "duracao_alvo_minutos":[10,15],"moeda_falada":"cartoletas",
        "layout_sem_sobreposicao":True,"jogos_analisados":len(data["jogos"]),
        "jogadores_analisados":len(data["jogadores"]),
        "vozes":[base.VOICE_FRANCISCA,base.VOICE_ANTONIO,base.VOICE_THALITA],
        "fontes":data.get("fontes",[]),"timeline":timeline
    },ensure_ascii=False,indent=2),encoding="utf-8")
    return output_path


def main() -> None:
    parser=argparse.ArgumentParser(description="Gera piloto técnico dialogado V3 do Cartola.")
    parser.add_argument("--rodada",type=int,default=21)
    parser.add_argument("--repo-root",default=".")
    parser.add_argument("--output",default="output/piloto_analise_tecnica_dialogada_rodada_21_v3.mp4")
    args=parser.parse_args()
    print(generate(args.rodada,Path(args.repo_root).resolve(),Path(args.output)))


if __name__=="__main__":
    main()
