"""Read-only tab list, snapshot, and human-gated navigate for the Pi panel."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from saturn_agent_browser.browser.control import read_control_mode, write_control_mode
from saturn_agent_browser.browser.daemon import browser_daemon_status
from saturn_agent_browser.browser import generations
from saturn_agent_browser.browser.capture import _should_redact, capture_a11y_indexed
from saturn_agent_browser.browser.interceptor import _host_allowed
from saturn_agent_browser.browser import leases
from saturn_agent_browser.browser.profile import connect_over_cdp, release_browser_context
from saturn_agent_browser.browser import sensitive
from saturn_agent_browser.browser.trusted import trusted_status
from saturn_agent_browser import config as browser_config

DEFAULT_PANEL_HOSTS = (
    "example.com,httpbin.org,the-internet.herokuapp.com,google.com,127.0.0.1,localhost"
)

CAPABILITIES_DISCONNECTED = {
    "snapshot": False,
    "dom": False,
    "streaming": False,
    "inspect": False,
    "navigate": False,
    "reason_snapshot": "browser_disconnected",
    "reason_dom": "browser_disconnected",
    "reason_streaming": "not_implemented",
    "reason_inspect": "not_implemented",
    "reason_navigate": "browser_disconnected",
}


def normalize_lane(lane: str | None) -> str:
    wanted = (lane or "isolated").strip().lower()
    if wanted in {"trusted", "trusted-chrome", "chrome"}:
        return "trusted"
    return "isolated"


def _lane_runtime(lane: str) -> dict[str, Any]:
    if lane == "trusted":
        status = trusted_status()
        return {
            "running": bool(status.get("running")),
            "pid": status.get("pid"),
            "cdp_url": status.get("cdp_url") or browser_config.trusted_cdp_url(),
            "label": "Chrome",
        }
    status = browser_daemon_status()
    return {
        "running": bool(status.get("running")),
        "pid": status.get("pid"),
        "cdp_url": status.get("cdp_url"),
        "label": "Chromium",
    }


def _any_browser_running() -> bool:
    return bool(browser_daemon_status().get("running") or trusted_status().get("running"))


def panel_navigate_hosts() -> list[str]:
    raw = os.environ.get("SATURN_AGENT_BROWSER_PANEL_NAVIGATE_HOSTS", DEFAULT_PANEL_HOSTS)
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _connected_capabilities(mode: str) -> dict[str, Any]:
    human = mode == "human"
    return {
        "snapshot": True,
        "dom": True,
        "streaming": False,
        "inspect": False,
        "navigate": human,
        "reason_dom": None,
        "reason_streaming": "not_implemented",
        "reason_inspect": "not_implemented",
        "reason_navigate": None if human else "human_control_required",
    }


def _tab_id(target_id: str) -> str:
    return f"tab-{target_id}"


def _sanitize_text(value: str, *, limit: int = 500) -> str:
    text = (value or "").replace("\x00", "")
    if len(text) > limit:
        return text[:limit]
    return text


def _browser_payload(status: dict[str, Any], *, connected: bool) -> dict[str, Any]:
    return {
        "running": bool(status.get("running")),
        "pid": status.get("pid") if connected or status.get("running") else None,
        "cdp_url": None,
    }


def list_cdp_pages(cdp_url: str, lane: str | None = None) -> list[dict[str, Any]]:
    lane = normalize_lane(lane)
    url = f"{cdp_url.rstrip('/')}/json"
    response = httpx.get(url, timeout=3.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    pages = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "page":
            continue
        target_id = str(item.get("id") or "").strip()
        if not target_id:
            continue
        page_url = _sanitize_text(str(item.get("url") or ""))
        seen.add(target_id)
        pages.append(
            {
                "tab_id": _tab_id(target_id),
                "target_id": target_id,
                "url": page_url,
                "title": _sanitize_text(str(item.get("title") or "")),
                "document_generation": generations.observe(lane=lane, target_id=target_id, url=page_url),
            }
        )
    generations.evict_stale(lane=lane, live_target_ids=seen)
    return pages


def read_view(lane: str | None = None) -> dict[str, Any]:
    lane = normalize_lane(lane)
    runtime = _lane_runtime(lane)
    mode = read_control_mode()
    if not runtime["running"]:
        return {
            "ok": True,
            "connected": False,
            "lane": lane,
            "ownership": "unknown",
            "run_id": None,
            "tabs": [],
            "selected_tab_id": None,
            "capabilities": dict(CAPABILITIES_DISCONNECTED),
            "browser": _browser_payload(runtime, connected=False),
        }
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url, lane)
    except Exception:
        return {
            "ok": False,
            "connected": False,
            "lane": lane,
            "error": "cdp_unreachable",
            "ownership": mode,
            "tabs": [],
            "selected_tab_id": None,
            "capabilities": dict(CAPABILITIES_DISCONNECTED),
            "browser": _browser_payload(runtime, connected=False),
        }
    selected = pages[0]["tab_id"] if pages else None
    for index, page in enumerate(pages):
        page["selected"] = index == 0
    return {
        "ok": True,
        "connected": True,
        "lane": lane,
        "ownership": mode,
        "run_id": None,
        "tabs": [{k: v for k, v in page.items() if k != "target_id"} for page in pages],
        "selected_tab_id": selected,
        "capabilities": _connected_capabilities(mode),
        "browser": _browser_payload(runtime, connected=True),
    }


def set_panel_control(mode: str) -> dict[str, Any]:
    if str(mode or "").strip() == "human" and not _any_browser_running():
        return {"ok": False, "error": "browser_disconnected"}
    result = write_control_mode(mode)
    if not result.get("ok"):
        return result
    view = read_view("trusted")
    return {"ok": True, "mode": result["mode"], "ownership": view.get("ownership"), "view": view}


def _page_target_id(page) -> str:
    session = page.context.new_cdp_session(page)
    try:
        info = session.send("Target.getTargetInfo")
        target = info.get("targetInfo") if isinstance(info, dict) else None
        if not isinstance(target, dict):
            target = info if isinstance(info, dict) else {}
        return str(target.get("targetId") or "")
    finally:
        session.detach()


def _find_page(context, target_id: str):
    for page in context.pages:
        try:
            if _page_target_id(page) == target_id:
                return page
        except Exception:
            continue
    return None


def _tab_from_pages(pages: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    return next((item for item in pages if item["target_id"] == target_id), None)


def capture_snapshot(tab_id: str, expected_generation: str | None = None, lane: str | None = None) -> dict[str, Any]:
    wanted = (tab_id or "").strip()
    if not wanted.startswith("tab-") or len(wanted) <= 4:
        return {"ok": False, "error": "invalid_tab_id"}
    expected = (expected_generation or "").strip() or None
    if expected is not None and not expected.startswith("doc-"):
        return {"ok": False, "error": "invalid_generation"}
    lane = normalize_lane(lane)
    if sensitive.is_sensitive(lane=lane, tab_id=wanted):
        human_lease = read_control_mode() == "human" and bool(leases.list_active(lane=lane, tab_id=wanted))
        if not human_lease:
            return {"ok": False, "error": "sensitive_blocked"}
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(lane)
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url, lane)
    except Exception:
        return {"ok": False, "error": "cdp_unreachable"}
    meta = _tab_from_pages(pages, target_id)
    if meta is None:
        return {"ok": False, "error": "unknown_tab"}
    if expected is not None and meta["document_generation"] != expected:
        return {"ok": False, "error": "stale_document"}
    pw = None
    context = None
    try:
        pw, context, _attached = connect_over_cdp(cdp_url)
        match = _find_page(context, target_id)
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        png = match.screenshot(type="png", full_page=False)
        try:
            after = list_cdp_pages(cdp_url, lane)
        except Exception:
            return {"ok": False, "error": "cdp_unreachable"}
        live = _tab_from_pages(after, target_id)
        if live is None:
            return {"ok": False, "error": "unknown_tab"}
        if expected is not None and live["document_generation"] != expected:
            return {"ok": False, "error": "stale_document"}
        return {
            "ok": True,
            "png": png,
            "tab_id": live["tab_id"],
            "document_generation": live["document_generation"],
            "url": live["url"],
            "title": live["title"],
        }
    except Exception:
        return {"ok": False, "error": "snapshot_failed"}
    finally:
        release_browser_context(context, pw, attached=True)


def _redacted_dom_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy a11y nodes with secret values redacted and text lengths bounded."""
    redacted: list[dict[str, Any]] = []
    for node in nodes:
        entry = dict(node)
        if _should_redact(node):
            entry["value"] = "[redacted]"
        for key in ("name", "value", "description"):
            value = entry.get(key)
            if isinstance(value, str) and len(value) > 300:
                entry[key] = value[:300]
        redacted.append(entry)
    return redacted


def capture_dom(
    tab_id: str,
    expected_generation: str | None = None,
    lane: str | None = None,
    max_nodes: int = 200,
    max_chars: int = 12000,
) -> dict[str, Any]:
    """Agent-readable DOM: numbered a11y digest + structured nodes as JSON.

    Read-only like ``capture_snapshot`` (no control-mode gate) but returns
    text instead of PNG. Same sensitive/lease and stale-generation guards.
    """
    wanted = (tab_id or "").strip()
    if not wanted.startswith("tab-") or len(wanted) <= 4:
        return {"ok": False, "error": "invalid_tab_id"}
    expected = (expected_generation or "").strip() or None
    if expected is not None and not expected.startswith("doc-"):
        return {"ok": False, "error": "invalid_generation"}
    try:
        max_nodes = int(max_nodes)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_max_nodes"}
    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_max_chars"}
    max_nodes = max(1, min(max_nodes, 1000))
    max_chars = max(500, min(max_chars, 100000))
    lane = normalize_lane(lane)
    if sensitive.is_sensitive(lane=lane, tab_id=wanted):
        human_lease = read_control_mode() == "human" and bool(leases.list_active(lane=lane, tab_id=wanted))
        if not human_lease:
            return {"ok": False, "error": "sensitive_blocked"}
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(lane)
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url, lane)
    except Exception:
        return {"ok": False, "error": "cdp_unreachable"}
    meta = _tab_from_pages(pages, target_id)
    if meta is None:
        return {"ok": False, "error": "unknown_tab"}
    if expected is not None and meta["document_generation"] != expected:
        return {"ok": False, "error": "stale_document"}
    pw = None
    context = None
    try:
        pw, context, _attached = connect_over_cdp(cdp_url)
        match = _find_page(context, target_id)
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        snap = capture_a11y_indexed(match)
        nodes = _redacted_dom_nodes(snap.nodes)
        total_nodes = len(nodes)
        shown_nodes = nodes[:max_nodes]
        lines = []
        for node in shown_nodes:
            role = node.get("role") or "generic"
            label = node.get("name") or node.get("value") or ""
            lines.append(f"[{node.get('index')}] {role} \"{label}\"" if label else f"[{node.get('index')}] {role}")
        digest = "\n".join(lines) if lines else "(empty page)"
        truncated = total_nodes > len(shown_nodes) or len(digest) > max_chars
        if len(digest) > max_chars:
            digest = digest[:max_chars]
        try:
            after = list_cdp_pages(cdp_url, lane)
        except Exception:
            return {"ok": False, "error": "cdp_unreachable"}
        live = _tab_from_pages(after, target_id)
        if live is None:
            return {"ok": False, "error": "unknown_tab"}
        if expected is not None and live["document_generation"] != expected:
            return {"ok": False, "error": "stale_document"}
        return {
            "ok": True,
            "tab_id": live["tab_id"],
            "document_generation": live["document_generation"],
            "url": live["url"] or snap.url,
            "title": live["title"] or snap.title,
            "mode": snap.mode,
            "node_count": total_nodes,
            "truncated": truncated,
            "digest": digest,
            "nodes": shown_nodes,
        }
    except Exception:
        return {"ok": False, "error": "dom_failed"}
    finally:
        release_browser_context(context, pw, attached=True)


def validate_panel_url(url: str) -> tuple[str | None, str | None]:
    raw = (url or "").strip()
    if not raw or len(raw) > 2000:
        return None, "invalid_url"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return None, "invalid_url"
    if parsed.username or parsed.password:
        return None, "invalid_url"
    host = (parsed.hostname or "").lower()
    if not host:
        return None, "invalid_url"
    allow = panel_navigate_hosts()
    if not allow or not _host_allowed(host, allow):
        return None, "origin_not_allowed"
    return raw, None


def navigate_tab(tab_id: str, url: str, expected_generation: str, lane: str | None = None) -> dict[str, Any]:
    if read_control_mode() != "human":
        return {"ok": False, "error": "human_control_required"}
    wanted = (tab_id or "").strip()
    expected = (expected_generation or "").strip()
    if not wanted.startswith("tab-") or len(wanted) <= 4:
        return {"ok": False, "error": "invalid_tab_id"}
    if not expected.startswith("doc-"):
        return {"ok": False, "error": "invalid_generation"}
    lane = normalize_lane(lane)
    if sensitive.is_sensitive(lane=lane, tab_id=wanted) and not leases.list_active(lane=lane, tab_id=wanted):
        return {"ok": False, "error": "lease_required"}
    target, err = validate_panel_url(url)
    if err:
        return {"ok": False, "error": err}
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(lane)
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url, lane)
    except Exception:
        return {"ok": False, "error": "cdp_unreachable"}
    meta = _tab_from_pages(pages, target_id)
    if meta is None:
        return {"ok": False, "error": "unknown_tab"}
    if meta["document_generation"] != expected:
        return {"ok": False, "error": "stale_document"}
    pw = None
    context = None
    try:
        pw, context, _attached = connect_over_cdp(cdp_url)
        match = _find_page(context, target_id)
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        match.goto(target, wait_until="domcontentloaded", timeout=20_000)
        after = list_cdp_pages(cdp_url, lane)
        live = _tab_from_pages(after, target_id)
        if live is None:
            return {"ok": False, "error": "unknown_tab"}
        final_url = live["url"]
        # Redirect enforcement: the post-navigate document must still be
        # allowlisted. A login/consent redirect off the panel hosts stops
        # here with a fresh generation so the panel can resync.
        _, redirect_err = validate_panel_url(final_url)
        new_generation = generations.bump(lane=lane, target_id=target_id, url=final_url, reason="navigate")
        if redirect_err:
            return {
                "ok": False,
                "error": redirect_err,
                "tab_id": live["tab_id"],
                "url": final_url,
                "title": live["title"],
                "document_generation": new_generation,
            }
        return {
            "ok": True,
            "tab_id": live["tab_id"],
            "url": final_url,
            "title": live["title"],
            "document_generation": new_generation,
        }
    except Exception:
        return {"ok": False, "error": "navigate_failed"}
    finally:
        release_browser_context(context, pw, attached=True)
