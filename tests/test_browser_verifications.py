"""Step-2 contextual presentation: verification handoffs (FBC backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_agent_browser import config
from saturn_agent_browser.browser import verifications


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    share = tmp_path / "share"
    share.mkdir()
    monkeypatch.setenv("SATURN_AGENT_BROWSER_SHARE", str(share))
    config.load_config.cache_clear()
    yield share
    config.load_config.cache_clear()


def live(url="https://example.com/login", generation="doc-9-abc", tab="tab-aaa"):
    def view(_lane):
        return {
            "ok": True,
            "connected": True,
            "lane": "isolated",
            "tabs": [
                {
                    "tab_id": tab,
                    "url": url,
                    "title": "Login",
                    "document_generation": generation,
                }
            ],
        }

    return view


def test_request_binds_live_document(isolated_state: Path):
    result = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", run_id="run-1", live_view_fn=live(),
    )
    assert result["ok"] is True, result
    handoff = result["handoff"]
    assert handoff["handoff_id"].startswith("vh_")
    assert handoff["origin"] == "https://example.com"
    assert handoff["status"] == "pending"


def test_request_rejects_stale_generation(isolated_state: Path):
    result = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-old",
        reason="login", live_view_fn=live(),
    )
    assert result == {"ok": False, "error": "stale_document"}


def test_request_rejects_unknown_tab(isolated_state: Path):
    result = verifications.request(
        lane="isolated", tab_id="tab-nope", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(),
    )
    assert result == {"ok": False, "error": "unknown_tab"}


def test_request_rejects_disconnected(isolated_state: Path):
    result = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=lambda _lane: {"ok": True, "connected": False, "tabs": []},
    )
    assert result == {"ok": False, "error": "browser_disconnected"}


def test_request_rejects_non_http_origin(isolated_state: Path):
    result = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(url="chrome://newtab/"),
    )
    assert result == {"ok": False, "error": "origin_mismatch"}


def test_repeated_detection_dedupes(isolated_state: Path):
    first = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", run_id="run-1", live_view_fn=live(),
    )
    second = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", run_id="run-1", live_view_fn=live(),
    )
    assert second["ok"] is True
    assert second["deduplicated"] is True
    assert second["handoff"]["handoff_id"] == first["handoff"]["handoff_id"]
    assert len(verifications.list_handoffs()["handoffs"]) == 1


def test_different_reason_is_new_handoff(isolated_state: Path):
    verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", run_id="run-1", live_view_fn=live(),
    )
    other = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="mfa", run_id="run-1", live_view_fn=live(),
    )
    assert other["deduplicated"] is False
    assert len(verifications.list_handoffs()["handoffs"]) == 2


def test_sync_marks_reloaded_document_stale(isolated_state: Path):
    verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(),
    )
    out = verifications.sync_lane(lane="isolated", live_view_fn=live(generation="doc-10-new"))
    assert out["handoffs"] == []
    assert verifications.list_handoffs(state="all")["handoffs"][0]["status"] == "stale"


def test_sync_marks_closed_tab_gone(isolated_state: Path):
    verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(),
    )
    out = verifications.sync_lane(
        lane="isolated",
        live_view_fn=lambda _lane: {"ok": True, "connected": True, "tabs": []},
    )
    assert out["handoffs"] == []
    assert verifications.list_handoffs(state="all")["handoffs"][0]["status"] == "gone"


def test_resolve_done_and_cancelled(isolated_state: Path):
    created = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(),
    )
    handoff_id = created["handoff"]["handoff_id"]
    done = verifications.resolve(handoff_id=handoff_id, decision="done", note="verified /secure")
    assert done["ok"] is True
    assert done["handoff"]["status"] == "done"
    again = verifications.resolve(handoff_id=handoff_id, decision="cancelled")
    assert again == {"ok": False, "error": "already_done"}
    assert verifications.resolve(handoff_id="vh_missing", decision="done") == {
        "ok": False,
        "error": "unknown_handoff",
    }
    assert verifications.resolve(handoff_id=handoff_id, decision="bogus") == {
        "ok": False,
        "error": "invalid_decision",
    }


def test_expired_handoffs_leave_pending(isolated_state: Path):
    verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", ttl_sec=60, live_view_fn=live(),
    )
    # Force expiry by backdating the stored record.
    import json

    path = verifications._store_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    only = next(iter(data["handoffs"].values()))
    only["expires_at"] = "2020-01-01T00:00:00Z"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert verifications.list_handoffs()["handoffs"] == []
    assert verifications.list_handoffs(state="all")["handoffs"][0]["status"] == "expired"


def test_handoff_view_has_no_secrets(isolated_state: Path):
    created = verifications.request(
        lane="isolated", tab_id="tab-aaa", document_generation="doc-9-abc",
        reason="login", live_view_fn=live(),
    )
    blob = json_dumps(created["handoff"])
    for word in ("password", "secret", "cookie", "token", "credential"):
        assert word not in blob.lower()


def json_dumps(payload) -> str:
    import json

    return json.dumps(payload)
