from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


def _safe(value: str) -> str:
    return "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in value
    )


def save_artifact(
    artifact: BaseModel,
    requirement_id: str,
    artifact_type: str,
    output_dir: str = "outputs",
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    path = out / (
        f"{timestamp}_"
        f"{_safe(requirement_id)}_"
        f"{_safe(artifact_type)}.json"
    )

    path.write_text(
        json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path
