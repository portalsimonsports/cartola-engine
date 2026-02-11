import json
import os
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DATA_TIMES = os.path.join(BASE_DIR, "data", "times_atual.json")
DATA_TOP5 = os.path.join(BASE_DIR, "data", "top5_atual.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)

def carregar_json(path):
    if not os.path.exists(path):
        print(f"Arquivo não encontrado: {path}")
        return None
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def gerar_imagem_top5(dados):
    img = Image.new("RGB", (1080, 1080), "#111827")
    draw = ImageDraw.Draw(img)

    y = 200
    for item in dados["dados"]:
        texto = f'{item["POS"]} - {item["NOME"]} ({item["CLUBE"]})'
        draw.text((150, y), texto, fill="white")
        y += 80

    img.save(os.path.join(OUTPUT_DIR, "top5.png"))

def main():
    top5 = carregar_json(DATA_TOP5)
    if top5:
        gerar_imagem_top5(top5)

if __name__ == "__main__":
    main()