"""Privileged credential broker (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass

from saturn_agent_browser import config
from saturn_agent_browser.broker import service, vault

AGENT_KDBX = vault.agent_kdbx_path()


@dataclass
class CredentialHandle:
    handle: str
    domain: str
    username: str
    status: str


def vault_ready() -> bool:
    return vault.vault_ready()


def generate_password(length: int = 24) -> str:
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_credential(domain: str, username: str, label: str) -> CredentialHandle:
    result = service.create_credential(domain, username, label)
    return CredentialHandle(
        handle=result["handle"],
        domain=result["domain"],
        username=result["username"],
        status=result["status"],
    )


def fill_credential(handle: str, *, page=None) -> str:
    if page is None:
        if not vault_ready():
            raise RuntimeError(f"Agent vault not ready: {AGENT_KDBX}")
        return "ok:broker_ready_no_page"
    return service.fill_credential(handle, page)


def broker_status() -> dict:
    fill_mode = config.get("CREDENTIAL_FILL", "broker") or "broker"
    status = vault.setup_status()
    status["fill_mode"] = fill_mode
    return status
