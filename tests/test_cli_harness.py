"""CLI harness smoke tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ".venv/bin/saturn-agent-browser"


def _run(args: list[str]) -> dict:
    result = subprocess.run(
        [str(CLI), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("args", [["status"], ["broker-status"], ["broker-setup"], ["last"]])
def test_cli_json_commands(args: list[str]):
    payload = _run(args)
    assert isinstance(payload, dict)


def test_cli_validate_contract():
    payload = _run(["validate-contract", str(ROOT / "contracts" / "local-form.json")])
    assert payload.get("ok") is True
