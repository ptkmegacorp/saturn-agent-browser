"""Browser daemon state file helpers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from saturn_agent_browser import config


@dataclass
class BrowserState:
    pid: int
    cdp_url: str
    headless: bool
    started_at: str
    user_data_dir: str


def state_file_path() -> Path:
    return config.browser_state_path()


def read_state() -> BrowserState | None:
    path = state_file_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BrowserState(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def write_state(state: BrowserState) -> None:
    path = state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def clear_state() -> None:
    path = state_file_path()
    if path.is_file():
        path.unlink()


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def cdp_healthy(cdp_url: str) -> bool:
    try:
        import httpx

        url = f"{cdp_url.rstrip('/')}/json/version"
        response = httpx.get(url, timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


def is_running(*, check_cdp: bool = True) -> bool:
    """True when state file exists, pid is alive, and CDP responds (optional)."""
    current = read_state()
    if current is None:
        return False
    if not is_pid_alive(current.pid):
        return False
    if check_cdp and not cdp_healthy(current.cdp_url):
        return False
    return True


def is_daemon_healthy(state: BrowserState | None = None) -> bool:
    current = state if state is not None else read_state()
    if current is None:
        return False
    if not is_pid_alive(current.pid):
        return False
    return cdp_healthy(current.cdp_url)


def daemon_running() -> bool:
    """True when state file exists, pid is alive, and CDP responds."""
    return is_running(check_cdp=True)


def read_cdp_url() -> str:
    state = read_state()
    if state is None:
        return config.cdp_url()
    return state.cdp_url


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
