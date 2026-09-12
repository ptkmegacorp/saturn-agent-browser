"""Phase 0 contract and interceptor tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saturn_agent_browser.actions import ActionRejectedError, validate_action
from saturn_agent_browser.browser.interceptor import intercept_action, validate_navigate
from saturn_agent_browser.contract import (
    AuthorityContract,
    BrowserAction,
    ContractMode,
    StopReason,
    contract_to_json,
    load_contract,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONTRACT = ROOT / "contracts" / "local-form.json"
HTTPBIN_CONTRACT = ROOT / "contracts" / "live-httpbin-form.json"


def test_contract_round_trip_local_fixture():
    contract = load_contract(LOCAL_CONTRACT)
    assert contract.task_id == "local-form-fixture-v1"
    assert contract.mode == ContractMode.DRAFT
    assert "submit" in contract.blocked_actions

    raw = contract_to_json(contract)
    parsed = json.loads(raw)
    again = AuthorityContract.model_validate(parsed)
    assert again.task_id == contract.task_id
    assert again.allowed_actions == contract.allowed_actions


def test_contract_round_trip_httpbin():
    contract = load_contract(HTTPBIN_CONTRACT)
    assert contract.origin_allowlist == ["httpbin.org"]
    assert contract.max_steps == 10
    assert contract.task_data["custemail"] == "saturn-test@example.invalid"


def test_submit_blocked():
    contract = load_contract(LOCAL_CONTRACT)
    with pytest.raises(ActionRejectedError, match="blocked"):
        validate_action(contract, BrowserAction(type="submit"))

    with pytest.raises(ActionRejectedError, match="blocked"):
        intercept_action(contract, BrowserAction(type="send"))

    with pytest.raises(ActionRejectedError, match="blocked"):
        validate_action(contract, BrowserAction(type="purchase"))

    with pytest.raises(ActionRejectedError, match="not in allowed_actions"):
        validate_action(contract, BrowserAction(type="download"))


def test_off_allowlist_navigate_blocked():
    contract = load_contract(HTTPBIN_CONTRACT)
    with pytest.raises(ActionRejectedError, match="outside origin_allowlist"):
        validate_navigate(contract, "https://evil.example/phish")

    with pytest.raises(ActionRejectedError, match="outside origin_allowlist"):
        intercept_action(
            contract,
            BrowserAction(type="navigate", url="https://not-httpbin.org/"),
        )


def test_allowed_navigate_passes():
    contract = load_contract(HTTPBIN_CONTRACT)
    action = intercept_action(
        contract,
        BrowserAction(type="navigate", url="https://httpbin.org/forms/post"),
    )
    assert action.url.endswith("/forms/post")


def test_stop_reason_enum_values():
    assert StopReason.PRE_SUBMIT_BOUNDARY.value == "pre_submit_boundary"
    assert StopReason.ESCALATE.value == "escalate"
