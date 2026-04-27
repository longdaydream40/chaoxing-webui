from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ModuleRecord:
    task_id: str
    course_id: str
    course_title: str
    module_id: str
    module_title: str
    status: str
    finished_jobs: int
    total_jobs: int
    message: str
    created_at: str


class ModuleRecorder:
    def __init__(self, base_dir: str = "module_records") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, task_id: str, payload: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_dir = self.base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        record = ModuleRecord(
            task_id=task_id,
            course_id=str(payload.get("course_id", "")),
            course_title=str(payload.get("course_title", "")),
            module_id=str(payload.get("module_id", "")),
            module_title=str(payload.get("module_title", "")),
            status=str(payload.get("status", "unknown")),
            finished_jobs=int(payload.get("finished_jobs", 0)),
            total_jobs=int(payload.get("total_jobs", 0)),
            message=str(payload.get("message", "")),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        filename = (
            f"{now}_{record.course_id}_{record.module_id}_{record.status}.json"
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )
        output = task_dir / filename
        output.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
        return str(output)

