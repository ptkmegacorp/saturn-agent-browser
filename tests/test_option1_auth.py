"""Option 1 credential approval gate tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from saturn_fbc.auth_client import AuthRequestView
from saturn_fbc.contract import AuthorityContract, ContractMode, CredentialSpec
from saturn_fbc.credentials import (
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

    @patch("saturn_fbc.credentials.fill_credential")
    @patch("saturn_fbc.auth_client.consume_approval", return_value="Sites/example.com--alice--fixture")
    @patch("saturn_fbc.auth_client.get_request")
    @patch("saturn_fbc.auth_client.create_login_request")
    @patch("saturn_fbc.broker.vault_ready", return_value=True)
    @patch("saturn_fbc.credentials.password_fields_need_fill", return_value=True)
    def test_approved_request_fills(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
        consume_approval,
        fill_credential,
    ) -> None:
        from saturn_fbc.credentials import ensure_credential_filled

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

        class FakePage:
            url = "https://example.com/login"

        state = CredentialRunState(handle="Sites/example.com--alice--fixture")
        result = ensure_credential_filled(self._contract(), FakePage(), state)
        self.assertEqual(result, CredentialFillResult.FILLED)
        fill_credential.assert_called_once()

    @patch("saturn_fbc.auth_client.get_request")
    @patch("saturn_fbc.auth_client.create_login_request")
    @patch("saturn_fbc.broker.vault_ready", return_value=True)
    @patch("saturn_fbc.credentials.password_fields_need_fill", return_value=True)
    def test_pending_request_waits(
        self,
        _need_fill,
        _vault_ready,
        create_login_request,
        get_request,
    ) -> None:
        from saturn_fbc.credentials import ensure_credential_filled

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


if __name__ == "__main__":
    unittest.main()
