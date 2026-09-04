"""Phase 4: credential broker tests."""

from __future__ import annotations

import pytest

from saturn_fbc.broker import broker_status, create_credential, generate_password, vault_ready


def test_generate_password_length():
    pw = generate_password(32)
    assert len(pw) == 32


def test_broker_status_reports_vault():
    status = broker_status()
    assert status["fill_mode"] == "broker"
    assert "vault_ready" in status
    assert "needs_you" in status


def test_create_credential_requires_vault_when_missing_key(monkeypatch, tmp_path):
    if vault_ready():
        pytest.skip("Agent vault configured on host")
    monkeypatch.setenv("AGENT_KDBX", str(tmp_path / "missing.kdbx"))
    with pytest.raises(RuntimeError, match="Agent vault not ready"):
        create_credential("example.com", "user", "label")


@pytest.mark.integration
def test_create_credential_round_trip():
    if not vault_ready():
        pytest.skip("Agent vault not configured")
    import uuid

    label = f"phase4-smoke-{uuid.uuid4().hex[:8]}"
    handle = create_credential("example.invalid", "saturn-test", label)
    assert handle.handle.startswith("Sites/")
    assert handle.status == "created"
