"""Step-3 protected interaction: lease-gated tap/scroll (FBC backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_agent_browser import config
from saturn_agent_browser.browser import generations, interact, leases
from saturn_agent_browser.browser.control import write_control_mode


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setenv("SATURN_AGENT_BROWSER_SHARE", str(share))
    config.load_config.cache_clear()
    yield share
    config.load_config.cache_clear()


@pytest.fixture
def human_with_lease(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    write_control_mode("human")
    monkeypatch.setattr(
        "saturn_agent_browser.browser.interact._lane_runtime",
        lambda lane: {"running": True, "cdp_url": "http://127.0.0.1:9"},
    )
    shown = {"url": "https://example.com/"}

    def fake_list(_url, _lane=None):
        return [
            {
                "tab_id": "tab-abc",
                "target_id": "abc",
                "url": shown["url"],
                "title": "Example",
                "document_generation": generations.observe(
                    lane="isolated", target_id="abc", url=shown["url"]
                ),
            }
        ]

    monkeypatch.setattr("saturn_agent_browser.browser.interact.list_cdp_pages", fake_list)

    class FakeMouse:
        def __init__(self):
            self.clicks = []
            self.wheels = []

        def click(self, x, y):
            self.clicks.append((x, y))

        def wheel(self, dx, dy):
            self.wheels.append((dx, dy))

    mouse = FakeMouse()

    class FakePage:
        def __init__(self):
            self.mouse = mouse

    class FakeContext:
        pages = [FakePage()]

    monkeypatch.setattr(
        "saturn_agent_browser.browser.interact.connect_over_cdp",
        lambda _url: (None, FakeContext(), True),
    )
    monkeypatch.setattr("saturn_agent_browser.browser.interact._find_page", lambda _ctx, _tid: FakeContext.pages[0])
    monkeypatch.setattr("saturn_agent_browser.browser.interact.release_browser_context", lambda *_a, **_k: None)

    acquired = leases.acquire(lane="isolated", tab_id="tab-abc", operator="op")
    assert acquired["ok"] is True
    gen = generations.observe(lane="isolated", target_id="abc", url=shown["url"])
    return {"mouse": mouse, "shown": shown, "gen": gen}


def test_tap_requires_human_and_lease(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    write_control_mode("agent")
    assert interact.tap("tab-abc", 10, 10, "doc-1")["error"] == "human_control_required"
    write_control_mode("human")
    assert interact.tap("tab-abc", 10, 10, "doc-1")["error"] == "lease_required"


def test_tap_rejects_bad_coordinates(human_with_lease):
    assert interact.tap("tab-abc", -5, 10, human_with_lease["gen"])["error"] == "invalid_coordinates"
    assert interact.tap("tab-abc", 10, "far", human_with_lease["gen"])["error"] == "invalid_coordinates"
    assert interact.tap("tab-abc", 10**9, 10, human_with_lease["gen"])["error"] == "invalid_coordinates"


def test_tap_clicks_and_bumps_generation(human_with_lease):
    before = human_with_lease["gen"]
    result = interact.tap("tab-abc", 120, 300, before)
    assert result.get("ok") is True, result
    assert human_with_lease["mouse"].clicks == [(120.0, 300.0)]
    assert result["document_generation"] != before
    assert result["origin_changed"] is False


def test_tap_rejects_stale_generation(human_with_lease):
    assert interact.tap("tab-abc", 10, 10, "doc-stale")["error"] == "stale_document"
    assert human_with_lease["mouse"].clicks == []


def test_tap_reports_origin_change_not_block(human_with_lease, monkeypatch: pytest.MonkeyPatch):
    import saturn_agent_browser.browser.interact as module

    real_after = module._after_action
    human_with_lease["shown"]["url"] = "https://accounts.example-idp.com/login"
    before = human_with_lease["gen"]
    # Fresh live generation for the new URL, then tap against it.
    gen = generations.observe(lane="isolated", target_id="abc", url=human_with_lease["shown"]["url"])
    assert gen != before
    result = interact.tap("tab-abc", 10, 10, gen)
    assert result.get("ok") is True, result
    assert result["url"] == "https://accounts.example-idp.com/login"
    assert real_after is not None


def test_scroll_wheels_and_bumps(human_with_lease):
    before = human_with_lease["gen"]
    result = interact.scroll("tab-abc", "down", before, amount=500)
    assert result.get("ok") is True, result
    assert human_with_lease["mouse"].wheels == [(0, 500)]
    assert result["document_generation"] != before

    gen2 = result["document_generation"]
    up = interact.scroll("tab-abc", "up", gen2, amount=100)
    assert up.get("ok") is True, up
    assert human_with_lease["mouse"].wheels[-1] == (0, -100)


def test_scroll_rejects_bad_direction(human_with_lease):
    assert interact.scroll("tab-abc", "sideways", human_with_lease["gen"])["error"] == "invalid_direction"


def test_input_on_sensitive_tab_allowed_with_lease(isolated_state: Path, monkeypatch: pytest.MonkeyPatch):
    """The human lease is exactly what opens the sensitive channel."""
    from saturn_agent_browser.browser import sensitive

    write_control_mode("human")
    assert sensitive.mark(lane="isolated", tab_id="tab-abc")["ok"] is True
    # No lease yet: snapshot-style paths stay closed and tap refuses too.
    assert interact.tap("tab-abc", 10, 10, "doc-1")["error"] == "lease_required"
