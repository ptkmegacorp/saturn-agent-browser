"""Credential policy: detect password fields and delegate to the broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from playwright.sync_api import Page

from saturn_fbc.contract import AuthorityContract, BrowserAction
from saturn_fbc.credential_selectors import PASSWORD_SELECTORS


class CredentialFillResult(str, Enum):
    SKIP = "skip"
    FILLED = "filled"
    MISSING_SPEC = "missing_spec"
    VAULT_NOT_READY = "vault_not_ready"
    NO_PASSWORD_FIELD = "no_password_field"
    AWAITING_APPROVAL = "awaiting_approval"
    AUTH_DENIED = "auth_denied"


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
    host = (parsed.hostname or "").lower().removeprefix("www.")
    scheme = parsed.scheme or "https"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{scheme}://{host}{port}"


def _binding_ids(contract: AuthorityContract, state: CredentialRunState) -> tuple[str, str | None, str | None]:
    run_id = contract.run_id or contract.task_id
    browser_session_id = state.browser_session_id or run_id
    tab_id = state.tab_id
    document_generation = state.document_generation
    return browser_session_id, tab_id, document_generation


def ensure_credential_filled(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> CredentialFillResult:
    if not policy_active(contract):
        return CredentialFillResult.SKIP

    if not password_fields_need_fill(page):
        return CredentialFillResult.SKIP

    from saturn_fbc.broker import create_credential, fill_credential, vault_ready

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


def _ensure_approval_and_fill(
    contract: AuthorityContract,
    page: Page,
    state: CredentialRunState,
) -> CredentialFillResult:
    from saturn_fbc import auth_client

    assert state.handle is not None
    run_id = contract.run_id or contract.task_id
    browser_session_id, tab_id, document_generation = _binding_ids(contract, state)
    idempotency_key = f"{run_id}:{state.handle}"

    if state.auth_request_id is None:
        created = auth_client.create_login_request(
            credential_handle=state.handle,
            allowed_origin=_page_origin(page),
            run_id=run_id,
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
    if current.state == "delivered":
        state.events.append(f"auth_request_already_delivered:{state.auth_request_id}")
        return CredentialFillResult.FILLED

    if current.state != "approved":
        return CredentialFillResult.AWAITING_APPROVAL

    consumed_handle = auth_client.consume_approval(
        state.auth_request_id,
        browser_session_id=browser_session_id,
        tab_id=tab_id,
        document_generation=document_generation,
        current_origin=page.url,
    )
    if not consumed_handle:
        return CredentialFillResult.AUTH_DENIED
    if consumed_handle != state.handle:
        return CredentialFillResult.AUTH_DENIED

    from saturn_fbc.broker import fill_credential

    fill_credential(consumed_handle, page=page)
    state.filled = True
    state.events.append(f"credential_filled_after_approval:{consumed_handle}")
    return CredentialFillResult.FILLED


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
