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


VERSION = "cartola_dialogo_tecnico_v2_2026_07_30"
WIDTH = base.WIDTH
HEIGHT = base.HEIGHT
CARD_W = 660
CARD_H = 825


@dataclass(frozen=True)
class TechnicalSegment:
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
    """Impede leitura de C$ como dólar canadense em qualquer roteiro futuro."""
    cleaned = re.sub(r"\bC\s*\$\s*", "", safe(text), flags=re.IGNORECASE)
    cleaned = re.sub(r"d[oó]lar(?:es)? canadense(?:s)?", "cartoletas", cleaned, flags=re.IGNORECASE)
    return cleaned


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_center(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, font, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) / 2
    y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


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


def gradient() -> Image.Image:
    image = Image.new("RGB", (CARD_W, CARD_H), base.BG)
    pixels = image.load()
    for y in range(CARD_H):
        for x in range(CARD_W):
            glow = max(0.0, 1.0 - (((x - 520) ** 2 + (y - 120) ** 2) ** 0.5) / 650)
            pixels[x, y] = (
                int(2 + 3 * glow),
                int(12 + 25 * glow),
                int(27 + 48 * glow),
            )
    return image


def header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((30, 25), "PS  PORTAL SIMONSPORTS", font=base.font(24, True), fill=base.WHITE)
    draw.text((30, 61), "CARTOLA • DADOS • ANÁLISE", font=base.font(14, True), fill=base.SILVER)
    draw.line((30, 98, 630, 98), fill=base.LINE, width=2)
    title_font = base.font(32, True)
    draw.text((30, 122), title, font=title_font, fill=(32, 196, 255))
    for index, line in enumerate(wrap(draw, subtitle, 600, base.font(19))[:2]):
        draw.text((30, 166 + index * 27), line, font=base.font(19), fill=base.SILVER)


def metric_card(
    title: str,
    subtitle: str,
    player: Dict[str, Any],
    output: Path,
    insight: str,
    keys: Sequence[Tuple[str, str, float]],
) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    header(draw, title, subtitle)

    name = safe(player.get("nome"), title)
    price = cartoletas(player.get("preco"))
    rounded(draw, (28, 225, 632, 315), 22, (5, 27, 52), (32, 196, 255), 2)
    draw.text((50, 242), name.upper(), font=base.font(31, True), fill=base.WHITE)
    draw.text((50, 281), price, font=base.font(20, True), fill=(255, 190, 55))

    y = 350
    palette = [(32, 196, 255), (181, 86, 255), (255, 190, 55), (53, 210, 122)]
    for index, (label, display, normalized) in enumerate(keys):
        color = palette[index % len(palette)]
        draw.text((48, y), label.upper(), font=base.font(19, True), fill=base.SILVER)
        draw.text((500, y - 2), display, font=base.font(22, True), fill=color, anchor="ra")
        rounded(draw, (48, y + 34, 612, y + 60), 13, (8, 28, 50), (23, 63, 94), 1)
        width = int(558 * max(0.025, min(1.0, normalized)))
        rounded(draw, (51, y + 37, 51 + width, y + 57), 10, color)
        y += 100

    rounded(draw, (35, 670, 625, 790), 22, (4, 20, 39), (181, 86, 255), 2)
    insight_font = base.font(18, True)
    for index, line in enumerate(wrap(draw, insight, 540, insight_font)[:4]):
        draw.text((60, 690 + index * 25), line, font=insight_font, fill=base.WHITE)
    image.save(output, "PNG", optimize=True)


def comparison_card(title: str, rows: List[Dict[str, Any]], output: Path, note: str) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    header(draw, title, "Comparação dos indicadores utilizados pelo modelo.")
    y = 230
    for index, row in enumerate(rows):
        color = [(32, 196, 255), (255, 190, 55), (181, 86, 255), (53, 210, 122)][index % 4]
        rounded(draw, (28, y, 632, y + 112), 22, (5, 25, 47), color, 2)
        draw.text((48, y + 18), safe(row["nome"]).upper(), font=base.font(23, True), fill=base.WHITE)
        draw.text((48, y + 54), f"Últimas 5: {number(row['media_ult5'])} pts", font=base.font(18, True), fill=color)
        draw.text((324, y + 54), f"Prob. 8+: {percent(row['prob_8'])}", font=base.font(18, True), fill=base.SILVER)
        draw.text((48, y + 82), f"Preço: {cartoletas(row['preco'])}", font=base.font(17), fill=base.SILVER)
        y += 128

    rounded(draw, (35, 680, 625, 790), 22, (4, 20, 39), (32, 196, 255), 2)
    for index, line in enumerate(wrap(draw, note, 540, base.font(18, True))[:4]):
        draw.text((60, 700 + index * 24), line, font=base.font(18, True), fill=base.WHITE)
    image.save(output, "PNG", optimize=True)


def methodology_card(output: Path) -> None:
    image = gradient()
    draw = ImageDraw.Draw(image)
    header(draw, "COMO A ANÁLISE É CONSTRUÍDA", "O vídeo não apenas lê a escalação: ele interpreta os sinais do modelo.")
    items = [
        ("1", "FORMA RECENTE", "Média das últimas cinco atuações."),
        ("2", "EXPECTATIVA", "Média esperada e probabilidades de 6 e 8 pontos."),
        ("3", "CONTEXTO", "Casa ou fora, fator do confronto e preço."),
        ("4", "RISCO", "Variância, confiança e divergências entre métricas."),
    ]
    y = 235
    colors = [(32, 196, 255), (181, 86, 255), (255, 190, 55), (53, 210, 122)]
    for (number_value, title, desc), color in zip(items, colors):
        rounded(draw, (35, y, 625, y + 112), 22, (5, 24, 45), color, 2)
        rounded(draw, (52, y + 23, 112, y + 83), 20, (8, 35, 60), color, 2)
        draw_center(draw, (52, y + 23, 112, y + 83), number_value, base.font(27, True), color)
        draw.text((135, y + 21), title, font=base.font(22, True), fill=base.WHITE)
        draw.text((135, y + 57), desc, font=base.font(17), fill=base.SILVER)
        y += 126
    rounded(draw, (35, 755, 625, 805), 18, (23, 14, 3), (255, 190, 55), 2)
    draw_center(draw, (35, 755, 625, 805), "SEM PROMESSA DE PONTUAÇÃO", base.font(20, True), (255, 190, 55))
    image.save(output, "PNG", optimize=True)


def build_dialogue(round_value: int, data: Dict[str, Any]) -> List[TechnicalSegment]:
    players = data["jogadores"]
    teams = data["times"]
    arias = players["Arias"]
    jacy = players["Jacy"]
    viveros = players["Viveros"]
    pedro = players["Pedro"]
    samuel = players["Samuel Lino"]
    matheus = players["Matheus Pereira"]
    lucas = players["Lucas Arcanjo"]

    return [
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Olá! Esta é a segunda versão do piloto de análise da rodada {round_value}. Agora nós não vamos apenas repetir a escalação. Vamos explicar os critérios: forma recente, expectativa do modelo, contexto do confronto, custo em cartoletas e nível de risco.",
            "metodologia", "Agora: dados, contexto e risco — não apenas leitura de nomes."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            f"Francisca, começo pelo Econômico. Ele custou {cartoletas(teams['economico']['custo'])}. Mas gastar menos não basta. Onde o modelo realmente encontrou valor nessa montagem?",
            "economico", f"Time Econômico: {cartoletas(teams['economico']['custo'])} • eficiência por preço."
        ),
        TechnicalSegment(
            "THALITA", base.VOICE_THALITA,
            "O valor aparece na combinação. O time preserva Arias e Viveros, que carregam teto, mas reduz o custo em peças de sustentação. Jacy é um bom exemplo: não precisa fazer uma pontuação extraordinária para justificar o investimento.",
            "jacy", "Jacy: peça de sustentação, preço baixo e menor oscilação."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            f"Jacy custa {cartoletas(jacy['preco'])}, tem média de {number(jacy['media_ult5'])} nas últimas cinco e média esperada de {number(jacy['media_esperada'])}. Francisca, isso significa segurança?",
            "jacy", f"Últimas 5: {number(jacy['media_ult5'])} • esperada: {number(jacy['media_esperada'])}."
        ),
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Não significa garantia. A probabilidade de superar seis pontos é de {percent(jacy['prob_6'])}, e a de superar oito cai para {percent(jacy['prob_8'])}. A leitura correta é estabilidade relativa e boa relação entre preço e expectativa, não promessa de pontuação alta.",
            "jacy", "Boa relação custo-expectativa; teto mais limitado."
        ),
        TechnicalSegment(
            "THALITA", base.VOICE_THALITA,
            "E Arias aparece nos três modelos e lidera o meio-campo do Top 5. Antônio, por que pagar tantas cartoletas se o próprio contexto mostra diferença relevante entre desempenho em casa e fora?",
            "arias", "Arias: consenso dos modelos, mas com risco contextual."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            f"Porque a forma recente sustenta o teto. Arias tem média de {number(arias['media_ult5'])} nas últimas cinco, expectativa de {number(arias['media_esperada'])} e probabilidade de {percent(arias['prob_8'])} para oito ou mais. Mas a média fora de casa cai para {number(arias['media_fora'])}, e a variância é alta. É potencial com risco, não confronto fácil.",
            "arias", f"Prob. 8+: {percent(arias['prob_8'])} • média fora: {number(arias['media_fora'])}."
        ),
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Do Econômico para o Intermediário, o orçamento sobe para {cartoletas(teams['intermediario']['custo'])}. O investimento adicional entra principalmente no meio e no ataque. Thalita, isso melhora o piso ou aumenta o teto?",
            "intermediario", f"Intermediário: {cartoletas(teams['intermediario']['custo'])} • reforço no meio e ataque."
        ),
        TechnicalSegment(
            "THALITA", base.VOICE_THALITA,
            f"Aumenta sobretudo o teto. Matheus Pereira chega com média de {number(matheus['media_ult5'])} nas últimas cinco, mas a expectativa do recorte é {number(matheus['media_esperada'])}, e a probabilidade de oito ou mais é {percent(matheus['prob_8'])}. O modelo respeita a capacidade recente, mas sinaliza que o contexto reduz a segurança.",
            "matheus", "Matheus Pereira: boa forma recente, contexto menos estável."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            "No ataque, Pedro e Samuel Lino aparecem juntos. À primeira vista parece apenas uma dobradinha de nomes caros. Mas os dados mostram outra coisa: os dois têm médias recentes acima de dez pontos e probabilidades elevadas para superar oito.",
            "ataque", "Pedro e Samuel Lino: teto elevado e volatilidade elevada."
        ),
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Pedro tem média recente de {number(pedro['media_ult5'])} e probabilidade de {percent(pedro['prob_8'])} para oito ou mais. Samuel Lino tem {number(samuel['media_ult5'])} de média recente e {percent(samuel['prob_8'])} para oito ou mais. Onde está o alerta, Antônio?",
            "ataque", "Os números de teto são fortes; o risco não pode ser omitido."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            f"Na variância. Pedro está em {number(pedro['variancia_ult5'])} e Samuel em {number(samuel['variancia_ult5'])}. Isso significa oscilação relevante. O Time para Pontuar, que custa {cartoletas(teams['pontuacao']['custo'])}, aceita essa volatilidade para buscar uma pontuação mais alta.",
            "pontuacao", f"Time para Pontuar: {cartoletas(teams['pontuacao']['custo'])} • maior exposição ao teto."
        ),
        TechnicalSegment(
            "THALITA", base.VOICE_THALITA,
            "E chegamos ao capitão. Viveros foi repetido nos três times. Francisca, essa decisão veio apenas porque ele liderou o Top 5 de atacantes?",
            "viveros", "Viveros: capitão por teto estatístico, não por popularidade."
        ),
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Não. Ele tem média de {number(viveros['media_ult5'])} nas últimas cinco, Poisson de {number(viveros['poisson_pontos'])} pontos e probabilidade de {percent(viveros['prob_8'])} para oito ou mais. Ao mesmo tempo, o fator do confronto ficou abaixo de um. Portanto, a escolha do capitão vem do teto do atleta, não da ideia de partida fácil.",
            "viveros", f"Últimas 5: {number(viveros['media_ult5'])} • prob. 8+: {percent(viveros['prob_8'])}."
        ),
        TechnicalSegment(
            "ANTÔNIO", base.VOICE_ANTONIO,
            f"No Top 5, o objetivo não é ler trinta nomes. É oferecer alternativas por perfil. Lucas Arcanjo, por exemplo, custa {cartoletas(lucas['preco'])}. A probabilidade de seis ou mais é {percent(lucas['prob_6'])}, mas o Poisson é conservador. Quando os modelos divergem, a análise deve mostrar a dúvida, não escondê-la.",
            "top5", "Top 5: alternativas por perfil, preço, teto e risco."
        ),
        TechnicalSegment(
            "THALITA", base.VOICE_THALITA,
            "Esse é o ponto que fortalece a análise: um atleta pode ter forma recente excelente e ainda carregar risco; outro pode ter teto menor, mas entregar melhor eficiência por cartoleta. A escolha depende da proposta de cada time.",
            "comparativo", "Teto, estabilidade e eficiência são critérios diferentes."
        ),
        TechnicalSegment(
            "FRANCISCA", base.VOICE_FRANCISCA,
            f"Este foi o piloto técnico da rodada {round_value}. Os dados ajudam a explicar por que cada atleta entrou, mas não garantem resultado. Portal SimonSports: análise, transparência e entretenimento. Até a próxima rodada!",
            "final", "Análise informativa: dados apoiam decisões, mas não garantem pontuação."
        ),
    ]


def create_visuals(data: Dict[str, Any], temp: Path, repo_root: Path, round_value: int) -> Dict[str, Path | None]:
    players = data["jogadores"]
    output_dir = repo_root / "output"
    visuals: Dict[str, Path | None] = {
        "economico": output_dir / f"time_economico_rodada_{round_value}.png",
        "intermediario": output_dir / f"time_intermediario_rodada_{round_value}.png",
        "pontuacao": output_dir / f"time_pontuacao_rodada_{round_value}.png",
        "top5": output_dir / f"top5_rodada_{round_value}.png",
        "comparativo": temp / "comparativo.png",
        "metodologia": temp / "metodologia.png",
        "jacy": temp / "jacy.png",
        "arias": temp / "arias.png",
        "matheus": temp / "matheus.png",
        "ataque": temp / "ataque.png",
        "viveros": temp / "viveros.png",
        "intro": None,
        "final": None,
    }
    methodology_card(visuals["metodologia"])

    jacy = {"nome": "Jacy", **players["Jacy"]}
    metric_card(
        "EFICIÊNCIA DO ECONÔMICO", "Preço baixo, expectativa compatível e risco controlado.", jacy, visuals["jacy"],
        players["Jacy"]["analise"],
        [
            ("Média últimas 5", f"{number(jacy['media_ult5'])} pts", jacy["media_ult5"] / 12),
            ("Média esperada", f"{number(jacy['media_esperada'])} pts", jacy["media_esperada"] / 12),
            ("Probabilidade 6+", percent(jacy["prob_6"]), jacy["prob_6"]),
            ("Índice de confiança", percent(jacy["indice_confianca"]), jacy["indice_confianca"]),
        ],
    )

    arias = {"nome": "Arias", **players["Arias"]}
    metric_card(
        "CONSENSO COM RISCO", "Forma recente forte; desempenho fora e variância pedem cautela.", arias, visuals["arias"],
        players["Arias"]["analise"],
        [
            ("Média últimas 5", f"{number(arias['media_ult5'])} pts", arias["media_ult5"] / 12),
            ("Média esperada", f"{number(arias['media_esperada'])} pts", arias["media_esperada"] / 12),
            ("Probabilidade 8+", percent(arias["prob_8"]), arias["prob_8"]),
            ("Média fora", f"{number(arias['media_fora'])} pts", arias["media_fora"] / 12),
        ],
    )

    matheus = {"nome": "Matheus Pereira", **players["Matheus Pereira"]}
    metric_card(
        "MEIO-CAMPO INTERMEDIÁRIO", "O modelo diferencia forma recente de expectativa contextual.", matheus, visuals["matheus"],
        players["Matheus Pereira"]["analise"],
        [
            ("Média últimas 5", f"{number(matheus['media_ult5'])} pts", matheus["media_ult5"] / 12),
            ("Média esperada", f"{number(matheus['media_esperada'])} pts", matheus["media_esperada"] / 12),
            ("Probabilidade 6+", percent(matheus["prob_6"]), matheus["prob_6"]),
            ("Probabilidade 8+", percent(matheus["prob_8"]), matheus["prob_8"]),
        ],
    )

    comparison_card(
        "ATAQUE DE MAIOR TETO",
        [
            {"nome": "Pedro", **players["Pedro"]},
            {"nome": "Samuel Lino", **players["Samuel Lino"]},
            {"nome": "Viveros", **players["Viveros"]},
        ],
        visuals["ataque"],
        "Médias recentes e probabilidades são fortes, mas Pedro e Samuel também apresentam variância elevada.",
    )

    viveros = {"nome": "Viveros", **players["Viveros"]}
    metric_card(
        "POR QUE ELE FOI CAPITÃO?", "O teto estatístico foi forte, embora o confronto não seja classificado como fácil.", viveros, visuals["viveros"],
        players["Viveros"]["analise"],
        [
            ("Média últimas 5", f"{number(viveros['media_ult5'])} pts", viveros["media_ult5"] / 14),
            ("Poisson de pontos", f"{number(viveros['poisson_pontos'])} pts", viveros["poisson_pontos"] / 14),
            ("Probabilidade 6+", percent(viveros["prob_6"]), viveros["prob_6"]),
            ("Probabilidade 8+", percent(viveros["prob_8"]), viveros["prob_8"]),
        ],
    )

    comparison_card(
        "PERFIS DE ESCALAÇÃO",
        [
            {"nome": "Jacy", **players["Jacy"]},
            {"nome": "Arias", **players["Arias"]},
            {"nome": "Viveros", **players["Viveros"]},
            {"nome": "Samuel Lino", **players["Samuel Lino"]},
        ],
        visuals["comparativo"],
        "Jacy representa eficiência; Arias, consenso com risco; Viveros e Samuel Lino, busca por teto ofensivo.",
    )
    return visuals


async def synthesize(segment: TechnicalSegment, output: Path) -> None:
    settings = base.VOICE_SETTINGS[segment.voice]
    communicator = base.edge_tts.Communicate(
        text=sanitize_tts(segment.text),
        voice=segment.voice,
        rate=settings["rate"],
        pitch=settings["pitch"],
        volume=settings["volume"],
    )
    await communicator.save(str(output))


async def synthesize_all(segments: List[TechnicalSegment], directory: Path) -> List[Path]:
    files: List[Path] = []
    for index, segment in enumerate(segments):
        path = directory / f"fala_v2_{index:02d}.mp3"
        await synthesize(segment, path)
        files.append(path)
    return files


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    analysis_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v2.json"
    data = load_json(analysis_path)
    segments = build_dialogue(round_value, data)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cartola-dialogo-tecnico-v2-") as temp_name:
        temp = Path(temp_name)
        visuals = create_visuals(data, temp, repo_root, round_value)
        image_paths = [
            repo_root / "output" / f"time_economico_rodada_{round_value}.png",
            repo_root / "output" / f"time_intermediario_rodada_{round_value}.png",
            repo_root / "output" / f"time_pontuacao_rodada_{round_value}.png",
            repo_root / "output" / f"top5_rodada_{round_value}.png",
        ]
        missing = [str(path) for path in image_paths if not path.exists()]
        if missing:
            raise RuntimeError(f"Imagens obrigatórias ausentes: {missing}")

        try:
            audio_files = asyncio.run(synthesize_all(segments, temp))
        except Exception as exc:
            raise RuntimeError(
                "Não foi possível gerar Francisca, Thalita e Antônio. "
                "O piloto foi interrompido para não utilizar voz genérica."
            ) from exc

        clips: List[Path] = []
        timeline: List[Dict[str, Any]] = []
        elapsed = 0.0
        for index, (segment, audio) in enumerate(zip(segments, audio_files)):
            duration = base.ffprobe_duration(audio)
            frame = temp / f"frame_v2_{index:02d}.png"
            clip = temp / f"clip_v2_{index:02d}.mp4"
            visual_path = visuals.get(segment.visual)
            base.create_frame(
                visual_path,
                image_paths,
                segment.speaker,
                segment.onscreen,
                round_value,
                frame,
            )
            base.segment_video(frame, audio, clip, duration)
            clip_duration = duration + 0.38
            timeline.append({
                "indice": index + 1,
                "inicio": round(elapsed, 3),
                "fim": round(elapsed + clip_duration, 3),
                "apresentador": segment.speaker,
                "voz": segment.voice,
                "texto_falado": sanitize_tts(segment.text),
                "texto_tela": segment.onscreen,
                "visual": segment.visual,
            })
            elapsed += clip_duration
            clips.append(clip)

        concat_file = temp / "concat_v2.txt"
        concat_file.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
        base.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", "-movflags", "+faststart", str(output_path),
        ])

    manifest = output_path.with_suffix(".json")
    manifest.write_text(json.dumps({
        "versao": VERSION,
        "status": "PILOTO_PARA_APROVACAO",
        "publicacao_automatica": False,
        "rodada": round_value,
        "arquivo": str(output_path),
        "duracao_segundos": round(base.ffprobe_duration(output_path), 3),
        "moeda_falada": "cartoletas",
        "vozes": [base.VOICE_FRANCISCA, base.VOICE_ANTONIO, base.VOICE_THALITA],
        "fontes": data.get("fontes", []),
        "timeline": timeline,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera piloto técnico dialogado do Cartola.")
    parser.add_argument("--rodada", type=int, default=21)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/piloto_analise_tecnica_dialogada_rodada_21_v2.mp4")
    args = parser.parse_args()
    result = generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output))
    print(result)


if __name__ == "__main__":
    main()
