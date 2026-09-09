"""Trusted Chrome lane: dedicated profile, CDP :9223."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_fbc.browser.trusted import (
    FORBIDDEN_FLAGS,
    list_browser_profiles,
    sandbox_args,
    start_trusted,
    trusted_launch_argv,
    trusted_status,
)


def test_launch_argv_has_no_cdp_and_separate_profile(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SATURN_FBC_SHARE", str(tmp_path / "share"))
    monkeypatch.setenv("SATURN_FBC_CHROMIUM_USER_DATA", str(tmp_path / "share" / "chromium"))
    monkeypatch.setenv("SATURN_FBC_TRUSTED_PROFILE", str(tmp_path / "share" / "trusted-chrome"))
    monkeypatch.setenv("SATURN_FBC_TRUSTED_NAME", "SaturnTrustedChromeTest")
    from saturn_fbc import config

    config.load_config.cache_clear()
    exe = tmp_path / "google-chrome-stable"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    profile = tmp_path / "share" / "trusted-chrome"
    argv = trusted_launch_argv(executable=exe, user_data=profile, url="https://example.com/")
    joined = " ".join(argv)
    for flag in FORBIDDEN_FLAGS:
        assert flag not in joined
    assert f"--user-data-dir={profile}" in argv
    assert "--class=SaturnTrustedChromeTest" in argv
    assert any(part.startswith("--remote-debugging-port=") for part in argv)
    assert "--no-sandbox" in argv
    isolated = str(config.chromium_user_data_dir())
    assert isolated not in joined
    config.load_config.cache_clear()


def test_profiles_lists_two_lanes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SATURN_FBC_SHARE", str(tmp_path / "share"))
    monkeypatch.setenv("SATURN_FBC_CHROMIUM_USER_DATA", str(tmp_path / "share" / "chromium"))
    monkeypatch.setenv("SATURN_FBC_TRUSTED_PROFILE", str(tmp_path / "share" / "trusted-chrome"))
    from saturn_fbc import config

    config.load_config.cache_clear()
    listing = list_browser_profiles()
    ids = [item["id"] for item in listing["profiles"]]
    assert ids == ["isolated-playwright", "trusted-chrome"]
    trusted = listing["profiles"][1]
    assert trusted["cdp"] is True
    isolated = listing["profiles"][0]
    assert isolated["cdp"] is True
    assert listing["profiles"][0]["user_data_dir"] != listing["profiles"][1]["user_data_dir"]
    config.load_config.cache_clear()


def test_sandbox_args_detects_apt_helper():
    helper = Path("/opt/google/chrome/chrome-sandbox")
    if not helper.is_file():
        pytest.skip("google-chrome-stable not installed")
    import stat as st

    info = helper.stat()
    if info.st_uid != 0 or st.S_IMODE(info.st_mode) != 0o4755:
        pytest.skip("chrome-sandbox is not setuid root")
    assert sandbox_args(Path("/usr/bin/google-chrome-stable")) == []


def test_start_without_executable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SATURN_FBC_SHARE", str(tmp_path / "share"))
    monkeypatch.setenv("SATURN_FBC_CHROMIUM_USER_DATA", str(tmp_path / "share" / "chromium"))
    monkeypatch.setenv("SATURN_FBC_TRUSTED_PROFILE", str(tmp_path / "share" / "trusted-chrome"))
    monkeypatch.setenv("SATURN_FBC_TRUSTED_EXECUTABLE", str(tmp_path / "missing-chrome"))
    from saturn_fbc import config

    config.load_config.cache_clear()
    result = start_trusted()
    assert result["ok"] is False
    assert result["error"] == "trusted_chrome_missing"
    status = trusted_status()
    assert status["running"] is False
    assert status["cdp"] is True
    assert status["cdp_url"] is None
    assert status["same_as_isolated"] is False
    config.load_config.cache_clear()
