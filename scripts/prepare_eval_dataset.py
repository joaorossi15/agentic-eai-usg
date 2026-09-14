from __future__ import annotations

import csv
import json
import random
from pathlib import Path


INPUT_PATH = Path("results/baseline_results.csv")
MASTER_PATH = Path("results/baseline_evaluation_master.csv")
EVALUATOR_PATH = Path("results/baseline_evaluator_sheet.csv")

RANDOM_SEED = 20260914

QUALITY_FIELDS = [
    "clarity",
    "completeness",
    "actionability",
    "testability",
    "faithfulness",
]


def load_results(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {path}")

    required_columns = {
        "run_id",
        "requirement_id",
        "principle",
        "requirement",
        "condition",
        "repetition",
        "model",
        "final_title",
        "final_description",
        "final_work_items",
    }

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("The results CSV does not contain a header.")

        missing = required_columns - set(reader.fieldnames)

        if missing:
            raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

        rows = list(reader)

    if not rows:
        raise ValueError("The results CSV contains no artifacts.")

    run_ids = [row["run_id"] for row in rows]

    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs found in the results.")

    return rows


def parse_work_items(raw: str) -> list[str]:
    try:
        work_items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse work items: {raw}") from exc

    if not isinstance(work_items, list):
        raise ValueError(f"Work items must be a JSON list: {raw}")

    return [str(item).strip() for item in work_items if str(item).strip()]


def format_eus(title: str, description: str, work_items: list[str]) -> str:
    work_items_text = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(work_items, start=1)
    )

    return (
        f"Title: {title.strip()}\n\n"
        f"Description:\n{description.strip()}\n\n"
        f"Work items:\n{work_items_text}"
    )


def prepare_artifacts(rows: list[dict]) -> list[dict]:
    artifacts = []

    for row in rows:
        work_items = parse_work_items(row["final_work_items"])

        artifacts.append({
            "run_id": row["run_id"],
            "requirement_id": row["requirement_id"],
            "principle": row["principle"],
            "requirement": row["requirement"],
            "condition": row["condition"],
            "repetition": row["repetition"],
            "model": row["model"],
            "title": row["final_title"],
            "description": row["final_description"],
            "work_items": json.dumps(work_items, ensure_ascii=False),
            "eus": format_eus(
                title=row["final_title"],
                description=row["final_description"],
                work_items=work_items,
            ),
        })

    rng = random.Random(RANDOM_SEED)
    rng.shuffle(artifacts)

    for index, artifact in enumerate(artifacts, start=1):
        artifact["artifact_id"] = f"A{index:03d}"

    return artifacts


def save_master(artifacts: list[dict], path: Path) -> None:
    fieldnames = [
        "artifact_id",
        "run_id",
        "requirement_id",
        "principle",
        "requirement",
        "condition",
        "repetition",
        "model",
        "title",
        "description",
        "work_items",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for artifact in artifacts:
            writer.writerow({
                field: artifact[field]
                for field in fieldnames
            })


def save_evaluator_sheet(artifacts: list[dict], path: Path) -> None:
    fieldnames = [
        "artifact_id",
        "requirement_id",
        "principle",
        "requirement",
        "eus",
        *QUALITY_FIELDS,
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for artifact in artifacts:
            writer.writerow({
                "artifact_id": artifact["artifact_id"],
                "requirement_id": artifact["requirement_id"],
                "principle": artifact["principle"],
                "requirement": artifact["requirement"],
                "eus": artifact["eus"],
                "clarity": "",
                "completeness": "",
                "actionability": "",
                "testability": "",
                "faithfulness": "",
            })


def main():
    rows = load_results(INPUT_PATH)
    artifacts = prepare_artifacts(rows)

    save_master(artifacts, MASTER_PATH)
    save_evaluator_sheet(artifacts, EVALUATOR_PATH)

    print(f"Loaded {len(rows)} artifacts.")
    print(f"Randomization seed: {RANDOM_SEED}")
    print(f"Master dataset: {MASTER_PATH}")
    print(f"Blinded evaluator sheet: {EVALUATOR_PATH}")


if __name__ == "__main__":
    main()
