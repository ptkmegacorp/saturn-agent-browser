"""Broker fill helpers — secrets stay inside this module."""

from __future__ import annotations

from playwright.sync_api import Page

from saturn_fbc.broker.vault import CredentialRecord, create_entry, load_entry, vault_ready


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
    user_selectors = [
        "input[type=email]",
        "input[name*=user i]",
        "input[name*=login i]",
        "input[name*=email i]",
        "input[autocomplete=username]",
        "input[type=text]",
    ]
    password_selectors = [
        "input[type=password]",
        "input[autocomplete=current-password]",
        "input[autocomplete=new-password]",
    ]

    password_box = _first_visible(page, password_selectors)
    if password_box is None:
        raise RuntimeError("No password field found on page")

    user_box = _first_visible(page, user_selectors)
    if user_box is not None:
        user_box.fill(record.username)
    password_box.fill(record.password)


def _first_visible(page: Page, selectors: list[str]):
    for sel in selectors:
        locator = page.locator(sel)
        if locator.count() > 0:
            target = locator.first
            try:
                if target.is_visible():
                    return target
            except Exception:
                continue
    return None
