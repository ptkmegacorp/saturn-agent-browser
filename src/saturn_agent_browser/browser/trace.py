"""JSONL trace writer for browser runs."""

from __future__ import annotations

import json
import os
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path

from saturn_agent_browser import config
from saturn_agent_browser.contract import StepRecord


def new_run_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


class TraceWriter:
    """Append-only JSONL trace under traces/<run-id>/ with mode 0700."""

    def __init__(self, run_id: str | None = None, *, base_dir: Path | None = None) -> None:
        self.run_id = run_id or new_run_id()
        root = base_dir or config.traces_dir()
        self.trace_dir = root / self.run_id
        self._ensure_private_dir(self.trace_dir)
        self.jsonl_path = self.trace_dir / "trace.jsonl"
        self._step = 0

    @staticmethod
    def _ensure_private_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, stat.S_IRWXU)

    def write_step(self, record: StepRecord) -> None:
        self._step = record.step
        line = record.model_dump(mode="json", exclude_none=True)
        line["ts"] = datetime.now(UTC).isoformat()
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    def screenshot_path(self, step: int) -> Path:
        return self.trace_dir / f"step-{step:04d}.png"
