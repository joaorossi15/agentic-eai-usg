from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from eai_usg.schemas import EUS
from study.service import (
    accept_revision,
    get_next_task,
    get_study_state,
    open_task,
    pause_task,
    reject_revision,
    request_revision,
    request_validation,
    resume_task,
    start_study,
    submit_task,
    update_editor,
    submit_background
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartStudyRequest(StrictModel):
    participant_id: str


class BackgroundRequest(StrictModel):
    primary_role: str
    years_experience: float = Field(ge=0)
    requirements_familiarity: int = Field(ge=1, le=5)
    user_story_familiarity: int = Field(ge=1, le=5)
    ethical_ai_familiarity: int = Field(ge=1, le=5)
    generative_ai_use: str


class DraftEUS(StrictModel):
    title: str = ""
    description: str = ""
    work_items: list[str] = Field(default_factory=list)


class UpdateEditorRequest(StrictModel):
    draft: DraftEUS
    field: str | None = None


class RevisionRequest(StrictModel):
    revision_instruction: str | None = None


class SubmitTaskRequest(StrictModel):
    final_eus: EUS
    inactive_seconds: float = Field(default=0, ge=0)


app = FastAPI(
    title="EAI-USG Human-AI Study API",
    version="1.0.0",
)


frontend_origin = os.getenv(
    "STUDY_FRONTEND_ORIGIN",
    "http://localhost:3000",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=str(exc),
    )


def _ensure_task_belongs_to_participant(
    participant_id: str,
    task_id: str,
) -> None:
    try:
        state = get_study_state(participant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    participant_task_ids = {
        task["task_id"]
        for task in state["tasks"]
    }

    if task_id not in participant_task_ids:
        raise HTTPException(
            status_code=404,
            detail="Task does not belong to this participant.",
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/study/start")
def api_start_study(
    request: StartStudyRequest,
) -> dict[str, Any]:
    try:
        return start_study(request.participant_id)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise _bad_request(exc) from exc

@app.post("/study/{participant_id}/background")
def api_submit_background(
    participant_id: str,
    request: BackgroundRequest,
) -> dict[str, str]:
    try:
        submit_background(
            participant_id=participant_id,
            background=request.model_dump(),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc

    return {"status": "saved"}

@app.get("/study/{participant_id}")
def api_get_study_state(
    participant_id: str,
) -> dict[str, Any]:
    try:
        return get_study_state(participant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.get("/study/{participant_id}/next")
def api_get_next_task(
    participant_id: str,
) -> dict[str, Any] | None:
    try:
        return get_next_task(participant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@app.post("/study/{participant_id}/tasks/{task_number}/open")
def api_open_task(
    participant_id: str,
    task_number: int,
) -> dict[str, Any]:
    try:
        return open_task(
            participant_id=participant_id,
            task_number=task_number,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.put("/study/{participant_id}/tasks/{task_id}/editor")
def api_update_editor(
    participant_id: str,
    task_id: str,
    request: UpdateEditorRequest,
) -> dict[str, str]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        update_editor(
            task_id=task_id,
            draft=request.draft.model_dump(),
            field=request.field,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc

    return {"status": "saved"}


@app.post("/study/{participant_id}/tasks/{task_id}/validation")
def api_request_validation(
    participant_id: str,
    task_id: str,
) -> dict[str, Any]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        validation = request_validation(task_id)

        return {
            "validation": validation.model_dump(
                mode="json"
            )
        }
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post("/study/{participant_id}/tasks/{task_id}/revision")
def api_request_revision(
    participant_id: str,
    task_id: str,
    request: RevisionRequest,
) -> dict[str, Any]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        return request_revision(
            task_id=task_id,
            revision_instruction=request.revision_instruction,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post(
    "/study/{participant_id}/tasks/{task_id}/revision/{interaction_id}/accept"
)
def api_accept_revision(
    participant_id: str,
    task_id: str,
    interaction_id: str,
) -> dict[str, Any]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        eus = accept_revision(
            task_id=task_id,
            interaction_id=interaction_id,
        )

        return {
            "status": "accepted",
            "current_eus": eus.model_dump(
                mode="json"
            ),
        }
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post(
    "/study/{participant_id}/tasks/{task_id}/revision/{interaction_id}/reject"
)
def api_reject_revision(
    participant_id: str,
    task_id: str,
    interaction_id: str,
) -> dict[str, str]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        reject_revision(
            task_id=task_id,
            interaction_id=interaction_id,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc

    return {"status": "rejected"}


@app.post("/study/{participant_id}/tasks/{task_id}/pause")
def api_pause_task(
    participant_id: str,
    task_id: str,
) -> dict[str, str]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        pause_task(task_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc

    return {"status": "paused"}


@app.post("/study/{participant_id}/tasks/{task_id}/resume")
def api_resume_task(
    participant_id: str,
    task_id: str,
) -> dict[str, str]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        resume_task(task_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc

    return {"status": "resumed"}


@app.post("/study/{participant_id}/tasks/{task_id}/submit")
def api_submit_task(
    participant_id: str,
    task_id: str,
    request: SubmitTaskRequest,
) -> dict[str, Any]:
    _ensure_task_belongs_to_participant(
        participant_id,
        task_id,
    )

    try:
        return submit_task(
            task_id=task_id,
            final_draft=request.final_eus.model_dump(
                mode="json"
            ),
            inactive_seconds=request.inactive_seconds,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
