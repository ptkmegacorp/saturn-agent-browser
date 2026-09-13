"""Page observation capture: a11y snapshot and redacted screenshots."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from saturn_agent_browser import config

SENSITIVE_NAME_RE = re.compile(
    r"(password|passwd|secret|token|otp|totp|ssn|credit|cvv|pin)",
    re.IGNORECASE,
)


class ObservationSnapshot:
    """Numbered accessibility digest plus metadata."""

    def __init__(
        self,
        *,
        url: str,
        title: str,
        mode: str,
        nodes: list[dict[str, Any]],
        digest: str,
    ) -> None:
        self.url = url
        self.title = title
        self.mode = mode
        self.nodes = nodes
        self.digest = digest

    def node_by_index(self, index: int) -> dict[str, Any] | None:
        for node in self.nodes:
            if node.get("index") == index:
                return node
        return None


def _node_label(node: dict[str, Any]) -> str:
    role = node.get("role") or "generic"
    name = node.get("name") or node.get("value") or ""
    return f"{role} \"{name}\"" if name else role


def _flatten_a11y_tree(
    node: dict[str, Any] | None,
    *,
    nodes: list[dict[str, Any]],
    parent_index: int | None = None,
) -> None:
    if not node:
        return

    role = (node.get("role") or "").lower()
    interesting = role in {
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "searchbox",
        "textarea",
        "heading",
        "listitem",
        "menuitem",
        "tab",
        "option",
    } or bool(node.get("name"))

    current_index: int | None = None
    if interesting:
        current_index = len(nodes) + 1
        entry: dict[str, Any] = {
            "index": current_index,
            "role": role or "generic",
            "name": node.get("name") or "",
            "value": node.get("value") or "",
            "parent_index": parent_index,
        }
        if node.get("description"):
            entry["description"] = node["description"]
        if node.get("checked") is not None:
            entry["checked"] = node["checked"]
        nodes.append(entry)

    for child in node.get("children") or []:
        _flatten_a11y_tree(child, nodes=nodes, parent_index=current_index or parent_index)


def _dom_fallback_snapshot(page: Page) -> list[dict[str, Any]]:
    """Build indexed interactive nodes from DOM when a11y snapshot is unavailable."""
    script = """
    () => {
      const sel = 'a, button, input, textarea, select, [role="button"], [role="link"]';
      return Array.from(document.querySelectorAll(sel)).map((el, i) => ({
        index: i + 1,
        role: el.tagName.toLowerCase(),
        name: el.getAttribute('aria-label') || el.getAttribute('name') || el.id || el.placeholder || el.innerText || '',
        value: el.value || '',
        href: el.href || '',
        selector: el.id ? '#' + CSS.escape(el.id) : sel + ':nth-of-type(' + (Array.from(document.querySelectorAll(el.tagName)).indexOf(el) + 1) + ')',
      }));
    }
    """
    raw = page.evaluate(script)
    return list(raw)


def capture_links(page: Page, max_links: int = 200) -> list[dict[str, str]]:
    """DOM anchor list (text + absolute href) so agents can navigate from a digest.

    The a11y tree carries names but no hrefs; this side-channel gives the URLs.
    Never raises — returns [] when the page is gone or JS is blocked.
    """
    max_links = max(1, min(int(max_links or 200), 1000))
    script = r"""
    () => {
      return Array.from(document.querySelectorAll('a[href]')).map((a) => ({
        text: ((a.innerText || '').replace(/\s+/g, ' ').trim() || (a.getAttribute('aria-label') || '').trim()).slice(0, 120),
        href: a.href || '',
      })).filter((l) => l.href);
    }
    """
    try:
        raw = page.evaluate(script)
    except Exception:
        return []
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        if not href or len(href) > 2000:
            continue
        text = str(item.get("text") or "")[:120]
        key = f"{text}\x00{href}"
        if key in seen:
            continue
        seen.add(key)
        links.append({"text": text, "href": href})
        if len(links) >= max_links:
            break
    return links


def collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def capture_page_text(page: Page, max_chars: int = 6000) -> str:
    """Bounded visible text (body.innerText, whitespace-collapsed).

    Covers static article copy the interactive-node digest misses.
    Never raises — returns "" when the page is gone or JS is blocked.
    """
    max_chars = max(0, min(int(max_chars or 0), 100000))
    if max_chars == 0:
        return ""
    try:
        raw = page.evaluate("() => (document.body ? document.body.innerText : '') || ''")
    except Exception:
        return ""
    return collapse_text(str(raw))[:max_chars]


def capture_a11y_indexed(page: Page) -> ObservationSnapshot:
    """Capture numbered a11y snapshot with DOM fallback."""
    mode = config.observation_mode()
    url = page.url
    title = page.title()

    nodes: list[dict[str, Any]] = []
    try:
        tree = page.accessibility.snapshot(interesting_only=True)
        _flatten_a11y_tree(tree, nodes=nodes)
    except Exception:
        nodes = []

    if not nodes:
        nodes = _dom_fallback_snapshot(page)

    lines = [f"[{n['index']}] {_node_label(n)}" for n in nodes]
    digest = "\n".join(lines) if lines else "(empty page)"
    return ObservationSnapshot(url=url, title=title, mode=mode, nodes=nodes, digest=digest)


def _should_redact(node: dict[str, Any]) -> bool:
    name = f"{node.get('name', '')} {node.get('role', '')}"
    return bool(SENSITIVE_NAME_RE.search(name))


def capture_screenshot(page: Page, trace_dir: Path, *, step: int) -> Path:
    """Write screenshot to trace dir. Password-like fields get a redaction placeholder overlay."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"step-{step:04d}.png"
    page.screenshot(path=str(path), full_page=False)

    # Placeholder: record redaction intent in a sidecar marker (pixel edit deferred).
    snapshot = capture_a11y_indexed(page)
    redacted = [n["index"] for n in snapshot.nodes if _should_redact(n)]
    if redacted:
        marker = trace_dir / f"step-{step:04d}.redacted.txt"
        marker.write_text(
            f"redaction_placeholder: sensitive field indices {redacted}\n",
            encoding="utf-8",
        )
    return path


def digest_hash(digest: str) -> str:
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]
