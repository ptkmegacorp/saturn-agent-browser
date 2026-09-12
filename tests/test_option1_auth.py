"""Option 1 credential approval gate tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from saturn_agent_browser.auth_client import AuthRequestView
from saturn_agent_browser.contract import AuthorityContract, ContractMode, CredentialSpec
from saturn_agent_browser.credentials import (
    CredentialFillResult,
    CredentialRunState,
    auto_create_allowed,
    requires_user_approval,
)


class Option1CredentialPolicyTests(unittest.TestCase):
    def _contract(self, **overrides):
        payload = {
            "task_id": "task-1",
            "run_id": "run-1",
            "mode": ContractMode.DRAFT,
            "subgoal": "login",
            "origin_allowlist": ["example.com"],
            "allowed_actions": ["click", "type"],
            "credential_policy": "existing_only",
            "credential_spec": CredentialSpec(
                domain="example.com",
                username="alice@example.com",
                label="fixture",
                handle="Sites/example.com--alice--fixture",
            ),
        }
        payload.update(overrides)
        return AuthorityContract(**payload)

    def test_existing_only_requires_approval(self) -> None:
        contract = self._contract()
        self.assertTrue(requires_user_approval(contract))
        self.assertFalse(auto_create_allowed(contract))

    @patch("saturn_agent_browser.auth_client.report_outcome", return_value=True)
    @patch("saturn_agent_browser.broker.fill_credential")
    @patch("saturn_agent_browser.auth_client.consume_result")
    @patch("saturn_agent_browser.auth_client.get_request")
    @patch("saturn_agent_browser.auth_client.create_login_request")
    @patch("saturn_agent_browser.broker.vault_ready", return_value=True)
    @patch("saturn_agent_browser.credentials.password_fields_need_fill", return_value=True)
    def test_approved_request_fills(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
        consume_result,
        fill_credential,
        report_outcome,
    ) -> None:
        from saturn_agent_browser.auth_client import ConsumeResult
        from saturn_agent_browser.credentials import ensure_credential_filled

        create_login_request.return_value = AuthRequestView(
            request_id="auth_test",
            state="awaiting_user",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        get_request.return_value = AuthRequestView(
            request_id="auth_test",
            state="approved",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        consume_result.return_value = ConsumeResult(
            handle="Sites/example.com--alice--fixture",
            error=None,
        )

        class FakePage:
            url = "https://example.com/login"

        state = CredentialRunState(handle="Sites/example.com--alice--fixture")
        result = ensure_credential_filled(self._contract(), FakePage(), state)
        self.assertEqual(result, CredentialFillResult.FILLED)
        fill_credential.assert_called_once()
        report_outcome.assert_called_with("auth_test", "filled")

    @patch("saturn_agent_browser.auth_client.consume_result")
    @patch("saturn_agent_browser.auth_client.get_request")
    @patch("saturn_agent_browser.auth_client.create_login_request")
    @patch("saturn_agent_browser.broker.vault_ready", return_value=True)
    @patch("saturn_agent_browser.credentials.password_fields_need_fill", return_value=True)
    def test_persist_failed_consume_is_retryable(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
        consume_result,
    ) -> None:
        from saturn_agent_browser.auth_client import ConsumeResult
        from saturn_agent_browser.credentials import ensure_credential_filled

        create_login_request.return_value = AuthRequestView(
            request_id="auth_persist",
            state="awaiting_user",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        get_request.return_value = AuthRequestView(
            request_id="auth_persist",
            state="approved",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        consume_result.return_value = ConsumeResult(handle=None, error="persist_failed")

        class FakePage:
            url = "https://example.com/login"

        state = CredentialRunState(handle="Sites/example.com--alice--fixture")
        result = ensure_credential_filled(self._contract(), FakePage(), state)
        self.assertEqual(result, CredentialFillResult.AUTH_UNAVAILABLE)

    @patch("saturn_agent_browser.auth_client.report_outcome", return_value=True)
    @patch("saturn_agent_browser.auth_client.get_request")
    @patch("saturn_agent_browser.auth_client.create_login_request")
    @patch("saturn_agent_browser.broker.vault_ready", return_value=True)
    @patch("saturn_agent_browser.credentials.password_fields_need_fill", return_value=True)
    def test_claimed_without_fill_reports_uncertain(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
        report_outcome,
    ) -> None:
        from saturn_agent_browser.credentials import ensure_credential_filled

        create_login_request.return_value = AuthRequestView(
            request_id="auth_claimed",
            state="awaiting_user",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        get_request.return_value = AuthRequestView(
            request_id="auth_claimed",
            state="claimed",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )

        class FakePage:
            url = "https://example.com/login"

        state = CredentialRunState(handle="Sites/example.com--alice--fixture")
        result = ensure_credential_filled(self._contract(), FakePage(), state)
        self.assertEqual(result, CredentialFillResult.AUTH_DENIED)
        report_outcome.assert_called_with("auth_claimed", "failed", "uncertain_delivery")

    @patch("saturn_agent_browser.auth_client.get_request")
    @patch("saturn_agent_browser.auth_client.create_login_request")
    @patch("saturn_agent_browser.broker.vault_ready", return_value=True)
    @patch("saturn_agent_browser.credentials.password_fields_need_fill", return_value=True)
    def test_pending_request_waits(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
    ) -> None:
        from saturn_agent_browser.credentials import ensure_credential_filled

        create_login_request.return_value = AuthRequestView(
            request_id="auth_wait",
            state="awaiting_user",
            origin="https://example.com",
            account_label="alice @ example.com",
            purpose="login",
            task_id="task-1",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        get_request.return_value = create_login_request.return_value

        class FakePage:
            url = "https://example.com/login"

        state = CredentialRunState(handle="Sites/example.com--alice--fixture")
        result = ensure_credential_filled(self._contract(), FakePage(), state)
        self.assertEqual(result, CredentialFillResult.AWAITING_APPROVAL)
        self.assertEqual(state.auth_request_id, "auth_wait")

    @patch("saturn_agent_browser.auth_client.report_outcome", return_value=True)
    def test_independent_verify_reports_verified(self, report_outcome) -> None:
        from saturn_agent_browser.credentials import CredentialRunState, report_login_verification

        class FakeLocator:
            def count(self):
                return 1

            @property
            def first(self):
                return self

            def is_visible(self):
                return True

        class FakePage:
            def locator(self, selector):
                return FakeLocator()

        page = FakePage()
        state = CredentialRunState(auth_request_id="auth_verify")
        self.assertTrue(report_login_verification(self._contract(success_checks=["#logged-in"]), page, state))
        report_outcome.assert_called_with("auth_verify", "verified")
        self.assertIn("auth_request_verified:auth_verify", state.events)


if __name__ == "__main__":
    unittest.main()
