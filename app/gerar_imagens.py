import json
import os
from PIL import Image, ImageDraw, ImageFont
import pandas as pd

def carregar_json(caminho):
    if not os.path.exists(caminho):
        return None, None
    with open(caminho) as f:
        data = json.load(f)
    if not data or "dados" not in data:
        return None, None
    return data["rodada"], pd.DataFrame(data["dados"])

def detectar_formacao(df):
    cont = df["POS"].value_counts()
    defesa = cont.get("LAT",0) + cont.get("ZAG",0)
    meio = cont.get("MEI",0)
    ataque = cont.get("ATA",0)
    return f"{defesa}-{meio}-{ataque}"

def gerar_time(df, rodada, tipo):
    titulares = df[(df["POS"]!="TEC") & (df["POS"]!="RES")]
    tecnico = df[df["POS"]=="TEC"]
    reservas = df[df["POS"]=="RES"]

    valor = round(titulares["PRECO"].sum(),2)
    formacao = detectar_formacao(titulares)

    largura, altura = 1080, 1350
    img = Image.new("RGB",(largura,altura),(20,90,40))
    draw = ImageDraw.Draw(img)

    font = ImageFont.load_default()

    draw.text((largura//2-200,40),f"{tipo} — RODADA {rodada}",fill="white",font=font)
    draw.text((largura//2-200,80),f"Esquema: {formacao} | Valor: C$ {valor}",fill="yellow",font=font)

    y = 200

    for _,r in titulares.iterrows():
        draw.text((200,y),f"{r['POS']} - {r['NOME']}",fill="white",font=font)
        y += 60

    if not tecnico.empty:
        y += 30
        r = tecnico.iloc[0]
        draw.text((200,y),f"TÉCNICO: {r['NOME']}",fill="cyan",font=font)
        y += 60

    if not reservas.empty:
        draw.text((200,y),"RESERVAS:",fill="white",font=font)
        y += 40
        for _,r in reservas.iterrows():
            draw.text((220,y),f"{r['POS']} - {r['NOME']}",fill="white",font=font)
            y += 50

    os.makedirs("output",exist_ok=True)
    img.save(f"output/{tipo}_rodada_{rodada}.png")

def processar(caminho):
    rodada, df = carregar_json(caminho)
    if df is None:
        return
    tipos = df["TIPO"].drop_duplicates()
    for tipo in tipos:
        gerar_time(df[df["TIPO"]==tipo], rodada, tipo)

if __name__ == "__main__":
    processar("data/times_atual.json")
    processar("data/top5_atual.json")
