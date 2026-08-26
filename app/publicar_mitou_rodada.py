from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from gerar_resultados_telegram import enviar_foto

PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output").strip() or "output")
LIMITE = 100.0

BG = (3, 13, 31)
NAVY = (5, 20, 47)
BLUE = (0, 112, 255)
BLUE2 = (18, 75, 173)
ORANGE = (255, 150, 0)
GOLD = (255, 190, 25)
WHITE = (245, 247, 250)
GREEN = (33, 122, 53)
GREEN2 = (24, 88, 40)
MUTED = (177, 194, 218)
BLACK = (4, 8, 14)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def fnt(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def norm(v: Any) -> str:
    s = str(v or "").strip().upper()
    repl = str.maketrans("ÁÀÃÂÉÊÍÓÔÕÚÇ", "AAAAEEIOOOUC")
    return s.translate(repl)


def num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return 0.0


def materializar_google() -> None:
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        Path(GOOGLE_APPLICATION_CREDENTIALS).write_text(
            json.dumps(json.loads(GOOGLE_SERVICE_ACCOUNT_JSON), ensure_ascii=False),
            encoding="utf-8",
        )


def sheets_service():
    materializar_google()
    creds = Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def values(sheet: str) -> List[List[Any]]:
    if not PLANILHA_ID:
        raise RuntimeError("PLANILHA_ID não definido")
    res = sheets_service().spreadsheets().values().get(
        spreadsheetId=PLANILHA_ID,
        range=f"'{sheet}'!A:Z",
    ).execute()
    return res.get("values", [])


def rows_by_header(data: List[List[Any]]) -> Tuple[Dict[str, int], List[List[Any]]]:
    if not data:
        return {}, []
    h = {norm(v): i for i, v in enumerate(data[0])}
    return h, data[1:]


def getv(row: List[Any], h: Dict[str, int], *names: str) -> Any:
    for name in names:
        i = h.get(norm(name), -1)
        if i >= 0 and i < len(row):
            return row[i]
    return ""


def equipes_mitadas() -> List[Dict[str, Any]]:
    h, rows = rows_by_header(values("HIST_TIMES"))
    if not h:
        raise RuntimeError("HIST_TIMES sem cabeçalho")
    melhor: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        rodada = int(num(getv(row, h, "RODADA")))
        if rodada <= 0:
            continue
        tipo = norm(getv(row, h, "TIPO", "ORIGEM"))
        pontos = num(getv(row, h, "PONTOS_TOTAL", "PONTOS COM C", "PONTOS_COM_C", "PONTOS"))
        if pontos < LIMITE:
            continue
        item = {
            "rodada": rodada,
            "tipo": tipo,
            "pontos": pontos,
            "capitao": str(getv(row, h, "CAPITAO", "CAPITÃO") or "").strip(),
            "esquema": str(getv(row, h, "ESQUEMA") or "").strip(),
        }
        if rodada not in melhor or pontos > melhor[rodada]["pontos"]:
            melhor[rodada] = item
    return [melhor[k] for k in sorted(melhor)]


def jogadores(rodada: int, tipo: str) -> List[Dict[str, Any]]:
    h, rows = rows_by_header(values("HIST_JOGADORES"))
    origem_alvo = "TIME_" + tipo.replace("TIME_", "")
    out = []
    for row in rows:
        if int(num(getv(row, h, "RODADA"))) != rodada:
            continue
        origem = norm(getv(row, h, "ORIGEM", "TIPO"))
        if origem != origem_alvo:
            continue
        out.append({
            "pos": norm(getv(row, h, "POS", "POSICAO", "POSIÇÃO")),
            "nome": str(getv(row, h, "APELIDO", "NOME") or "").strip(),
            "pontos": getv(row, h, "PONTOS", "PTS"),
            "status": norm(getv(row, h, "STATUS")),
        })
    return out


def nome_modelo(tipo: str) -> str:
    t = norm(tipo).replace("TIME_", "")
    return {
        "ECONOMICO": "TIME ECONÔMICO",
        "INTERMEDIARIO": "TIME INTERMEDIÁRIO",
        "PONTUACAO": "TIME PONTUAÇÃO",
    }.get(t, t.replace("_", " "))


def rounded(draw: ImageDraw.ImageDraw, box, radius=20, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_center(draw, xy, text, font, fill):
    x, y = xy
    b = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (b[2]-b[0])/2, y), text, font=font, fill=fill)


def render_card(item: Dict[str, Any], players: List[Dict[str, Any]]) -> Path:
    W, H = 1080, 1350
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # Fundo esportivo
    for y in range(H):
        ratio = y / H
        c = (int(BG[0] + 5*ratio), int(BG[1] + 12*ratio), int(BG[2] + 20*ratio))
        d.line((0, y, W, y), fill=c)
    for x in range(-200, W, 150):
        d.line((x, 0, x+650, H), fill=(8, 31, 65), width=2)

    # Branding
    d.text((55, 35), "PORTAL", font=fnt(24, True), fill=WHITE)
    d.text((55, 62), "SIMON", font=fnt(42, True), fill=WHITE)
    d.text((205, 62), "SPORTS", font=fnt(42, True), fill=BLUE)
    d.text((57, 108), "CARTOLA • DICAS • ANÁLISES", font=fnt(18), fill=MUTED)

    # Título
    text_center(d, (W/2, 130), "MITOU", fnt(92, True), WHITE)
    text_center(d, (W/2, 220), "NA RODADA", fnt(72, True), ORANGE)

    modelo = nome_modelo(item["tipo"])
    rounded(d, (250, 310, 830, 365), 18, NAVY, BLUE, 3)
    text_center(d, (540, 321), f"{modelo} • RODADA {item['rodada']}", fnt(28, True), WHITE)

    # Score e pergunta
    d.text((55, 405), "VOCÊ FEZ", font=fnt(30, True), fill=WHITE)
    d.text((55, 440), "QUANTOS", font=fnt(46, True), fill=ORANGE)
    d.text((55, 490), "PONTOS?", font=fnt(42, True), fill=WHITE)

    rounded(d, (45, 555, 330, 755), 24, BLACK, ORANGE, 4)
    score_txt = f"{item['pontos']:.2f}".replace(".", ",")
    text_center(d, (187, 590), score_txt, fnt(62, True), WHITE)
    text_center(d, (187, 675), "PONTUAÇÃO FINAL", fnt(23, True), GOLD)

    tit = [p for p in players if p["status"] != "RESERVA"]
    res = [p for p in players if p["status"] == "RESERVA"]
    count_pts = sum(1 for p in tit if str(p.get("pontos", "")).strip() != "")
    rounded(d, (45, 775, 330, 875), 20, NAVY, BLUE, 3)
    text_center(d, (187, 790), f"{count_pts}/{len(tit) or 12}", fnt(46, True), WHITE)
    text_center(d, (187, 842), "ATLETAS PONTUADOS", fnt(17, True), MUTED)

    # Campo
    fx1, fy1, fx2, fy2 = 365, 410, 1030, 1015
    d.rounded_rectangle((fx1, fy1, fx2, fy2), radius=28, fill=GREEN2, outline=BLUE, width=4)
    d.rectangle((fx1+18, fy1+18, fx2-18, fy2-18), outline=(220, 245, 220), width=3)
    d.line((fx1+18, (fy1+fy2)//2, fx2-18, (fy1+fy2)//2), fill=(220,245,220), width=2)
    d.ellipse((650, 680, 745, 775), outline=(220,245,220), width=2)

    pos_rows = {
        "GOL": [(700, 905)],
        "LAT": [(470, 785), (920, 785)],
        "ZAG": [(600, 785), (800, 785)],
        "MEI": [(520, 620), (700, 620), (885, 620), (610, 620), (800, 620)],
        "ATA": [(525, 470), (700, 470), (885, 470)],
    }
    counters = {k: 0 for k in pos_rows}

    def card(x, y, p):
        w, h = 145, 110
        rounded(d, (x-w//2, y-h//2, x+w//2, y+h//2), 15, (8,15,24), ORANGE, 2)
        pos = p.get("pos") or ""
        text_center(d, (x, y-47), pos, fnt(15, True), GOLD)
        name = (p.get("nome") or "").upper()
        if len(name) > 14:
            name = name[:13] + "…"
        text_center(d, (x, y-16), name, fnt(17, True), WHITE)
        pts = str(p.get("pontos", "")).strip()
        if pts:
            try:
                pts = f"{num(pts):.2f}".replace(".", ",")
            except Exception:
                pass
        text_center(d, (x, y+21), pts or "—", fnt(21, True), ORANGE)

    tecnicos = []
    for p in tit:
        pos = p.get("pos") or ""
        if pos == "TEC":
            tecnicos.append(p)
            continue
        slots = pos_rows.get(pos)
        if not slots:
            continue
        idx = counters.get(pos, 0)
        if idx >= len(slots):
            continue
        x, y = slots[idx]
        counters[pos] = idx + 1
        card(x, y, p)

    # Capitão / técnico / reservas
    cap = item.get("capitao") or "—"
    rounded(d, (45, 900, 330, 980), 18, NAVY, ORANGE, 3)
    d.text((65, 918), "CAPITÃO:", font=fnt(18, True), fill=GOLD)
    d.text((65, 944), str(cap).upper(), font=fnt(28, True), fill=WHITE)

    tec = tecnicos[0]["nome"] if tecnicos else "—"
    rounded(d, (45, 995, 330, 1075), 18, NAVY, BLUE, 3)
    d.text((65, 1012), "TÉCNICO", font=fnt(17, True), fill=MUTED)
    d.text((65, 1038), str(tec).upper()[:19], font=fnt(24, True), fill=WHITE)

    rounded(d, (365, 1035, 1030, 1130), 18, NAVY, BLUE, 3)
    d.text((390, 1050), "RESERVAS", font=fnt(20, True), fill=BLUE)
    if res:
        nomes = " • ".join((p.get("nome") or "").upper() for p in res[:5])
        d.text((390, 1085), nomes[:62], font=fnt(18, True), fill=WHITE)
    else:
        d.text((390, 1085), "SEM RESERVAS REGISTRADAS", font=fnt(18, True), fill=MUTED)

    # Rodapé
    d.line((40, 1170, 1040, 1170), fill=ORANGE, width=3)
    d.text((55, 1200), "PORTAL", font=fnt(22, True), fill=WHITE)
    d.text((55, 1230), "SIMON", font=fnt(38, True), fill=WHITE)
    d.text((195, 1230), "SPORTS", font=fnt(38, True), fill=BLUE)
    d.text((540, 1210), "SÓ VAI CURTIR QUEM MITOU!", font=fnt(30, True), fill=ORANGE)
    d.text((540, 1260), "@dicascartolaportalsimonsports", font=fnt(20), fill=WHITE)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"mitou_na_rodada_{item['rodada']}.png"
    im.save(path, quality=95)
    return path


def flag_path(rodada: int) -> Path:
    return Path("data/flags") / f"mitou_rodada_{rodada}.publicado.json"


def publicar(item: Dict[str, Any], force: bool = False) -> bool:
    fp = flag_path(item["rodada"])
    if fp.exists() and not force:
        print(f"R{item['rodada']} já possui flag de Mitou. Pulando.")
        return False
    ps = jogadores(item["rodada"], item["tipo"])
    img = render_card(item, ps)
    caption = (
        f"🏆 <b>MITOU NA RODADA {item['rodada']}</b>\n"
        f"{nome_modelo(item['tipo']).title()} • {item['pontos']:.2f} pontos\n\n"
        f"📡 Portal SimonSports\n"
        f"🔗 @dicascartolaportalsimonsports"
    )
    enviar_foto(str(img), caption)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps({
        "rodada": item["rodada"],
        "tipo": item["tipo"],
        "pontos": round(item["pontos"], 2),
        "telegram_enviado": True,
        "publicado_em": datetime.now(timezone.utc).isoformat(),
        "modelo": "MITOU_NA_RODADA_V1_APROVADO",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MITOU R{item['rodada']} enviado: {item['tipo']} {item['pontos']:.2f}")
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rodada", type=int, default=0)
    p.add_argument("--retroativo", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    todos = equipes_mitadas()
    if args.rodada:
        todos = [x for x in todos if x["rodada"] == args.rodada]
    elif not args.retroativo:
        if todos:
            todos = [todos[-1]]

    publicados = 0
    for item in todos:
        if publicar(item, args.force):
            publicados += 1
    print(f"Publicações Mitou concluídas: {publicados}")


if __name__ == "__main__":
    main()
