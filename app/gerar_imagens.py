import json
import os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DATA_TIMES = os.path.join(BASE_DIR, "data", "times_atual.json")
DATA_TOP5 = os.path.join(BASE_DIR, "data", "top5_atual.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ================================
# UTIL
# ================================

def carregar_json(path):
    if not os.path.exists(path):
        print(f"Arquivo não encontrado: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def carregar_font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


# ================================
# TOP 5 MODERNO
# ================================

def gerar_imagem_top5(dados):
    img = Image.new("RGB", (1080, 1080), "#111827")
    draw = ImageDraw.Draw(img)

    titulo_font = carregar_font(70)
    nome_font = carregar_font(45)

    draw.text((540, 120), "TOP 5 DA RODADA", fill="white", anchor="mm", font=titulo_font)

    y = 250
    for i, item in enumerate(dados["dados"], start=1):
        texto = f'{i}. {item["POS"]} - {item["NOME"]} ({item["CLUBE"]})'
        draw.text((540, y), texto, fill="white", anchor="mm", font=nome_font)
        y += 110

    img.save(os.path.join(OUTPUT_DIR, "top5.png"))
    print("Top5 gerado com sucesso")


# ================================
# TIMES EM FORMATO CAMPINHO
# ================================

def gerar_imagens_times(dados):
    times = defaultdict(list)

    for item in dados["dados"]:
        times[item["TIPO"]].append(item)

    for tipo, jogadores in times.items():

        img = Image.new("RGB", (1080, 1920), "#0e2a1f")
        draw = ImageDraw.Draw(img)

        titulo_font = carregar_font(70)
        nome_font = carregar_font(40)

        draw.text((540, 120), f"TIME {tipo}", fill="white", anchor="mm", font=titulo_font)

        titulares = [j for j in jogadores if j["STATUS"] == "TITULAR"]

        # Coordenadas simulando campinho
        posicoes = {
            "GOL": [(540, 400)],
            "LAT": [(250, 650), (830, 650)],
            "ZAG": [(360, 800), (720, 800)],
            "MEI": [(200, 1000), (540, 1000), (880, 1000)],
            "ATA": [(300, 1250), (780, 1250)],
            "TEC": [(540, 1500)]
        }

        contador_pos = defaultdict(int)

        for jogador in titulares:
            pos = jogador["POS"]
            nome = jogador["NOME"]

            if pos in posicoes:
                idx = contador_pos[pos]
                if idx < len(posicoes[pos]):
                    x, y = posicoes[pos][idx]
                    draw.text((x, y), nome, fill="white", anchor="mm", font=nome_font)
                    contador_pos[pos] += 1

        caminho = os.path.join(OUTPUT_DIR, f"time_{tipo.lower()}.png")
        img.save(caminho)
        print(f"Time {tipo} gerado com sucesso")


# ================================
# MAIN
# ================================

def main():

    top5 = carregar_json(DATA_TOP5)
    if top5:
        gerar_imagem_top5(top5)

    times = carregar_json(DATA_TIMES)
    if times:
        gerar_imagens_times(times)


if __name__ == "__main__":
    main()