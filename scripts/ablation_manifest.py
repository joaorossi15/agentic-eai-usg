import csv
from pathlib import Path

REPETITIONS = 3

CONFIGURATIONS = [
    "full",
    "no_analysis",
    "no_revision",
    "no_validation",
    "single_pass",
]

MAIN_MODEL = "gpt-5.6-terra"

INPUT_PATH = Path("data/ablation_requirements.csv")
OUTPUT_PATH = Path("results/ablation_manifest.csv")

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
            raise ValueError("The ablation CSV does not contain a header.")

        missing = required_columns - set(reader.fieldnames)

        if missing:
            raise ValueError(
                "Missing required columns: "
                + ", ".join(sorted(missing))
            )

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
        for configuration in CONFIGURATIONS:
            for repetition in range(1, REPETITIONS + 1):

                rows.append({
                    "run_id": (
                        f"{req['id']}__"
                        f"{configuration}__"
                        f"{repetition}"
                    ),
                    "requirement_id": req["id"],
                    "principle": req["principle"],
                    "source_row": req["source_row"],
                    "requirement": req["requirement"],
                    "configuration": configuration,
                    "repetition": repetition,
                    "model": MAIN_MODEL,
                })

    return rows


def save_manifest(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "run_id",
        "requirement_id",
        "principle",
        "source_row",
        "requirement",
        "configuration",
        "repetition",
        "model",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    requirements = load_requirements(INPUT_PATH)

    if len(requirements) != EXPECTED_REQUIREMENTS:
        raise ValueError(
            f"Expected {EXPECTED_REQUIREMENTS} requirements, "
            f"found {len(requirements)}."
        )

    manifest = build_manifest(requirements)

    expected_runs = (
        EXPECTED_REQUIREMENTS
        * len(CONFIGURATIONS)
        * REPETITIONS
    )

    if len(manifest) != expected_runs:
        raise ValueError(
            f"Expected {expected_runs} runs, "
            f"generated {len(manifest)}."
        )

    run_ids = [row["run_id"] for row in manifest]

    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs detected.")

    save_manifest(manifest, OUTPUT_PATH)

    print(f"Loaded {len(requirements)} ablation requirements.")
    print(f"Configurations: {len(CONFIGURATIONS)}")
    print(f"Repetitions: {REPETITIONS}")
    print(f"Created {len(manifest)} planned runs.")
    print(f"Manifest saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
