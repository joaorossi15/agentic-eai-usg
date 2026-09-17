from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eai_usg.schemas import EUS, TraceabilityResult, ValidationResult
from study.design import EthicalPrinciple, ParticipantAssignment, StudyCondition


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    withdrawn = "withdrawn"


class TaskStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class StudyEventType(str, Enum):
    task_started = "task_started"
    editor_changed = "editor_changed"
    validation_requested = "validation_requested"
    validation_completed = "validation_completed"
    revision_requested = "revision_requested"
    revision_completed = "revision_completed"
    revision_accepted = "revision_accepted"
    revision_rejected = "revision_rejected"
    task_paused = "task_paused"
    task_resumed = "task_resumed"
    task_submitted = "task_submitted"


class AIInteractionType(str, Enum):
    validation = "validation"
    revision = "revision"


class RevisionDecision(str, Enum):
    accepted = "accepted"
    rejected = "rejected"


class StudyEvent(StrictModel):
    event_type: StudyEventType
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class AIInteraction(StrictModel):
    interaction_type: AIInteractionType
    requested_at: datetime
    completed_at: datetime
    latency_seconds: float = Field(ge=0)
    input_eus: EUS
    validation_feedback: ValidationResult | None = None
    validation_output: ValidationResult | None = None
    revision_instruction: str | None = None
    revision_output: EUS | None = None
    revision_decision: RevisionDecision | None = None
    api_response_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interaction(self) -> "AIInteraction":
        if self.completed_at < self.requested_at:
            raise ValueError("AI interaction completion cannot precede its request.")

        if self.interaction_type == AIInteractionType.validation:
            if self.validation_output is None:
                raise ValueError("A validation interaction must contain validation_output.")

            if self.validation_feedback is not None:
                raise ValueError("A validation interaction cannot contain validation_feedback.")

            if self.revision_instruction is not None:
                raise ValueError("A validation interaction cannot contain revision_instruction.")

            if self.revision_output is not None:
                raise ValueError("A validation interaction cannot contain revision_output.")

            if self.revision_decision is not None:
                raise ValueError("A validation interaction cannot contain revision_decision.")

        if self.interaction_type == AIInteractionType.revision:
            if self.validation_feedback is None:
                raise ValueError("A revision interaction must contain validation_feedback.")

            if self.revision_output is None:
                raise ValueError("A revision interaction must contain revision_output.")

            if self.validation_output is not None:
                raise ValueError("A revision interaction cannot contain validation_output.")

        return self


class TaskTiming(StrictModel):
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    wall_clock_seconds: float | None = Field(default=None, ge=0)
    ai_wait_seconds: float = Field(default=0, ge=0)
    inactive_seconds: float = Field(default=0, ge=0)
    active_authoring_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_timing(self) -> "TaskTiming":
        if self.started_at is not None and self.submitted_at is not None:
            if self.submitted_at < self.started_at:
                raise ValueError("Task submission cannot precede task start.")

        if self.wall_clock_seconds is not None:
            excluded = self.ai_wait_seconds + self.inactive_seconds

            if excluded > self.wall_clock_seconds + 0.001:
                raise ValueError("AI wait time and inactive time cannot exceed wall-clock time.")

            if self.active_authoring_seconds is not None:
                expected = self.wall_clock_seconds - excluded

                if abs(self.active_authoring_seconds - expected) > 0.1:
                    raise ValueError(
                        "active_authoring_seconds must equal wall_clock_seconds "
                        "- ai_wait_seconds - inactive_seconds."
                    )

        return self


class TaskSession(StrictModel):
    task_id: str
    participant_id: str
    task_number: int = Field(ge=1, le=6)
    requirement_id: str
    principle: EthicalPrinciple
    condition: StudyCondition
    status: TaskStatus = TaskStatus.not_started

    initial_eus: EUS | None = None
    initial_traceability: TraceabilityResult | None = None
    current_eus: EUS | None = None
    final_eus: EUS | None = None

    timing: TaskTiming = Field(default_factory=TaskTiming)
    ai_interactions: list[AIInteraction] = Field(default_factory=list)
    events: list[StudyEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task(self) -> "TaskSession":
        validation_interactions = [
            interaction
            for interaction in self.ai_interactions
            if interaction.interaction_type == AIInteractionType.validation
        ]

        revision_interactions = [
            interaction
            for interaction in self.ai_interactions
            if interaction.interaction_type == AIInteractionType.revision
        ]

        if len(validation_interactions) > 1:
            raise ValueError("A task may contain at most one AI validation.")

        if len(revision_interactions) > 1:
            raise ValueError("A task may contain at most one AI revision.")

        if self.condition == StudyCondition.manual:
            if self.initial_eus is not None:
                raise ValueError("Manual tasks cannot contain an initial AI-generated EUS.")

            if self.initial_traceability is not None:
                raise ValueError("Manual tasks cannot contain AI traceability.")

            if self.ai_interactions:
                raise ValueError("Manual tasks cannot contain AI interactions.")

        if self.condition == StudyCondition.eai_usg:
            if self.initial_eus is None:
                raise ValueError("EAI-USG tasks must contain the frozen initial EUS.")

            if self.initial_traceability is None:
                raise ValueError("EAI-USG tasks must contain the frozen initial traceability.")

        if revision_interactions and not validation_interactions:
            raise ValueError("AI revision cannot occur without prior validation.")

        if self.status == TaskStatus.completed:
            if self.final_eus is None:
                raise ValueError("A completed task must contain the final submitted EUS.")

            if self.timing.submitted_at is None:
                raise ValueError("A completed task must contain a submission timestamp.")

            if self.timing.active_authoring_seconds is None:
                raise ValueError("A completed task must contain active authoring time.")

        return self


class ParticipantRecord(StrictModel):
    participant_id: str
    created_at: datetime


class StudySession(StrictModel):
    session_id: str
    participant: ParticipantRecord
    assignment: ParticipantAssignment
    status: SessionStatus = SessionStatus.not_started
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tasks: list[TaskSession] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_session(self) -> "StudySession":
        if self.participant.participant_id != self.assignment.participant_id:
            raise ValueError("Participant ID does not match the assigned participant.")

        task_numbers = [task.task_number for task in self.tasks]

        if len(task_numbers) != len(set(task_numbers)):
            raise ValueError("Study session contains duplicate task numbers.")

        assignment_by_number = {
            task.task_number: task
            for task in self.assignment.tasks
        }

        for task in self.tasks:
            if task.participant_id != self.participant.participant_id:
                raise ValueError("Task participant ID does not match the study session.")

            assigned_task = assignment_by_number.get(task.task_number)

            if assigned_task is None:
                raise ValueError(f"Task {task.task_number} does not exist in the participant assignment.")

            if task.requirement_id != assigned_task.requirement_id:
                raise ValueError(f"Task {task.task_number} uses the wrong requirement.")

            if task.principle != assigned_task.principle:
                raise ValueError(f"Task {task.task_number} uses the wrong ethical principle.")

            if task.condition != assigned_task.condition:
                raise ValueError(f"Task {task.task_number} uses the wrong study condition.")

        if self.completed_at is not None and self.started_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("Study completion cannot precede study start.")

        if self.status == SessionStatus.completed:
            if len(self.tasks) != 6:
                raise ValueError("A completed study session must contain all six tasks.")

            if any(task.status != TaskStatus.completed for task in self.tasks):
                raise ValueError("All tasks must be completed before the study session is completed.")

            if self.completed_at is None:
                raise ValueError("A completed study session must contain a completion timestamp.")

        return self
