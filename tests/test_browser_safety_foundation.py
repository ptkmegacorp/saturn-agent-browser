"""Step-1 safety foundation: generations, leases, sensitive gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_agent_browser import config
from saturn_agent_browser.browser import generations, leases, sensitive


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setenv("SATURN_AGENT_BROWSER_SHARE", str(share))
    config.load_config.cache_clear()
    yield share
    config.load_config.cache_clear()


def test_observe_stable_for_same_url(isolated_state: Path):
    first = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    second = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    assert first == second
    assert first.startswith("doc-")


def test_observe_bumps_on_url_change(isolated_state: Path):
    before = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    after = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/next")
    assert before != after


def test_bump_forces_new_generation_same_url(isolated_state: Path):
    """Same-URL reload must invalidate the panel's held generation."""
    shown = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    reloaded = generations.bump(lane="isolated", target_id="AAA", url="https://example.com/", reason="navigate")
    assert shown != reloaded
    assert generations.observe(lane="isolated", target_id="AAA", url="https://example.com/") == reloaded


def test_evict_stale_drops_closed_tabs(isolated_state: Path):
    gen = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    assert gen.startswith("doc-")
    evicted = generations.evict_stale(lane="isolated", live_target_ids=set())
    assert evicted == ["AAA"]
    assert generations.current(lane="isolated", target_id="AAA") is None


def test_lanes_are_isolated(isolated_state: Path):
    a = generations.observe(lane="isolated", target_id="AAA", url="https://example.com/")
    b = generations.observe(lane="trusted", target_id="AAA", url="https://example.com/")
    assert a != b


def test_lease_acquire_validate_release(isolated_state: Path):
    acquired = leases.acquire(lane="isolated", tab_id="tab-AAA", operator="op", run_id="run-1")
    assert acquired["ok"] is True
    lease_id = acquired["lease"]["lease_id"]
    assert leases.validate(lease_id=lease_id, lane="isolated", tab_id="tab-AAA")["ok"] is True
    assert leases.release(lease_id=lease_id)["ok"] is True
    assert leases.validate(lease_id=lease_id)["ok"] is False


def test_lease_competing_controller_revokes(isolated_state: Path):
    first = leases.acquire(lane="isolated", tab_id="tab-AAA", operator="op-a")
    second = leases.acquire(lane="isolated", tab_id="tab-AAA", operator="op-b")
    assert second["ok"] is True
    assert first["lease"]["lease_id"] in second["revoked"]
    assert leases.validate(lease_id=first["lease"]["lease_id"])["ok"] is False
    assert leases.validate(lease_id=second["lease"]["lease_id"])["ok"] is True


def test_lease_wrong_tab_fails(isolated_state: Path):
    acquired = leases.acquire(lane="isolated", tab_id="tab-AAA", operator="op")
    lease_id = acquired["lease"]["lease_id"]
    assert leases.validate(lease_id=lease_id, tab_id="tab-BBB")["ok"] is False


def test_lease_stale_document_fails(isolated_state: Path):
    acquired = leases.acquire(
        lane="isolated", tab_id="tab-AAA", operator="op", document_generation="doc-1-x"
    )
    lease_id = acquired["lease"]["lease_id"]
    assert leases.validate(lease_id=lease_id, document_generation="doc-2-y")["error"] == "stale_document"


def test_sensitive_blocks_snapshot_without_lease(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_agent_browser.browser import view

    monkeypatch.setattr(view, "read_control_mode", lambda: "agent")
    assert sensitive.mark(lane="isolated", tab_id="tab-AAA")["ok"] is True
    result = view.capture_snapshot("tab-AAA", lane="isolated")
    assert result == {"ok": False, "error": "sensitive_blocked"}
    assert sensitive.clear(lane="isolated", tab_id="tab-AAA")["ok"] is True


def test_sensitive_allows_snapshot_with_human_lease(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_agent_browser.browser import view

    monkeypatch.setattr(view, "read_control_mode", lambda: "human")
    assert sensitive.mark(lane="isolated", tab_id="tab-AAA")["ok"] is True
    # No lease yet -> still blocked.
    assert view.capture_snapshot("tab-AAA", lane="isolated")["error"] == "sensitive_blocked"
    acquired = leases.acquire(lane="isolated", tab_id="tab-AAA", operator="op")
    assert acquired["ok"] is True
    # Blocked-ness lifts; the failure now comes from no browser running.
    result = view.capture_snapshot("tab-AAA", lane="isolated")
    assert result["error"] in {"browser_disconnected", "unknown_tab", "cdp_unreachable"}


def test_navigate_enforces_redirect_allowlist(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_agent_browser.browser.control import write_control_mode
    from saturn_agent_browser.browser.view import navigate_tab

    write_control_mode("human")
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    shown_url = {"url": "https://example.com/"}

    def fake_list(_url, _lane=None):
        return [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": shown_url["url"],
                "title": "t",
                "document_generation": generations.observe(
                    lane="isolated", target_id="abc", url=shown_url["url"]
                ),
            }
        ]

    monkeypatch.setattr("saturn_agent_browser.browser.view.list_cdp_pages", fake_list)

    class FakePage:
        def goto(self, url, **_kwargs):
            # Simulate a login redirect escaping the panel allowlist.
            shown_url["url"] = "https://evil.example/callback?code=secret"

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.view._page_target_id", lambda _page: "abc")
    monkeypatch.setattr("saturn_agent_browser.browser.view.release_browser_context", lambda *_a, **_k: None)

    gen = generations.observe(lane="isolated", target_id="abc", url="https://example.com/")
    result = navigate_tab("tab-abc", "https://example.com/", gen, lane="isolated")
    assert result["ok"] is False
    assert result["error"] == "origin_not_allowed"
    # Panel gets a fresh generation to resync; the stale held gen no longer works.
    assert result["document_generation"] != gen


def test_navigate_same_url_bumps_generation(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    from saturn_agent_browser.browser.control import write_control_mode
    from saturn_agent_browser.browser.view import navigate_tab

    write_control_mode("human")
    monkeypatch.setattr(
        "saturn_agent_browser.browser.view.browser_daemon_status",
        lambda: {"running": True, "cdp_url": "http://127.0.0.1:9", "pid": 1},
    )
    shown_url = {"url": "https://example.com/"}

    def fake_list(_url, _lane=None):
        return [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": shown_url["url"],
                "title": "t",
                "document_generation": generations.observe(
                    lane="isolated", target_id="abc", url=shown_url["url"]
                ),
            }
        ]

    monkeypatch.setattr("saturn_agent_browser.browser.view.list_cdp_pages", fake_list)

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

    gen = generations.observe(lane="isolated", target_id="abc", url="https://example.com/")
    moved = navigate_tab("tab-abc", "https://example.com/", gen, lane="isolated")
    assert moved.get("ok") is True, moved
    assert moved["document_generation"] != gen
