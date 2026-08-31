from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import RunArtifacts


def save_run(run: RunArtifacts, output_dir: str = "outputs/runs") -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in run.requirement.id)
    path = out / f"{timestamp}_{safe_id}_{run.workflow_config}.json"
    path.write_text(json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
