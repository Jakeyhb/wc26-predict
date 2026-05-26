from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.config import get_settings

TASK_RUNS_FILE = "beat_task_runs.json"


def _task_runs_path() -> Path:
    settings = get_settings()
    settings.model_artifact_dir.mkdir(parents=True, exist_ok=True)
    return settings.model_artifact_dir / TASK_RUNS_FILE


def read_task_runs() -> dict[str, str]:
    path = _task_runs_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_task_run(task_name: str, *, when: datetime | None = None) -> None:
    path = _task_runs_path()
    payload: dict[str, Any] = read_task_runs()
    payload[task_name] = (when or datetime.now(UTC)).isoformat()
    with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        temp_path = Path(tmp.name)
    temp_path.replace(path)
