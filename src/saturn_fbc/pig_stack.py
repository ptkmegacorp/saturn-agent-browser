"""GPU tenant lifecycle: overlay hide, profile switch (sticky — no restore on exit)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from saturn_fbc import config


PROFILE = config.get("PIG_STACK_PROFILE", "saturn-frontier-browser-control") or "saturn-frontier-browser-control"
LLAMA_HOST = config.get("LLAMA_HOST", "127.0.0.1") or "127.0.0.1"
LLAMA_PORT = config.get("LLAMA_PORT", "8091") or "8091"
MODEL_ID = config.get("PIG_MODEL_ID", "spark-x2.5-4b-q4_k_m-local") or "spark-x2.5-4b-q4_k_m-local"


@dataclass
class TenantState:
    previous_profile: str | None
    overlay_was_visible: bool


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def current_profile() -> str | None:
    try:
        result = _run(["pig-stack", "current"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in result.stdout.splitlines():
        if "profile" in line.lower():
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    current_env = Path.home() / ".config" / "pig-stack" / "current.env"
    if current_env.is_file():
        for raw in current_env.read_text(encoding="utf-8").splitlines():
            if raw.startswith("PIG_STACK_PROFILE="):
                return raw.split("=", 1)[1].strip().strip('"')
    return None


def overlay_visible() -> bool:
    try:
        result = _run(["pig-stack", "overlay", "status"], check=False)
    except FileNotFoundError:
        return False
    return "running" in result.stdout.lower() or "visible" in result.stdout.lower()


def openai_base_url() -> str:
    return f"http://{LLAMA_HOST}:{LLAMA_PORT}/v1"


def acquire_tenant(*, skip_switch: bool = False) -> TenantState:
    """Hide overlay and switch to saturn-frontier-browser-control profile."""
    prev = current_profile()
    overlay = overlay_visible()
    if skip_switch:
        return TenantState(previous_profile=prev, overlay_was_visible=overlay)

    _run(["pig-stack", "overlay", "hide"], check=False)
    if prev != PROFILE:
        _run(["pig-stack", "switch", PROFILE])
    return TenantState(previous_profile=prev, overlay_was_visible=overlay)


def release_tenant(state: TenantState, *, skip_switch: bool = False) -> None:
    """No-op: leave pig-stack on saturn-frontier-browser-control after a run."""
    _ = (state, skip_switch)


def health_json() -> dict:
    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            health = client.get(f"http://{LLAMA_HOST}:{LLAMA_PORT}/health")
            models = client.get(openai_base_url() + "/models")
        return {
            "profile": current_profile(),
            "llama_health": health.json() if health.status_code == 200 else health.text,
            "models": models.json() if models.status_code == 200 else models.text,
            "model_id": MODEL_ID,
            "base_url": openai_base_url(),
        }
    except Exception as exc:
        return {"error": str(exc), "profile": current_profile(), "base_url": openai_base_url()}


def status_payload() -> dict:
    payload = health_json()
    payload["tenant_profile"] = PROFILE
    return payload
