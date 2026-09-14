import csv
from pathlib import Path

REPETITIONS = 3

BACKENDS = [
    {
        "backend": "openai",
        "model": "gpt-5.6-terra",
    },
    {
        "backend": "anthropic",
        "model": "claude-fable-5-1",
    },
    {
        "backend": "google",
        "model": "gemini-3.8-flash",
    },
]

INPUT_PATH = Path("data/backend_requirements.csv")
OUTPUT_PATH = Path("results/backend_manifest.csv")

EXPECTED_REQUIREMENTS = 12


def load_requirements(path: Path) -> list[dict]:
    required_columns = {
        "ID",
        "Principle",
        "Source Row",
        "Requirement",
    }

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("The requirements CSV does not contain a header.")

        missing = required_columns - set(reader.fieldnames)

        if missing:
            raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

        requirements = []

        for row in reader:
            requirement = row["Requirement"].strip()

            if not requirement:
                continue

            requirements.append({
                "id": row["ID"].strip(),
                "principle": row["Principle"].strip(),
                "source_row": row["Source Row"].strip(),
                "requirement": requirement,
            })

    return requirements


def build_manifest(requirements: list[dict]) -> list[dict]:
    rows = []

    for req in requirements:
        for backend in BACKENDS:
            for repetition in range(1, REPETITIONS + 1):
                rows.append({
                    "run_id": f"{req['id']}__{backend['backend']}__{repetition}",
                    "requirement_id": req["id"],
                    "principle": req["principle"],
                    "source_row": req["source_row"],
                    "requirement": req["requirement"],
                    "backend": backend["backend"],
                    "model": backend["model"],
                    "repetition": repetition,
                })

    return rows


def save_manifest(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "run_id",
        "requirement_id",
        "principle",
        "source_row",
        "requirement",
        "backend",
        "model",
        "repetition",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    requirements = load_requirements(INPUT_PATH)

    if len(requirements) != EXPECTED_REQUIREMENTS:
        raise ValueError(f"Expected {EXPECTED_REQUIREMENTS} requirements, found {len(requirements)}.")

    manifest = build_manifest(requirements)

    expected_runs = EXPECTED_REQUIREMENTS * len(BACKENDS) * REPETITIONS

    if len(manifest) != expected_runs:
        raise ValueError(f"Expected {expected_runs} runs, generated {len(manifest)}.")

    run_ids = [row["run_id"] for row in manifest]

    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs detected.")

    save_manifest(manifest, OUTPUT_PATH)

    print(f"Loaded {len(requirements)} backend-evaluation requirements.")
    print(f"Backends: {len(BACKENDS)}")
    print(f"Repetitions: {REPETITIONS}")
    print(f"Created {len(manifest)} planned runs.")
    print(f"Manifest saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
