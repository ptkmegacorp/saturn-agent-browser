"""Phase 5 integration: bounded live httpbin test (network required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_agent_browser.contract import StopReason
from saturn_agent_browser.runner import run_contract


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.network
def test_live_httpbin_form_no_submit():
    result = run_contract(
        ROOT / "contracts" / "live-httpbin-form.json",
        headless=True,
        mode="skeleton",
    )
    assert result.stop_reason == StopReason.PRE_SUBMIT_BOUNDARY
    assert result.escalation_path is None
