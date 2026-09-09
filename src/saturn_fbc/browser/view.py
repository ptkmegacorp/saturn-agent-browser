"""Read-only tab list and snapshot for the Saturn Pi browser panel."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from saturn_fbc.browser.daemon import browser_daemon_status
from saturn_fbc.browser.profile import connect_over_cdp, release_browser_context

CAPABILITIES_DISCONNECTED = {
    "snapshot": False,
    "streaming": False,
    "inspect": False,
    "navigate": False,
    "reason_snapshot": "browser_disconnected",
    "reason_streaming": "not_implemented",
    "reason_inspect": "not_implemented",
    "reason_navigate": "snapshot_only",
}

CAPABILITIES_CONNECTED = {
    "snapshot": True,
    "streaming": False,
    "inspect": False,
    "navigate": False,
    "reason_streaming": "not_implemented",
    "reason_inspect": "not_implemented",
    "reason_navigate": "snapshot_only",
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


def read_view() -> dict[str, Any]:
    status = browser_daemon_status()
    if not status.get("running"):
        return {
            "ok": True,
            "connected": False,
            "ownership": "unknown",
            "run_id": None,
            "tabs": [],
            "selected_tab_id": None,
            "capabilities": dict(CAPABILITIES_DISCONNECTED),
            "browser": {
                "running": False,
                "pid": None,
                "cdp_url": None,
            },
        }
    cdp_url = str(status.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url)
    except Exception:
        return {
            "ok": False,
            "connected": False,
            "error": "cdp_unreachable",
            "tabs": [],
            "selected_tab_id": None,
            "capabilities": dict(CAPABILITIES_DISCONNECTED),
            "browser": {
                "running": True,
                "pid": status.get("pid"),
                "cdp_url": None,
            },
        }
    selected = pages[0]["tab_id"] if pages else None
    for index, page in enumerate(pages):
        page["selected"] = index == 0
    return {
        "ok": True,
        "connected": True,
        "ownership": "unknown",
        "run_id": None,
        "tabs": [{k: v for k, v in page.items() if k != "target_id"} for page in pages],
        "selected_tab_id": selected,
        "capabilities": dict(CAPABILITIES_CONNECTED),
        "browser": {
            "running": True,
            "pid": status.get("pid"),
            "cdp_url": None,
        },
    }


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


def capture_snapshot(tab_id: str) -> dict[str, Any]:
    wanted = (tab_id or "").strip()
    if not wanted.startswith("tab-") or len(wanted) <= 4:
        return {"ok": False, "error": "invalid_tab_id"}
    target_id = wanted[len("tab-") :]
    status = browser_daemon_status()
    if not status.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(status.get("cdp_url") or "")
    try:
        pages = list_cdp_pages(cdp_url)
    except Exception:
        return {"ok": False, "error": "cdp_unreachable"}
    meta = next((item for item in pages if item["target_id"] == target_id), None)
    if meta is None:
        return {"ok": False, "error": "unknown_tab"}
    pw = None
    context = None
    attached = False
    try:
        pw, context, attached = connect_over_cdp(cdp_url)
        match = None
        for page in context.pages:
            try:
                if _page_target_id(page) == target_id:
                    match = page
                    break
            except Exception:
                continue
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        png = match.screenshot(type="png", full_page=False)
        return {
            "ok": True,
            "png": png,
            "tab_id": meta["tab_id"],
            "document_generation": meta["document_generation"],
            "url": meta["url"],
            "title": meta["title"],
        }
    except Exception:
        return {"ok": False, "error": "snapshot_failed"}
    finally:
        release_browser_context(context, pw, attached=True)
