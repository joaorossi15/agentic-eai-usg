from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import DeterministicCheckResult, EUS


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(
        None,
        _normalize(a),
        _normalize(b),
    ).ratio()


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
        structure_issues.append(
            "No work items or acceptance criteria were produced."
        )

    for i, item in enumerate(eus.work_items):
        if not item.strip():
            structure_issues.append(
                f"Work item {i + 1} is empty."
            )

    for i in range(len(eus.work_items)):
        for j in range(i + 1, len(eus.work_items)):

            score = _similarity(
                eus.work_items[i],
                eus.work_items[j],
            )

            if score >= duplicate_threshold:
                redundancy_issues.append(
                    f"Work items {i + 1} and {j + 1} are near-duplicates "
                    f"(similarity={score:.2f})."
                )

    for i, item in enumerate(eus.work_items):

        score = _similarity(
            eus.description,
            item,
        )

        if score >= description_overlap_threshold:
            redundancy_issues.append(
                f"Work item {i + 1} closely paraphrases the description "
                f"(similarity={score:.2f})."
            )

    return DeterministicCheckResult(
        passed=(
            not structure_issues
            and not redundancy_issues
        ),
        structure_issues=structure_issues,
        redundancy_issues=redundancy_issues,
    )
