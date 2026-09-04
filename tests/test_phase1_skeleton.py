"""Phase 1 skeleton script logic tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from saturn_fbc.contract import BrowserAction, load_contract
from saturn_fbc.skeleton import build_fill_plan, fixture_url, run_skeleton

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONTRACT = ROOT / "contracts" / "local-form.json"


class FakeSnapshot:
    def __init__(self, nodes):
        self.nodes = nodes


def test_fixture_url_is_file_uri():
    url = fixture_url(ROOT / "fixtures" / "local-form.html")
    assert url.startswith("file://")
    assert url.endswith("local-form.html")


def test_build_fill_plan_maps_fields():
    contract = load_contract(LOCAL_CONTRACT)
    snap = FakeSnapshot(
        [
            {"index": 1, "role": "textbox", "name": "Full name"},
            {"index": 2, "role": "textbox", "name": "Email"},
            {"index": 3, "role": "textbox", "name": "Phone"},
            {"index": 4, "role": "textbox", "name": "Comments"},
        ]
    )
    plan = build_fill_plan(contract, snap)
    assert len(plan) == 4
    assert all(a.type == "type" for a in plan)
    texts = [a.text for a in plan]
    assert contract.task_data["email"] in texts
    assert contract.task_data["name"] in texts


def test_run_skeleton_mocked_session():
    contract = load_contract(LOCAL_CONTRACT)

    mock_session = MagicMock()
    mock_session.page = MagicMock()
    mock_session.trace.trace_dir = ROOT / "traces" / "test-run"
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    fake_snap = FakeSnapshot(
        [{"index": 1, "role": "textbox", "name": "Email"}]
    )

    with (
        patch("saturn_fbc.skeleton.BrowserSession", return_value=mock_session),
        patch("saturn_fbc.skeleton.capture_a11y_indexed", return_value=fake_snap),
        patch("saturn_fbc.skeleton.build_fill_plan", return_value=[BrowserAction(type="type", index=1, text="x")]),
    ):
        trace_dir = run_skeleton(contract_path=LOCAL_CONTRACT, headless=True)

    assert trace_dir == mock_session.trace.trace_dir
    mock_session.page.goto.assert_called_once()
    mock_session.act.assert_called_once()
    mock_session.stop.assert_called_once()


@pytest.mark.integration
def test_run_skeleton_integration():
    pytest.importorskip("playwright")
    trace_dir = run_skeleton(contract_path=LOCAL_CONTRACT, headless=True)
    assert trace_dir.is_dir()
    jsonl = trace_dir / "trace.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
