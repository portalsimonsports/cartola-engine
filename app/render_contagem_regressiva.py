"""Card aprovado de contagem regressiva — Portal SimonSports.

Uso: python app/render_contagem_regressiva.py --ano 2027 --dias 95 --data 27/01/2027 --saida /tmp/contagem.png
Não publica nada; apenas renderiza o PNG a partir da arte-mestre aprovada.
"""
import argparse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).resolve().parents[1] / "assets" / "contagem_regressiva_modelo_aprovado.jpg"


def font(size):
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError("Fonte profissional não disponível")


def centered(draw, text, center_x, y, max_width, start_size, fill, stroke=0, stroke_fill=None):
    size = start_size
    while size >= 20:
        ft = font(size)
        box = draw.textbbox((0, 0), text, font=ft, stroke_width=stroke)
        if box[2] - box[0] <= max_width:
            break
        size -= 4
    x = round(center_x - (box[2] - box[0]) / 2 - box[0])
    draw.text((x, y), text, font=ft, fill=fill, stroke_width=stroke,
              stroke_fill=stroke_fill or fill)
    return (x, y, ft)


def render(ano, dias, data, output):
    if not BASE.exists():
        raise RuntimeError("Arte-mestre aprovada ausente: " + str(BASE))
    dt = datetime.strptime(data, "%d/%m/%Y")
    if dt.year != ano or dias <= 0 or dias > 400:
        raise ValueError("Ano, data ou contagem inválidos")
    im = Image.open(BASE).convert("RGBA")
    if im.size != (1254, 1254):
        raise RuntimeError("Dimensão inesperada da arte-mestre")
    draw = ImageDraw.Draw(im)
    # Apenas os três campos dinâmicos. Todo o restante é a arte aprovada.
    centered(draw, str(ano), 874, 238, 235, 49, (15, 149, 241))

    # Halo dourado discreto sob o número, preservando o troféu original.
    mask = Image.new("RGBA", im.size, (0, 0, 0, 0))
    glow = ImageDraw.Draw(mask)
    x, y, ft = centered(glow, str(dias), 627, 360, 700, 420,
                        (255, 190, 20, 200), 7, (255, 175, 0, 180))
    im = Image.alpha_composite(im, mask.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(im)
    draw.text((x, y), str(dias), font=ft, fill=(255, 202, 54),
              stroke_width=9, stroke_fill=(99, 48, 0))
    draw.text((x, y), str(dias), font=ft, fill=(255, 208, 66),
              stroke_width=3, stroke_fill=(255, 246, 179))
    centered(draw, data, 815, 1045, 360, 53, (245, 247, 254))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, format="PNG", optimize=True)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--dias", type=int, required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()
    print(render(args.ano, args.dias, args.data, args.saida))


if __name__ == "__main__":
    main()
