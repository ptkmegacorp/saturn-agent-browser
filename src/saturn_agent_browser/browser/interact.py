"""Human-only protected interaction: coordinate tap + scroll.

This is the least-capable useful input path for Open verification. It is
deliberately separate from the agent runner (browser/executor.py):

- every call requires human control mode AND a live lease on (lane, tab);
- the caller-held document generation must match live (stale fails);
- coordinates are remote-page CSS pixels; bounds are an abuse guard, not a
  precision promise (panel scales snapshot taps; viewport sync is deferred);
- after input the generation always bumps (cached frames invalidate) and
  the final URL is re-read. Unlike navigate, a tap may legitimately land
  cross-origin (SSO app -> IdP): instead of blocking, the result reports
  origin_changed so the panel rebinds explicitly and secret delivery paths
  (which revalidate separately) stay closed until rebound.

Text/IME entry, key events and streaming follow after this path is proven.
"""

from __future__ import annotations

import math
import time
from typing import Any

from saturn_agent_browser.browser import generations
from saturn_agent_browser.browser import leases
from saturn_agent_browser.browser.control import read_control_mode
from saturn_agent_browser.browser.profile import connect_over_cdp, release_browser_context
from saturn_agent_browser.browser.view import (
    _find_page,
    _lane_runtime,
    _tab_from_pages,
    list_cdp_pages,
    normalize_lane,
)

_COORD_MAX = 10000.0


def _valid_coord(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or number > _COORD_MAX:
        return None
    return number


def _gates(lane: str, tab_id: str, generation: str) -> tuple[dict[str, Any] | None, str, str, str]:
    """Shared preconditions. Returns (error, lane, tab_id, generation)."""
    if read_control_mode() != "human":
        return {"ok": False, "error": "human_control_required"}, lane, tab_id, generation
    wanted = (tab_id or "").strip()
    expected = (generation or "").strip()
    lane = normalize_lane(lane)
    if not wanted.startswith("tab-") or len(wanted) <= 4:
        return {"ok": False, "error": "invalid_tab_id"}, lane, wanted, expected
    if not expected.startswith("doc-"):
        return {"ok": False, "error": "invalid_generation"}, lane, wanted, expected
    if not leases.list_active(lane=lane, tab_id=wanted):
        return {"ok": False, "error": "lease_required"}, lane, wanted, expected
    return None, lane, wanted, expected


def _live_tab(cdp_url: str, lane: str, target_id: str, expected: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (meta, error). Meta is the pre-action live tab entry."""
    try:
        pages = list_cdp_pages(cdp_url, lane)
    except Exception:
        return None, {"ok": False, "error": "cdp_unreachable"}
    meta = _tab_from_pages(pages, target_id)
    if meta is None:
        return None, {"ok": False, "error": "unknown_tab"}
    if meta["document_generation"] != expected:
        return None, {"ok": False, "error": "stale_document"}
    return meta, None


def _after_action(cdp_url: str, lane: str, target_id: str, before_url: str) -> dict[str, Any]:
    """Re-read, bump, and report with explicit origin-change flag."""
    try:
        after = list_cdp_pages(cdp_url, lane)
    except Exception:
        return {"ok": False, "error": "cdp_unreachable"}
    live = _tab_from_pages(after, target_id)
    if live is None:
        return {"ok": False, "error": "unknown_tab"}
    final_url = live["url"]
    new_generation = generations.bump(lane=lane, target_id=target_id, url=final_url, reason="input")
    return {
        "ok": True,
        "tab_id": live["tab_id"],
        "url": final_url,
        "title": live["title"],
        "document_generation": new_generation,
        "origin_changed": final_url != before_url,
    }


def tap(tab_id: str, x: Any, y: Any, expected_generation: str, lane: str | None = None) -> dict[str, Any]:
    err, lane, wanted, expected = _gates(lane or "isolated", tab_id, expected_generation)
    if err:
        return err
    coord_x = _valid_coord(x)
    coord_y = _valid_coord(y)
    if coord_x is None or coord_y is None:
        return {"ok": False, "error": "invalid_coordinates"}
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(lane)
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    meta, meta_err = _live_tab(cdp_url, lane, target_id, expected)
    if meta_err:
        return meta_err
    before_url = meta["url"]
    pw = None
    context = None
    try:
        pw, context, _attached = connect_over_cdp(cdp_url)
        match = _find_page(context, target_id)
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        match.mouse.click(coord_x, coord_y)
        time.sleep(0.5)
        return _after_action(cdp_url, lane, target_id, before_url)
    except Exception:
        return {"ok": False, "error": "input_failed"}
    finally:
        release_browser_context(context, pw, attached=True)


def scroll(
    tab_id: str,
    direction: str,
    expected_generation: str,
    amount: Any = 400,
    lane: str | None = None,
) -> dict[str, Any]:
    err, lane, wanted, expected = _gates(lane or "isolated", tab_id, expected_generation)
    if err:
        return err
    way = (direction or "down").strip().lower()
    if way not in {"up", "down"}:
        return {"ok": False, "error": "invalid_direction"}
    try:
        pixels = int(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_amount"}
    pixels = max(50, min(pixels, 4000))
    delta = -pixels if way == "up" else pixels
    target_id = wanted[len("tab-") :]
    runtime = _lane_runtime(lane)
    if not runtime.get("running"):
        return {"ok": False, "error": "browser_disconnected"}
    cdp_url = str(runtime.get("cdp_url") or "")
    meta, meta_err = _live_tab(cdp_url, lane, target_id, expected)
    if meta_err:
        return meta_err
    before_url = meta["url"]
    pw = None
    context = None
    try:
        pw, context, _attached = connect_over_cdp(cdp_url)
        match = _find_page(context, target_id)
        if match is None:
            return {"ok": False, "error": "unknown_tab"}
        match.mouse.wheel(0, delta)
        time.sleep(0.3)
        return _after_action(cdp_url, lane, target_id, before_url)
    except Exception:
        return {"ok": False, "error": "input_failed"}
    finally:
        release_browser_context(context, pw, attached=True)
