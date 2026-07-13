from __future__ import annotations

import math
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Canvas sizes optimized for Telegram mobile viewing.
TOP5_SIZE = (1440, 2560)
TEAM_SIZE = (1440, 1920)
RESULT_SIZE = (1440, 1920)

BG_TOP = (5, 15, 30)
BG_BOTTOM = (12, 35, 58)
PANEL = (14, 31, 51)
PANEL_2 = (20, 43, 68)
WHITE = (244, 248, 252)
MUTED = (161, 181, 201)
LINE = (48, 79, 108)
CYAN = (34, 211, 238)
BLUE = (38, 126, 255)
ORANGE = (255, 169, 54)
GREEN = (35, 184, 112)
YELLOW = (250, 204, 78)

POSITION_COLORS = {
    "GOL": (255, 191, 61),
    "LAT": (46, 213, 196),
    "ZAG": (93, 144, 255),
    "MEI": (166, 107, 255),
    "ATA": (255, 93, 118),
    "TEC": (151, 167, 184),
}
POSITION_LABELS = {
    "GOL": "GOLEIROS",
    "LAT": "LATERAIS",
    "ZAG": "ZAGUEIROS",
    "MEI": "MEIAS",
    "ATA": "ATACANTES",
    "TEC": "TÉCNICOS",
}


@dataclass
class RenderOutput:
    files: List[str]
    kind: str
    title: str
    caption: str


def _font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    candidates: List[str] = []
    if weight == "bold":
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
        ])
    elif weight == "semibold":
        candidates.extend([
            "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            "/usr/share/fonts/opentype/inter/InterDisplay-Regular.otf",
        ])
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _clean_markdown(value: Any) -> str:
    text = _safe(value)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _money(value: Any) -> str:
    try:
        return f"C$ {float(str(value).replace(',', '.')):.2f}"
    except Exception:
        return "C$ --"


def _normalize_pos(value: Any) -> str:
    text = _safe(value).upper()
    aliases = {
        "GOLEIRO": "GOL", "G": "GOL",
        "LATERAL": "LAT", "L": "LAT",
        "ZAGUEIRO": "ZAG", "Z": "ZAG",
        "MEIA": "MEI", "M": "MEI",
        "ATACANTE": "ATA", "A": "ATA",
        "TECNICO": "TEC", "TÉCNICO": "TEC", "T": "TEC",
    }
    return aliases.get(text, text[:3])


def _gradient_background(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse(
        (width * 0.50, -height * 0.15, width * 1.15, height * 0.45),
        fill=(0, 150, 255, 28),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def _round(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _shadowed_panel(image: Image.Image, box, radius=28, fill=PANEL, outline=LINE):
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 9, y1 + 12, x2 + 9, y2 + 12), radius=radius, fill=(0, 0, 0, 100))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _brand_header(image: Image.Image, title: str, subtitle: str, badge: str, *, top5: bool = False):
    width, _ = image.size
    draw = ImageDraw.Draw(image)
    logo_box = (70, 54, 190, 174) if top5 else (58, 46, 160, 148)
    _round(draw, logo_box, 30, fill=(10, 55, 90), outline=CYAN, width=4)
    logo_font = _font(44 if top5 else 36, "bold")
    draw.text((logo_box[0] + 30, logo_box[1] + 24), "PS", font=logo_font, fill=WHITE)

    x = logo_box[2] + 28
    draw.text((x, logo_box[1] + 2), "PORTAL", font=_font(28 if top5 else 22), fill=CYAN)
    draw.text((x, logo_box[1] + 35), "SIMONSPORTS", font=_font(48 if top5 else 38, "bold"), fill=WHITE)
    draw.text((x, logo_box[1] + 90), "DADOS • ANÁLISE • CARTOLA", font=_font(20 if top5 else 16), fill=MUTED)

    badge_font = _font(24 if top5 else 20, "semibold")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    bw = bbox[2] - bbox[0] + 52
    _round(draw, (width - bw - 68, 70, width - 68, 128), 26, fill=(17, 63, 96), outline=CYAN, width=2)
    draw.text((width - bw - 42, 83), badge, font=badge_font, fill=WHITE)

    line_y = 210 if top5 else 175
    draw.line((68, line_y, width - 68, line_y), fill=LINE, width=3)
    title_font = _font(64 if top5 else 48, "bold")
    subtitle_font = _font(28 if top5 else 22)
    draw.text((68, line_y + 38), title[:48], font=title_font, fill=WHITE)
    draw.text((70, line_y + 120), subtitle[:100], font=subtitle_font, fill=MUTED)


def _footer(image: Image.Image, y: Optional[int] = None, page: Optional[Tuple[int, int]] = None):
    width, height = image.size
    y = y or height - 105
    draw = ImageDraw.Draw(image)
    draw.line((68, y, width - 68, y), fill=LINE, width=3)
    draw.text((68, y + 26), "@dicascartolaportalsimonsports", font=_font(22), fill=CYAN)
    brand = "PORTAL SIMONSPORTS"
    bbox = draw.textbbox((0, 0), brand, font=_font(22))
    draw.text((width - 68 - (bbox[2] - bbox[0]), y + 26), brand, font=_font(22), fill=MUTED)
    if page:
        p, total = page
        txt = f"{p}/{total}"
        bbox = draw.textbbox((0, 0), txt, font=_font(22, "semibold"))
        draw.text((width // 2 - (bbox[2] - bbox[0]) / 2, y + 26), txt, font=_font(22, "semibold"), fill=WHITE)


def _title_round(dados: Dict[str, Any], default_title: str):
    rodada = _safe(dados.get("rodada") or dados.get("rodada_atual"))
    title = _clean_markdown(dados.get("titulo") or default_title)
    if "atualização" in title.lower() and rodada:
        title = f"TOP 5 • RODADA {rodada}"
    blocos = dados.get("blocos_topo") or []
    subtitle = ""
    if isinstance(blocos, list) and blocos:
        subtitle = _clean_markdown(blocos[0])
    subtitle = subtitle or _clean_markdown(dados.get("status") or dados.get("status_mercado"))
    subtitle = subtitle or "Seleção atualizada pelo Portal SimonSports"
    badge = f"RODADA {rodada}" if rodada else "CARTOLA"
    return title or default_title, subtitle, badge, rodada or "atual"


def _club_badge(draw: ImageDraw.ImageDraw, x: int, y: int, club: str, radius: int, font_size: int, fill=(27, 73, 112)):
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=fill, outline=WHITE, width=3)
    code = _safe(club, "--")[:3].upper()
    font = _font(font_size, "semibold")
    bbox = draw.textbbox((0,0), code, font=font)
    draw.text((x-(bbox[2]-bbox[0])/2, y-(bbox[3]-bbox[1])/2-2), code, font=font, fill=WHITE)


def _top5_groups(items):
    groups = {key: [] for key in POSITION_LABELS}
    for item in items:
        if not isinstance(item, dict):
            continue
        pos = _normalize_pos(item.get("pos") or item.get("posicao"))
        if pos in groups:
            groups[pos].append(item)
    for pos in groups:
        groups[pos] = groups[pos][:5]
    return groups


def _draw_top5_block(image: Image.Image, box, pos: str, items):
    _shadowed_panel(image, box, radius=30, fill=PANEL)
    draw = ImageDraw.Draw(image)
    x1,y1,x2,y2 = box
    accent = POSITION_COLORS[pos]
    draw.rounded_rectangle((x1, y1, x1+14, y2), radius=7, fill=accent)
    draw.text((x1+34, y1+24), POSITION_LABELS[pos], font=_font(34,"bold"), fill=WHITE)
    _round(draw, (x2-102,y1+18,x2-28,y1+64), 21, fill=accent)
    code_font = _font(20,"bold")
    bbox = draw.textbbox((0,0), pos, font=code_font)
    draw.text((x2-65-(bbox[2]-bbox[0])/2, y1+29), pos, font=code_font, fill=(5,16,29))
    row_y = y1+88
    row_h = 88
    for idx in range(1,6):
        yy = row_y+(idx-1)*row_h
        if idx%2==1:
            draw.rounded_rectangle((x1+24,yy,x2-24,yy+76), radius=16, fill=PANEL_2)
        item = items[idx-1] if idx-1 < len(items) else None
        if not item:
            draw.text((x1+38,yy+24), f"{idx:02d}", font=_font(24), fill=MUTED)
            draw.text((x1+116,yy+22), "Sem dado", font=_font(28), fill=MUTED)
            continue
        rank_color = accent if idx<=3 else MUTED
        draw.text((x1+38,yy+22), f"{idx:02d}", font=_font(24,"semibold"), fill=rank_color)
        _club_badge(draw, x1+112, yy+38, _safe(item.get("clube")), 25, 15)
        name = _safe(item.get("nome"),"Jogador")
        if len(name)>19:
            name=name[:18]+"…"
        draw.text((x1+150,yy+14), name, font=_font(27,"semibold"), fill=WHITE)
        club=_safe(item.get("clube"),"--")
        draw.text((x1+152,yy+48), club, font=_font(18), fill=MUTED)
        price=_money(item.get("preco") or item.get("preco_num"))
        pf=_font(24,"semibold")
        bbox=draw.textbbox((0,0),price,font=pf)
        draw.text((x2-34-(bbox[2]-bbox[0]),yy+25),price,font=pf,fill=accent)


def render_top5(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    items = dados.get("lista") or dados.get("jogadores") or []
    groups = _top5_groups(items if isinstance(items,list) else [])
    title,subtitle,badge,rodada = _title_round(dados,"TOP 5 DA RODADA")
    width,height=TOP5_SIZE
    image=_gradient_background(width,height)
    _brand_header(image,title,subtitle,badge,top5=True)
    margin=70
    gap_x=34
    gap_y=34
    top=410
    footer_y=height-115
    usable_w=width-2*margin
    block_w=(usable_w-gap_x)//2
    block_h=(footer_y-top-2*gap_y)//3
    order=["GOL","LAT","ZAG","MEI","ATA","TEC"]
    for i,pos in enumerate(order):
        row=i//2
        col=i%2
        x1=margin+col*(block_w+gap_x)
        y1=top+row*(block_h+gap_y)
        _draw_top5_block(image,(x1,y1,x1+block_w,y1+block_h),pos,groups[pos])
    _footer(image,footer_y)
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    path=str(Path(output_dir)/f"top5_rodada_{rodada}.png")
    image.convert("RGB").save(path,"PNG",optimize=True)
    return RenderOutput([path],"top5",title,f"Top 5 da Rodada {rodada}")


def _extract_team_players(dados: Dict[str, Any]):
    for key in ("jogadores","time","escalacao","lista","atletas"):
        value=dados.get(key)
        if isinstance(value,list) and value:
            return [x for x in value if isinstance(x,dict)]
    return []


def _field(image: Image.Image, box):
    draw=ImageDraw.Draw(image)
    x1,y1,x2,y2=box
    stripe=(y2-y1)//10
    for i in range(10):
        fill=(25,119,74) if i%2==0 else (29,132,81)
        draw.rectangle((x1,y1+i*stripe,x2,y1+(i+1)*stripe),fill=fill)
    draw.rounded_rectangle(box,radius=32,outline=(210,244,222),width=5)
    pad=30
    draw.rectangle((x1+pad,y1+pad,x2-pad,y2-pad),outline=(210,244,222),width=4)
    mid=(y1+y2)//2
    draw.line((x1+pad,mid,x2-pad,mid),fill=(210,244,222),width=4)
    draw.ellipse((image.size[0]//2-92,mid-92,image.size[0]//2+92,mid+92),outline=(210,244,222),width=4)


def _line_positions(count,y,x1,x2):
    if count<=0:return []
    if count==1:return [((x1+x2)//2,y)]
    step=(x2-x1)/(count-1)
    return [(int(x1+i*step),y) for i in range(count)]


def _player_token(image,x,y,player,color,captain=False):
    draw=ImageDraw.Draw(image)
    draw.ellipse((x-46,y-46,x+46,y+46),fill=color,outline=WHITE,width=4)
    club=_safe(player.get("clube"),"--")[:3].upper()
    cf=_font(20,"bold")
    bbox=draw.textbbox((0,0),club,font=cf)
    draw.text((x-(bbox[2]-bbox[0])/2,y-(bbox[3]-bbox[1])/2-3),club,font=cf,fill=WHITE)
    if captain:
        draw.ellipse((x+30,y-52,x+66,y-16),fill=YELLOW,outline=WHITE,width=2)
        draw.text((x+41,y-46),"C",font=_font(16,"bold"),fill=(25,25,25))
    name=_safe(player.get("nome"),"Jogador")
    if len(name)>18:name=name[:17]+"…"
    nf=_font(22,"semibold")
    bbox=draw.textbbox((0,0),name,font=nf)
    label_w=max(178,bbox[2]-bbox[0]+34)
    _round(draw,(x-label_w//2,y+56,x+label_w//2,y+125),18,fill=(7,28,43),outline=(161,212,190),width=2)
    draw.text((x-(bbox[2]-bbox[0])/2,y+65),name,font=nf,fill=WHITE)
    price=_money(player.get("preco") or player.get("preco_num"))
    pf=_font(17)
    pb=draw.textbbox((0,0),price,font=pf)
    draw.text((x-(pb[2]-pb[0])/2,y+96),price,font=pf,fill=(180,240,211))


def render_team(dados: Dict[str, Any], output_dir: str) -> RenderOutput:
    players=_extract_team_players(dados)
    groups={key:[] for key in POSITION_LABELS}
    for p in players:
        pos=_normalize_pos(p.get("pos") or p.get("posicao"))
        if pos in groups:groups[pos].append(p)
    title,subtitle,badge,rodada=_title_round(dados,"TIME DA RODADA")
    kind=_safe(dados.get("tipo_publicacao") or dados.get("tipo") or "time").lower()
    if "econom" in kind:title=f"TIME ECONÔMICO • {badge}"
    elif "intermedi" in kind:title=f"TIME INTERMEDIÁRIO • {badge}"
    elif "pontua" in kind or "ideal" in kind:title=f"TIME PARA PONTUAR • {badge}"
    else:title=f"TIME DA RODADA • {badge}"
    width,height=TEAM_SIZE
    image=_gradient_background(width,height)
    _brand_header(image,title,subtitle,badge)
    draw=ImageDraw.Draw(image)
    total=0.0
    for p in players:
        try: total+=float(str(p.get("preco") or p.get("preco_num") or 0).replace(",","."))
        except: pass
    formation=_safe(dados.get("formacao")) or f"{len(groups['LAT'])+len(groups['ZAG'])}-{len(groups['MEI'])}-{len(groups['ATA'])}"
    _shadowed_panel(image,(58,260,width-58,325),radius=22,fill=(12,38,60))
    draw.text((86,277),f"FORMAÇÃO {formation}",font=_font(22,"semibold"),fill=CYAN)
    draw.text((430,277),f"PATRIMÔNIO {_money(total)}",font=_font(22,"semibold"),fill=ORANGE)
    coach=groups["TEC"][0] if groups["TEC"] else None
    if coach:
        cname=_safe(coach.get("nome"))
        if len(cname)>22:cname=cname[:21]+"…"
        draw.text((890,277),f"TÉC. {cname}",font=_font(22,"semibold"),fill=WHITE)
    field_box=(58,355,width-58,height-145)
    _field(image,field_box)
    x1,y1,x2,y2=field_box
    lines=[
        (groups["ATA"],y1+155,POSITION_COLORS["ATA"]),
        (groups["MEI"],y1+475,POSITION_COLORS["MEI"]),
        (groups["LAT"]+groups["ZAG"],y1+800,POSITION_COLORS["ZAG"]),
        (groups["GOL"][:1],y1+1120,POSITION_COLORS["GOL"]),
    ]
    cap=_safe(dados.get("capitao") or dados.get("capitão")).lower()
    for plist,y,color in lines:
        coords=_line_positions(len(plist),y,x1+150,x2-150)
        for p,(x,yy) in zip(plist,coords):
            pname=_safe(p.get("nome")).lower()
            iscap=bool(p.get("capitao") or p.get("capitão")) or bool(cap and pname==cap)
            _player_token(image,x,yy,p,color,iscap)
    _footer(image,height-105)
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    slug=re.sub(r"[^a-z0-9]+","_",kind).strip("_") or "time"
    path=str(Path(output_dir)/f"{slug}_rodada_{rodada}.png")
    image.convert("RGB").save(path,"PNG",optimize=True)
    return RenderOutput([path],"team",title,title.title())


def _extract_matches(dados):
    for key in ("partidas","jogos","resultados","lista","matches"):
        value=dados.get(key)
        if isinstance(value,list) and value:
            candidates=[x for x in value if isinstance(x,dict)]
            if any(any(k in m for k in ("mandante","visitante","home","away","time_casa","time_fora")) for m in candidates):
                return candidates
    return []


def _match_value(match,*keys,default=""):
    for k in keys:
        if k in match and match.get(k) not in (None,""):return match.get(k)
    return default


def _score(value):
    if value in (None,""):return "–"
    try:return str(int(float(value)))
    except:return _safe(value,"–")


def _abbr(name):
    name=_safe(name,"---")
    cleaned=re.sub(r"[^A-Za-zÀ-ÿ0-9 ]","",name).strip()
    if len(cleaned)<=4:return cleaned.upper()
    words=[w for w in cleaned.split() if w]
    if len(words)>=2:return "".join(w[0] for w in words[:3]).upper()
    return cleaned[:3].upper()


def _draw_match_card(image,box,match,index):
    _shadowed_panel(image,box,radius=28,fill=PANEL)
    draw=ImageDraw.Draw(image)
    x1,y1,x2,y2=box
    home=_safe(_match_value(match,"mandante","home","time_casa","casa","equipe_mandante"),"Mandante")
    away=_safe(_match_value(match,"visitante","away","time_fora","fora","equipe_visitante"),"Visitante")
    hs=_score(_match_value(match,"placar_mandante","gols_mandante","home_score","gm","placar_casa",default=None))
    as_=_score(_match_value(match,"placar_visitante","gols_visitante","away_score","gv","placar_fora",default=None))
    status=_clean_markdown(_match_value(match,"status","situacao","minuto","fase",default="Programado"))
    dt=_clean_markdown(_match_value(match,"data_hora","data","horario","inicio",default=""))
    draw.text((x1+32,y1+22),f"JOGO {index:02d}",font=_font(19,"semibold"),fill=MUTED)
    status_color=GREEN if any(t in status.lower() for t in ("encerr","fim","final")) else ORANGE if any(t in status.lower() for t in ("andamento","ao vivo","live","interval")) else BLUE
    _round(draw,(x2-230,y1+18,x2-30,y1+66),22,fill=status_color)
    sf=_font(18,"bold")
    st=status[:17].upper()
    sb=draw.textbbox((0,0),st,font=sf)
    draw.text((x2-130-(sb[2]-sb[0])/2,y1+31),st,font=sf,fill=(5,20,30))
    _club_badge(draw,x1+86,y1+138,_abbr(home),38,18,fill=(31,89,138))
    _club_badge(draw,x2-86,y1+138,_abbr(away),38,18,fill=(31,89,138))
    hf=_font(28,"semibold")
    hd=home if len(home)<=22 else home[:21]+"…"
    ad=away if len(away)<=22 else away[:21]+"…"
    draw.text((x1+142,y1+102),hd,font=hf,fill=WHITE)
    ab=draw.textbbox((0,0),ad,font=hf)
    draw.text((x2-142-(ab[2]-ab[0]),y1+102),ad,font=hf,fill=WHITE)
    score=f"{hs}  ×  {as_}"
    scf=_font(58,"bold")
    scb=draw.textbbox((0,0),score,font=scf)
    _round(draw,(image.size[0]//2-145,y1+80,image.size[0]//2+145,y1+178),26,fill=(5,24,41),outline=LINE,width=2)
    draw.text((image.size[0]//2-(scb[2]-scb[0])/2,y1+93),score,font=scf,fill=WHITE)
    if dt:
        df=_font(18)
        short=dt[:52]
        db=draw.textbbox((0,0),short,font=df)
        draw.text((image.size[0]//2-(db[2]-db[0])/2,y1+200),short,font=df,fill=MUTED)


def render_results(dados: Dict[str,Any], output_dir: str) -> RenderOutput:
    matches=_extract_matches(dados)
    title,subtitle,badge,rodada=_title_round(dados,"RESULTADOS DA RODADA")
    if not matches:
        matches=[{"mandante":"Aguardando","visitante":"dados das partidas","status":"Sem resultados"}]
    width,height=RESULT_SIZE
    per_page=4
    pages=max(1,math.ceil(len(matches)/per_page))
    files=[]
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    for page in range(pages):
        image=_gradient_background(width,height)
        _brand_header(image,title,subtitle,badge)
        y=300
        for idx,m in enumerate(matches[page*per_page:(page+1)*per_page],start=page*per_page+1):
            _draw_match_card(image,(58,y,width-58,y+280),m,idx)
            y+=315
        _footer(image,height-105,(page+1,pages))
        path=str(Path(output_dir)/f"resultados_rodada_{rodada}_p{page+1}.png")
        image.convert("RGB").save(path,"PNG",optimize=True)
        files.append(path)
    return RenderOutput(files,"results",title,f"Resultados da Rodada {rodada}")


def render_bulletin(dados: Dict[str,Any], output_dir: str) -> RenderOutput:
    title,subtitle,badge,rodada=_title_round(dados,"BOLETIM CARTOLA")
    width,height=RESULT_SIZE
    image=_gradient_background(width,height)
    _brand_header(image,title,subtitle,badge)
    _shadowed_panel(image,(58,300,width-58,height-145),radius=30,fill=PANEL)
    draw=ImageDraw.Draw(image)
    draw.text((92,340),"INFORMAÇÕES DA PUBLICAÇÃO",font=_font(32,"bold"),fill=CYAN)
    msg=_safe(dados.get("mensagem_oficial") or dados.get("mensagem") or dados.get("texto"))
    lines=[]
    for raw in msg.splitlines():
        clean=_clean_markdown(raw)
        if clean and "t.me/" not in clean and not clean.startswith("http"):lines.append(clean)
    y=420
    for line in lines[:20]:
        for sub in textwrap.wrap(line,width=54)[:2]:
            draw.ellipse((94,y+11,108,y+25),fill=ORANGE)
            draw.text((132,y),sub[:80],font=_font(26),fill=WHITE)
            y+=46
        y+=16
        if y>height-220:break
    if not lines:
        draw.text((92,440),"Publicação recebida sem dados estruturados.",font=_font(28),fill=MUTED)
    _footer(image,height-105)
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    path=str(Path(output_dir)/f"boletim_{rodada}.png")
    image.convert("RGB").save(path,"PNG",optimize=True)
    return RenderOutput([path],"bulletin",title,"Boletim Cartola")


def detect_kind(dados: Dict[str,Any]) -> str:
    kind=_safe(dados.get("tipo_publicacao") or dados.get("tipo") or dados.get("contexto")).lower()
    if any(t in kind for t in ("resultado","placar","partida","live")):return "results"
    if any(t in kind for t in ("time","campinho","escalacao","escalação","econom","intermedi","pontua","ideal")):return "team"
    if "top5" in kind or "top 5" in kind:return "top5"
    if _extract_matches(dados):return "results"
    if any(k in dados for k in ("jogadores","time","escalacao","atletas")):return "team"
    items=dados.get("lista")
    if isinstance(items,list) and items:
        counts={pos:0 for pos in POSITION_LABELS}
        for item in items:
            if isinstance(item,dict):
                pos=_normalize_pos(item.get("pos") or item.get("posicao"))
                if pos in counts:counts[pos]+=1
        if max(counts.values() or [0])>=4:return "top5"
        if any(counts.values()):return "team"
    return "bulletin"


def render_publication(dados: Dict[str,Any], output_dir: str="output") -> RenderOutput:
    kind=detect_kind(dados)
    if kind=="top5":return render_top5(dados,output_dir)
    if kind=="team":return render_team(dados,output_dir)
    if kind=="results":return render_results(dados,output_dir)
    return render_bulletin(dados,output_dir)
