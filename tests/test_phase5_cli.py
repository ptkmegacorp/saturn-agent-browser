"""Phase 5: CLI harness tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from saturn_fbc.cli import app


runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_cli_status_json():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "tenant_profile" in payload


def test_cli_validate_contract():
    contract = ROOT / "contracts" / "live-httpbin-form.json"
    result = runner.invoke(app, ["validate-contract", str(contract)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_cli_run_skeleton_headless():
    contract = ROOT / "contracts" / "local-form.json"
    result = runner.invoke(
        app,
        ["run-skeleton", "--contract", str(contract), "--headless"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert Path(payload["trace_dir"]).is_dir()


def test_cli_broker_status():
    result = runner.invoke(app, ["broker-status"])
    assert result.exit_code == 0
    assert "vault_ready" in json.loads(result.stdout)


def test_cli_broker_create_requires_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_KDBX", str(tmp_path / "missing.kdbx"))
    result = runner.invoke(
        app,
        [
            "broker-create",
            "--domain",
            "example.com",
            "--username",
            "user@example.com",
            "--label",
            "test",
        ],
    )
    assert result.exit_code != 0


def test_cli_specialist_status(monkeypatch):
    monkeypatch.setattr(
        "saturn_fbc.specialist.specialist_configured",
        lambda: False,
    )
    result = runner.invoke(app, ["specialist-status"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["configured"] is False
