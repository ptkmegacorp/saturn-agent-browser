"""Broker fill helpers — secrets stay inside this module."""

from __future__ import annotations

from playwright.sync_api import Page

from saturn_fbc.broker.vault import CredentialRecord, create_entry, load_entry, vault_ready
from saturn_fbc.credential_selectors import PASSWORD_SELECTORS, USER_SELECTORS


def create_credential(domain: str, username: str, label: str) -> dict:
    record = create_entry(domain, username, label)
    return {
        "handle": record.handle,
        "domain": domain,
        "username": username,
        "status": "created",
    }


def fill_credential(handle: str, page: Page) -> str:
    if not vault_ready():
        raise RuntimeError("Agent vault not ready")
    record = load_entry(handle)
    _fill_login_form(page, record)
    return "ok"


def _fill_login_form(page: Page, record: CredentialRecord) -> None:
    password_boxes = _all_visible(page, PASSWORD_SELECTORS)
    if not password_boxes:
        raise RuntimeError("No password field found on page")

    user_box = _first_visible(page, USER_SELECTORS)
    if user_box is not None:
        try:
            current = (user_box.input_value(timeout=500) or "").strip()
        except Exception:
            current = ""
        if not current:
            user_box.fill(record.username)

    for password_box in password_boxes:
        try:
            current = (password_box.input_value(timeout=500) or "").strip()
        except Exception:
            current = ""
        if not current:
            password_box.fill(record.password)


def _first_visible(page: Page, selectors: list[str]):
    for box in _all_visible(page, selectors):
        return box
    return None


def _all_visible(page: Page, selectors: list[str]):
    found = []
    seen: set[int] = set()
    for sel in selectors:
        locator = page.locator(sel)
        for target in locator.all():
            try:
                if not target.is_visible():
                    continue
                key = id(target)
                if key in seen:
                    continue
                seen.add(key)
                found.append(target)
            except Exception:
                continue
    return found
