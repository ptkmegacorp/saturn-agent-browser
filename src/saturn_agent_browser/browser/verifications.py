"""Task-linked browser verification handoffs (Open verification).

When a bounded browser task hits authentication/verification it cannot
complete itself, FBC records a handoff: the exact live (lane, tab, document
generation, origin) plus reason, expected completion condition, expiry and
an optional linked Saturn Auth request. The Pi capsule renders the handoff
as an attention card next to the exact browser surface and the linked Auth
approval; Done/Cancel resolves it and the task resumes only on independent
verification.

Safety properties:
- request binds to the LIVE document: tab must exist and the caller-held
  generation must match the live one, else stale_document. A same-URL
  reload between detection and request invalidates the handoff.
- origin must be a valid http(s) origin and equal the live tab origin,
  else origin_mismatch. Webpage text is untrusted; only host/task callers
  create handoffs.
- repeated detection dedupes against (run, tab, generation, reason).
- terminal states (done/cancelled/expired/stale/gone) are sticky; sync()
  revalidates pending handoffs against the live view.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlparse


def _store_path():
    from saturn_agent_browser.browser.state import state_file_path

    return state_file_path().with_name("browser-verifications.json")


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _blank() -> dict[str, Any]:
    return {"handoffs": {}}


def _load() -> dict[str, Any]:
    path = _store_path()
    if not path.is_file():
        return _blank()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blank()
    if not isinstance(data, dict) or not isinstance(data.get("handoffs"), dict):
        return _blank()
    return data


def _save(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


TERMINAL = frozenset({"done", "cancelled", "expired", "stale", "gone"})


def _expired(handoff: dict[str, Any]) -> bool:
    try:
        expiry = datetime.fromisoformat(str(handoff.get("expires_at")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    return expiry <= _now()


def _mark_expired(data: dict[str, Any]) -> None:
    for handoff in data["handoffs"].values():
        if isinstance(handoff, dict) and handoff.get("status") == "pending" and _expired(handoff):
            handoff["status"] = "expired"


def _live_view(lane: str) -> dict[str, Any]:
    from saturn_agent_browser.browser.view import normalize_lane, read_view

    return read_view(normalize_lane(lane))


def _origin_of(url: str) -> str | None:
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return None
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def sanitize(handoff: dict[str, Any]) -> dict[str, Any]:
    return {
        "handoff_id": handoff.get("handoff_id"),
        "task_id": handoff.get("task_id"),
        "run_id": handoff.get("run_id"),
        "lane": handoff.get("lane"),
        "tab_id": handoff.get("tab_id"),
        "document_generation": handoff.get("document_generation"),
        "origin": handoff.get("origin"),
        "reason": handoff.get("reason"),
        "expects": handoff.get("expects"),
        "auth_request_id": handoff.get("auth_request_id"),
        "status": handoff.get("status"),
        "expires_at": handoff.get("expires_at"),
        "created_at": handoff.get("created_at"),
    }


def request(
    *,
    lane: str,
    tab_id: str,
    document_generation: str,
    reason: str,
    task_id: str | None = None,
    run_id: str | None = None,
    caller: str = "saturn-agent-browser",
    expects: str | None = None,
    auth_request_id: str | None = None,
    ttl_sec: int = 300,
    live_view_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create (or dedupe) a verification handoff bound to the live document."""
    from saturn_agent_browser.browser.view import normalize_lane

    lane = normalize_lane(lane)
    tab_id = (tab_id or "").strip()
    generation = (document_generation or "").strip()
    reason = (reason or "").strip()
    if not tab_id.startswith("tab-"):
        return {"ok": False, "error": "invalid_tab_id"}
    if not generation.startswith("doc-"):
        return {"ok": False, "error": "invalid_generation"}
    if not reason:
        return {"ok": False, "error": "reason_required"}
    ttl = max(60, min(int(ttl_sec or 300), 3600))

    view = (live_view_fn or _live_view)(lane)
    if not view.get("connected"):
        return {"ok": False, "error": "browser_disconnected"}
    live = next((t for t in view.get("tabs", []) if t.get("tab_id") == tab_id), None)
    if live is None:
        return {"ok": False, "error": "unknown_tab"}
    if live.get("document_generation") != generation:
        return {"ok": False, "error": "stale_document"}
    origin = _origin_of(live.get("url") or "")
    if origin is None:
        return {"ok": False, "error": "origin_mismatch"}

    data = _load()
    _mark_expired(data)
    for handoff in data["handoffs"].values():
        if (
            isinstance(handoff, dict)
            and handoff.get("status") == "pending"
            and handoff.get("lane") == lane
            and handoff.get("tab_id") == tab_id
            and handoff.get("document_generation") == generation
            and handoff.get("reason") == reason
            and (handoff.get("run_id") or None) == (run_id or None)
        ):
            return {"ok": True, "deduplicated": True, "handoff": sanitize(handoff)}

    now = _now()
    handoff_id = f"vh_{uuid.uuid4().hex[:16]}"
    handoff = {
        "handoff_id": handoff_id,
        "task_id": task_id,
        "run_id": run_id,
        "caller": (caller or "").strip() or "saturn-agent-browser",
        "lane": lane,
        "tab_id": tab_id,
        "document_generation": generation,
        "origin": origin,
        "reason": reason,
        "expects": expects,
        "auth_request_id": auth_request_id,
        "status": "pending",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=ttl)),
    }
    data["handoffs"][handoff_id] = handoff
    _save(data)
    return {"ok": True, "deduplicated": False, "handoff": sanitize(handoff)}


def list_handoffs(
    *,
    state: str = "pending",
    lane: str | None = None,
    live_view_fn: Callable[[str], dict[str, Any]] | None = None,
    sync: bool = False,
) -> dict[str, Any]:
    """List handoffs (default: pending). sync=True revalidates first."""
    data = _load()
    _mark_expired(data)
    if sync:
        for lane_name in ({h.get("lane") for h in data["handoffs"].values() if isinstance(h, dict)} | ({lane} if lane else set())):
            if lane_name:
                _sync_lane(data, lane_name, live_view_fn)
    _save(data)
    out = []
    for handoff in data["handoffs"].values():
        if not isinstance(handoff, dict):
            continue
        if state != "all" and handoff.get("status") != state:
            continue
        if lane is not None and handoff.get("lane") != lane:
            continue
        out.append(sanitize(handoff))
    out.sort(key=lambda h: h.get("created_at") or "")
    return {"ok": True, "handoffs": out}


def _sync_lane(data: dict[str, Any], lane: str, live_view_fn=None) -> None:
    view = (live_view_fn or _live_view)(lane)
    live_by_tab = {t.get("tab_id"): t for t in view.get("tabs", [])} if view.get("connected") else {}
    for handoff in data["handoffs"].values():
        if not isinstance(handoff, dict) or handoff.get("status") != "pending" or handoff.get("lane") != lane:
            continue
        if _expired(handoff):
            handoff["status"] = "expired"
            continue
        live = live_by_tab.get(handoff.get("tab_id"))
        if live is None:
            # Tab closed/replaced, or browser down (empty view): only mark
            # gone when the browser is reachable but the tab is absent.
            if view.get("connected"):
                handoff["status"] = "gone"
            continue
        if live.get("document_generation") != handoff.get("document_generation"):
            handoff["status"] = "stale"


def sync_lane(*, lane: str, live_view_fn=None) -> dict[str, Any]:
    from saturn_agent_browser.browser.view import normalize_lane

    lane = normalize_lane(lane)
    data = _load()
    _mark_expired(data)
    _sync_lane(data, lane, live_view_fn)
    _save(data)
    return list_handoffs(state="pending", lane=lane)


def resolve(*, handoff_id: str, decision: str, note: str | None = None) -> dict[str, Any]:
    """Resolve a pending handoff as done (verified) or cancelled."""
    decision = (decision or "").strip()
    if decision not in {"done", "cancelled"}:
        return {"ok": False, "error": "invalid_decision"}
    data = _load()
    _mark_expired(data)
    handoff = data["handoffs"].get((handoff_id or "").strip())
    if not isinstance(handoff, dict):
        return {"ok": False, "error": "unknown_handoff"}
    if handoff.get("status") != "pending":
        return {"ok": False, "error": f"already_{handoff.get('status')}"}
    handoff["status"] = decision
    handoff["resolved_at"] = _iso(_now())
    if note:
        handoff["note"] = str(note)[:500]
    _save(data)
    return {"ok": True, "handoff": sanitize(handoff)}


def clear_all() -> None:
    path = _store_path()
    if path.is_file():
        path.unlink()
