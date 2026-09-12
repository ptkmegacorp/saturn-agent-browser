"""Read-only browser view/snapshot for the Pi panel."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from saturn_agent_browser.browser.view import capture_snapshot, list_cdp_pages, read_view


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


def test_read_view_disconnected(isolated_state: Path):
    view = read_view()
    assert view["ok"] is True
    assert view["connected"] is False
    assert view["tabs"] == []
    assert view["capabilities"]["snapshot"] is False
    assert view["browser"]["cdp_url"] is None


def test_list_cdp_pages_filters_non_pages(isolated_state: Path):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"id": "aaa", "type": "page", "url": "https://example.com/", "title": "Example"},
                {"id": "bbb", "type": "iframe", "url": "https://ads.example/", "title": "ad"},
                {"id": "", "type": "page", "url": "https://skip.example/", "title": "no-id"},
            ]

    with patch("saturn_agent_browser.browser.view.httpx.get", return_value=FakeResponse()):
        pages = list_cdp_pages("http://127.0.0.1:9")
    assert [p["tab_id"] for p in pages] == ["tab-aaa"]
    assert pages[0]["url"] == "https://example.com/"
    assert pages[0]["document_generation"].startswith("doc-")


def test_capture_snapshot_unknown_tab_when_disconnected(isolated_state: Path):
    result = capture_snapshot("tab-does-not-exist-xxxxxxxx")
    assert result["ok"] is False
    assert result["error"] in {"browser_disconnected", "unknown_tab", "cdp_unreachable"}


def test_capture_snapshot_matches_exact_tab(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
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
        def screenshot(self, **_kwargs):
            return b"\x89PNG\r\n\x1a\nfake"

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)

    shot = capture_snapshot("tab-abc")
    assert shot.get("ok") is True, shot
    assert shot["png"].startswith(b"\x89PNG")
    assert shot["tab_id"] == "tab-abc"
    stale = capture_snapshot("tab-ffffffffffffffffffffffffffffffff")
    assert stale["ok"] is False
    assert stale["error"] == "unknown_tab"


def test_capture_snapshot_rejects_stale_generation(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    pages = [
        {
            "tab_id": "tab-abc",
            "target_id": "abc",
            "url": "https://example.com/",
            "title": "Example",
            "document_generation": "doc-1",
        }
    ]
    monkeypatch.setattr("saturn_agent_browser.browser.view.list_cdp_pages", lambda _url, _lane=None: pages)

    class FakePage:
        def screenshot(self, **_kwargs):
            return b"\x89PNG\r\n\x1a\nfake"

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)

    assert capture_snapshot("tab-abc", expected_generation="doc-other")["error"] == "stale_document"
    ok = capture_snapshot("tab-abc", expected_generation="doc-1")
    assert ok["ok"] is True


def test_capture_snapshot_rejects_generation_changed_during_capture(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    calls = {"n": 0}

    def fake_list(_url, _lane=None):
        calls["n"] += 1
        gen = "doc-1" if calls["n"] == 1 else "doc-2"
        return [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": "https://example.com/" if calls["n"] == 1 else "https://example.com/next",
                "title": "Example",
                "document_generation": gen,
            }
        ]

    monkeypatch.setattr("saturn_agent_browser.browser.view.list_cdp_pages", fake_list)

    class FakePage:
        def screenshot(self, **_kwargs):
            return b"\x89PNG\r\n\x1a\nfake"

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)

    result = capture_snapshot("tab-abc", expected_generation="doc-1")
    assert result["ok"] is False
    assert result["error"] == "stale_document"


def test_navigate_requires_human_and_allowlist(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_agent_browser.browser.control import write_control_mode
    from saturn_agent_browser.browser.view import navigate_tab, validate_panel_url

    assert validate_panel_url("javascript:alert(1)")[1] == "invalid_url"
    assert validate_panel_url("https://user:pass@example.com/")[1] == "invalid_url"
    assert validate_panel_url("https://evil.example/")[1] == "origin_not_allowed"
    assert validate_panel_url("https://example.com/")[0] == "https://example.com/"

    write_control_mode("agent")
    blocked = navigate_tab("tab-abc", "https://example.com/", "doc-1")
    assert blocked["error"] == "human_control_required"

    write_control_mode("human")
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    shown_url = {"url": "about:blank"}

    def fake_navigate_list(_url, _lane=None):
        from saturn_agent_browser.browser import generations as _gens

        return [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": shown_url["url"],
                "title": shown_url["url"],
                "document_generation": _gens.observe(
                    lane="isolated", target_id="abc", url=shown_url["url"]
                ),
            }
        ]

    monkeypatch.setattr("saturn_agent_browser.browser.view.list_cdp_pages", fake_navigate_list)

    class FakePage:
        def goto(self, url, **_kwargs):
            shown_url["url"] = url

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)

    stale = navigate_tab("tab-abc", "https://example.com/", "doc-stale")
    assert stale["error"] == "stale_document"
    from saturn_agent_browser.browser import generations as _navigate_gens

    live_gen = _navigate_gens.observe(lane="isolated", target_id="abc", url=shown_url["url"])
    moved = navigate_tab("tab-abc", "https://example.com/", live_gen)
    assert moved.get("ok") is True, moved
