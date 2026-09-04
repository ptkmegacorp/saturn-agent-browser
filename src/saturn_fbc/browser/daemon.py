"""Persistent headed Chromium daemon — launch, state, CLI lifecycle."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

from saturn_fbc import config
from saturn_fbc.browser.profile import close_context, launch_daemon_context
from saturn_fbc.browser.state import (
    BrowserState,
    clear_state,
    cdp_healthy,
    is_daemon_healthy,
    is_pid_alive,
    read_state,
    utc_now_iso,
    write_state,
)

SERVICE_NAME = "saturn-fbc-browser.service"


def browser_mode() -> str:
    return config.browser_mode()


def is_daemon_mode() -> bool:
    return browser_mode() == "daemon"


def browser_daemon_status(*, clear_stale: bool = False) -> dict:
    state = read_state()
    running = is_daemon_healthy(state)
    stale = state is not None and not running
    if stale and clear_stale:
        clear_state()
        state = None
        stale = False
    return {
        "running": running,
        "pid": state.pid if running and state else None,
        "cdp_url": state.cdp_url if running and state else None,
        "headless": state.headless if running and state else None,
        "started_at": state.started_at if running and state else None,
        "user_data_dir": state.user_data_dir if running and state else None,
        "browser_mode": browser_mode(),
        "stale": stale,
    }


def _systemd_unit_installed() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-enabled", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _start_via_systemd() -> None:
    result = subprocess.run(
        ["systemctl", "--user", "start", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"systemctl --user start {SERVICE_NAME} failed: {detail}")


def _start_via_subprocess() -> None:
    env = os.environ.copy()
    config.load_config()
    project_root = config.PROJECT_ROOT
    venv_python = project_root / ".venv" / "bin" / "python"
    python = str(venv_python if venv_python.is_file() else sys.executable)
    subprocess.Popen(
        [python, "-m", "saturn_fbc.browser.daemon"],
        cwd=str(project_root),
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_browser(*, wait_timeout: float = 30.0, prefer_systemd: bool = True) -> dict:
    """Start the browser daemon if not already healthy."""
    status = browser_daemon_status(clear_stale=True)
    if status["running"]:
        return {"ok": True, "already_running": True, **status}

    started_via = "systemd"
    if prefer_systemd and _systemd_unit_installed():
        _start_via_systemd()
    else:
        started_via = "subprocess"
        _start_via_subprocess()

    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if is_daemon_healthy():
            result = browser_daemon_status()
            return {"ok": True, "already_running": False, "started_via": started_via, **result}
        time.sleep(0.25)

    raise RuntimeError(
        f"Browser daemon did not become healthy within {wait_timeout:.0f}s "
        f"(mode={browser_mode()}, started_via={started_via})"
    )


def stop_browser(*, timeout: float = 10.0) -> dict:
    """Stop systemd unit (if present) and clear stale state."""
    state = read_state()
    subprocess.run(
        ["systemctl", "--user", "stop", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    if state and is_pid_alive(state.pid):
        try:
            os.kill(state.pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and is_pid_alive(state.pid):
            time.sleep(0.1)
    clear_state()
    return {"ok": True, **browser_daemon_status()}


def restart_browser(*, wait_timeout: float = 30.0) -> dict:
    stop_browser()
    return start_browser(wait_timeout=wait_timeout)


def ensure_daemon_for_headed_run(headless: bool | None) -> None:
    """Auto-start daemon before headed runs when SATURN_FBC_BROWSER_MODE=daemon."""
    if config.resolve_headless(headless):
        return
    if not is_daemon_mode():
        return
    if is_daemon_healthy():
        return
    start_browser()


def run_daemon(*, headless: bool = False) -> int:
    """Blocking daemon entry: launch Chromium, write state, wait for SIGTERM."""
    config.load_config()
    if read_state() and is_daemon_healthy():
        return 0

    playwright: Playwright | None = None
    context: BrowserContext | None = None
    shutting_down = False

    def _shutdown(signum: int, _frame: object) -> None:
        nonlocal shutting_down
        shutting_down = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    user_data = config.chromium_user_data_dir()
    cdp_url = config.cdp_url()
    write_state(
        BrowserState(
            pid=os.getpid(),
            cdp_url=cdp_url,
            headless=headless,
            started_at=utc_now_iso(),
            user_data_dir=str(user_data),
        )
    )

    try:
        playwright, context = launch_daemon_context(headless=headless)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and not cdp_healthy(cdp_url):
            time.sleep(0.25)
        if not cdp_healthy(cdp_url):
            raise RuntimeError(f"CDP endpoint not healthy at {cdp_url}")

        while not shutting_down:
            if not is_pid_alive(os.getpid()):
                break
            time.sleep(0.5)
    finally:
        clear_state()
        if context is not None:
            close_context(context, playwright)

    return 0


def main() -> None:
    headless = config.resolve_headless(None)
    raise SystemExit(run_daemon(headless=headless))


if __name__ == "__main__":
    main()
