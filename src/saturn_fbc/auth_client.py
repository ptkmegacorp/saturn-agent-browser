"""Loopback client for Saturn Auth approval requests."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
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


def base_url() -> str:
    return os.environ.get("SATURN_AUTH_URL", DEFAULT_AUTH_URL).rstrip("/")


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url()}{path}"
    data = None
    headers = {"Content-Type": "application/json", "X-Saturn-Consumer": CONSUMER}
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
) -> AuthRequestView | None:
    payload = {
        "consumer": CONSUMER,
        "purpose": "login",
        "credential_handle": credential_handle,
        "allowed_origin": allowed_origin,
        "run_id": run_id,
        "browser_session_id": browser_session_id,
        "tab_id": tab_id,
        "document_generation": document_generation,
        "task_id": task_id,
        "expiry_sec": expiry_sec,
        "idempotency_key": idempotency_key,
    }
    result = _request("POST", "/v1/requests", payload)
    if not result.get("ok"):
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
    browser_session_id: str,
    tab_id: str | None,
    document_generation: str | None,
    current_origin: str,
) -> str | None:
    payload = {
        "consumer": CONSUMER,
        "browser_session_id": browser_session_id,
        "tab_id": tab_id,
        "document_generation": document_generation,
        "current_origin": current_origin,
    }
    result = _request("POST", f"/v1/requests/{request_id}/consume", payload)
    if not result.get("ok"):
        return None
    handle = result.get("credential_handle")
    return str(handle) if handle else None


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
