from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eai_usg.io import save_run
from eai_usg.pipeline import EAIUSGPipeline, WorkflowConfig
from eai_usg.schemas import EUS, EthicalRequirement


def print_eus(eus: EUS) -> None:
    print("\nEUS")
    print("=" * 70)
    print(f"Title: {eus.title}")
    print()
    print(eus.description)
    print()
    print("Work items:")

    for index, item in enumerate(eus.work_items, start=1):
        print(f"{index}. {item}")

    print("=" * 70)


def print_traceability(traceability) -> None:
    print("\nTraceability")
    print("=" * 70)

    if traceability is None:
        print("No current traceability map is available.")
        return

    if traceability.description_obligation_ids:
        print("Description:")
        print("  " + ", ".join(traceability.description_obligation_ids))
    else:
        print("Description:")
        print("  No obligation links.")

    print("\nWork items:")

    for trace in traceability.work_items:
        obligation_ids = ", ".join(trace.obligation_ids)
        print(f"  {trace.work_item_index + 1} -> {obligation_ids}")
        print(f"     {trace.explanation}")

    print("=" * 70)


def print_validation(validation) -> None:
    print("\nValidation")
    print("=" * 70)

    if validation is None:
        print("The current EUS has not been validated.")
        return

    print(f"Passed: {validation.passed}")
    print(f"Semantic gate: {validation.semantic_gate_passed}")
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
        print("\nNo substantive issues.")

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
    requirement,
    analysis,
    eus,
    traceability,
    validation,
    model,
) -> Path:
    output_dir = Path("outputs/interactive")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in requirement.id)
    path = output_dir / f"{timestamp}_{safe_id}.json"

    payload = {
        "requirement": requirement.model_dump(mode="json"),
        "model": model,
        "analysis": analysis.model_dump(mode="json") if analysis is not None else None,
        "eus": eus.model_dump(mode="json"),
        "traceability": traceability.model_dump(mode="json") if traceability is not None else None,
        "validation": validation.model_dump(mode="json") if validation is not None else None,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id")
    parser.add_argument("--requirement")
    parser.add_argument(
        "--config",
        choices=[config.value for config in WorkflowConfig],
        default=WorkflowConfig.FULL.value,
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args()

    requirement_id = args.id

    if not requirement_id:
        requirement_id = input("Requirement ID: ").strip()

    requirement_text = args.requirement

    if not requirement_text:
        requirement_text = input("Ethical requirement: ").strip()

    if not requirement_id:
        raise ValueError("Requirement ID cannot be empty.")

    if not requirement_text:
        raise ValueError("Ethical requirement cannot be empty.")

    pipeline = EAIUSGPipeline(
        model=args.model,
        quality_threshold=args.threshold,
    )

    requirement = EthicalRequirement(
        id=requirement_id,
        text=requirement_text,
    )

    print("\nGenerating EUS...")

    result = pipeline.run(
        requirement=requirement,
        config=WorkflowConfig(args.config),
    )

    initial_run_path = save_run(result)

    analysis = result.analysis
    current_eus = result.final_eus
    current_traceability = result.final_traceability
    current_validation = result.final_validation or result.validation

    print_eus(current_eus)
    print_traceability(current_traceability)
    print_validation(current_validation)

    print(f"\nInitial run saved to: {initial_run_path}")

    while True:
        print("\nWhat would you like to do?")
        print("1. Edit EUS manually")
        print("2. Validate current EUS")
        print("3. Ask EAI-USG to revise")
        print("4. Show current EUS")
        print("5. Show traceability")
        print("6. Show validation")
        print("7. Save current state")
        print("8. Exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            edited_eus = edit_eus(current_eus)

            if edited_eus.model_dump() != current_eus.model_dump():
                current_eus = edited_eus
                current_traceability = None
                current_validation = None
                print("\nEUS updated. Previous traceability and validation are now stale and were cleared.")
            else:
                print("\nNo changes made.")

        elif choice == "2":
            print("\nValidating current EUS...")

            validation_result = pipeline.validate_eus(
                requirement=requirement,
                eus=current_eus,
                analysis=analysis,
                traceability=current_traceability,
            )

            analysis = validation_result.analysis
            current_validation = validation_result.validation

            print_validation(current_validation)

        elif choice == "3":
            print("\nOptional revision instruction.")
            print("Leave blank to revise only from validation feedback.")

            instruction = input("> ").strip() or None

            if current_validation is not None and current_validation.passed and instruction is None:
                print("\nThe current EUS already passes validation. Provide a revision instruction if you still want EAI-USG to revise it.")
                continue

            print("\nRevising EUS...")

            try:
                revision_result = pipeline.revise_eus(
                    requirement=requirement,
                    eus=current_eus,
                    revision_instruction=instruction,
                    analysis=analysis,
                    traceability=current_traceability,
                )
            except ValueError as exc:
                print(f"\nRevision not performed: {exc}")
                continue

            analysis = revision_result.analysis
            current_eus = revision_result.revised_eus
            current_traceability = revision_result.revised_traceability
            current_validation = revision_result.final_validation

            print_eus(current_eus)
            print_traceability(current_traceability)
            print_validation(current_validation)

        elif choice == "4":
            print_eus(current_eus)

        elif choice == "5":
            print_traceability(current_traceability)

        elif choice == "6":
            print_validation(current_validation)

        elif choice == "7":
            path = save_current_state(
                requirement=requirement,
                analysis=analysis,
                eus=current_eus,
                traceability=current_traceability,
                validation=current_validation,
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
