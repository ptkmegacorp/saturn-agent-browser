"""Execute validated BrowserAction instances via Playwright."""

from __future__ import annotations

from playwright.sync_api import Page

from saturn_agent_browser.actions import ActionRejectedError
from saturn_agent_browser.browser.capture import ObservationSnapshot, capture_a11y_indexed
from saturn_agent_browser.contract import BrowserAction


def _resolve_locator(page: Page, snapshot: ObservationSnapshot, action: BrowserAction):
    if action.index is not None:
        node = snapshot.node_by_index(action.index)
        if node is None:
            raise ActionRejectedError(f"No a11y node at index {action.index}")
        field_name = node.get("name") or ""
        if field_name and field_name.lower() not in {"submit order", "submit"}:
            named = page.locator(f"[name='{field_name}']")
            if named.count() > 0:
                return named
        if selector := node.get("selector"):
            return page.locator(selector)
        role = node.get("role") or "generic"
        name = node.get("name") or ""
        if name:
            return page.get_by_role(role, name=name, exact=False)
        return page.get_by_role(role).nth(max(action.index - 1, 0))

    if action.selector:
        return page.locator(action.selector)

    raise ActionRejectedError(f"Action '{action.type}' requires index or selector")


def execute_action(page: Page, action: BrowserAction, *, snapshot: ObservationSnapshot | None = None) -> str:
    """Run one browser action; return a short result summary."""
    snap = snapshot or capture_a11y_indexed(page)
    action_type = action.type

    if action_type == "navigate":
        if not action.url:
            raise ActionRejectedError("navigate requires url")
        page.goto(action.url, wait_until="domcontentloaded")
        return f"navigated to {page.url}"

    if action_type == "scroll":
        amount = action.amount or 400
        delta = amount if action.direction != "up" else -amount
        page.mouse.wheel(0, delta)
        return f"scrolled {action.direction or 'down'} {amount}px"

    if action_type == "click":
        if action.x is not None and action.y is not None:
            page.mouse.click(action.x, action.y)
            return f"clicked at ({action.x},{action.y})"
        locator = _resolve_locator(page, snap, action)
        locator.first.click(timeout=5000)
        return f"clicked index={action.index}"

    if action_type == "type":
        text = action.text if action.text is not None else action.value
        if text is None:
            raise ActionRejectedError("type requires text or value")
        locator = _resolve_locator(page, snap, action)
        locator.first.fill(text)
        return f"typed into index={action.index}"

    if action_type == "select":
        value = action.value or action.text
        if value is None:
            raise ActionRejectedError("select requires value or text")
        locator = _resolve_locator(page, snap, action)
        locator.first.select_option(value)
        return f"selected {value!r} at index={action.index}"

    raise ActionRejectedError(f"Unsupported action type: {action_type}")
