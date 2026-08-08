from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import gerar_base_video_por_snapshot as base


def safe(value: Any) -> str:
    return str(value or "").strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def build_pre_fechamento(rodada: int, root: Path) -> Path:
    original_validate = base.validate_team_snapshot
    original_recover = base.recover_initial_top5

    def validate_team(payload: Dict[str, Any], round_value: int, label: str) -> None:
        if as_int(payload.get("rodada")) != round_value:
            raise RuntimeError(
                f"Snapshot {label} pertence à rodada {payload.get('rodada')}, não à rodada {round_value}."
            )
        event = safe(payload.get("evento_programado")).upper()
        if event != "PRE_FECHAMENTO_TIMES":
            raise RuntimeError(
                f"Snapshot {label} não é de PRE_FECHAMENTO_TIMES: {event or 'SEM_EVENTO'}"
            )
        if len(base.athletes(payload)) < 12:
            raise RuntimeError(
                f"Snapshot {label} incompleto: {len(base.athletes(payload))} registros."
            )

    def recover_top5(
        repo_root: Path,
        round_value: int,
        current_snapshot: Dict[str, Any],
        target_time: Optional[object],
    ) -> Tuple[Dict[str, Any], str]:
        del target_time
        event = safe(current_snapshot.get("evento_programado")).upper()
        rows = base.athletes(current_snapshot)
        if as_int(current_snapshot.get("rodada")) != round_value:
            raise RuntimeError("Top 5 de pré-fechamento pertence a outra rodada.")
        if event != "PRE_FECHAMENTO_TOP5":
            raise RuntimeError(
                f"Top 5 não é de PRE_FECHAMENTO_TOP5: {event or 'SEM_EVENTO'}"
            )
        if len(rows) < 30:
            raise RuntimeError(
                f"Top 5 de pré-fechamento incompleto: {len(rows)} registros."
            )
        path = f"data/publicacoes_atuais/top5_rodada_{round_value}.json"
        return current_snapshot, path

    try:
        base.validate_team_snapshot = validate_team
        base.recover_initial_top5 = recover_top5
        output_path = base.build(rodada, root)
    finally:
        base.validate_team_snapshot = original_validate
        base.recover_initial_top5 = original_recover

    data = json.loads(output_path.read_text(encoding="utf-8"))
    data["status"] = "SNAPSHOT_PUBLICADO_PRE_FECHAMENTO"
    data["fase_video"] = "PRE_FECHAMENTO"
    data["evento_times"] = "PRE_FECHAMENTO_TIMES"
    data["evento_top5"] = "PRE_FECHAMENTO_TOP5"
    data["publicacao_automatica"] = True

    for item in (data.get("times") or {}).values():
        if isinstance(item, dict):
            item["tipo_pontuacao"] = "snapshot publicado do pré-fechamento"

    top5 = data.get("top5")
    if isinstance(top5, dict):
        top5["evento_programado"] = "PRE_FECHAMENTO_TOP5"

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Base de pré-fechamento criada: {output_path}")
    return output_path


def build(rodada: int, root: Path, fase: str) -> Path:
    fase = safe(fase).upper()
    if fase == "INICIAL":
        path = base.build(rodada, root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fase_video"] = "INICIAL"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    if fase == "PRE_FECHAMENTO":
        return build_pre_fechamento(rodada, root)
    raise RuntimeError(f"Fase inválida: {fase}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rodada", type=int, required=True)
    parser.add_argument("--fase", required=True, choices=["INICIAL", "PRE_FECHAMENTO"])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    print(build(args.rodada, Path(args.repo_root).resolve(), args.fase))


if __name__ == "__main__":
    main()
