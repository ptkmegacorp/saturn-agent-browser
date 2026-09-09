"""Ordinary Google Chrome lane — dedicated profile, CDP :9223 for Pi snapshots."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from saturn_fbc import config
from saturn_fbc.browser.state import cdp_healthy, is_pid_alive, utc_now_iso

FORBIDDEN_FLAGS = (
    "--headless",
    "--headless=new",
    "--headless=old",
)


def _state_path() -> Path:
    return config.trusted_state_path()


def _profile() -> Path:
    return config.trusted_profile_dir()


def read_trusted_state() -> dict[str, Any] | None:
    path = _state_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_trusted_state(payload: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def clear_trusted_state() -> None:
    path = _state_path()
    if path.is_file():
        path.unlink()


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def pids_for_trusted_profile(user_data: Path | None = None) -> list[int]:
    marker = str(user_data or _profile())
    found: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        text = _cmdline(pid)
        if marker and marker in text and "chrome" in text.lower():
            found.append(pid)
    return sorted(found)


def _chrome_sandbox_helpers(executable: Path) -> list[Path]:
    resolved = executable
    try:
        if executable.is_symlink():
            resolved = executable.resolve()
    except OSError:
        pass
    helpers = [resolved.parent / "chrome-sandbox", executable.parent / "chrome-sandbox"]
    system = Path("/usr/bin/google-chrome-stable")
    opt = Path("/opt/google/chrome/google-chrome")
    try:
        same_system = executable.resolve() == system.resolve() or executable.resolve() == opt.resolve()
    except OSError:
        same_system = False
    if executable == system or same_system:
        helpers.append(Path("/opt/google/chrome/chrome-sandbox"))
    seen: list[Path] = []
    for path in helpers:
        if path not in seen:
            seen.append(path)
    return seen


def sandbox_args(executable: Path) -> list[str]:
    """User-extracted Chrome cannot chown chrome-sandbox; apt install can."""
    for helper in _chrome_sandbox_helpers(executable):
        try:
            info = helper.stat()
        except OSError:
            continue
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid == 0 and mode == 0o4755:
            return []
    return ["--no-sandbox"]


def trusted_launch_argv(*, executable: Path, user_data: Path, url: str = "chrome://newtab/") -> list[str]:
    argv = [
        str(executable),
        f"--user-data-dir={user_data}",
        f"--class={config.trusted_wm_class()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        *sandbox_args(executable),
        f"--remote-debugging-port={config.trusted_cdp_port()}",
        "--remote-allow-origins=*",
        url,
    ]
    joined = " ".join(argv)
    for flag in FORBIDDEN_FLAGS:
        if flag in joined:
            raise RuntimeError(f"refusing trusted Chrome argv containing {flag}")
    return argv


def trusted_status() -> dict[str, Any]:
    exe = config.trusted_executable()
    profile = _profile()
    pids = pids_for_trusted_profile(profile)
    state = read_trusted_state()
    running = bool(pids)
    return {
        "ok": True,
        "lane": "trusted-chrome",
        "running": running,
        "pids": pids,
        "pid": pids[0] if pids else None,
        "executable": str(exe) if exe else None,
        "user_data_dir": str(profile),
        "cdp": True,
        "cdp_url": config.trusted_cdp_url() if running else None,
        "sandbox": None if exe is None else ("setuid" if not sandbox_args(exe) else "no-sandbox"),
        "started_at": state.get("started_at") if state else None,
        "isolated_profile": str(config.chromium_user_data_dir()),
        "same_as_isolated": profile.resolve() == config.chromium_user_data_dir().resolve(),
    }


def list_browser_profiles() -> dict[str, Any]:
    isolated = {
        "id": "isolated-playwright",
        "browser": "Playwright Chromium",
        "user_data_dir": str(config.chromium_user_data_dir()),
        "cdp": True,
        "cdp_url": config.cdp_url(),
    }
    trusted = {
        "id": "trusted-chrome",
        "browser": "Google Chrome stable (Brave fallback)",
        "user_data_dir": str(_profile()),
        "cdp": True,
        "cdp_url": config.trusted_cdp_url(),
        "executable": str(config.trusted_executable()) if config.trusted_executable() else None,
    }
    return {"ok": True, "profiles": [isolated, trusted], "default": "isolated-playwright"}


def start_trusted(*, url: str = "chrome://newtab/", wait_timeout: float = 20.0) -> dict[str, Any]:
    current = trusted_status()
    if current["running"]:
        if cdp_healthy(config.trusted_cdp_url()):
            return {"ok": True, "already_running": True, **current}
        stop_trusted()
    exe = config.trusted_executable()
    if exe is None:
        return {
            "ok": False,
            "error": "trusted_chrome_missing",
            "hint": "Install Google Chrome stable (scripts/install-google-chrome.sh)",
        }
    profile = _profile()
    isolated = config.chromium_user_data_dir()
    if profile.resolve() == isolated.resolve():
        return {"ok": False, "error": "trusted_profile_collides_with_isolated"}
    profile.mkdir(parents=True, exist_ok=True)
    os.chmod(profile, 0o700)
    argv = trusted_launch_argv(executable=exe, user_data=profile, url=url)
    env = os.environ.copy()
    env.setdefault("DISPLAY", os.environ.get("DISPLAY", ":0"))
    subprocess.Popen(
        argv,
        env=env,
        cwd=str(profile),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        pids = pids_for_trusted_profile(profile)
        if pids:
            payload = {
                "pid": pids[0],
                "executable": str(exe),
                "user_data_dir": str(profile),
                "started_at": utc_now_iso(),
                "cdp": True,
                "cdp_url": config.trusted_cdp_url(),
                "lane": "trusted-chrome",
            }
            write_trusted_state(payload)
            cdp_deadline = time.monotonic() + min(15.0, wait_timeout)
            while time.monotonic() < cdp_deadline:
                if cdp_healthy(config.trusted_cdp_url()):
                    return {"ok": True, "already_running": False, **trusted_status()}
                time.sleep(0.2)
            return {"ok": True, "already_running": False, "cdp_ready": False, **trusted_status()}
        time.sleep(0.2)
    return {"ok": False, "error": "trusted_chrome_did_not_start"}


def stop_trusted(*, timeout: float = 8.0) -> dict[str, Any]:
    profile = _profile()
    pids = pids_for_trusted_profile(profile)
    for pid in pids:
        if not is_pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and pids_for_trusted_profile(profile):
        time.sleep(0.1)
    leftover = pids_for_trusted_profile(profile)
    for pid in leftover:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    clear_trusted_state()
    return {"ok": True, **trusted_status()}
