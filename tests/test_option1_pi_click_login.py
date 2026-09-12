"""Live Saturn Pi Approve + fixture login (skip if Pi or Auth is down)."""

from __future__ import annotations

import os
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from saturn_agent_browser.auth_client import get_request
from saturn_agent_browser.credentials import (
    CredentialFillResult,
    CredentialRunState,
    fill_with_operator_gate,
    report_login_verification,
)
from saturn_agent_browser.option1_fixture import FixtureLoginWorld


def _pi_up() -> bool:
    url = os.environ.get("SATURN_PI_URL", "http://127.0.0.1:3210").rstrip("/") + "/"
    login = os.environ.get("SATURN_PI_OPERATOR_LOGIN", "etanner27@gmail.com")
    req = urllib.request.Request(url, headers={"Tailscale-User-Login": login})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _auth_up() -> bool:
    url = os.environ.get("SATURN_AUTH_URL", "http://127.0.0.1:8792").rstrip("/") + "/v1/health"
    token_file = Path.home() / ".local" / "state" / "saturn-auth" / "callers" / "fbc"
    if not token_file.is_file():
        return False
    token = token_file.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _chromium():
    from playwright.sync_api import sync_playwright

    from saturn_agent_browser.config import load_config

    load_config()
    return sync_playwright()


class Option1PiClickLoginTests(unittest.TestCase):
    def test_pi_click_fill_verify_continue(self) -> None:
        if not _pi_up():
            self.skipTest("Saturn Pi is not listening on loopback")
        if not _auth_up():
            self.skipTest("Saturn Auth is not listening on loopback")
        token_file = Path.home() / ".local" / "state" / "saturn-auth" / "callers" / "fbc"
        if not token_file.is_file():
            self.skipTest("FBC Auth caller token is missing")

        world = FixtureLoginWorld()
        world.start(in_process_auth=False)
        prev_click = os.environ.get("SATURN_AGENT_BROWSER_PI_CLICK")
        try:
            os.environ["SATURN_AUTH_URL"] = os.environ.get("SATURN_AUTH_URL", "http://127.0.0.1:8792").rstrip("/")
            os.environ["SATURN_AUTH_FBC_TOKEN_FILE"] = str(token_file)
            os.environ["SATURN_AGENT_BROWSER_PI_CLICK"] = "1"
            from saturn_agent_browser.config import load_config

            load_config.cache_clear()
            load_config()
            run_id = "option1-pi-click-test-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            contract = world.contract(run_id=run_id)
            with _chromium() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(world.login_url)
                state = CredentialRunState(handle=world.handle)
                filled = fill_with_operator_gate(contract, page, state)
                self.assertEqual(filled, CredentialFillResult.FILLED)
                self.assertIsNotNone(state.auth_request_id)
                page.click("#login-btn")
                page.wait_for_selector("#logged-in")
                self.assertTrue(report_login_verification(contract, page, state))
                view = get_request(state.auth_request_id)
                self.assertIsNotNone(view)
                self.assertEqual(view.state, "verified")
                page.goto(world.continue_url)
                self.assertGreater(page.locator("#continued").count(), 0)
                browser.close()
        finally:
            if prev_click is None:
                os.environ.pop("SATURN_AGENT_BROWSER_PI_CLICK", None)
            else:
                os.environ["SATURN_AGENT_BROWSER_PI_CLICK"] = prev_click
            world.stop()


if __name__ == "__main__":
    unittest.main()
