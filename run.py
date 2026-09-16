from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from eai_usg.pipeline import EAIUSGPipeline
from eai_usg.schemas import EUS, EthicalRequirement, TraceabilityResult, ValidationResult


DEFAULT_DATASET = "data/human-study-dataset.csv"


def load_study_requirement(requirement_id: str, dataset_path: str) -> EthicalRequirement:
    path = Path(dataset_path)

    if not path.exists():
        raise FileNotFoundError(f"Human-study dataset not found at '{dataset_path}'.")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row["ID"].strip().upper() == requirement_id.strip().upper():
                return EthicalRequirement(
                    id=row["ID"].strip(),
                    text=row["Requirement"].strip(),
                )

    raise ValueError(f"Requirement '{requirement_id}' was not found in '{dataset_path}'.")


def list_study_requirements(dataset_path: str) -> None:
    path = Path(dataset_path)

    if not path.exists():
        raise FileNotFoundError(f"Human-study dataset not found at '{dataset_path}'.")

    print("\nAvailable Human-AI study requirements")
    print("=" * 70)

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            print(f"{row['ID']}: {row['Principle']}")

    print("=" * 70)


def print_requirement(requirement: EthicalRequirement) -> None:
    print("\nEthical requirement")
    print("=" * 70)
    print(f"ID: {requirement.id}")
    print(requirement.text)
    print("=" * 70)


def print_eus(eus: EUS, heading: str = "EUS") -> None:
    print(f"\n{heading}")
    print("=" * 70)
    print(f"Title: {eus.title}")
    print()
    print(eus.description)
    print()
    print("Work items:")

    for index, item in enumerate(eus.work_items, start=1):
        print(f"{index}. {item}")

    print("=" * 70)


def print_traceability(result: TraceabilityResult) -> None:
    analysis = result.analysis
    traceability = result.traceability

    print("\nInitial AI traceability")
    print("=" * 70)
    print("This traceability map refers to the initial AI-generated EUS.")

    print("\nSource obligations:")

    for obligation in analysis.obligations:
        print(f"  {obligation.id}: {obligation.text}")
        print(f"     Source: \"{obligation.source_span}\"")
        print(f"     Support: {obligation.support_type.value}")

    print("\nDescription:")

    if traceability.description_obligation_ids:
        print("  " + ", ".join(traceability.description_obligation_ids))
    else:
        print("  No obligation links.")

    print("\nWork items:")

    for trace in traceability.work_items:
        obligation_ids = ", ".join(trace.obligation_ids) or "No obligation links"
        print(f"  {trace.work_item_index + 1} -> {obligation_ids}")
        print(f"     {trace.explanation}")

    print("=" * 70)


def print_validation(validation: ValidationResult | None) -> None:
    print("\nValidation")
    print("=" * 70)

    if validation is None:
        print("The current EUS has not been validated.")
        print("=" * 70)
        return

    print(f"Clarity: {validation.clarity}/5")
    print(f"Completeness: {validation.completeness}/5")
    print(f"Actionability: {validation.actionability}/5")
    print(f"Testability: {validation.testability}/5")
    print(f"Faithfulness: {validation.faithfulness}/5")

    if validation.issues:
        print("\nIssues:")

        for index, issue in enumerate(validation.issues, start=1):
            print(f"{index}. [{issue.severity.value}] {issue.dimension.value}")
            print(f"   Problem: {issue.problem}")
            print(f"   Revision objective: {issue.recommended_change}")
    else:
        print("\nNo substantive issues identified.")

    print("=" * 70)


def edit_eus(eus: EUS) -> EUS:
    print("\nManual edit")
    print("Leave a field blank to keep its current value.")
    print("Enter '-' for a work item to remove it.")

    title_input = input(f"\nTitle [{eus.title}]: ").strip()
    title = title_input if title_input else eus.title

    description_input = input(f"\nDescription [{eus.description}]: ").strip()
    description = description_input if description_input else eus.description

    work_items = []

    print("\nExisting work items:")

    for index, item in enumerate(eus.work_items, start=1):
        value = input(f"{index}. [{item}]: ").strip()

        if value == "-":
            continue

        work_items.append(value if value else item)

    print("\nAdd work items. Leave blank when finished.")

    while True:
        value = input("New work item: ").strip()

        if not value:
            break

        work_items.append(value)

    if not work_items:
        print("An EUS must contain at least one work item. Keeping the previous work items.")
        work_items = eus.work_items

    return EUS(
        title=title,
        description=description,
        work_items=work_items,
    )


def save_current_state(
    requirement: EthicalRequirement,
    initial_eus: EUS,
    initial_traceability: TraceabilityResult,
    current_eus: EUS,
    current_validation: ValidationResult | None,
    backend: str,
    model: str,
) -> Path:
    output_dir = Path("outputs/interactive")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in requirement.id)
    path = output_dir / f"{timestamp}_{safe_id}.json"

    payload = {
        "requirement": requirement.model_dump(mode="json"),
        "backend": backend,
        "model": model,
        "initial_eus": initial_eus.model_dump(mode="json"),
        "initial_analysis": initial_traceability.analysis.model_dump(mode="json"),
        "initial_traceability": initial_traceability.traceability.model_dump(mode="json"),
        "current_eus": current_eus.model_dump(mode="json"),
        "current_validation": (
            current_validation.model_dump(mode="json")
            if current_validation is not None
            else None
        ),
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def get_requirement(args) -> EthicalRequirement:
    if args.requirement:
        requirement_id = args.id or "CUSTOM"

        return EthicalRequirement(
            id=requirement_id,
            text=args.requirement.strip(),
        )

    if args.id:
        return load_study_requirement(
            requirement_id=args.id,
            dataset_path=args.dataset,
        )

    print("\nRequirement source")
    print("1. Human-AI study dataset")
    print("2. Custom requirement")

    choice = input("\nChoice: ").strip()

    if choice == "1":
        list_study_requirements(args.dataset)
        requirement_id = input("\nRequirement ID: ").strip()

        if not requirement_id:
            raise ValueError("Requirement ID cannot be empty.")

        return load_study_requirement(
            requirement_id=requirement_id,
            dataset_path=args.dataset,
        )

    if choice == "2":
        requirement_id = input("Requirement ID [CUSTOM]: ").strip() or "CUSTOM"
        requirement_text = input("Ethical requirement: ").strip()

        if not requirement_text:
            raise ValueError("Ethical requirement cannot be empty.")

        return EthicalRequirement(
            id=requirement_id,
            text=requirement_text,
        )

    raise ValueError("Invalid requirement source.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id")
    parser.add_argument("--requirement")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--backend", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    requirement = get_requirement(args)

    pipeline = EAIUSGPipeline(
        backend=args.backend,
        model=args.model,
    )

    print_requirement(requirement)

    print("\nGenerating initial EUS...")
    initial_eus = pipeline.generate_eus(requirement=requirement)

    print("\nGenerating traceability...")
    initial_traceability = pipeline.trace_eus(
        requirement=requirement,
        eus=initial_eus,
    )

    current_eus = initial_eus.model_copy(deep=True)
    current_validation = None

    print_eus(current_eus, heading="Initial AI-generated EUS")
    print_traceability(initial_traceability)

    while True:
        print("\nWhat would you like to do?")
        print("1. Edit current EUS manually")
        print("2. Validate current EUS")
        print("3. Ask EAI-USG to propose a revision")
        print("4. Show current EUS")
        print("5. Show initial AI traceability")
        print("6. Show current validation")
        print("7. Save current state")
        print("8. Exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            edited_eus = edit_eus(current_eus)

            if edited_eus.model_dump() != current_eus.model_dump():
                current_eus = edited_eus
                current_validation = None
                print("\nEUS updated. Previous validation is now stale and was cleared.")
            else:
                print("\nNo changes made.")

        elif choice == "2":
            print("\nValidating current EUS...")

            current_validation = pipeline.validate_eus(
                requirement=requirement,
                eus=current_eus,
            )

            print_validation(current_validation)

        elif choice == "3":
            if current_validation is None:
                print("\nValidate the current EUS before requesting an AI revision.")
                continue

            print("\nOptional targeted revision instruction.")
            print("Leave blank to revise based only on the validation feedback.")

            instruction = input("> ").strip() or None

            print("\nGenerating proposed revision...")

            proposed_revision = pipeline.revise_eus(
                requirement=requirement,
                eus=current_eus,
                feedback=current_validation,
                revision_instruction=instruction,
            )

            print_eus(proposed_revision, heading="Proposed AI revision")

            decision = input("\nAccept this revision? [y/N]: ").strip().lower()

            if decision in {"y", "yes"}:
                current_eus = proposed_revision
                current_validation = None
                print("\nRevision accepted. The previous validation is now stale and was cleared.")
            else:
                print("\nRevision not accepted. The current EUS was left unchanged.")

        elif choice == "4":
            print_eus(current_eus, heading="Current EUS")

        elif choice == "5":
            print_traceability(initial_traceability)

        elif choice == "6":
            print_validation(current_validation)

        elif choice == "7":
            path = save_current_state(
                requirement=requirement,
                initial_eus=initial_eus,
                initial_traceability=initial_traceability,
                current_eus=current_eus,
                current_validation=current_validation,
                backend=pipeline.llm.backend,
                model=pipeline.llm.model,
            )

            print(f"\nCurrent state saved to: {path}")

        elif choice == "8":
            print("\nExiting EAI-USG.")
            break

        else:
            print("\nInvalid option.")


if __name__ == "__main__":
    main()
