from __future__ import annotations

import csv
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from eai_usg.io import save_backend_run
from eai_usg.pipeline import EAIUSGPipeline
from eai_usg.schemas import EthicalRequirement


MANIFEST_PATH = Path("results/backend_manifest.csv")
RESULTS_PATH = Path("results/backend_results.csv")
ERRORS_PATH = Path("results/backend_errors.csv")
RUN_OUTPUT_DIR = "outputs/backend_runs"

EXPECTED_REQUIREMENTS = 12
EXPECTED_BACKENDS = 3
REPETITIONS = 3
EXPECTED_RUNS = EXPECTED_REQUIREMENTS * EXPECTED_BACKENDS * REPETITIONS

EXPECTED_BACKEND_NAMES = {
    "openai",
    "anthropic",
    "google",
}

RUN_ORDER_SEED = 20260914


RESULT_FIELDS = [
    "run_id",
    "requirement_id",
    "principle",
    "source_row",
    "requirement",
    "backend",
    "model",
    "repetition",
    "started_at",
    "elapsed_seconds",
    "title",
    "description",
    "work_items",
    "checks_passed",
    "structure_issues",
    "redundancy_issues",
    "api_response_ids",
    "saved_run_path",
]

ERROR_FIELDS = [
    "run_id",
    "requirement_id",
    "backend",
    "model",
    "repetition",
    "started_at",
    "elapsed_seconds",
    "error",
]


def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {path}. Run backend_manifest.py first."
        )

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != EXPECTED_RUNS:
        raise ValueError(
            f"Expected {EXPECTED_RUNS} runs in the manifest, but found {len(rows)}."
        )

    run_ids = [row["run_id"] for row in rows]

    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs found in the manifest.")

    backend_names = {row["backend"] for row in rows}

    if backend_names != EXPECTED_BACKEND_NAMES:
        raise ValueError(
            f"Unexpected backends in manifest. "
            f"Expected: {sorted(EXPECTED_BACKEND_NAMES)}. "
            f"Found: {sorted(backend_names)}."
        )

    requirement_ids = {row["requirement_id"] for row in rows}

    if len(requirement_ids) != EXPECTED_REQUIREMENTS:
        raise ValueError(
            f"Expected {EXPECTED_REQUIREMENTS} unique requirements, "
            f"but found {len(requirement_ids)}."
        )

    backend_counts = Counter(row["backend"] for row in rows)
    expected_backend_runs = EXPECTED_REQUIREMENTS * REPETITIONS

    for backend in EXPECTED_BACKEND_NAMES:
        if backend_counts[backend] != expected_backend_runs:
            raise ValueError(
                f"Expected {expected_backend_runs} runs for backend "
                f"{backend}, found {backend_counts[backend]}."
            )

    for requirement_id in requirement_ids:
        for backend in EXPECTED_BACKEND_NAMES:
            repetitions = {
                int(row["repetition"])
                for row in rows
                if row["requirement_id"] == requirement_id
                and row["backend"] == backend
            }

            expected_repetitions = set(range(1, REPETITIONS + 1))

            if repetitions != expected_repetitions:
                raise ValueError(
                    f"Unexpected repetitions for {requirement_id} / {backend}. "
                    f"Expected: {sorted(expected_repetitions)}. "
                    f"Found: {sorted(repetitions)}."
                )

    return rows


def load_completed_run_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["run_id"] for row in reader}


def serialize_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def result_to_row(
    job: dict,
    result,
    saved_path: Path,
    started_at: str,
    elapsed_seconds: float,
) -> dict:
    return {
        "run_id": job["run_id"],
        "requirement_id": job["requirement_id"],
        "principle": job["principle"],
        "source_row": job["source_row"],
        "requirement": job["requirement"],
        "backend": result.backend,
        "model": result.model,
        "repetition": result.repetition,
        "started_at": started_at,
        "elapsed_seconds": f"{elapsed_seconds:.3f}",
        "title": result.eus.title,
        "description": result.eus.description,
        "work_items": serialize_list(result.eus.work_items),
        "checks_passed": result.checks.passed,
        "structure_issues": serialize_list(result.checks.structure_issues),
        "redundancy_issues": serialize_list(result.checks.redundancy_issues),
        "api_response_ids": serialize_list(result.api_response_ids),
        "saved_run_path": str(saved_path),
    }


def append_csv(
    row: dict,
    path: Path,
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_MINIMAL,
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


def main():
    manifest = load_manifest(MANIFEST_PATH)
    completed = load_completed_run_ids(RESULTS_PATH)

    rng = random.Random(RUN_ORDER_SEED)
    rng.shuffle(manifest)

    remaining = [
        job
        for job in manifest
        if job["run_id"] not in completed
    ]

    print("=" * 70)
    print("EAI-USG LLM Backend Evaluation")
    print("=" * 70)
    print(f"Planned runs:   {len(manifest)}")
    print(f"Completed runs: {len(completed)}")
    print(f"Remaining runs: {len(remaining)}")
    print(f"Execution seed: {RUN_ORDER_SEED}")
    print("=" * 70)
    print()

    if not remaining:
        print("All backend-evaluation runs are already complete.")
        return

    completed_this_session = 0
    failed_this_session = 0

    for position, job in enumerate(remaining, start=1):
        run_id = job["run_id"]
        backend = job["backend"]
        model = job["model"]
        repetition = int(job["repetition"])

        print(f"[{position}/{len(remaining)}] {run_id}")
        print(
            f"backend={backend} | "
            f"model={model} | "
            f"repetition={repetition}"
        )

        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        try:
            pipeline = EAIUSGPipeline(
                backend=backend,
                model=model,
            )

            requirement = EthicalRequirement(
                id=job["requirement_id"],
                text=job["requirement"],
            )

            result = pipeline.run(
                requirement=requirement,
                repetition=repetition,
            )

            elapsed_seconds = time.perf_counter() - start_time

            saved_path = save_backend_run(
                result,
                output_dir=RUN_OUTPUT_DIR,
            )

            row = result_to_row(
                job=job,
                result=result,
                saved_path=saved_path,
                started_at=started_at,
                elapsed_seconds=elapsed_seconds,
            )

            append_csv(
                row,
                RESULTS_PATH,
                RESULT_FIELDS,
            )

            completed_this_session += 1

            print(
                f"OK | checks={result.checks.passed} | "
                f"{elapsed_seconds:.1f}s"
            )

        except Exception as exc:
            elapsed_seconds = time.perf_counter() - start_time

            error_row = {
                "run_id": run_id,
                "requirement_id": job["requirement_id"],
                "backend": backend,
                "model": model,
                "repetition": repetition,
                "started_at": started_at,
                "elapsed_seconds": f"{elapsed_seconds:.3f}",
                "error": repr(exc),
            }

            append_csv(
                error_row,
                ERRORS_PATH,
                ERROR_FIELDS,
            )

            failed_this_session += 1

            print(
                f"ERROR | {type(exc).__name__}: {exc}"
            )

        print()

    total_completed = len(
        load_completed_run_ids(RESULTS_PATH)
    )

    print("=" * 70)
    print("Backend evaluation execution finished")
    print("=" * 70)
    print(f"Completed this session: {completed_this_session}")
    print(f"Failed this session:    {failed_this_session}")
    print(f"Total completed:        {total_completed}/{EXPECTED_RUNS}")
    print(f"Results: {RESULTS_PATH}")

    if failed_this_session:
        print(f"Errors: {ERRORS_PATH}")
        print("Run this script again to retry failed API runs.")


if __name__ == "__main__":
    main()
