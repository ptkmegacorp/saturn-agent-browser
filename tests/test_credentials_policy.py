"""Credential policy unit tests."""

from __future__ import annotations

from pathlib import Path

from saturn_fbc.contract import AuthorityContract, ContractMode, CredentialSpec, load_contract
from saturn_fbc.credentials import (
    policy_active,
    resolve_domain,
    resolve_label,
    resolve_username,
)

ROOT = Path(__file__).resolve().parents[1]
SIGNUP_CONTRACT = ROOT / "contracts" / "local-signup-broker.json"


def test_policy_active():
    contract = load_contract(SIGNUP_CONTRACT)
    assert policy_active(contract) is True
    contract.credential_policy = "none"
    assert policy_active(contract) is False


def test_credential_spec_resolvers():
    contract = load_contract(SIGNUP_CONTRACT)
    assert resolve_username(contract) == "job-agent@example.invalid"
    assert resolve_label(contract) == "local-signup-fixture"
    assert resolve_domain(contract, page=type("P", (), {"url": "file:///tmp/x"})()) == "local.signup"


def test_credential_spec_on_contract_model():
    contract = AuthorityContract(
        task_id="t1",
        mode=ContractMode.DRAFT,
        subgoal="signup",
        origin_allowlist=["example.com"],
        allowed_actions=["type"],
        credential_policy="request_only",
        credential_spec=CredentialSpec(
            domain="example.com",
            username="you@gmail.com",
            label="acme-role",
        ),
        task_data={"email": "you@gmail.com"},
    )
    assert contract.credential_spec is not None
    assert contract.credential_spec.username == "you@gmail.com"
