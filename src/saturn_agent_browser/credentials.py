"""Credential policy: detect password fields and delegate to the broker."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from playwright.sync_api import Page

from saturn_agent_browser.browser.live_bindings import read_live_bindings
from saturn_agent_browser.contract import AuthorityContract, BrowserAction
from saturn_agent_browser.credential_selectors import PASSWORD_SELECTORS


class CredentialFillResult(str, Enum):
    SKIP = "skip"
    FILLED = "filled"
    MISSING_SPEC = "missing_spec"
    VAULT_NOT_READY = "vault_not_ready"
    NO_PASSWORD_FIELD = "no_password_field"
    AWAITING_APPROVAL = "awaiting_approval"
    AUTH_DENIED = "auth_denied"
    AUTH_UNAVAILABLE = "auth_unavailable"


@dataclass
class CredentialRunState:
    handle: str | None = None
    created: bool = False
    filled: bool = False
    auth_request_id: str | None = None
    browser_session_id: str | None = None
    tab_id: str | None = None
    document_generation: str | None = None
    events: list[str] = field(default_factory=list)


def policy_active(contract: AuthorityContract) -> bool:
    return (contract.credential_policy or "none").strip().lower() != "none"


def visible_password_fields(page: Page) -> list:
    fields: list = []
    seen: set[int] = set()
    for sel in PASSWORD_SELECTORS:
        for locator in page.locator(sel).all():
            try:
                if not locator.is_visible():
                    continue
                handle = id(locator)
                if handle in seen:
                    continue
                seen.add(handle)
                value = locator.input_value(timeout=500)
                fields.append((locator, (value or "").strip()))
            except Exception:
                continue
    return fields


def password_fields_need_fill(page: Page) -> bool:
    fields = visible_password_fields(page)
    if not fields:
        return False
    return any(not value for _locator, value in fields)


def resolve_domain(contract: AuthorityContract, page: Page) -> str | None:
    if contract.credential_spec and contract.credential_spec.domain:
        return contract.credential_spec.domain.strip().lower()
    parsed = urlparse(page.url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or None


def resolve_username(contract: AuthorityContract) -> str | None:
    if contract.credential_spec and contract.credential_spec.username:
        return contract.credential_spec.username.strip()
    for key in ("email", "username", "login"):
        raw = contract.task_data.get(key)
        if raw:
            return str(raw).strip()
    return None


def resolve_label(contract: AuthorityContract) -> str:
    if contract.credential_spec and contract.credential_spec.label:
        return contract.credential_spec.label.strip()
    return contract.task_id


def initial_handle(contract: AuthorityContract) -> str | None:
    if contract.credential_spec and contract.credential_spec.handle:
        return contract.credential_spec.handle.strip()
    return None


def requires_user_approval(contract: AuthorityContract) -> bool:
    policy = (contract.credential_policy or "none").strip().lower()
    if policy in {"existing_only", "approval_required"}:
        return True
    if policy == "request_only" and initial_handle(contract):
        return True
    return False


def auto_create_allowed(contract: AuthorityContract) -> bool:
    policy = (contract.credential_policy or "none").strip().lower()
    if policy in {"existing_only", "approval_required"}:
        return False
    return True


def _page_origin(page: Page) -> str:
    parsed = urlparse(page.url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return page.url
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


PROFILE_ID = "saturn-agent-browser"


def _binding_ids(contract: AuthorityContract, state: CredentialRunState, page: Page) -> tuple[str, str, str, str, str]:
    run_id = contract.run_id or contract.task_id
    browser_session_id, tab_id, document_generation = read_live_bindings(page)
    state.browser_session_id = browser_session_id
    state.tab_id = tab_id
    state.document_generation = document_generation
    return run_id, PROFILE_ID, browser_session_id, tab_id, document_generation


def ensure_credential_filled(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> CredentialFillResult:
    if not policy_active(contract):
        return CredentialFillResult.SKIP

    if not password_fields_need_fill(page):
        return CredentialFillResult.SKIP

    from saturn_agent_browser.broker import create_credential, fill_credential, vault_ready

    if not vault_ready():
        return CredentialFillResult.VAULT_NOT_READY

    if state.handle is None:
        state.handle = initial_handle(contract)

    if state.handle is None:
        if not auto_create_allowed(contract):
            return CredentialFillResult.MISSING_SPEC
        domain = resolve_domain(contract, page)
        username = resolve_username(contract)
        label = resolve_label(contract)
        if not domain or not username:
            return CredentialFillResult.MISSING_SPEC
        created = create_credential(domain, username, label)
        state.handle = created.handle
        state.created = True
        state.events.append(f"credential_created:{created.handle}")

    if requires_user_approval(contract):
        approval_result = _ensure_approval_and_fill(contract, page, state)
        return approval_result

    fill_credential(state.handle, page=page)
    state.filled = True
    state.events.append(f"credential_filled:{state.handle}")
    return CredentialFillResult.FILLED


def pi_click_enabled() -> bool:
    return os.environ.get("SATURN_AGENT_BROWSER_PI_CLICK", "").strip() == "1"


def fill_with_operator_gate(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> CredentialFillResult:
    """Fixture/test helper: fill, then Saturn Pi Approve for this request id only.

    Production visual/skeleton loops do not call this. Requires SATURN_AGENT_BROWSER_PI_CLICK=1
    and an exact auth_request_id (never the first pending card).
    """
    result = ensure_credential_filled(contract, page, state)
    if result != CredentialFillResult.AWAITING_APPROVAL or not pi_click_enabled():
        return result
    if not state.auth_request_id:
        return result
    from saturn_agent_browser.auth_client import wait_request_state
    from saturn_agent_browser.pi_operator_click import click_browser_auth_approve_cli

    try:
        click_browser_auth_approve_cli(state.auth_request_id)
    except Exception as err:
        state.events.append(f"pi_click_failed:{err.__class__.__name__}")
        return CredentialFillResult.AUTH_UNAVAILABLE
    waited = wait_request_state(state.auth_request_id)
    if waited is None:
        return CredentialFillResult.AUTH_UNAVAILABLE
    if waited.state in ("denied", "cancelled", "expired", "failed"):
        return CredentialFillResult.AUTH_DENIED
    return ensure_credential_filled(contract, page, state)


def _ensure_approval_and_fill(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> CredentialFillResult:
    from saturn_agent_browser import auth_client

    assert state.handle is not None
    run_id = contract.run_id or contract.task_id
    run_id, profile_id, browser_session_id, tab_id, document_generation = _binding_ids(contract, state, page)
    idempotency_key = f"{run_id}:{state.handle}"

    if state.auth_request_id is None:
        created = auth_client.create_login_request(
            credential_handle=state.handle,
            allowed_origin=_page_origin(page),
            run_id=run_id,
            profile_id=profile_id,
            browser_session_id=browser_session_id,
            tab_id=tab_id,
            document_generation=document_generation,
            task_id=contract.task_id,
            idempotency_key=idempotency_key,
        )
        if created is None:
            return CredentialFillResult.VAULT_NOT_READY
        state.auth_request_id = created.request_id
        state.events.append(f"auth_request_created:{created.request_id}")

    current = auth_client.get_request(state.auth_request_id)
    if current is None:
        return CredentialFillResult.VAULT_NOT_READY

    if current.state == "awaiting_user":
        return CredentialFillResult.AWAITING_APPROVAL
    if current.state in {"denied", "cancelled", "expired", "failed"}:
        state.events.append(f"auth_request_{current.state}:{state.auth_request_id}")
        return CredentialFillResult.AUTH_DENIED
    if current.state == "claimed":
        auth_client.report_outcome(state.auth_request_id, "failed", "uncertain_delivery")
        state.events.append(f"auth_request_uncertain_delivery:{state.auth_request_id}")
        return CredentialFillResult.AUTH_DENIED
    if current.state in {"filled", "verified"}:
        state.events.append(f"auth_request_{current.state}:{state.auth_request_id}")
        return CredentialFillResult.FILLED
    if current.state == "delivered":
        state.events.append(f"auth_request_already_delivered:{state.auth_request_id}")
        return CredentialFillResult.AUTH_DENIED

    if current.state != "approved":
        return CredentialFillResult.AWAITING_APPROVAL

    consumed = auth_client.consume_result(
        state.auth_request_id,
        run_id=run_id,
        profile_id=profile_id,
        browser_session_id=browser_session_id,
        tab_id=tab_id,
        document_generation=document_generation,
        current_origin=_page_origin(page),
    )
    if consumed.error == "persist_failed":
        state.events.append(f"auth_persist_failed:{state.auth_request_id}")
        return CredentialFillResult.AUTH_UNAVAILABLE
    consumed_handle = consumed.handle
    if not consumed_handle:
        return CredentialFillResult.AUTH_DENIED
    if consumed_handle != state.handle:
        auth_client.report_outcome(state.auth_request_id, "failed", "handle_mismatch")
        return CredentialFillResult.AUTH_DENIED

    from saturn_agent_browser.broker import fill_credential

    try:
        fill_credential(consumed_handle, page=page)
    except Exception as err:
        auth_client.report_outcome(state.auth_request_id, "failed", "fill_exception")
        state.events.append(f"credential_fill_failed:{err.__class__.__name__}")
        return CredentialFillResult.AUTH_DENIED
    if not auth_client.report_outcome(state.auth_request_id, "filled"):
        return CredentialFillResult.AUTH_DENIED
    state.filled = True
    state.events.append(f"credential_filled_after_approval:{consumed_handle}")
    return CredentialFillResult.FILLED


def page_matches_success(page: Page, contract: AuthorityContract) -> bool:
    """Independent logged-in check from contract.success_checks (not the fill path)."""
    for selector in contract.success_checks:
        if not selector:
            continue
        try:
            loc = page.locator(selector)
            if loc.count() == 0:
                continue
            if loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def report_login_verification(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> bool:
    """Report verified or failed after an independent success-check. Does not fill."""
    from saturn_agent_browser import auth_client

    if not state.auth_request_id:
        return False
    if page_matches_success(page, contract):
        if not auth_client.report_outcome(state.auth_request_id, "verified"):
            return False
        state.events.append(f"auth_request_verified:{state.auth_request_id}")
        return True
    auth_client.report_outcome(state.auth_request_id, "failed", "login_not_verified")
    state.events.append("auth_request_verify_failed")
    return False


def is_password_type_action(page: Page, action: BrowserAction, snapshot) -> bool:
    if action.type != "type" or action.index is None:
        return False
    node = snapshot.node_by_index(action.index)
    if node is None:
        return False
    blob = f"{node.get('role', '')} {node.get('name', '')}".lower()
    if any(token in blob for token in ("password", "passphrase", "new-password")):
        return True
    field_name = str(node.get("name") or "")
    if field_name:
        try:
            named = page.locator(f"[name='{field_name}']")
            if named.count() > 0:
                input_type = (named.first.get_attribute("type") or "").lower()
                autocomplete = (named.first.get_attribute("autocomplete") or "").lower()
                if input_type == "password" or "password" in autocomplete:
                    return True
        except Exception:
            pass
    return False
