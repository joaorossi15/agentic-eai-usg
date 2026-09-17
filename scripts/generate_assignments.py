from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from study.design import create_schedule, summarize_schedule


DEFAULT_PARTICIPANTS = 32
DEFAULT_OUTPUT_DIR = "outputs/study_design"


def save_json(assignments, output_dir: Path) -> Path:
    path = output_dir / "participant_assignments.json"

    payload = [
        assignment.model_dump(mode="json")
        for assignment in assignments
    ]

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def save_csv(assignments, output_dir: Path) -> Path:
    path = output_dir / "participant_assignments.csv"

    fieldnames = [
        "participant_id",
        "participant_number",
        "counterbalance_block",
        "schedule_position",
        "condition_order",
        "task_number",
        "requirement_id",
        "principle",
        "condition",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for assignment in assignments:
            condition_order = " -> ".join(
                condition.value
                for condition in assignment.condition_order
            )

            for task in assignment.tasks:
                writer.writerow(
                    {
                        "participant_id": assignment.participant_id,
                        "participant_number": assignment.participant_number,
                        "counterbalance_block": assignment.counterbalance_block,
                        "schedule_position": assignment.schedule_position,
                        "condition_order": condition_order,
                        "task_number": task.task_number,
                        "requirement_id": task.requirement_id,
                        "principle": task.principle.value,
                        "condition": task.condition.value,
                    }
                )

    return path


def save_summary(summary: dict, output_dir: Path) -> Path:
    path = output_dir / "assignment_summary.json"

    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def print_summary(summary: dict) -> None:
    print("\nStudy assignment summary")
    print("=" * 70)
    print(f"Participants: {summary['participants']}")

    print("\nCondition order:")
    print(f"  Manual first: {summary['condition_order']['manual_first']}")
    print(f"  EAI-USG first: {summary['condition_order']['eai_usg_first']}")

    print("\nRequirement exposure:")
    print(f"{'Requirement':<12} {'Manual':>8} {'EAI-USG':>8}")

    for requirement_id, counts in summary["requirements"].items():
        print(
            f"{requirement_id:<12} "
            f"{counts['manual']:>8} "
            f"{counts['eai_usg']:>8}"
        )

    print("\nPrinciple exposure:")
    print(f"{'Principle':<25} {'Manual':>8} {'EAI-USG':>8}")

    for principle, counts in summary["principles"].items():
        print(
            f"{principle:<25} "
            f"{counts['manual']:>8} "
            f"{counts['eai_usg']:>8}"
        )

    print("=" * 70)


def validate_schedule(assignments, summary: dict) -> None:
    if not assignments:
        raise ValueError("No participant assignments were generated.")

    if len(assignments) % 16 == 0:
        expected_per_requirement_per_condition = len(assignments) * 3 // 16

        for requirement_id, counts in summary["requirements"].items():
            if counts["manual"] != expected_per_requirement_per_condition:
                raise ValueError(
                    f"{requirement_id} has unexpected Manual exposure: "
                    f"{counts['manual']} instead of "
                    f"{expected_per_requirement_per_condition}."
                )

            if counts["eai_usg"] != expected_per_requirement_per_condition:
                raise ValueError(
                    f"{requirement_id} has unexpected EAI-USG exposure: "
                    f"{counts['eai_usg']} instead of "
                    f"{expected_per_requirement_per_condition}."
                )

    condition_order = summary["condition_order"]

    if abs(
        condition_order["manual_first"]
        - condition_order["eai_usg_first"]
    ) > 1:
        raise ValueError("Condition-order counterbalancing is unexpectedly uneven.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--participants",
        type=int,
        default=DEFAULT_PARTICIPANTS,
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
    )
    args = parser.parse_args()

    if args.participants < 1:
        raise ValueError("Participant count must be at least 1.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    assignments = create_schedule(args.participants)
    summary = summarize_schedule(assignments)

    validate_schedule(assignments, summary)

    json_path = save_json(assignments, output_dir)
    csv_path = save_csv(assignments, output_dir)
    summary_path = save_summary(summary, output_dir)

    print_summary(summary)

    print("\nFiles generated:")
    print(f"  Assignments JSON: {json_path}")
    print(f"  Assignments CSV:  {csv_path}")
    print(f"  Summary:          {summary_path}")


if __name__ == "__main__":
    main()
