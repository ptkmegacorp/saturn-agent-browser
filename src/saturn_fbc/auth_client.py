"""Loopback client for Saturn Auth approval requests."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_AUTH_URL = "http://127.0.0.1:8792"
CONSUMER = "saturn-fbc"


@dataclass(frozen=True)
class AuthRequestView:
    request_id: str
    state: str
    origin: str
    account_label: str | None
    purpose: str
    task_id: str | None
    expires_at: str
    reason: str | None = None


@dataclass(frozen=True)
class ConsumeResult:
    handle: str | None
    error: str | None = None


def base_url() -> str:
    return os.environ.get("SATURN_AUTH_URL", DEFAULT_AUTH_URL).rstrip("/")


def _token() -> str:
    raw = os.environ.get("SATURN_AUTH_FBC_TOKEN")
    if raw:
        return raw.strip()
    path = os.environ.get("SATURN_AUTH_FBC_TOKEN_FILE") or str(
        Path.home() / ".local" / "state" / "saturn-auth" / "callers" / "fbc"
    )
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url()}{path}"
    data = None
    headers = {"Content-Type": "application/json", "X-Saturn-Consumer": CONSUMER}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": body or err.reason}
        parsed["http_status"] = err.code
        return parsed


def create_login_request(
    *,
    credential_handle: str,
    allowed_origin: str,
    run_id: str,
    browser_session_id: str,
    tab_id: str | None,
    document_generation: str | None,
    task_id: str | None,
    idempotency_key: str,
    expiry_sec: int = 300,
    profile_id: str = "saturn-fbc",
) -> AuthRequestView | None:
    payload = {
        "consumer": CONSUMER,
        "purpose": "login",
        "credential_handle": credential_handle,
        "allowed_origin": allowed_origin,
        "run_id": run_id,
        "profile_id": profile_id,
        "browser_session_id": browser_session_id,
        "tab_id": tab_id,
        "document_generation": document_generation,
        "task_id": task_id,
        "expiry_sec": expiry_sec,
        "idempotency_key": idempotency_key,
    }
    result = _request("POST", "/v1/requests", payload)
    if not result.get("ok"):
        sys.stderr.write(
            "saturn-auth create failed: "
            f"{result.get('error') or result.get('http_status')} "
            f"{result.get('message') or ''}\n"
        )
        return None
    return _view(result["request"])


def get_request(request_id: str) -> AuthRequestView | None:
    result = _request("GET", f"/v1/requests/{request_id}")
    if not result.get("ok"):
        return None
    return _view(result["request"])


def consume_approval(
    request_id: str,
    *,
    run_id: str,
    profile_id: str,
    browser_session_id: str,
    tab_id: str | None,
    document_generation: str | None,
    current_origin: str,
) -> str | None:
    return consume_result(
        request_id,
        run_id=run_id,
        profile_id=profile_id,
        browser_session_id=browser_session_id,
        tab_id=tab_id,
        document_generation=document_generation,
        current_origin=current_origin,
    ).handle


def consume_result(
    request_id: str,
    *,
    run_id: str,
    profile_id: str,
    browser_session_id: str,
    tab_id: str | None,
    document_generation: str | None,
    current_origin: str,
) -> ConsumeResult:
    payload = {
        "consumer": CONSUMER,
        "run_id": run_id,
        "profile_id": profile_id,
        "browser_session_id": browser_session_id,
        "tab_id": tab_id,
        "document_generation": document_generation,
        "current_origin": current_origin,
    }
    result = _request("POST", f"/v1/requests/{request_id}/consume", payload)
    if not result.get("ok"):
        return ConsumeResult(handle=None, error=str(result.get("error") or "consume_failed"))
    handle = result.get("credential_handle")
    return ConsumeResult(handle=str(handle) if handle else None, error=None)


def wait_request_state(
    request_id: str,
    *,
    until: tuple[str, ...] = ("approved", "denied", "cancelled", "expired", "failed", "claimed", "filled", "verified"),
    wait_sec: int = 300,
) -> AuthRequestView | None:
    """Long-poll until this request leaves awaiting_user (no sleep loop)."""
    peek = get_request(request_id)
    if peek is None:
        return None
    if peek.state in until or peek.state != "awaiting_user":
        return peek
    since = None
    result = _request("GET", f"/v1/requests/{request_id}")
    if result.get("ok"):
        since = result.get("generation")
    while True:
        qs = f"?wait=1&wait_sec={max(1, min(wait_sec, 300))}"
        if since is not None:
            qs += f"&since={since}"
        result = _request("GET", f"/v1/requests/{request_id}{qs}")
        if not result.get("ok"):
            return get_request(request_id)
        since = result.get("generation")
        view = _view(result["request"])
        if view.state in until or view.state != "awaiting_user":
            return view



def report_outcome(request_id: str, outcome: str, reason: str | None = None) -> bool:
    payload = {"consumer": CONSUMER, "outcome": outcome}
    if reason:
        payload["reason"] = reason
    result = _request("POST", f"/v1/requests/{request_id}/report", payload)
    return bool(result.get("ok"))


def _view(raw: dict[str, Any]) -> AuthRequestView:
    return AuthRequestView(
        request_id=str(raw["request_id"]),
        state=str(raw["state"]),
        origin=str(raw.get("origin") or ""),
        account_label=raw.get("account_label"),
        purpose=str(raw.get("purpose") or "login"),
        task_id=raw.get("task_id"),
        expires_at=str(raw.get("expires_at") or ""),
        reason=raw.get("reason"),
    )
