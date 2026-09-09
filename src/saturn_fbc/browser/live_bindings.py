"""Live browser session / tab / document generations for Auth bindings."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse


def attach_live_bindings(page) -> None:
    """Track browser-session, tab, and document generation on a Playwright page."""
    context = getattr(page, "context", None)
    if context is None:
        return
    if not getattr(context, "_saturn_browser_session_id", None):
        context._saturn_browser_session_id = f"browser-{uuid.uuid4().hex[:16]}"
    page._saturn_browser_session_id = context._saturn_browser_session_id
    if not getattr(page, "_saturn_tab_id", None):
        page._saturn_tab_id = f"tab-{uuid.uuid4().hex[:16]}"
    if getattr(page, "_saturn_bindings_attached", False):
        return
    page._saturn_bindings_attached = True
    bump_document(page, reason="attach")

    def on_nav(frame) -> None:
        parent = getattr(frame, "parent_frame", None)
        if parent is not None:
            return
        bump_document(page, reason="navigate")

    def on_crash(_page) -> None:
        bump_document(page, reason="crash")

    on = getattr(page, "on", None)
    if callable(on):
        on("framenavigated", on_nav)
        on("crash", on_crash)


def bump_document(page, *, reason: str) -> str:
    seq = int(getattr(page, "_saturn_document_seq", 0)) + 1
    page._saturn_document_seq = seq
    page._saturn_document_id = f"doc-{seq}-{reason}-{uuid.uuid4().hex[:10]}"
    return page._saturn_document_id


def read_live_bindings(page) -> tuple[str, str, str]:
    """Return (browser_session_id, tab_id, document_generation) for the live page."""
    context = getattr(page, "context", None)
    if context is not None:
        attach_live_bindings(page)
        return (
            str(page._saturn_browser_session_id),
            str(page._saturn_tab_id),
            str(page._saturn_document_id),
        )
    origin = _origin_from_url(getattr(page, "url", "") or "")
    session = getattr(page, "_saturn_browser_session_id", None) or "browser-test"
    tab = getattr(page, "_saturn_tab_id", None) or "tab-test"
    document = getattr(page, "_saturn_document_id", None) or f"doc:{origin or 'unknown'}"
    return str(session), str(tab), str(document)


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return url
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"
