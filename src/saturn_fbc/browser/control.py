"""Human vs agent ownership for the headed daemon (sidecar, not BrowserState)."""

from __future__ import annotations

import json
import os
from typing import Any

from saturn_fbc.browser.state import state_file_path, utc_now_iso

MODES = frozenset({"human", "agent"})


def control_file_path():
    return state_file_path().with_name("browser-control.json")


def read_control_mode() -> str:
    path = control_file_path()
    if not path.is_file():
        return "agent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "agent"
    if not isinstance(data, dict):
        return "agent"
    mode = str(data.get("mode") or "").strip()
    return mode if mode in MODES else "agent"


def write_control_mode(mode: str) -> dict[str, Any]:
    wanted = str(mode or "").strip()
    if wanted not in MODES:
        return {"ok": False, "error": "invalid_control_mode"}
    path = control_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mode": wanted, "updated_at": utc_now_iso()}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return {"ok": True, **payload}


def clear_control_mode() -> None:
    path = control_file_path()
    if path.is_file():
        path.unlink()
