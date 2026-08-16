from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import gerar_video_dialogo_cartola_v3 as v3
import gerar_video_dialogo_cartola_v10 as v10

VERSION = "cartola_dialogo_tecnico_v11_comparacao_abertura_pre_2026_08_16"
ORIGINAL_BUILD = v10.build_dialogue_v10


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def first_names(items: List[Dict[str, Any]], key: str = "nome", limit: int = 3) -> str:
    names = [clean(item.get(key)) for item in items if clean(item.get(key))]
    return ", ".join(names[:limit])


def comparison_segments(round_value: int, data: Dict[str, Any], template: v3.Segment) -> List[v3.Segment]:
    comparison = data.get("comparacao_abertura_pre_fechamento") or {}
    if not isinstance(comparison, dict) or comparison.get("comparacao_obrigatoria") is not True:
        raise RuntimeError("Comparação abertura x pré-fechamento ausente na base técnica.")

    teams = comparison.get("times") or {}
    top5 = comparison.get("top5") or {}
    changed = [item for item in teams.values() if isinstance(item, dict) and item.get("houve_mudanca")]

    if comparison.get("houve_mudanca"):
        intro = (
            f"Agora vem a parte que diferencia este vídeo do publicado na abertura da rodada {round_value}: "
            "a comparação direta entre a fotografia inicial e o pré-fechamento. "
            f"Houve alteração em {len(changed)} dos três modelos"
        )
        if top5.get("houve_mudanca"):
            intro += " e também houve movimentação no Top 5."
        else:
            intro += ", enquanto o Top 5 permaneceu sem troca relevante de nomes ou posições."
    else:
        intro = (
            f"Comparando com a análise de abertura da rodada {round_value}, os três modelos e o Top 5 "
            "permaneceram estáveis. O pré-fechamento confirma a estratégia inicial, sem mudança suficiente "
            "para justificar troca de direção."
        )

    details: List[str] = []
    for slug in ("economico", "intermediario", "pontuacao"):
        item = teams.get(slug) or {}
        if not item.get("houve_mudanca"):
            continue
        entered = first_names(item.get("entraram") or [])
        exited = first_names(item.get("sairam") or [])
        fragments = [item.get("modelo") or slug]
        if entered:
            fragments.append("entraram " + entered)
        if exited:
            fragments.append("saíram " + exited)
        if item.get("capitao_mudou"):
            fragments.append(
                "capitão mudou de " + clean(item.get("capitao_abertura")) + " para " + clean(item.get("capitao_pre_fechamento"))
            )
        if item.get("formacao_mudou"):
            fragments.append(
                "formação mudou de " + clean(item.get("formacao_abertura")) + " para " + clean(item.get("formacao_pre_fechamento"))
            )
        details.append("; ".join(fragment for fragment in fragments if fragment))

    top_fragments: List[str] = []
    if top5.get("total_entraram"):
        top_fragments.append(f"{top5.get('total_entraram')} entrada(s)")
    if top5.get("total_sairam"):
        top_fragments.append(f"{top5.get('total_sairam')} saída(s)")
    if top5.get("total_subiram"):
        top_fragments.append(f"{top5.get('total_subiram')} atleta(s) subiram")
    if top5.get("total_cairam"):
        top_fragments.append(f"{top5.get('total_cairam')} atleta(s) caíram")

    if details:
        detail_text = "Nos times, " + ". ".join(details) + "."
    else:
        detail_text = "Nos três times não houve troca de titulares, capitão ou formação entre a abertura e o pré-fechamento."

    if top_fragments:
        detail_text += " No Top 5, a comparação apontou " + ", ".join(top_fragments) + "."
    else:
        detail_text += " No Top 5, não houve movimentação relevante entre as duas fotografias."

    reason_examples: List[str] = []
    for item in teams.values():
        if not isinstance(item, dict):
            continue
        for bucket in ("entraram", "sairam"):
            for athlete in item.get(bucket) or []:
                name = clean(athlete.get("nome"))
                reason = clean(athlete.get("motivo"))
                if name and reason:
                    reason_examples.append(f"{name}: {reason}")
                if len(reason_examples) >= 3:
                    break
            if len(reason_examples) >= 3:
                break
        if len(reason_examples) >= 3:
            break

    if reason_examples:
        reason_text = (
            "Os motivos são derivados das diferenças reais registradas pelos dois snapshots. "
            + ". ".join(reason_examples)
            + ". Quando não existe indicador objetivo suficiente, o roteiro não inventa justificativa externa."
        )
    else:
        reason_text = (
            "Como não houve troca relevante, não existe motivo artificial a ser criado. "
            "O pré-fechamento apenas confirma o que já estava indicado na análise de abertura."
        )

    visual = template.visual
    return [
        v3.Segment(
            speaker=template.speaker,
            voice=template.voice,
            text=intro,
            visual=visual,
            onscreen=f"Rodada {round_value} • Abertura × Pré-fechamento",
        ),
        v3.Segment(
            speaker=template.speaker,
            voice=template.voice,
            text=detail_text,
            visual=visual,
            onscreen="O que mudou nos Times e no Top 5",
        ),
        v3.Segment(
            speaker=template.speaker,
            voice=template.voice,
            text=reason_text,
            visual=visual,
            onscreen="Motivos das mudanças com base nos snapshots",
        ),
    ]


def build_dialogue_v11(round_value: int, data: Dict[str, Any]) -> List[v3.Segment]:
    segments = ORIGINAL_BUILD(round_value, data)
    if clean(data.get("fase_video")).upper() != "PRE_FECHAMENTO":
        return segments
    if not segments:
        raise RuntimeError("Roteiro base vazio.")
    inserts = comparison_segments(round_value, data, segments[0])
    return segments[:1] + inserts + segments[1:]


def update_manifest(output_path: Path, data: Dict[str, Any]) -> None:
    path = output_path.with_suffix(".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["versao"] = VERSION
    if clean(data.get("fase_video")).upper() == "PRE_FECHAMENTO":
        comparison = data.get("comparacao_abertura_pre_fechamento") or {}
        spoken = " ".join(clean(item.get("texto_falado")) for item in payload.get("timeline") or []).lower()
        if "abertura" not in spoken or "pré-fechamento" not in spoken:
            raise RuntimeError("O áudio de pré-fechamento não contém a comparação com a abertura.")
        payload["comparacao_abertura_pre_fechamento_no_audio"] = True
        payload["comparacao_houve_mudanca"] = bool(comparison.get("houve_mudanca"))
        payload["comparacao_times_com_mudanca"] = comparison.get("times_com_mudanca") or []
        payload["comparacao_top5"] = comparison.get("top5") or {}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(round_value: int, repo_root: Path, output_path: Path) -> Path:
    data_path = repo_root / "data" / f"analise_tecnica_rodada_{round_value}_v3.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    old_build = v10.build_dialogue_v10
    try:
        v10.build_dialogue_v10 = build_dialogue_v11
        result = v10.generate(round_value, repo_root, output_path)
        update_manifest(output_path, data)
        return result
    finally:
        v10.build_dialogue_v10 = old_build


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(generate(args.rodada, Path(args.repo_root).resolve(), Path(args.output)))


if __name__ == "__main__":
    main()
