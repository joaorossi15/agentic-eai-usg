from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from eai_usg.schemas import EUS, EthicalRequirement, RequirementAnalysis, TraceabilityMap
from study.design import ParticipantAssignment, StudyCondition


load_dotenv()

DEFAULT_ASSIGNMENTS_PATH = "outputs/study_design/participant_assignments.json"
DEFAULT_ARTIFACTS_DIR = "outputs/human_study"


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return database_url


engine: Engine = create_engine(
    _get_database_url(),
    pool_pre_ping=True,
)


def test_connection() -> None:
    with engine.connect() as connection:
        value = connection.execute(text("SELECT 1")).scalar_one()

    if value != 1:
        raise RuntimeError("Unexpected database response.")

    print("Database connection successful.")


def _json(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    return json.dumps(value, ensure_ascii=False)


def load_assignment(
    participant_id: str,
    assignments_path: str = DEFAULT_ASSIGNMENTS_PATH,
) -> ParticipantAssignment:
    path = Path(assignments_path)

    if not path.exists():
        raise FileNotFoundError(f"Assignment file not found at '{assignments_path}'.")

    data = json.loads(path.read_text(encoding="utf-8"))

    for raw_assignment in data:
        if raw_assignment["participant_id"] == participant_id:
            return ParticipantAssignment.model_validate(raw_assignment)

    raise ValueError(f"No study assignment found for participant '{participant_id}'.")


def load_frozen_artifact(
    requirement_id: str,
    artifacts_dir: str = DEFAULT_ARTIFACTS_DIR,
) -> dict[str, Any]:
    path = Path(artifacts_dir) / f"{requirement_id}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Frozen artifact for '{requirement_id}' not found at '{path}'."
        )

    artifact = json.loads(path.read_text(encoding="utf-8"))

    requirement = EthicalRequirement.model_validate(artifact["requirement"])
    initial_eus = EUS.model_validate(artifact["initial_eus"])
    analysis = RequirementAnalysis.model_validate(artifact["analysis"])
    traceability = TraceabilityMap.model_validate(artifact["traceability"])

    if requirement.id != requirement_id:
        raise ValueError(
            f"Frozen artifact ID mismatch: expected '{requirement_id}', "
            f"found '{requirement.id}'."
        )

    return {
        "requirement": requirement,
        "initial_eus": initial_eus,
        "analysis": analysis,
        "traceability": traceability,
    }


def save_background(
    participant_id: str,
    background: dict[str, Any],
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE participants
                SET background = CAST(:background AS JSONB)
                WHERE participant_id = :participant_id
                """
            ),
            {
                "participant_id": participant_id,
                "background": _json(background),
            },
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Participant '{participant_id}' does not exist."
            )

def create_participant(
    participant_id: str,
    assignments_path: str = DEFAULT_ASSIGNMENTS_PATH,
) -> dict[str, Any]:
    assignment = load_assignment(
        participant_id=participant_id,
        assignments_path=assignments_path,
    )

    with engine.begin() as connection:
        existing = connection.execute(
            text(
                """
                SELECT *
                FROM participants
                WHERE participant_id = :participant_id
                """
            ),
            {"participant_id": participant_id},
        ).mappings().first()

        if existing is not None:
            return dict(existing)

        participant = connection.execute(
            text(
                """
                INSERT INTO participants (
                    participant_id,
                    participant_number
                )
                VALUES (
                    :participant_id,
                    :participant_number
                )
                RETURNING *
                """
            ),
            {
                "participant_id": assignment.participant_id,
                "participant_number": assignment.participant_number,
            },
        ).mappings().one()

    return dict(participant)


def initialize_participant_tasks(
    participant_id: str,
    assignments_path: str = DEFAULT_ASSIGNMENTS_PATH,
    artifacts_dir: str = DEFAULT_ARTIFACTS_DIR,
) -> list[dict[str, Any]]:
    assignment = load_assignment(
        participant_id=participant_id,
        assignments_path=assignments_path,
    )

    create_participant(
        participant_id=participant_id,
        assignments_path=assignments_path,
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE participant_id = :participant_id
                """
            ),
            {"participant_id": participant_id},
        ).scalar_one()

        if existing_count:
            if existing_count != 6:
                raise RuntimeError(
                    f"Participant '{participant_id}' already has "
                    f"{existing_count} tasks instead of 6."
                )

            rows = connection.execute(
                text(
                    """
                    SELECT *
                    FROM tasks
                    WHERE participant_id = :participant_id
                    ORDER BY task_number
                    """
                ),
                {"participant_id": participant_id},
            ).mappings().all()

            return [dict(row) for row in rows]

        for assigned_task in assignment.tasks:
            initial_eus = None
            initial_analysis = None
            initial_traceability = None
            current_eus = None

            if assigned_task.condition == StudyCondition.eai_usg:
                artifact = load_frozen_artifact(
                    requirement_id=assigned_task.requirement_id,
                    artifacts_dir=artifacts_dir,
                )

                initial_eus = artifact["initial_eus"]
                initial_analysis = artifact["analysis"]
                initial_traceability = artifact["traceability"]
                current_eus = initial_eus

            connection.execute(
                text(
                    """
                    INSERT INTO tasks (
                        participant_id,
                        task_number,
                        requirement_id,
                        principle,
                        condition,
                        initial_eus,
                        initial_analysis,
                        initial_traceability,
                        current_eus
                    )
                    VALUES (
                        :participant_id,
                        :task_number,
                        :requirement_id,
                        :principle,
                        :condition,
                        CAST(:initial_eus AS JSONB),
                        CAST(:initial_analysis AS JSONB),
                        CAST(:initial_traceability AS JSONB),
                        CAST(:current_eus AS JSONB)
                    )
                    """
                ),
                {
                    "participant_id": participant_id,
                    "task_number": assigned_task.task_number,
                    "requirement_id": assigned_task.requirement_id,
                    "principle": assigned_task.principle.value,
                    "condition": assigned_task.condition.value,
                    "initial_eus": _json(initial_eus),
                    "initial_analysis": _json(initial_analysis),
                    "initial_traceability": _json(initial_traceability),
                    "current_eus": _json(current_eus),
                },
            )

        rows = connection.execute(
            text(
                """
                SELECT *
                FROM tasks
                WHERE participant_id = :participant_id
                ORDER BY task_number
                """
            ),
            {"participant_id": participant_id},
        ).mappings().all()

    return [dict(row) for row in rows]


def get_participant(participant_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT *
                FROM participants
                WHERE participant_id = :participant_id
                """
            ),
            {"participant_id": participant_id},
        ).mappings().first()

    return dict(row) if row is not None else None


def get_tasks(participant_id: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM tasks
                WHERE participant_id = :participant_id
                ORDER BY task_number
                """
            ),
            {"participant_id": participant_id},
        ).mappings().all()

    return [dict(row) for row in rows]


def get_task(task_id: str) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT *
                FROM tasks
                WHERE task_id = :task_id
                """
            ),
            {"task_id": task_id},
        ).mappings().first()

    return dict(row) if row is not None else None


def start_participant(participant_id: str) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE participants
                SET
                    status = 'in_progress',
                    started_at = COALESCE(started_at, NOW())
                WHERE participant_id = :participant_id
                  AND status != 'completed'
                """
            ),
            {"participant_id": participant_id},
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Participant '{participant_id}' does not exist or is already completed."
            )


def start_task(task_id: str) -> dict[str, Any]:
    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                UPDATE tasks
                SET
                    status = 'in_progress',
                    started_at = COALESCE(started_at, NOW())
                WHERE task_id = :task_id
                  AND status != 'completed'
                RETURNING *
                """
            ),
            {"task_id": task_id},
        ).mappings().first()

        if row is None:
            raise ValueError(f"Task '{task_id}' does not exist or is already completed.")

    return dict(row)


def save_current_eus(
    task_id: str,
    eus: EUS | dict[str, Any],
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE tasks
                SET current_eus = CAST(:current_eus AS JSONB)
                WHERE task_id = :task_id
                  AND status != 'completed'
                """
            ),
            {
                "task_id": task_id,
                "current_eus": _json(eus),
            },
        )

        if result.rowcount != 1:
            raise ValueError(f"Task '{task_id}' does not exist or is already completed.")


def save_event(
    task_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    with engine.begin() as connection:
        event_id = connection.execute(
            text(
                """
                INSERT INTO events (
                    task_id,
                    event_type,
                    event_timestamp,
                    payload
                )
                VALUES (
                    :task_id,
                    :event_type,
                    NOW(),
                    CAST(:payload AS JSONB)
                )
                RETURNING event_id
                """
            ),
            {
                "task_id": task_id,
                "event_type": event_type,
                "payload": _json(payload or {}),
            },
        ).scalar_one()

    return str(event_id)


def begin_ai_interaction(
    task_id: str,
    interaction_type: str,
    input_eus: EUS,
    validation_feedback: dict[str, Any] | None = None,
    revision_instruction: str | None = None,
) -> str:
    if interaction_type not in {"validation", "revision"}:
        raise ValueError("interaction_type must be 'validation' or 'revision'.")

    with engine.begin() as connection:
        task = connection.execute(
            text(
                """
                SELECT condition, status
                FROM tasks
                WHERE task_id = :task_id
                FOR UPDATE
                """
            ),
            {"task_id": task_id},
        ).mappings().first()

        if task is None:
            raise ValueError(f"Task '{task_id}' does not exist.")

        if task["condition"] != StudyCondition.eai_usg.value:
            raise ValueError("AI interactions are not allowed in Manual tasks.")

        if task["status"] == "completed":
            raise ValueError("AI interactions are not allowed after task submission.")

        interaction_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM ai_interactions
                WHERE task_id = :task_id
                  AND interaction_type = :interaction_type
                """
            ),
            {
                "task_id": task_id,
                "interaction_type": interaction_type,
            },
        ).scalar_one()

        if interaction_count >= 1:
            raise ValueError(
                f"Task '{task_id}' already contains an AI {interaction_type} interaction."
            )

        if interaction_type == "revision":
            validation_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM ai_interactions
                    WHERE task_id = :task_id
                      AND interaction_type = 'validation'
                      AND completed_at IS NOT NULL
                    """
                ),
                {"task_id": task_id},
            ).scalar_one()

            if validation_count == 0:
                raise ValueError("AI revision requires a completed validation first.")

        interaction_id = connection.execute(
            text(
                """
                INSERT INTO ai_interactions (
                    task_id,
                    interaction_type,
                    requested_at,
                    input_eus,
                    validation_feedback,
                    revision_instruction
                )
                VALUES (
                    :task_id,
                    :interaction_type,
                    NOW(),
                    CAST(:input_eus AS JSONB),
                    CAST(:validation_feedback AS JSONB),
                    :revision_instruction
                )
                RETURNING interaction_id
                """
            ),
            {
                "task_id": task_id,
                "interaction_type": interaction_type,
                "input_eus": _json(input_eus),
                "validation_feedback": _json(validation_feedback),
                "revision_instruction": revision_instruction,
            },
        ).scalar_one()

    return str(interaction_id)


def complete_validation(
    interaction_id: str,
    validation_output: dict[str, Any],
    api_response_ids: list[str],
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE ai_interactions
                SET
                    completed_at = NOW(),
                    latency_seconds = EXTRACT(
                        EPOCH FROM (NOW() - requested_at)
                    ),
                    validation_output = CAST(:validation_output AS JSONB),
                    api_response_ids = CAST(:api_response_ids AS JSONB)
                WHERE interaction_id = :interaction_id
                  AND interaction_type = 'validation'
                  AND completed_at IS NULL
                """
            ),
            {
                "interaction_id": interaction_id,
                "validation_output": _json(validation_output),
                "api_response_ids": _json(api_response_ids),
            },
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Validation interaction '{interaction_id}' does not exist "
                "or has already been completed."
            )


def complete_revision(
    interaction_id: str,
    revision_output: EUS,
    api_response_ids: list[str],
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE ai_interactions
                SET
                    completed_at = NOW(),
                    latency_seconds = EXTRACT(
                        EPOCH FROM (NOW() - requested_at)
                    ),
                    revision_output = CAST(:revision_output AS JSONB),
                    api_response_ids = CAST(:api_response_ids AS JSONB)
                WHERE interaction_id = :interaction_id
                  AND interaction_type = 'revision'
                  AND completed_at IS NULL
                """
            ),
            {
                "interaction_id": interaction_id,
                "revision_output": _json(revision_output),
                "api_response_ids": _json(api_response_ids),
            },
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Revision interaction '{interaction_id}' does not exist "
                "or has already been completed."
            )


def set_revision_decision(
    interaction_id: str,
    decision: str,
) -> None:
    if decision not in {"accepted", "rejected"}:
        raise ValueError("Revision decision must be 'accepted' or 'rejected'.")

    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                UPDATE ai_interactions
                SET revision_decision = :decision
                WHERE interaction_id = :interaction_id
                  AND interaction_type = 'revision'
                  AND completed_at IS NOT NULL
                """
            ),
            {
                "interaction_id": interaction_id,
                "decision": decision,
            },
        )

        if result.rowcount != 1:
            raise ValueError(
                f"Completed revision interaction '{interaction_id}' was not found."
            )


def get_ai_interactions(task_id: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM ai_interactions
                WHERE task_id = :task_id
                ORDER BY requested_at
                """
            ),
            {"task_id": task_id},
        ).mappings().all()

    return [dict(row) for row in rows]


def get_events(task_id: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT *
                FROM events
                WHERE task_id = :task_id
                ORDER BY event_timestamp
                """
            ),
            {"task_id": task_id},
        ).mappings().all()

    return [dict(row) for row in rows]


def submit_task(
    task_id: str,
    final_eus: EUS,
    inactive_seconds: float = 0,
) -> dict[str, Any]:
    if inactive_seconds < 0:
        raise ValueError("inactive_seconds cannot be negative.")

    with engine.begin() as connection:
        task = connection.execute(
            text(
                """
                SELECT *
                FROM tasks
                WHERE task_id = :task_id
                FOR UPDATE
                """
            ),
            {"task_id": task_id},
        ).mappings().first()

        if task is None:
            raise ValueError(f"Task '{task_id}' does not exist.")

        if task["status"] == "completed":
            raise ValueError(f"Task '{task_id}' has already been submitted.")

        if task["started_at"] is None:
            raise ValueError("Task must be started before it can be submitted.")

        ai_wait_seconds = float(
            connection.execute(
                text(
                    """
                    SELECT COALESCE(SUM(latency_seconds), 0)
                    FROM ai_interactions
                    WHERE task_id = :task_id
                      AND completed_at IS NOT NULL
                    """
                ),
                {"task_id": task_id},
            ).scalar_one()
        )

        wall_clock_seconds = float(
            connection.execute(
                text(
                    """
                    SELECT EXTRACT(
                        EPOCH FROM (NOW() - :started_at)
                    )
                    """
                ),
                {"started_at": task["started_at"]},
            ).scalar_one()
        )

        active_authoring_seconds = max(
            0.0,
            wall_clock_seconds - ai_wait_seconds - inactive_seconds,
        )

        row = connection.execute(
            text(
                """
                UPDATE tasks
                SET
                    status = 'completed',
                    current_eus = CAST(:final_eus AS JSONB),
                    final_eus = CAST(:final_eus AS JSONB),
                    submitted_at = NOW(),
                    wall_clock_seconds = :wall_clock_seconds,
                    ai_wait_seconds = :ai_wait_seconds,
                    inactive_seconds = :inactive_seconds,
                    active_authoring_seconds = :active_authoring_seconds
                WHERE task_id = :task_id
                RETURNING *
                """
            ),
            {
                "task_id": task_id,
                "final_eus": _json(final_eus),
                "wall_clock_seconds": wall_clock_seconds,
                "ai_wait_seconds": ai_wait_seconds,
                "inactive_seconds": inactive_seconds,
                "active_authoring_seconds": active_authoring_seconds,
            },
        ).mappings().one()

    return dict(row)


def complete_participant(participant_id: str) -> None:
    with engine.begin() as connection:
        completed_tasks = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE participant_id = :participant_id
                  AND status = 'completed'
                """
            ),
            {"participant_id": participant_id},
        ).scalar_one()

        total_tasks = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE participant_id = :participant_id
                """
            ),
            {"participant_id": participant_id},
        ).scalar_one()

        if total_tasks != 6:
            raise ValueError(
                f"Participant '{participant_id}' has {total_tasks} tasks instead of 6."
            )

        if completed_tasks != 6:
            raise ValueError(
                f"Participant '{participant_id}' has completed "
                f"{completed_tasks} of 6 tasks."
            )

        result = connection.execute(
            text(
                """
                UPDATE participants
                SET
                    status = 'completed',
                    completed_at = NOW()
                WHERE participant_id = :participant_id
                RETURNING participant_id
                """
            ),
            {"participant_id": participant_id},
        ).scalar_one_or_none()

        if result is None:
            raise ValueError(f"Participant '{participant_id}' does not exist.")


if __name__ == "__main__":
    test_connection()
