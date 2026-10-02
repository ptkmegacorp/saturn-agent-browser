#!/usr/bin/env python3
"""Local Playwright operator wrappers. Implementation lives in saturn-pi tools/ui-operator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FBC_ROOT = Path(__file__).resolve().parents[2]
_UI_ROOT = Path(
    os.environ.get(
        "SATURN_PI_UI_OPERATOR_ROOT",
        FBC_ROOT.parent / "saturn-pi" / "tools" / "ui-operator",
    )
).expanduser()
_SATURN_PI = shutil.which("saturn-pi") or os.environ.get("SATURN_PI_BIN", "saturn-pi")
if str(_UI_ROOT) not in sys.path:
    sys.path.insert(0, str(_UI_ROOT))


def click_browser_auth_approve_cli(request_id: str) -> str:
    """Approve via a child saturn-pi ui process (safe inside an existing Playwright loop)."""
    if not request_id or not str(request_id).strip():
        raise ValueError("request_id_required")
    rid = str(request_id).strip()
    result = subprocess.run(
        [_SATURN_PI, "ui", "recipe", "fbc-approve", "--request-id", rid],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = {}
    stdout = (result.stdout or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            payload = {"ok": False, "error": stdout}
    if result.returncode != 0 or not payload.get("ok"):
        raise RuntimeError(payload.get("error") or result.stderr.strip() or f"exit {result.returncode}")
    return str(payload.get("request_id") or rid)


def click_browser_auth_approve(
    *,
    request_id: str | None = None,
    origin: str | None = None,
    base_url: str | None = None,
    operator: str | None = None,
    headless: bool = True,
) -> str:
    if not request_id or not str(request_id).strip():
        raise ValueError("request_id_required")
    del origin  # never pick the first pending card
    from saturn_pi_ui.recipes.fbc_auth import run_fbc_approve
    from saturn_pi_ui.session import PiUiSession

    with PiUiSession(base_url=base_url, operator=operator, headless=headless) as session:
        return run_fbc_approve(session, request_id=str(request_id).strip())


def click_browser_auth_deny(
    *,
    request_id: str | None = None,
    origin: str | None = None,
    base_url: str | None = None,
    operator: str | None = None,
    headless: bool = True,
) -> str:
    if not request_id or not str(request_id).strip():
        raise ValueError("request_id_required")
    del origin
    from saturn_pi_ui.recipes.fbc_auth import run_fbc_deny
    from saturn_pi_ui.session import PiUiSession

    with PiUiSession(base_url=base_url, operator=operator, headless=headless) as session:
        return run_fbc_deny(session, request_id=str(request_id).strip())


def main(argv: list[str] | None = None) -> int:
    from saturn_pi_ui.cli import main as ui_main

    return ui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
