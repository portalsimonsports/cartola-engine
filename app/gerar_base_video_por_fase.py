from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gerar_base_video_por_snapshot as base


def safe(value: Any) -> str:
    return str(value or "").strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = (
        payload.get("jogadores")
        or payload.get("atletas")
        or payload.get("dados")
        or payload.get("lista")
        or []
    )
    return [item for item in raw if isinstance(item, dict)]


def valid_snapshot(
    payload: Dict[str, Any],
    rodada: int,
    evento: str,
    minimo: int,
) -> bool:
    return (
        isinstance(payload, dict)
        and as_int(payload.get("rodada")) == rodada
        and safe(payload.get("evento_programado")).upper() == evento
        and len(rows(payload)) >= minimo
    )


def restore_binary(root: Path, commit: str, relative_path: str) -> None:
    if not commit or commit == "WORKTREE":
        return
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(
            f"Imagem histórica não encontrada no commit {commit}: {relative_path}"
        )
    output = root / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.stdout)
    print(f"Imagem histórica recuperada: {relative_path} | commit={commit}")


def recover_from_git(
    root: Path,
    relative_path: str,
    rodada: int,
    evento: str,
    minimo: int,
) -> Tuple[Dict[str, Any], str]:
    current_path = root / relative_path
    current = base.read_json(current_path, required=False)
    if valid_snapshot(current, rodada, evento, minimo):
        return current, "WORKTREE"

    for commit in base.git_commits_for_path(root, relative_path):
        payload = base.git_json(root, commit, relative_path)
        if not valid_snapshot(payload, rodada, evento, minimo):
            continue

        if evento == "PRE_FECHAMENTO_TOP5" and not payload.get("dados"):
            payload["dados"] = rows(payload)

        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"Snapshot histórico recuperado: {relative_path} | "
            f"evento={evento} | commit={commit} | registros={len(rows(payload))}"
        )
        return payload, commit

    raise RuntimeError(
        f"Não foi encontrado snapshot histórico {evento} da rodada {rodada} "
        f"em {relative_path}."
    )


def prepare_preclose_snapshots(rodada: int, root: Path) -> Dict[str, str]:
    sources: Dict[str, str] = {}
    team_paths = {
        "economico": f"data/publicacoes_atuais/time_economico_rodada_{rodada}.json",
        "intermediario": f"data/publicacoes_atuais/time_intermediario_rodada_{rodada}.json",
        "pontuacao": f"data/publicacoes_atuais/time_pontuacao_rodada_{rodada}.json",
    }

    for slug, path in team_paths.items():
        _, source = recover_from_git(
            root,
            path,
            rodada,
            "PRE_FECHAMENTO_TIMES",
            12,
        )
        sources[slug] = source
        if source != "WORKTREE":
            restore_binary(
                root,
                source,
                f"output/time_{slug}_rodada_{rodada}.png",
            )

    top_path = f"data/publicacoes_atuais/top5_rodada_{rodada}.json"
    _, source = recover_from_git(
        root,
        top_path,
        rodada,
        "PRE_FECHAMENTO_TOP5",
        30,
    )
    sources["top5"] = source
    if source != "WORKTREE":
        restore_binary(root, source, f"output/top5_rodada_{rodada}.png")
    return sources


def build_pre_fechamento(rodada: int, root: Path) -> Path:
    sources = prepare_preclose_snapshots(rodada, root)
    original_validate = base.validate_team_snapshot
    original_recover = base.recover_initial_top5

    def validate_team(payload: Dict[str, Any], round_value: int, label: str) -> None:
        if not valid_snapshot(payload, round_value, "PRE_FECHAMENTO_TIMES", 12):
            raise RuntimeError(
                f"Snapshot {label} inválido para PRE_FECHAMENTO_TIMES: "
                f"rodada={payload.get('rodada')} "
                f"evento={payload.get('evento_programado')} "
                f"registros={len(rows(payload))}"
            )

    def recover_top5(
        repo_root: Path,
        round_value: int,
        current_snapshot: Dict[str, Any],
        target_time: Optional[object],
    ) -> Tuple[Dict[str, Any], str]:
        del repo_root, target_time
        if not valid_snapshot(
            current_snapshot,
            round_value,
            "PRE_FECHAMENTO_TOP5",
            30,
        ):
            raise RuntimeError(
                "Top 5 recuperado não corresponde ao PRE_FECHAMENTO_TOP5."
            )
        if not current_snapshot.get("dados"):
            current_snapshot["dados"] = rows(current_snapshot)
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
    data["snapshots_recuperados_do_git"] = sources

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
