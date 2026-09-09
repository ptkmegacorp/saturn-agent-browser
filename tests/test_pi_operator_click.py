"""Local Saturn Pi operator-click (skip if Pi is down)."""

from __future__ import annotations

import os
import unittest
import urllib.error
import urllib.request


def _pi_up() -> bool:
    url = os.environ.get("SATURN_PI_URL", "http://127.0.0.1:3210").rstrip("/") + "/"
    login = os.environ.get("SATURN_PI_OPERATOR_LOGIN", "etanner27@gmail.com")
    req = urllib.request.Request(url, headers={"Tailscale-User-Login": login})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class PiOperatorClickSmokeTests(unittest.TestCase):
    def test_home_loads_with_injected_login(self) -> None:
        if not _pi_up():
            self.skipTest("Saturn Pi is not listening on loopback")
        from saturn_fbc.config import load_config
        from playwright.sync_api import sync_playwright

        load_config()
        login = os.environ.get("SATURN_PI_OPERATOR_LOGIN", "etanner27@gmail.com")
        pi = os.environ.get("SATURN_PI_URL", "http://127.0.0.1:3210").rstrip("/")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(extra_http_headers={"Tailscale-User-Login": login})
            page = context.new_page()
            page.goto(f"{pi}/", wait_until="domcontentloaded")
            page.get_by_role("button", name="Open Saturn browser authentication approvals").wait_for(timeout=10_000)
            context.close()
            browser.close()

    def test_approve_requires_request_id(self) -> None:
        from saturn_fbc.pi_operator_click import click_browser_auth_approve

        with self.assertRaises(ValueError):
            click_browser_auth_approve(request_id=None)

    def test_ui_cli_shot(self) -> None:
        if not _pi_up():
            self.skipTest("Saturn Pi is not listening on loopback")
        from pathlib import Path

        from saturn_fbc.pi_operator_click import main

        dest = Path("/tmp/saturn-pi-ui-shot-test.png")
        code = main(["shot", "--path", str(dest)])
        self.assertEqual(code, 0)
        self.assertTrue(dest.is_file() and dest.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
