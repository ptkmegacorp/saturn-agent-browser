"""Read-only tab list, snapshot, and human-gated navigate for the Pi panel."""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from saturn_fbc.browser.control import read_control_mode, write_control_mode
from saturn_fbc.browser.daemon import browser_daemon_status
from saturn_fbc.browser.interceptor import _host_allowed
from saturn_fbc.browser.profile import connect_over_cdp, release_browser_context
from saturn_fbc.browser.trusted import trusted_status
from saturn_fbc import config as fbc_config

DEFAULT_PANEL_HOSTS = (
    "example.com,httpbin.org,the-internet.herokuapp.com,google.com,127.0.0.1,localhost"
)

CAPABILITIES_DISCONNECTED = {
    "snapshot": False,
    "streaming": False,
    "inspect": False,
    "navigate": False,
    "reason_snapshot": "browser_disconnected",
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
            "cdp_url": status.get("cdp_url") or fbc_config.trusted_cdp_url(),
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
    raw = os.environ.get("SATURN_FBC_PANEL_NAVIGATE_HOSTS", DEFAULT_PANEL_HOSTS)
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _connected_capabilities(mode: str) -> dict[str, Any]:
    human = mode == "human"
    return {
        "snapshot": True,
        "streaming": False,
        "inspect": False,
        "navigate": human,
        "reason_streaming": "not_implemented",
        "reason_inspect": "not_implemented",
        "reason_navigate": None if human else "human_control_required",
    }


def _generation(target_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{target_id}\n{url}".encode("utf-8")).hexdigest()[:12]
    return f"doc-{digest}"


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


def list_cdp_pages(cdp_url: str) -> list[dict[str, Any]]:
    url = f"{cdp_url.rstrip('/')}/json"
    response = httpx.get(url, timeout=3.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    pages = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "page":
            continue
        target_id = str(item.get("id") or "").strip()
        if not target_id:
            continue
        page_url = _sanitize_text(str(item.get("url") or ""))
        pages.append(
            {
                "tab_id": _tab_id(target_id),
                "target_id": target_id,
                "url": page_url,
                "title": _sanitize_text(str(item.get("title") or "")),
                "document_generation": _generation(target_id, page_url),
            }
        )
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
        pages = list_cdp_pages(cdp_url)
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
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(normalize_lane(lane))
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url)
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
            after = list_cdp_pages(cdp_url)
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
    target, err = validate_panel_url(url)
    if err:
        return {"ok": False, "error": err}
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(normalize_lane(lane))
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url)
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
        after = list_cdp_pages(cdp_url)
        live = _tab_from_pages(after, target_id)
        if live is None:
            return {"ok": False, "error": "unknown_tab"}
        return {
            "ok": True,
            "tab_id": live["tab_id"],
            "url": live["url"],
            "title": live["title"],
            "document_generation": live["document_generation"],
        }
    except Exception:
        return {"ok": False, "error": "navigate_failed"}
    finally:
        release_browser_context(context, pw, attached=True)
