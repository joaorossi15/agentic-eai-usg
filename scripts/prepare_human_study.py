from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from eai_usg.checks import run_deterministic_checks, run_traceability_checks
from eai_usg.pipeline import EAIUSGPipeline
from eai_usg.schemas import EthicalRequirement


DEFAULT_DATASET = "data/human-study-dataset.csv"
DEFAULT_OUTPUT_DIR = "outputs/human_study"
EXPECTED_REQUIREMENTS = 16

EXPECTED_PRINCIPLES = {
    "Transparency": 4,
    "Privacy": 4,
    "Freedom & Autonomy": 4,
    "Justice & Equity": 4,
}


def load_requirements(dataset_path: str) -> list[dict]:
    path = Path(dataset_path)

    if not path.exists():
        raise FileNotFoundError(f"Human-study dataset not found at '{dataset_path}'.")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) != EXPECTED_REQUIREMENTS:
        raise ValueError(
            f"Expected {EXPECTED_REQUIREMENTS} human-study requirements, found {len(rows)}."
        )

    required_columns = {
        "ID",
        "Split",
        "Principle",
        "Source Row",
        "Requirement",
    }

    missing_columns = required_columns - set(rows[0].keys())

    if missing_columns:
        raise ValueError(
            f"Dataset is missing required columns: {', '.join(sorted(missing_columns))}."
        )

    ids = [row["ID"].strip() for row in rows]

    if len(ids) != len(set(ids)):
        raise ValueError("Human-study dataset contains duplicate requirement IDs.")

    principle_counts: dict[str, int] = {}

    for row in rows:
        requirement_id = row["ID"].strip()
        principle = row["Principle"].strip()
        requirement_text = row["Requirement"].strip()
        split = row["Split"].strip()

        if not requirement_id:
            raise ValueError("Dataset contains an empty requirement ID.")

        if not requirement_text:
            raise ValueError(f"Requirement '{requirement_id}' has empty text.")

        if split != "Human Study":
            raise ValueError(
                f"Requirement '{requirement_id}' has unexpected split '{split}'."
            )

        principle_counts[principle] = principle_counts.get(principle, 0) + 1

    if principle_counts != EXPECTED_PRINCIPLES:
        raise ValueError(
            "Unexpected principle distribution. "
            f"Expected {EXPECTED_PRINCIPLES}, found {principle_counts}."
        )

    return rows


def generate_artifact(
    pipeline: EAIUSGPipeline,
    row: dict,
) -> dict:
    requirement = EthicalRequirement(
        id=row["ID"].strip(),
        text=row["Requirement"].strip(),
    )

    response_start = len(pipeline.llm.response_ids)

    print(f"\n[{requirement.id}] Generating initial EUS...")
    initial_eus = pipeline.generate_eus(requirement=requirement)

    print(f"[{requirement.id}] Generating analysis and traceability...")
    traceability_result = pipeline.trace_eus(
        requirement=requirement,
        eus=initial_eus,
    )

    print(f"[{requirement.id}] Running deterministic checks...")
    deterministic_checks = run_deterministic_checks(initial_eus)

    print(f"[{requirement.id}] Running traceability checks...")
    traceability_checks = run_traceability_checks(
        analysis=traceability_result.analysis,
        eus=initial_eus,
        traceability=traceability_result.traceability,
    )

    api_response_ids = pipeline.llm.response_ids[response_start:]

    return {
        "requirement": requirement.model_dump(mode="json"),
        "study_metadata": {
            "principle": row["Principle"].strip(),
            "source_row": int(row["Source Row"]),
        },
        "backend": pipeline.llm.backend,
        "model": pipeline.llm.model,
        "initial_eus": initial_eus.model_dump(mode="json"),
        "analysis": traceability_result.analysis.model_dump(mode="json"),
        "traceability": traceability_result.traceability.model_dump(mode="json"),
        "deterministic_checks": deterministic_checks.model_dump(mode="json"),
        "traceability_checks": traceability_checks.model_dump(mode="json"),
        "api_response_ids": api_response_ids,
    }


def validate_artifact(artifact: dict) -> None:
    requirement_id = artifact["requirement"]["id"]

    if not artifact["deterministic_checks"]["passed"]:
        raise ValueError(
            f"{requirement_id} failed deterministic checks: "
            f"{artifact['deterministic_checks']}"
        )

    if not artifact["traceability_checks"]["passed"]:
        raise ValueError(
            f"{requirement_id} failed traceability checks: "
            f"{artifact['traceability_checks']}"
        )


def save_artifact(artifact: dict, output_dir: Path) -> Path:
    requirement_id = artifact["requirement"]["id"]
    path = output_dir / f"{requirement_id}.json"

    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--backend", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    rows = load_requirements(args.dataset)

    output_dir = Path(args.output_dir)
    staging_dir = Path(f"{args.output_dir}.staging")

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"'{output_dir}' already contains files. "
            "Human-study artifacts are intended to be generated and frozen once. "
            "Move or delete the existing directory explicitly if you really want to regenerate them."
        )

    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    staging_dir.mkdir(parents=True, exist_ok=True)

    pipeline = EAIUSGPipeline(
        backend=args.backend,
        model=args.model,
    )

    print("Preparing Human-AI study artifacts")
    print("=" * 70)
    print(f"Requirements: {len(rows)}")
    print(f"Backend: {pipeline.llm.backend}")
    print(f"Model: {pipeline.llm.model}")
    print(f"Dataset: {args.dataset}")
    print("=" * 70)

    generated_paths: list[Path] = []

    try:
        for index, row in enumerate(rows, start=1):
            requirement_id = row["ID"].strip()

            print(f"\n[{index}/{len(rows)}] {requirement_id}")

            artifact = generate_artifact(
                pipeline=pipeline,
                row=row,
            )

            validate_artifact(artifact)

            path = save_artifact(
                artifact=artifact,
                output_dir=staging_dir,
            )

            generated_paths.append(path)

            print(f"[{requirement_id}] OK")

        if len(generated_paths) != EXPECTED_REQUIREMENTS:
            raise ValueError(
                f"Expected {EXPECTED_REQUIREMENTS} artifacts, generated {len(generated_paths)}."
            )

        output_dir.parent.mkdir(parents=True, exist_ok=True)

        if output_dir.exists():
            output_dir.rmdir()

        staging_dir.rename(output_dir)

    except Exception:
        print("\nPreparation failed.")
        print(f"Partial artifacts remain in '{staging_dir}' for inspection.")
        raise

    print("\n" + "=" * 70)
    print("Human-AI study artifacts generated successfully.")
    print(f"Artifacts: {len(generated_paths)}")
    print(f"Output directory: {output_dir}")
    print("All deterministic and traceability checks passed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
