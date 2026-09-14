from __future__ import annotations

import csv
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from eai_usg.io import save_run
from eai_usg.pipeline import EAIUSGPipeline, WorkflowConfig
from eai_usg.schemas import EthicalRequirement


MANIFEST_PATH = Path("results/baseline_manifest.csv")
RESULTS_PATH = Path("results/baseline_results.csv")
ERRORS_PATH = Path("results/baseline_errors.csv")

EXPECTED_REQUIREMENTS = 12
EXPECTED_CONDITIONS = 2
REPETITIONS = 3
EXPECTED_RUNS = EXPECTED_REQUIREMENTS * EXPECTED_CONDITIONS * REPETITIONS

RUN_ORDER_SEED = 20260913
QUALITY_THRESHOLD = None


RESULT_FIELDS = [
    "run_id",
    "requirement_id",
    "principle",
    "source_row",
    "requirement",
    "condition",
    "configuration",
    "repetition",
    "model",
    "started_at",
    "elapsed_seconds",
    "initial_title",
    "initial_description",
    "initial_work_items",
    "final_title",
    "final_description",
    "final_work_items",
    "revision_occurred",
    "status",
    "review_reason",
    "internal_clarity",
    "internal_completeness",
    "internal_actionability",
    "internal_testability",
    "internal_faithfulness",
    "api_response_ids",
    "saved_run_path",
]

ERROR_FIELDS = [
    "run_id",
    "requirement_id",
    "condition",
    "configuration",
    "repetition",
    "model",
    "started_at",
    "elapsed_seconds",
    "error",
]


def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}. Run build_baseline_manifest.py first.")

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != EXPECTED_RUNS:
        raise ValueError(f"Expected {EXPECTED_RUNS} runs in the manifest, but found {len(rows)}.")

    run_ids = [row["run_id"] for row in rows]

    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs found in the manifest.")

    expected_conditions = {
        "eai_usg",
        "same_model_single_pass",
    }

    manifest_conditions = {row["condition"] for row in rows}

    if manifest_conditions != expected_conditions:
        raise ValueError(f"Unexpected conditions in manifest. Expected: {sorted(expected_conditions)}. Found: {sorted(manifest_conditions)}.")

    expected_configurations = {
        WorkflowConfig.FULL.value,
        WorkflowConfig.SINGLE_PASS.value,
    }

    manifest_configurations = {row["configuration"] for row in rows}

    if manifest_configurations != expected_configurations:
        raise ValueError(f"Unexpected configurations in manifest. Expected: {sorted(expected_configurations)}. Found: {sorted(manifest_configurations)}.")

    for row in rows:
        if row["condition"] == "eai_usg" and row["configuration"] != WorkflowConfig.FULL.value:
            raise ValueError(f"Condition eai_usg must use configuration=full: {row['run_id']}")

        if row["condition"] == "same_model_single_pass" and row["configuration"] != WorkflowConfig.SINGLE_PASS.value:
            raise ValueError(f"Condition same_model_single_pass must use configuration=single_pass: {row['run_id']}")

    return rows


def load_completed_run_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["run_id"] for row in reader}


def serialize_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def result_to_row(job: dict, result, saved_path, started_at: str, elapsed_seconds: float) -> dict:
    validation = result.final_validation or result.validation

    return {
        "run_id": job["run_id"],
        "requirement_id": job["requirement_id"],
        "principle": job["principle"],
        "source_row": job["source_row"],
        "requirement": job["requirement"],
        "condition": job["condition"],
        "configuration": job["configuration"],
        "repetition": job["repetition"],
        "model": job["model"],
        "started_at": started_at,
        "elapsed_seconds": f"{elapsed_seconds:.3f}",
        "initial_title": result.initial_draft.title,
        "initial_description": result.initial_draft.description,
        "initial_work_items": serialize_list(result.initial_draft.work_items),
        "final_title": result.final_eus.title,
        "final_description": result.final_eus.description,
        "final_work_items": serialize_list(result.final_eus.work_items),
        "revision_occurred": result.revised_draft is not None,
        "status": result.status.value,
        "review_reason": result.review_reason.value if result.review_reason is not None else "",
        "internal_clarity": validation.clarity if validation is not None else "",
        "internal_completeness": validation.completeness if validation is not None else "",
        "internal_actionability": validation.actionability if validation is not None else "",
        "internal_testability": validation.testability if validation is not None else "",
        "internal_faithfulness": validation.faithfulness if validation is not None else "",
        "api_response_ids": json.dumps(result.api_response_ids, ensure_ascii=False),
        "saved_run_path": str(saved_path),
    }


def append_csv(row: dict, path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def main():
    manifest = load_manifest(MANIFEST_PATH)
    completed = load_completed_run_ids(RESULTS_PATH)

    rng = random.Random(RUN_ORDER_SEED)
    rng.shuffle(manifest)

    remaining = [job for job in manifest if job["run_id"] not in completed]

    print("=" * 70)
    print("EAI-USG Baseline Comparison")
    print("=" * 70)
    print(f"Planned runs:   {len(manifest)}")
    print(f"Completed runs: {len(completed)}")
    print(f"Remaining runs: {len(remaining)}")
    print(f"Execution seed: {RUN_ORDER_SEED}")
    print("=" * 70)
    print()

    if not remaining:
        print("All automated baseline comparison runs are already complete.")
        return

    completed_this_session = 0
    failed_this_session = 0

    for position, job in enumerate(remaining, start=1):
        run_id = job["run_id"]
        condition = job["condition"]
        configuration = WorkflowConfig(job["configuration"])
        model = job["model"]

        print(f"[{position}/{len(remaining)}] {run_id}")
        print(f"condition={condition} | config={configuration.value} | model={model}")

        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        try:
            pipeline = EAIUSGPipeline(model=model, quality_threshold=QUALITY_THRESHOLD)
            requirement = EthicalRequirement(id=job["requirement_id"], text=job["requirement"])
            result = pipeline.run(requirement, configuration)

            elapsed_seconds = time.perf_counter() - start_time
            saved_path = save_run(result)
            row = result_to_row(job, result, saved_path, started_at, elapsed_seconds)

            append_csv(row, RESULTS_PATH, RESULT_FIELDS)

            completed_this_session += 1

            print(f"OK | status={result.status.value} | revision={result.revised_draft is not None} | {elapsed_seconds:.1f}s")

        except Exception as exc:
            elapsed_seconds = time.perf_counter() - start_time

            error_row = {
                "run_id": run_id,
                "requirement_id": job["requirement_id"],
                "condition": condition,
                "configuration": job["configuration"],
                "repetition": job["repetition"],
                "model": model,
                "started_at": started_at,
                "elapsed_seconds": f"{elapsed_seconds:.3f}",
                "error": repr(exc),
            }

            append_csv(error_row, ERRORS_PATH, ERROR_FIELDS)

            failed_this_session += 1

            print(f"ERROR | {type(exc).__name__}: {exc}")

        print()

    total_completed = len(load_completed_run_ids(RESULTS_PATH))

    print("=" * 70)
    print("Baseline comparison execution finished")
    print("=" * 70)
    print(f"Completed this session: {completed_this_session}")
    print(f"Failed this session:    {failed_this_session}")
    print(f"Total completed:        {total_completed}/{EXPECTED_RUNS}")
    print(f"Results: {RESULTS_PATH}")

    if failed_this_session:
        print(f"Errors: {ERRORS_PATH}")
        print("Run this script again to retry failed runs.")


if __name__ == "__main__":
    main()
