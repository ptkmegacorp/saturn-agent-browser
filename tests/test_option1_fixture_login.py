"""Option 1 controlled fixture login: approve, one fill, independent verify."""

from __future__ import annotations

import unittest
from pathlib import Path

from saturn_agent_browser.auth_client import consume_approval, get_request
from saturn_agent_browser.browser.trace import TraceWriter
from saturn_agent_browser.credentials import (
    CredentialFillResult,
    CredentialRunState,
    ensure_credential_filled,
    report_login_verification,
)
from saturn_agent_browser.option1_fixture import FixtureLoginWorld


def _chromium():
    from playwright.sync_api import sync_playwright

    from saturn_agent_browser.config import load_config

    load_config()
    return sync_playwright()


class Option1FixtureLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            pw = _chromium()
            playwright = pw.start()
            browser = playwright.chromium.launch(headless=True)
            browser.close()
            playwright.stop()
        except Exception as err:
            raise unittest.SkipTest(f"Playwright Chromium unavailable: {err}") from err

    def test_approve_fill_verify_continue(self) -> None:
        with FixtureLoginWorld() as world:
            contract = world.contract()
            with _chromium() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(world.login_url)
                state = CredentialRunState(handle=world.handle)
                first = ensure_credential_filled(contract, page, state)
                self.assertEqual(first, CredentialFillResult.AWAITING_APPROVAL)
                self.assertIsNotNone(state.auth_request_id)
                world.approve(state.auth_request_id)
                filled = ensure_credential_filled(contract, page, state)
                self.assertEqual(filled, CredentialFillResult.FILLED)
                page.click("#login-btn")
                page.wait_for_selector("#logged-in")
                self.assertTrue(report_login_verification(contract, page, state))
                view = get_request(state.auth_request_id)
                self.assertIsNotNone(view)
                self.assertEqual(view.state, "verified")
                replay = consume_approval(
                    state.auth_request_id,
                    run_id=contract.run_id,
                    profile_id="saturn-agent-browser",
                    browser_session_id=state.browser_session_id,
                    tab_id=state.tab_id,
                    document_generation=state.document_generation,
                    current_origin=world.origin,
                )
                self.assertIsNone(replay)
                page.goto(world.continue_url)
                self.assertGreater(page.locator("#continued").count(), 0)
                traces = Path(world.root) / "traces"
                writer = TraceWriter(contract.run_id, base_dir=traces)
                from saturn_agent_browser.contract import StepRecord

                writer.write_step(
                    StepRecord(step=1, url=page.url, title=page.title(), result="verified")
                )
                blob = writer.jsonl_path.read_text(encoding="utf-8")
                self.assertFalse(world.secret_leaked(world.store_blob(), blob, " ".join(state.events)))
                browser.close()

    def test_deny_does_not_fill(self) -> None:
        with FixtureLoginWorld() as world:
            contract = world.contract(run_id="run-deny")
            with _chromium() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(world.login_url)
                state = CredentialRunState(handle=world.handle)
                self.assertEqual(
                    ensure_credential_filled(contract, page, state),
                    CredentialFillResult.AWAITING_APPROVAL,
                )
                world.deny(state.auth_request_id)
                result = ensure_credential_filled(contract, page, state)
                self.assertEqual(result, CredentialFillResult.AUTH_DENIED)
                self.assertEqual((page.locator("#password").input_value() or "").strip(), "")
                self.assertFalse(world.secret_leaked(world.store_blob()))
                browser.close()

    def test_same_origin_navigation_rejects_fill(self) -> None:
        with FixtureLoginWorld() as world:
            contract = world.contract(run_id="run-stale")
            with _chromium() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(world.login_url)
                state = CredentialRunState(handle=world.handle)
                self.assertEqual(
                    ensure_credential_filled(contract, page, state),
                    CredentialFillResult.AWAITING_APPROVAL,
                )
                world.approve(state.auth_request_id)
                page.goto(world.login_url + "?after=1")
                result = ensure_credential_filled(contract, page, state)
                self.assertEqual(result, CredentialFillResult.AUTH_DENIED)
                self.assertEqual((page.locator("#password").input_value() or "").strip(), "")
                browser.close()

    def test_origin_mismatch_rejected(self) -> None:
        with FixtureLoginWorld() as world:
            contract = world.contract(run_id="run-origin")
            with _chromium() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(world.login_url)
                state = CredentialRunState(handle=world.handle)
                self.assertEqual(
                    ensure_credential_filled(contract, page, state),
                    CredentialFillResult.AWAITING_APPROVAL,
                )
                world.approve(state.auth_request_id)
                page.goto(world.other_origin)
                result = ensure_credential_filled(contract, page, state)
                self.assertEqual(result, CredentialFillResult.AUTH_DENIED)
                browser.close()


if __name__ == "__main__":
    unittest.main()
