from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import BackendGenerationArtifacts


def _safe(value: str) -> str:
    return "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in value
    )


def save_backend_run(
    run: BackendGenerationArtifacts,
    output_dir: str = "outputs/backend_runs",
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    path = out / (
        f"{timestamp}_"
        f"{_safe(run.requirement.id)}_"
        f"{_safe(run.backend)}_"
        f"{_safe(run.model)}_"
        f"r{run.repetition}.json"
    )

    path.write_text(
        json.dumps(
            run.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path
