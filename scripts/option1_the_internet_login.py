#!/usr/bin/env python3
"""Option-1 live HTTPS login: the-internet demo account in Agent.kdbx.

iPhone Approve (default):

  SATURN_FBC_HEADLESS=1 .venv/bin/python scripts/option1_the_internet_login.py --hitl

Local Saturn Pi click (test):

  SATURN_FBC_HEADLESS=1 .venv/bin/python scripts/option1_the_internet_login.py --pi-click
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

HANDLE = "Sites/the-internet.herokuapp.com--tomsmith--option1-low-risk"
LOGIN_URL = "https://the-internet.herokuapp.com/login"


def main() -> int:
    parser = argparse.ArgumentParser(description="the-internet option-1 login")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--hitl", action="store_true", help="Wait for iPhone / Saturn Pi Approve")
    mode.add_argument("--pi-click", action="store_true", help="Approve via saturn-pi ui recipe in a child process")
    args = parser.parse_args()
    if not args.hitl and not args.pi_click:
        args.hitl = True

    os.environ.setdefault("SATURN_AUTH_URL", "http://127.0.0.1:8792")
    os.environ["SATURN_AUTH_FBC_TOKEN_FILE"] = str(
        Path.home() / ".local" / "state" / "saturn-auth" / "callers" / "fbc"
    )
    os.environ.pop("SATURN_AUTH_FIXTURE_VAULT", None)
    if args.pi_click:
        os.environ["SATURN_FBC_PI_CLICK"] = "1"
    else:
        os.environ.pop("SATURN_FBC_PI_CLICK", None)

    from saturn_fbc.auth_client import get_request, wait_request_state
    from saturn_fbc.broker import vault as broker_vault
    from saturn_fbc.browser.live_bindings import attach_live_bindings
    from saturn_fbc.config import load_config
    from saturn_fbc.contract import load_contract
    from saturn_fbc.credentials import (
        CredentialFillResult,
        CredentialRunState,
        ensure_credential_filled,
        fill_with_operator_gate,
        report_login_verification,
    )
    from playwright.sync_api import sync_playwright

    load_config.cache_clear()
    load_config()
    if not broker_vault.vault_ready():
        print("vault_not_ready", file=sys.stderr)
        return 2

    contract = load_contract(ROOT / "contracts" / "the-internet-login.json")
    contract.run_id = "the-internet-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    headless = os.environ.get("SATURN_FBC_HEADLESS", "1") != "0"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        attach_live_bindings(page)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.locator("#password").wait_for(state="visible", timeout=20_000)
        state = CredentialRunState(handle=HANDLE)
        if args.pi_click:
            filled = fill_with_operator_gate(contract, page, state)
        else:
            first = ensure_credential_filled(contract, page, state)
            rid = state.auth_request_id
            print(f"auth_request_id={rid}", flush=True)
            print("origin=https://the-internet.herokuapp.com", flush=True)
            print(
                "\n"
                "iPhone: Saturn Pi → Reload if needed → Home → Browser auth\n"
                "  Confirm website https://the-internet.herokuapp.com (demo tomsmith)\n"
                "  Approve, then this process fills, clicks Login, and verifies.\n",
                flush=True,
            )
            if first != CredentialFillResult.AWAITING_APPROVAL:
                print(f"expected awaiting_approval, got {first.value}", file=sys.stderr)
                browser.close()
                return 2
            waited = wait_request_state(rid) if rid else None
            print(f"request_state={waited.state if waited else 'missing'}", flush=True)
            if waited is None or waited.state != "approved":
                browser.close()
                return 1
            filled = ensure_credential_filled(contract, page, state)
        rid = state.auth_request_id
        if args.pi_click:
            print(f"auth_request_id={rid}", flush=True)
            print("origin=https://the-internet.herokuapp.com", flush=True)
        print(f"fill={filled.value}", flush=True)
        if state.events:
            print("events=" + ";".join(state.events), flush=True)
        if filled != CredentialFillResult.FILLED:
            view = get_request(rid) if rid else None
            print(f"auth_state={view.state if view else 'missing'}", flush=True)
            browser.close()
            return 1
        page.locator("#login button[type=submit]").click()
        page.locator(".flash.success").wait_for(state="visible", timeout=20_000)
        verified = report_login_verification(contract, page, state)
        view = get_request(rid)
        print(f"verified={verified} auth_state={view.state if view else 'missing'}", flush=True)
        print(f"url={page.url}", flush=True)
        browser.close()
        return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
