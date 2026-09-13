"""Agent-readable DOM capture for the Pi panel / CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_agent_browser.browser.view import capture_dom
from saturn_agent_browser.browser.capture import ObservationSnapshot


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    share = tmp_path / "share"
    share.mkdir()
    browsers = Path.home() / ".local/share/saturn-agent-browser/playwright-browsers"
    monkeypatch.setenv("SATURN_AGENT_BROWSER_SHARE", str(share))
    monkeypatch.setenv("SATURN_AGENT_BROWSER_CHROMIUM_USER_DATA", str(share / "chromium"))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    monkeypatch.setenv("SATURN_AGENT_BROWSER_BROWSER_MODE", "daemon")
    from saturn_agent_browser import config

    config.load_config.cache_clear()
    yield share
    config.load_config.cache_clear()


def _patch_cdp(monkeypatch: pytest.MonkeyPatch, snap: ObservationSnapshot):
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.list_cdp_pages",
        lambda _url, _lane=None: [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": "https://example.com/",
                "title": "Example",
                "document_generation": "doc-1",
            }
        ],
    )

    class FakePage:
        pass

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)
    monkeypatch.setattr("saturn_agent_browser.browser.view.capture_a11y_indexed", lambda _page: snap)


def test_capture_dom_ok_and_redacts_secrets(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    snap = ObservationSnapshot(
        url="https://example.com/",
        title="Example",
        mode="a11y_indexed",
        nodes=[
            {"index": 1, "role": "link", "name": "Learn more", "value": ""},
            {"index": 2, "role": "textbox", "name": "password", "value": "hunter2-secret"},
        ],
        digest="[1] link \"Learn more\"\n[2] textbox \"password\"",
    )
    _patch_cdp(monkeypatch, snap)

    result = capture_dom("tab-abc", expected_generation="doc-1")
    assert result["ok"] is True, result
    assert result["tab_id"] == "tab-abc"
    assert result["node_count"] == 2
    assert "[1]" in result["digest"] and "Learn more" in result["digest"]
    assert "hunter2-secret" not in result["digest"]
    assert "hunter2-secret" not in str(result["nodes"])
    assert result["nodes"][1]["value"] == "[redacted]"


def test_capture_dom_rejects_stale_and_unknown(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    snap = ObservationSnapshot(url="u", title="t", mode="a11y_indexed", nodes=[], digest="(empty page)")
    _patch_cdp(monkeypatch, snap)

    assert capture_dom("tab-abc", expected_generation="doc-other")["error"] == "stale_document"
    assert capture_dom("tab-nope")["error"] == "unknown_tab"
    assert capture_dom("bad-id")["error"] == "invalid_tab_id"


def test_capture_dom_truncates(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    nodes = [{"index": i + 1, "role": "link", "name": f"story {i}", "value": ""} for i in range(10)]
    snap = ObservationSnapshot(url="u", title="t", mode="a11y_indexed", nodes=nodes, digest="x")
    _patch_cdp(monkeypatch, snap)

    result = capture_dom("tab-abc", max_nodes=3, max_chars=500)
    assert result["ok"] is True
    assert result["node_count"] == 10
    assert len(result["nodes"]) == 3
    assert result["truncated"] is True
