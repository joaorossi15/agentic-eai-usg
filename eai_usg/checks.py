from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import (
    DeterministicCheckResult,
    EUS,
    RequirementAnalysis,
    TraceabilityCheckResult,
    TraceabilityMap,
)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def run_deterministic_checks(
    eus: EUS,
    duplicate_threshold: float = 0.90,
    description_overlap_threshold: float = 0.93,
) -> DeterministicCheckResult:
    structure_issues: list[str] = []
    redundancy_issues: list[str] = []

    if not eus.title.strip():
        structure_issues.append("Title is empty.")

    if not eus.description.strip():
        structure_issues.append("Description is empty.")

    if not eus.work_items:
        structure_issues.append("No work items were produced.")

    for i, item in enumerate(eus.work_items):
        if not item.strip():
            structure_issues.append(f"Work item {i + 1} is empty.")

    for i in range(len(eus.work_items)):
        for j in range(i + 1, len(eus.work_items)):
            score = _similarity(eus.work_items[i], eus.work_items[j])

            if score >= duplicate_threshold:
                redundancy_issues.append(
                    f"Work items {i + 1} and {j + 1} are near-duplicates "
                    f"(similarity={score:.2f})."
                )

    for i, item in enumerate(eus.work_items):
        score = _similarity(eus.description, item)

        if score >= description_overlap_threshold:
            redundancy_issues.append(
                f"Work item {i + 1} closely paraphrases the description "
                f"(similarity={score:.2f})."
            )

    return DeterministicCheckResult(
        passed=not structure_issues and not redundancy_issues,
        structure_issues=structure_issues,
        redundancy_issues=redundancy_issues,
    )


def run_traceability_checks(
    analysis: RequirementAnalysis,
    eus: EUS,
    traceability: TraceabilityMap,
) -> TraceabilityCheckResult:
    issues: list[str] = []

    obligation_ids = {obligation.id for obligation in analysis.obligations}

    if len(obligation_ids) != len(analysis.obligations):
        issues.append("Requirement analysis contains duplicate obligation IDs.")

    description_ids = traceability.description_obligation_ids

    if len(description_ids) != len(set(description_ids)):
        issues.append("Description traceability contains duplicate obligation IDs.")

    invalid_description_ids = [
        obligation_id
        for obligation_id in description_ids
        if obligation_id not in obligation_ids
    ]

    if invalid_description_ids:
        issues.append(
            f"Description references unknown obligation IDs: "
            f"{', '.join(invalid_description_ids)}."
        )

    traced_work_item_indices: set[int] = set()
    traced_obligation_ids: set[str] = set(description_ids)

    for trace in traceability.work_items:
        if trace.work_item_index < 0 or trace.work_item_index >= len(eus.work_items):
            issues.append(
                f"Traceability references nonexistent work item "
                f"{trace.work_item_index + 1}."
            )
            continue

        if trace.work_item_index in traced_work_item_indices:
            issues.append(
                f"Work item {trace.work_item_index + 1} has multiple traceability entries."
            )

        traced_work_item_indices.add(trace.work_item_index)

        if not trace.obligation_ids:
            issues.append(
                f"Work item {trace.work_item_index + 1} has no traced obligations."
            )

        if len(trace.obligation_ids) != len(set(trace.obligation_ids)):
            issues.append(
                f"Work item {trace.work_item_index + 1} traceability contains "
                f"duplicate obligation IDs."
            )

        invalid_ids = [
            obligation_id
            for obligation_id in trace.obligation_ids
            if obligation_id not in obligation_ids
        ]

        if invalid_ids:
            issues.append(
                f"Work item {trace.work_item_index + 1} references unknown "
                f"obligation IDs: {', '.join(invalid_ids)}."
            )

        traced_obligation_ids.update(trace.obligation_ids)

    for index in range(len(eus.work_items)):
        if index not in traced_work_item_indices:
            issues.append(f"Work item {index + 1} has no traceability entry.")

    valid_traced_obligation_ids = traced_obligation_ids & obligation_ids
    untraced_obligation_ids = obligation_ids - valid_traced_obligation_ids

    if untraced_obligation_ids:
        issues.append(
            f"Source obligations are not represented in the traceability map: "
            f"{', '.join(sorted(untraced_obligation_ids))}."
        )

    return TraceabilityCheckResult(
        passed=not issues,
        issues=issues,
    )
