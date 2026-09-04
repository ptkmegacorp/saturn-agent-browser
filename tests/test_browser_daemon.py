"""Browser daemon state and CLI lifecycle tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saturn_fbc.browser import daemon, state
from saturn_fbc.browser.state import BrowserState


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setenv("SATURN_FBC_SHARE", str(share))
    monkeypatch.setenv("SATURN_FBC_CHROMIUM_USER_DATA", str(share / "chromium"))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(share / "playwright-browsers"))
    monkeypatch.setenv("SATURN_FBC_NAME", "SaturnFrontierBrowserTest")
    from saturn_fbc import config

    config.load_config.cache_clear()
    yield share
    config.load_config.cache_clear()


def test_state_file_roundtrip(isolated_state: Path):
    payload = BrowserState(
        pid=4242,
        cdp_url="http://127.0.0.1:9222",
        headless=False,
        started_at="2026-09-04T23:30:00Z",
        user_data_dir=str(isolated_state / "chromium"),
    )
    state.write_state(payload)
    path = state.state_file_path()
    assert path.is_file()
    assert oct(path.stat().st_mode)[-3:] == "600"
    loaded = state.read_state()
    assert loaded == payload


def test_clear_state_removes_file(isolated_state: Path):
    state.write_state(
        BrowserState(
            pid=1,
            cdp_url="http://127.0.0.1:9222",
            headless=False,
            started_at="2026-09-04T23:30:00Z",
            user_data_dir=str(isolated_state / "chromium"),
        )
    )
    state.clear_state()
    assert not state.state_file_path().exists()


def test_is_pid_alive_current_process():
    import os

    assert state.is_pid_alive(os.getpid()) is True
    assert state.is_pid_alive(999_999_999) is False


def test_browser_mode_config(monkeypatch: pytest.MonkeyPatch):
    from saturn_fbc import config

    monkeypatch.setenv("SATURN_FBC_BROWSER_MODE", "ephemeral")
    config.load_config.cache_clear()
    assert config.browser_mode() == "ephemeral"

    monkeypatch.setenv("SATURN_FBC_BROWSER_MODE", "invalid-mode")
    config.load_config.cache_clear()
    assert config.browser_mode() == "daemon"


def test_browser_daemon_status_not_running(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SATURN_FBC_BROWSER_MODE", "daemon")
    from saturn_fbc import config

    config.load_config.cache_clear()
    payload = daemon.browser_daemon_status()
    assert payload["running"] is False
    assert payload["browser_mode"] == "daemon"
    assert payload["pid"] is None


def test_browser_daemon_status_running_mock(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    import os

    state.write_state(
        BrowserState(
            pid=os.getpid(),
            cdp_url="http://127.0.0.1:9222",
            headless=False,
            started_at="2026-09-04T23:30:00Z",
            user_data_dir=str(isolated_state / "chromium"),
        )
    )
    with patch.object(state, "cdp_healthy", return_value=True):
        payload = daemon.browser_daemon_status()
    assert payload["running"] is True
    assert payload["pid"] == os.getpid()
    assert payload["cdp_url"] == "http://127.0.0.1:9222"


def test_start_browser_already_running(isolated_state: Path):
    import os

    state.write_state(
        BrowserState(
            pid=os.getpid(),
            cdp_url="http://127.0.0.1:9222",
            headless=False,
            started_at="2026-09-04T23:30:00Z",
            user_data_dir=str(isolated_state / "chromium"),
        )
    )
    with patch.object(state, "cdp_healthy", return_value=True):
        result = daemon.start_browser(wait_timeout=1.0)
    assert result["ok"] is True
    assert result["already_running"] is True


def test_start_browser_subprocess_mock(isolated_state: Path):
    import os

    def fake_healthy(*_args, **_kwargs):
        return state.read_state() is not None and state.is_pid_alive(state.read_state().pid)

    with (
        patch.object(daemon, "_systemd_unit_installed", return_value=False),
        patch.object(daemon, "_start_via_subprocess") as spawn,
        patch.object(state, "cdp_healthy", side_effect=fake_healthy),
    ):
        spawn.side_effect = lambda: state.write_state(
            BrowserState(
                pid=os.getpid(),
                cdp_url="http://127.0.0.1:9222",
                headless=False,
                started_at="2026-09-04T23:30:00Z",
                user_data_dir=str(isolated_state / "chromium"),
            )
        )
        result = daemon.start_browser(wait_timeout=2.0, prefer_systemd=True)
    assert result["ok"] is True
    assert result["already_running"] is False
    assert result["started_via"] == "subprocess"
    spawn.assert_called_once()


def test_stop_browser_clears_state(isolated_state: Path):
    state.write_state(
        BrowserState(
            pid=999_999_999,
            cdp_url="http://127.0.0.1:9222",
            headless=False,
            started_at="2026-09-04T23:30:00Z",
            user_data_dir=str(isolated_state / "chromium"),
        )
    )
    with patch("subprocess.run") as run_mock:
        run_mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = daemon.stop_browser()
    assert result["ok"] is True
    assert not state.state_file_path().exists()


def test_ensure_daemon_for_headed_run_skips_headless(monkeypatch: pytest.MonkeyPatch):
    with patch.object(daemon, "start_browser") as start_mock:
        daemon.ensure_daemon_for_headed_run(True)
    start_mock.assert_not_called()


def test_ensure_daemon_for_headed_run_skips_ephemeral(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SATURN_FBC_BROWSER_MODE", "ephemeral")
    from saturn_fbc import config

    config.load_config.cache_clear()
    with patch.object(daemon, "start_browser") as start_mock:
        daemon.ensure_daemon_for_headed_run(False)
    start_mock.assert_not_called()


def test_ensure_daemon_for_headed_run_starts_when_down(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SATURN_FBC_BROWSER_MODE", "daemon")
    from saturn_fbc import config

    config.load_config.cache_clear()
    with (
        patch.object(state, "is_daemon_healthy", return_value=False),
        patch.object(daemon, "start_browser") as start_mock,
    ):
        daemon.ensure_daemon_for_headed_run(False)
    start_mock.assert_called_once()


def test_runner_status_includes_browser_daemon(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_fbc import config
    from saturn_fbc.runner import status as runner_status

    config.load_config.cache_clear()
    with patch("saturn_fbc.pig_stack.health_json", return_value={"profile": "test"}):
        payload = runner_status()
    assert "browser_daemon" in payload
    assert payload["browser_daemon"]["running"] is False
