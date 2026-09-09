#!/usr/bin/env python3
"""Local Playwright operator wrappers. Implementation lives in saturn-pi tools/ui-operator."""

from __future__ import annotations

import sys
from pathlib import Path

_UI_ROOT = Path("~/projects/saturn-pi/tools/ui-operator")
if str(_UI_ROOT) not in sys.path:
    sys.path.insert(0, str(_UI_ROOT))


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
