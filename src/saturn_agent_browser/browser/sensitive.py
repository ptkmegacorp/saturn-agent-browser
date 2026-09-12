"""Sensitive-mode gates for browser targets.

Before secret entry/delivery, a target enters sensitive mode: agent
screenshots, DOM reads, traces and generic input for that target suspend,
queued/cached frames invalidate, and only an authorized human viewer (valid
lease) is exempt. Generic snapshot endpoints fail safe with
``sensitive_blocked`` instead of pixels.

This module owns the flag set. Enforcement lives in view.py (snapshot /
navigate) and later in the runner/observation paths. Persisted beside
browser state (0600).
"""

from __future__ import annotations

import json
import os
from typing import Any

from saturn_agent_browser.browser.state import state_file_path


def sensitive_file_path():
    return state_file_path().with_name("browser-sensitive.json")


def _blank() -> dict[str, Any]:
    return {"targets": {}}


def _load() -> dict[str, Any]:
    path = sensitive_file_path()
    if not path.is_file():
        return _blank()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blank()
    if not isinstance(data, dict) or not isinstance(data.get("targets"), dict):
        return _blank()
    return data


def _save(data: dict[str, Any]) -> None:
    path = sensitive_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _key(lane: str, tab_id: str) -> str:
    return f"{(lane or 'isolated').strip() or 'isolated'}\x00{(tab_id or '').strip()}"


def mark(*, lane: str, tab_id: str, reason: str = "credential_entry") -> dict[str, Any]:
    tab_id = (tab_id or "").strip()
    if not tab_id.startswith("tab-"):
        return {"ok": False, "error": "invalid_tab_id"}
    data = _load()
    data["targets"][_key(lane, tab_id)] = {"reason": reason, "tab_id": tab_id}
    _save(data)
    return {"ok": True, "tab_id": tab_id, "sensitive": True}


def clear(*, lane: str, tab_id: str) -> dict[str, Any]:
    data = _load()
    data["targets"].pop(_key(lane, tab_id), None)
    _save(data)
    return {"ok": True, "tab_id": (tab_id or "").strip(), "sensitive": False}


def is_sensitive(*, lane: str, tab_id: str) -> bool:
    return _key(lane, tab_id) in _load()["targets"]


def clear_all() -> None:
    path = sensitive_file_path()
    if path.is_file():
        path.unlink()
