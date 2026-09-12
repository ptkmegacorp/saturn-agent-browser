"""Phase 2: Spark client and loop tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from saturn_agent_browser.contract import AuthorityContract, BrowserAction, ContractMode
from saturn_agent_browser.spark.client import SparkClient, SparkResponse, _extract_json, build_user_prompt
from saturn_agent_browser.spark.loop import run_spark_loop


def _sample_contract() -> AuthorityContract:
    return AuthorityContract(
        task_id="test",
        mode=ContractMode.DRAFT,
        subgoal="Fill form",
        origin_allowlist=[],
        allowed_actions=["type", "click"],
        blocked_actions=["submit"],
        max_steps=5,
        start_url="file:///tmp/form.html",
        task_data={"name": "Test"},
        success_checks=["name field filled"],
    )


def test_extract_json_from_fenced_block():
    raw = 'Here is action:\n```json\n{"type":"type","index":2,"text":"x"}\n```'
    parsed = _extract_json(raw)
    assert parsed["type"] == "type"
    assert parsed["index"] == 2


def test_build_user_prompt_includes_subgoal():
    prompt = build_user_prompt(_sample_contract(), digest="[1] textbox", url="file:///x", last_steps=[])
    assert "Fill form" in prompt
    assert "[1] textbox" in prompt


def test_spark_client_parse_valid_response():
    client = SparkClient(base_url="http://127.0.0.1:8091/v1")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"type":"type","index":1,"text":"hello"}'}}]
    }
    mock_response.raise_for_status = MagicMock()
    with patch("saturn_agent_browser.spark.client.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        result = client.propose_action(
            _sample_contract(),
            digest="[1] textbox",
            url="file:///x",
            last_steps=[],
        )
    assert isinstance(result, SparkResponse)
    assert result.action == BrowserAction(type="type", index=1, text="hello")


@pytest.mark.integration
def test_spark_loop_dry_run_on_fixture():
    from pathlib import Path

    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "local-form.json"
    from saturn_agent_browser.contract import load_contract

    contract = load_contract(contract_path)
    result = run_spark_loop(contract, headless=True, skip_gpu=True, dry_run_spark=True)
    assert result.trace_dir.is_dir()
    assert result.stop_reason.value == "pre_submit_boundary"
