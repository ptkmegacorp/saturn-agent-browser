"""Scoped, expiring human-control leases for browser targets.

The global human/agent flag in control.py stays as compatibility state.
Authoritative ownership for a sensitive target comes from a lease bound to
(user/operator, run, lane, tab, document generation) with an expiry.
Competing controllers, disconnects and timeouts release the lease while the
task itself stays safely paused.

Lease ids are opaque: ``lease_<16hex>``. Persisted beside browser state
(0600) so daemon/CLI/panel paths share one view.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from saturn_agent_browser.browser.state import state_file_path


def leases_file_path():
    return state_file_path().with_name("browser-leases.json")


def _now() -> datetime:
    return datetime.now(UTC)


def _blank() -> dict[str, Any]:
    return {"leases": {}}


def _load() -> dict[str, Any]:
    path = leases_file_path()
    if not path.is_file():
        return _blank()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blank()
    if not isinstance(data, dict) or not isinstance(data.get("leases"), dict):
        return _blank()
    return data


def _save(data: dict[str, Any]) -> None:
    path = leases_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _expired(lease: dict[str, Any]) -> bool:
    try:
        expiry = datetime.fromisoformat(str(lease.get("expires_at")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    return expiry <= _now()


def _prune(data: dict[str, Any]) -> list[str]:
    dead = [lid for lid, lease in data["leases"].items() if not isinstance(lease, dict) or _expired(lease)]
    for lid in dead:
        del data["leases"][lid]
    return dead


def acquire(
    *,
    lane: str,
    tab_id: str,
    operator: str,
    run_id: str | None = None,
    document_generation: str | None = None,
    ttl_sec: int = 300,
) -> dict[str, Any]:
    """Grant an exclusive lease; revokes other live leases on the same target."""
    lane = (lane or "isolated").strip() or "isolated"
    tab_id = (tab_id or "").strip()
    operator = (operator or "").strip() or "saturn-pi-operator"
    if not tab_id.startswith("tab-"):
        return {"ok": False, "error": "invalid_tab_id"}
    ttl = max(30, min(int(ttl_sec or 300), 3600))
    data = _load()
    _prune(data)
    revoked = [
        lid
        for lid, lease in data["leases"].items()
        if isinstance(lease, dict) and lease.get("lane") == lane and lease.get("tab_id") == tab_id
    ]
    for lid in revoked:
        del data["leases"][lid]
    lease_id = f"lease_{uuid.uuid4().hex[:16]}"
    now = _now()
    lease = {
        "lease_id": lease_id,
        "lane": lane,
        "tab_id": tab_id,
        "operator": operator,
        "run_id": run_id,
        "document_generation": document_generation,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z"),
        "ttl_sec": ttl,
    }
    data["leases"][lease_id] = lease
    _save(data)
    return {"ok": True, "lease": lease, "revoked": revoked}


def validate(
    *,
    lease_id: str,
    lane: str | None = None,
    tab_id: str | None = None,
    document_generation: str | None = None,
) -> dict[str, Any]:
    """Check a lease is live and still bound to the given target/document."""
    data = _load()
    lease = data["leases"].get((lease_id or "").strip())
    if not isinstance(lease, dict) or _expired(lease):
        if isinstance(lease, dict):
            del data["leases"][lease_id]
            _save(data)
        return {"ok": False, "error": "unknown_or_expired_lease"}
    if lane is not None and lease.get("lane") != lane:
        return {"ok": False, "error": "lease_lane_mismatch"}
    if tab_id is not None and lease.get("tab_id") != tab_id:
        return {"ok": False, "error": "lease_tab_mismatch"}
    if (
        document_generation is not None
        and lease.get("document_generation") not in (None, document_generation)
    ):
        return {"ok": False, "error": "stale_document"}
    return {"ok": True, "lease": lease}


def release(*, lease_id: str) -> dict[str, Any]:
    data = _load()
    if (lease_id or "").strip() in data["leases"]:
        del data["leases"][lease_id.strip()]
        _save(data)
        return {"ok": True, "released": lease_id.strip()}
    _prune(data)
    _save(data)
    return {"ok": False, "error": "unknown_lease"}


def list_active(*, lane: str | None = None, tab_id: str | None = None) -> list[dict[str, Any]]:
    data = _load()
    if _prune(data):
        _save(data)
    out = []
    for lease in data["leases"].values():
        if not isinstance(lease, dict):
            continue
        if lane is not None and lease.get("lane") != lane:
            continue
        if tab_id is not None and lease.get("tab_id") != tab_id:
            continue
        out.append(lease)
    return out


def clear_all() -> None:
    path = leases_file_path()
    if path.is_file():
        path.unlink()
