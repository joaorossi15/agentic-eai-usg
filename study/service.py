from __future__ import annotations

from typing import Any

from eai_usg.pipeline import EAIUSGPipeline
from eai_usg.schemas import EUS, ValidationResult
from study.design import StudyCondition
from study.storage import (
    begin_ai_interaction,
    complete_participant,
    complete_revision,
    complete_validation,
    create_participant,
    get_ai_interactions,
    get_participant,
    get_task,
    get_tasks,
    initialize_participant_tasks,
    load_frozen_artifact,
    save_current_eus,
    save_event,
    set_revision_decision,
    start_participant,
    start_task as storage_start_task,
    submit_task as storage_submit_task,
)


def _normalize_participant_id(participant_id: str) -> str:
    participant_id = participant_id.strip().upper()

    if not participant_id:
        raise ValueError("Participant ID cannot be empty.")

    return participant_id


def _get_task_or_raise(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)

    if task is None:
        raise ValueError(f"Task '{task_id}' does not exist.")

    return task


def _require_in_progress(task_id: str) -> dict[str, Any]:
    task = _get_task_or_raise(task_id)

    if task["status"] != "in_progress":
        raise ValueError(f"Task '{task_id}' is not currently in progress.")

    return task


def _require_eai_usg_task(task_id: str) -> dict[str, Any]:
    task = _require_in_progress(task_id)

    if task["condition"] != StudyCondition.eai_usg.value:
        raise ValueError("This operation is available only in EAI-USG tasks.")

    return task


def _current_eus(task: dict[str, Any]) -> EUS:
    raw_eus = task["current_eus"]

    if raw_eus is None:
        raise ValueError("The current EUS is empty.")

    return EUS.model_validate(raw_eus)


def _get_requirement(task: dict[str, Any]):
    artifact = load_frozen_artifact(task["requirement_id"])
    return artifact["requirement"]


def _find_interaction(
    interactions: list[dict[str, Any]],
    interaction_type: str,
) -> dict[str, Any] | None:
    for interaction in interactions:
        if interaction["interaction_type"] == interaction_type:
            return interaction

    return None


def _build_task_view(task: dict[str, Any]) -> dict[str, Any]:
    artifact = load_frozen_artifact(task["requirement_id"])
    interactions = get_ai_interactions(str(task["task_id"]))

    validation = _find_interaction(interactions, "validation")
    revision = _find_interaction(interactions, "revision")

    traceability = None

    if task["condition"] == StudyCondition.eai_usg.value:
        traceability = {
            "analysis": task["initial_analysis"],
            "traceability": task["initial_traceability"],
        }

    return {
        "task_id": str(task["task_id"]),
        "task_number": task["task_number"],
        "requirement": artifact["requirement"].model_dump(mode="json"),
        "principle": task["principle"],
        "condition": task["condition"],
        "status": task["status"],
        "initial_eus": task["initial_eus"],
        "initial_traceability": traceability,
        "current_eus": task["current_eus"],
        "final_eus": task["final_eus"],
        "validation": (
            validation["validation_output"]
            if validation is not None and validation["completed_at"] is not None
            else None
        ),
        "revision": (
            {
                "interaction_id": str(revision["interaction_id"]),
                "instruction": revision["revision_instruction"],
                "output": revision["revision_output"],
                "decision": revision["revision_decision"],
            }
            if revision is not None and revision["completed_at"] is not None
            else None
        ),
        "validation_used": validation is not None,
        "revision_used": revision is not None,
    }


def start_study(participant_id: str) -> dict[str, Any]:
    participant_id = _normalize_participant_id(participant_id)

    create_participant(participant_id)
    initialize_participant_tasks(participant_id)
    start_participant(participant_id)

    return get_study_state(participant_id)


def get_study_state(participant_id: str) -> dict[str, Any]:
    participant_id = _normalize_participant_id(participant_id)
    participant = get_participant(participant_id)

    if participant is None:
        raise ValueError(f"Participant '{participant_id}' does not exist.")

    tasks = get_tasks(participant_id)

    next_task_number = None

    for task in tasks:
        if task["status"] != "completed":
            next_task_number = task["task_number"]
            break

    return {
        "participant_id": participant_id,
        "status": participant["status"],
        "started_at": participant["started_at"],
        "completed_at": participant["completed_at"],
        "next_task_number": next_task_number,
        "tasks": [
            {
                "task_id": str(task["task_id"]),
                "task_number": task["task_number"],
                "requirement_id": task["requirement_id"],
                "principle": task["principle"],
                "condition": task["condition"],
                "status": task["status"],
            }
            for task in tasks
        ],
    }


def get_next_task(participant_id: str) -> dict[str, Any] | None:
    participant_id = _normalize_participant_id(participant_id)
    tasks = get_tasks(participant_id)

    for task in tasks:
        if task["status"] != "completed":
            return _build_task_view(task)

    return None


def open_task(participant_id: str, task_number: int) -> dict[str, Any]:
    participant_id = _normalize_participant_id(participant_id)
    tasks = get_tasks(participant_id)

    selected = None

    for task in tasks:
        if task["task_number"] < task_number and task["status"] != "completed":
            raise ValueError("Previous tasks must be completed before starting this task.")

        if task["task_number"] == task_number:
            selected = task

    if selected is None:
        raise ValueError(f"Task {task_number} does not exist for participant '{participant_id}'.")

    if selected["status"] == "completed":
        raise ValueError("Completed tasks cannot be reopened.")

    was_not_started = selected["status"] == "not_started"
    selected = storage_start_task(str(selected["task_id"]))

    if was_not_started:
        save_event(str(selected["task_id"]), "task_started")

    return _build_task_view(selected)


def update_editor(
    task_id: str,
    draft: dict[str, Any],
    field: str | None = None,
) -> None:
    _require_in_progress(task_id)

    normalized = {
        "title": str(draft.get("title", "")),
        "description": str(draft.get("description", "")),
        "work_items": list(draft.get("work_items", [])),
    }

    save_current_eus(task_id, normalized)

    payload = {
        "field": field,
        "eus": normalized,
    }

    save_event(task_id, "editor_changed", payload)


def request_validation(task_id: str) -> ValidationResult:
    task = _require_eai_usg_task(task_id)
    eus = _current_eus(task)
    requirement = _get_requirement(task)
    interactions = get_ai_interactions(task_id)

    existing = _find_interaction(interactions, "validation")

    if existing is not None and existing["completed_at"] is not None:
        raise ValueError("The validation capability has already been used for this task.")

    if existing is None:
        interaction_id = begin_ai_interaction(
            task_id=task_id,
            interaction_type="validation",
            input_eus=eus,
        )

        save_event(
            task_id,
            "validation_requested",
            {"interaction_id": interaction_id},
        )
    else:
        interaction_id = str(existing["interaction_id"])

    pipeline = EAIUSGPipeline()
    response_start = len(pipeline.llm.response_ids)

    try:
        validation = pipeline.validate_eus(
            requirement=requirement,
            eus=eus,
        )

        response_ids = pipeline.llm.response_ids[response_start:]

        complete_validation(
            interaction_id=interaction_id,
            validation_output=validation.model_dump(mode="json"),
            api_response_ids=response_ids,
        )

        save_event(
            task_id,
            "validation_completed",
            {
                "interaction_id": interaction_id,
                "validation": validation.model_dump(mode="json"),
            },
        )

        return validation

    except Exception as exc:
        save_event(
            task_id,
            "validation_failed",
            {
                "interaction_id": interaction_id,
                "error_type": type(exc).__name__,
            },
        )
        raise


def request_revision(
    task_id: str,
    revision_instruction: str | None = None,
) -> dict[str, Any]:
    task = _require_eai_usg_task(task_id)
    eus = _current_eus(task)
    requirement = _get_requirement(task)
    interactions = get_ai_interactions(task_id)

    validation_interaction = _find_interaction(interactions, "validation")

    if validation_interaction is None or validation_interaction["completed_at"] is None:
        raise ValueError("The current EUS must be validated before requesting a revision.")

    existing_revision = _find_interaction(interactions, "revision")

    if existing_revision is not None and existing_revision["completed_at"] is not None:
        raise ValueError("The revision capability has already been used for this task.")

    validation = ValidationResult.model_validate(
        validation_interaction["validation_output"]
    )

    if revision_instruction is not None:
        revision_instruction = revision_instruction.strip() or None

    if existing_revision is None:
        interaction_id = begin_ai_interaction(
            task_id=task_id,
            interaction_type="revision",
            input_eus=eus,
            validation_feedback=validation.model_dump(mode="json"),
            revision_instruction=revision_instruction,
        )

        save_event(
            task_id,
            "revision_requested",
            {
                "interaction_id": interaction_id,
                "revision_instruction": revision_instruction,
            },
        )
    else:
        interaction_id = str(existing_revision["interaction_id"])

    pipeline = EAIUSGPipeline()
    response_start = len(pipeline.llm.response_ids)

    try:
        revision = pipeline.revise_eus(
            requirement=requirement,
            eus=eus,
            feedback=validation,
            revision_instruction=revision_instruction,
        )

        response_ids = pipeline.llm.response_ids[response_start:]

        complete_revision(
            interaction_id=interaction_id,
            revision_output=revision,
            api_response_ids=response_ids,
        )

        save_event(
            task_id,
            "revision_completed",
            {
                "interaction_id": interaction_id,
                "revision": revision.model_dump(mode="json"),
            },
        )

        return {
            "interaction_id": interaction_id,
            "revision": revision.model_dump(mode="json"),
        }

    except Exception as exc:
        save_event(
            task_id,
            "revision_failed",
            {
                "interaction_id": interaction_id,
                "error_type": type(exc).__name__,
            },
        )
        raise


def accept_revision(task_id: str, interaction_id: str) -> EUS:
    _require_eai_usg_task(task_id)
    interactions = get_ai_interactions(task_id)

    revision = next(
        (
            interaction
            for interaction in interactions
            if str(interaction["interaction_id"]) == interaction_id
            and interaction["interaction_type"] == "revision"
        ),
        None,
    )

    if revision is None:
        raise ValueError("Revision interaction was not found.")

    if revision["completed_at"] is None or revision["revision_output"] is None:
        raise ValueError("The revision has not been completed.")

    if revision["revision_decision"] is not None:
        raise ValueError("A decision has already been recorded for this revision.")

    revised_eus = EUS.model_validate(revision["revision_output"])

    set_revision_decision(interaction_id, "accepted")
    save_current_eus(task_id, revised_eus)

    save_event(
        task_id,
        "revision_accepted",
        {
            "interaction_id": interaction_id,
            "eus": revised_eus.model_dump(mode="json"),
        },
    )

    return revised_eus


def reject_revision(task_id: str, interaction_id: str) -> None:
    _require_eai_usg_task(task_id)
    interactions = get_ai_interactions(task_id)

    revision = next(
        (
            interaction
            for interaction in interactions
            if str(interaction["interaction_id"]) == interaction_id
            and interaction["interaction_type"] == "revision"
        ),
        None,
    )

    if revision is None:
        raise ValueError("Revision interaction was not found.")

    if revision["completed_at"] is None:
        raise ValueError("The revision has not been completed.")

    if revision["revision_decision"] is not None:
        raise ValueError("A decision has already been recorded for this revision.")

    set_revision_decision(interaction_id, "rejected")

    save_event(
        task_id,
        "revision_rejected",
        {"interaction_id": interaction_id},
    )


def pause_task(task_id: str) -> None:
    _require_in_progress(task_id)
    save_event(task_id, "task_paused")


def resume_task(task_id: str) -> None:
    _require_in_progress(task_id)
    save_event(task_id, "task_resumed")


def submit_task(
    task_id: str,
    final_draft: dict[str, Any],
    inactive_seconds: float = 0,
) -> dict[str, Any]:
    task = _require_in_progress(task_id)

    pending_interactions = [
        interaction
        for interaction in get_ai_interactions(task_id)
        if interaction["completed_at"] is None
    ]

    if pending_interactions:
        raise ValueError("The task cannot be submitted while an AI operation is pending.")

    final_eus = EUS.model_validate(final_draft)

    result = storage_submit_task(
        task_id=task_id,
        final_eus=final_eus,
        inactive_seconds=inactive_seconds,
    )

    save_event(
        task_id,
        "task_submitted",
        {
            "final_eus": final_eus.model_dump(mode="json"),
            "active_authoring_seconds": result["active_authoring_seconds"],
            "ai_wait_seconds": result["ai_wait_seconds"],
            "inactive_seconds": result["inactive_seconds"],
        },
    )

    participant_id = task["participant_id"]
    tasks = get_tasks(participant_id)

    if all(item["status"] == "completed" for item in tasks):
        complete_participant(participant_id)

    return {
        "task": _build_task_view(result),
        "study_completed": all(item["status"] == "completed" for item in get_tasks(participant_id)),
    }
