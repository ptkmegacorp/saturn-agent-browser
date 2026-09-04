"""Phase 5 integration: bounded live httpbin test (network required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from saturn_fbc.contract import StopReason
from saturn_fbc.spark.loop import run_contract_path


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.network
def test_live_httpbin_form_no_submit():
    result = run_contract_path(
        ROOT / "contracts" / "live-httpbin-form.json",
        headless=True,
        skip_gpu=False,
    )
    assert result.stop_reason == StopReason.SUCCESS
    assert result.escalation_path is None
