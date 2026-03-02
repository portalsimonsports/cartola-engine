import json
import os
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
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
# TOP 5
# ================================

def gerar_imagem_top5():

    path = os.path.join(DATA_DIR, "top5_atual.json")
    dados = carregar_json(path)
    if not dados:
        return

    lista = dados.get("dados", []) if isinstance(dados, dict) else dados

    if not lista:
        print("Top5 vazio")
        return

    img = Image.new("RGB", (1080, 1080), "#111827")
    draw = ImageDraw.Draw(img)

    titulo_font = carregar_font(70)
    nome_font = carregar_font(45)

    draw.text((540, 120), "TOP 5 DA RODADA", fill="white", anchor="mm", font=titulo_font)

    y = 250
    for i, item in enumerate(lista[:5], start=1):
        pos = item.get("POS", "")
        nome = item.get("NOME", "")
        clube = item.get("CLUBE", "")
        texto = f"{i}. {pos} - {nome} ({clube})"
        draw.text((540, y), texto, fill="white", anchor="mm", font=nome_font)
        y += 110

    img.save(os.path.join(OUTPUT_DIR, "top5.png"))
    print("Top5 gerado com sucesso")


# ================================
# TIMES (1 ARQUIVO = 1 IMAGEM)
# ================================

def gerar_imagem_time(nome_arquivo, titulo):

    path = os.path.join(DATA_DIR, nome_arquivo)
    dados = carregar_json(path)
    if not dados:
        return

    lista = dados.get("dados", []) if isinstance(dados, dict) else dados

    if not lista:
        print(f"{nome_arquivo} vazio")
        return

    img = Image.new("RGB", (1080, 1920), "#0e2a1f")
    draw = ImageDraw.Draw(img)

    titulo_font = carregar_font(70)
    nome_font = carregar_font(40)

    draw.text((540, 120), titulo, fill="white", anchor="mm", font=titulo_font)

    titulares = [j for j in lista if j.get("STATUS") == "TITULAR"]

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
        pos = jogador.get("POS")
        nome = jogador.get("NOME")

        if pos in posicoes:
            idx = contador_pos[pos]
            if idx < len(posicoes[pos]):
                x, y = posicoes[pos][idx]
                draw.text((x, y), nome, fill="white", anchor="mm", font=nome_font)
                contador_pos[pos] += 1

    nome_saida = nome_arquivo.replace(".json", ".png")
    img.save(os.path.join(OUTPUT_DIR, nome_saida))
    print(f"{titulo} gerado com sucesso")


# ================================
# MAIN
# ================================

def main():

    print("Iniciando geração de imagens...")

    gerar_imagem_top5()

    gerar_imagem_time("times_atual_economico.json", "TIME ECONÔMICO")
    gerar_imagem_time("times_atual_intermediario.json", "TIME INTERMEDIÁRIO")
    gerar_imagem_time("times_atual_pontuacao.json", "TIME PONTUAÇÃO")

    print("Processo finalizado.")


if __name__ == "__main__":
    main()