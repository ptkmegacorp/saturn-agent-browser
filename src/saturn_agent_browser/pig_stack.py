"""GPU tenant wiring removed (2026-09-12 hard cut).

Reserved for a future local visual specialist; see models/potential-models/ui-venus-2-official-pipeline.md.

This module keeps its import surface (TenantState, acquire/release, health/status
helpers) so run/CLI/tests keep working, but it never touches pig-stack or
llama-server: no subprocess calls, no HTTP, no profile switching, no overlay
handling. ``acquire_tenant`` is a no-op and ``health_json`` always reports the
tenant as removed.
"""

from __future__ import annotations

from dataclasses import dataclass

MODEL_ID = "ui-venus-2-9b-q4km-local"
LLAMA_HOST = "127.0.0.1"
LLAMA_PORT = "8091"


@dataclass
class TenantState:
    previous_profile: str | None
    overlay_was_visible: bool


def openai_base_url() -> str:
    return f"http://{LLAMA_HOST}:{LLAMA_PORT}/v1"


def acquire_tenant(*, skip_switch: bool = False) -> TenantState:
    """No-op: GPU tenant switching was removed; run/CLI never touches pig-stack."""
    _ = skip_switch
    return TenantState(previous_profile=None, overlay_was_visible=False)


def release_tenant(state: TenantState, *, skip_switch: bool = False) -> None:
    """No-op: there is no tenant to release."""
    _ = (state, skip_switch)


def health_json() -> dict:
    return {
        "error": "gpu-tenant-removed",
        "profile": None,
        "model_id": MODEL_ID,
        "base_url": openai_base_url(),
    }


def status_payload() -> dict:
    payload = health_json()
    payload["tenant_profile"] = None
    return payload
