"""Server-side document generations for CDP-attached panel tabs.

The panel talks to browsers over CDP /json, which reports target id, url
and title but no document loader identity. The previous URL-hash generation
was blind to same-URL reloads: navigating A -> A produced the same
generation, so stale checks could not see the reload.

This store keys (lane, target_id) -> {url, seq, generation} and persists
beside the other browser state files (0600). Generations look like
``doc-<seq>-<12hex>`` so the existing ``doc-`` prefix contract with the Pi
panel and CLI stays intact.

Rules:
- observe(): same target + same url -> stable generation (cheap polling
  does not churn). URL change -> seq bump (navigation another actor did).
- bump(): explicit invalidation after our own navigate, crash/replacement,
  or human-lease events. Same-URL reload MUST bump.
- evict_stale(): drop targets the browser no longer lists (tab closed or
  replaced) so a recycled target id cannot inherit an old generation.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from saturn_agent_browser.browser.state import state_file_path


def generations_file_path():
    return state_file_path().with_name("browser-generations.json")


def _blank() -> dict[str, Any]:
    return {"targets": {}}


def _load() -> dict[str, Any]:
    path = generations_file_path()
    if not path.is_file():
        return _blank()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _blank()
    if not isinstance(data, dict) or not isinstance(data.get("targets"), dict):
        return _blank()
    return data


def _save(data: dict[str, Any]) -> None:
    path = generations_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _key(lane: str, target_id: str) -> str:
    return f"{lane}\x00{target_id}"


def _mint(lane: str, target_id: str, url: str, seq: int, reason: str) -> str:
    digest = hashlib.sha256(f"{lane}\n{target_id}\n{url}\n{seq}\n{reason}".encode("utf-8")).hexdigest()[:12]
    return f"doc-{seq}-{digest}"


def observe(*, lane: str, target_id: str, url: str) -> str:
    """Return the current generation, bumping seq when the URL changed."""
    lane = (lane or "isolated").strip() or "isolated"
    target_id = (target_id or "").strip()
    url = url or ""
    data = _load()
    entry = data["targets"].get(_key(lane, target_id))
    if entry is None or not isinstance(entry, dict):
        entry = {"url": url, "seq": 1, "generation": _mint(lane, target_id, url, 1, "attach")}
        data["targets"][_key(lane, target_id)] = entry
        _save(data)
        return entry["generation"]
    if entry.get("url") != url:
        seq = int(entry.get("seq") or 0) + 1
        entry.update({"url": url, "seq": seq, "generation": _mint(lane, target_id, url, seq, "navigate")})
        _save(data)
    return str(entry["generation"])


def current(*, lane: str, target_id: str) -> str | None:
    data = _load()
    entry = data["targets"].get(_key(lane, target_id))
    if not isinstance(entry, dict):
        return None
    gen = entry.get("generation")
    return str(gen) if gen else None


def bump(*, lane: str, target_id: str, url: str, reason: str = "bump") -> str:
    """Force a new generation (post-navigate, reload, crash, lease events)."""
    lane = (lane or "isolated").strip() or "isolated"
    target_id = (target_id or "").strip()
    data = _load()
    entry = data["targets"].get(_key(lane, target_id))
    seq = (int(entry.get("seq") or 0) + 1) if isinstance(entry, dict) else 1
    generation = _mint(lane, target_id, url or "", seq, reason)
    data["targets"][_key(lane, target_id)] = {"url": url or "", "seq": seq, "generation": generation}
    _save(data)
    return generation


def evict_stale(*, lane: str, live_target_ids: set[str]) -> list[str]:
    """Drop stored targets the browser no longer lists. Returns evicted ids."""
    lane = (lane or "isolated").strip() or "isolated"
    data = _load()
    evicted: list[str] = []
    for key in list(data["targets"].keys()):
        key_lane, _, target_id = key.partition("\x00")
        if key_lane != lane:
            continue
        if target_id not in live_target_ids:
            del data["targets"][key]
            evicted.append(target_id)
    if evicted:
        _save(data)
    return evicted


def clear_all() -> None:
    path = generations_file_path()
    if path.is_file():
        path.unlink()
