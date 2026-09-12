#!/usr/bin/env python3
"""Option-1 fixture login against a disposable vault and loopback HTTP page.

Default: auto-approve with the in-process Pi token (same Auth API as iPhone).

  .venv/bin/python scripts/option1_fixture_login.py

HITL: disposable KeePass + loopback login, live Saturn Auth (:8792), iPhone Approve.

  .venv/bin/python scripts/option1_fixture_login.py --hitl
  .venv/bin/python scripts/option1_fixture_login.py --pi-click
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Option-1 fixture login")
    parser.add_argument(
        "--hitl",
        action="store_true",
        help="Wait for iPhone Approve on live Saturn Auth instead of auto-approve",
    )
    parser.add_argument(
        "--pi-click",
        action="store_true",
        help="Test-scoped: click Saturn Pi Approve for this fixture request id (not saturn-agent-browser run)",
    )
    args = parser.parse_args()

    from saturn_agent_browser.auth_client import get_request
    from saturn_agent_browser.config import load_config
    from saturn_agent_browser.credentials import (
        CredentialFillResult,
        CredentialRunState,
        ensure_credential_filled,
        fill_with_operator_gate,
        report_login_verification,
    )
    from saturn_agent_browser.option1_fixture import FixtureLoginWorld
    from playwright.sync_api import sync_playwright

    live_auth = args.hitl or args.pi_click
    world = FixtureLoginWorld()
    world.start(in_process_auth=not live_auth)
    if live_auth:
        live = os.environ.get("SATURN_AUTH_URL", "http://127.0.0.1:8792").rstrip("/")
        os.environ["SATURN_AUTH_URL"] = live
        os.environ["SATURN_AUTH_FBC_TOKEN_FILE"] = str(
            Path.home() / ".local" / "state" / "saturn-auth" / "callers" / "fbc"
        )

    try:
        load_config()
        os.environ["AGENT_KDBX"] = str(world.kdbx)
        os.environ["AGENT_VAULT_KEY_FILE"] = str(world.key_file)
        load_config.cache_clear()
        load_config()
        run_id = "option1-fixture-cli-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        contract = world.contract(run_id=run_id)
        with sync_playwright() as playwright:
            headed = args.hitl and os.environ.get("SATURN_AGENT_BROWSER_HEADLESS", "0") != "1"
            browser = playwright.chromium.launch(headless=not headed)
            page = browser.new_page()
            page.goto(world.login_url)
            os.environ["AGENT_KDBX"] = str(world.kdbx)
            os.environ["AGENT_VAULT_KEY_FILE"] = str(world.key_file)
            from saturn_agent_browser.broker import vault as broker_vault

            if not broker_vault.vault_ready():
                print(
                    f"vault_not_ready kdbx={broker_vault.agent_kdbx_path()} "
                    f"exists={broker_vault.agent_kdbx_path().is_file()} "
                    f"key={broker_vault.vault_key_file()} "
                    f"key_exists={broker_vault.vault_key_file().is_file()}",
                    file=sys.stderr,
                )
                return 2
            state = CredentialRunState(handle=world.handle)
            if args.pi_click:
                os.environ["SATURN_AGENT_BROWSER_PI_CLICK"] = "1"
                filled = fill_with_operator_gate(contract, page, state)
                rid = state.auth_request_id
                print(f"auth_request_id={rid}", flush=True)
                print(f"origin={world.origin}", flush=True)
                print(f"fill={filled.value}", flush=True)
                if filled != CredentialFillResult.FILLED:
                    browser.close()
                    return 1
                page.click("#login-btn")
                page.wait_for_selector("#logged-in")
                verified = report_login_verification(contract, page, state)
                view = get_request(rid)
                print(f"verified={verified} auth_state={view.state if view else 'missing'}")
                page.goto(world.continue_url)
                continued = page.locator("#continued").count() > 0
                print(f"continued={continued}")
                browser.close()
                return 0 if verified and continued else 1
            result = ensure_credential_filled(contract, page, state)
            if result != CredentialFillResult.AWAITING_APPROVAL:
                print(f"expected awaiting_approval, got {result.value}", file=sys.stderr)
                return 2
            rid = state.auth_request_id
            print(f"auth_request_id={rid}", flush=True)
            print(f"origin={world.origin}", flush=True)
            if live_auth:
                print(
                    "\n"
                    "iPhone HITL\n"
                    "  1. Saturn Pi → Reload if needed → Home → Browser auth\n"
                    f"  2. Confirm origin {world.origin} (loopback fixture, not a real site)\n"
                    "  3. Approve to allow one KeePass fill, or Deny to abort\n"
                    f"Waiting on {rid} for about 30 seconds (Auth long-poll, no sleep loop).\n",
                    flush=True,
                )
                from saturn_agent_browser.auth_client import wait_request_state

                waited = wait_request_state(rid)
                print(f"request_state={waited.state if waited else 'missing'}", flush=True)
                if waited is None or waited.state != "approved":
                    print("not approved; stopping before fill")
                    browser.close()
                    return 1
            else:
                world.approve(rid)
            filled = ensure_credential_filled(contract, page, state)
            print(f"fill={filled.value}")
            if filled != CredentialFillResult.FILLED:
                browser.close()
                return 1
            page.click("#login-btn")
            page.wait_for_selector("#logged-in")
            verified = report_login_verification(contract, page, state)
            view = get_request(rid)
            print(f"verified={verified} auth_state={view.state if view else 'missing'}")
            page.goto(world.continue_url)
            continued = page.locator("#continued").count() > 0
            print(f"continued={continued}")
            browser.close()
            return 0 if verified and continued else 1
    finally:
        world.stop()


if __name__ == "__main__":
    raise SystemExit(main())
