"""Phase 6: visual specialist health probe."""

from __future__ import annotations

import pytest

from saturn_fbc.specialist import SpecialistNotConfiguredError, propose_visual_action


def test_specialist_not_configured(monkeypatch):
    monkeypatch.setattr(
        "saturn_fbc.specialist.specialist_configured",
        lambda: False,
    )
    with pytest.raises(SpecialistNotConfiguredError):
        propose_visual_action()


def test_specialist_configured(monkeypatch):
    monkeypatch.setattr(
        "saturn_fbc.specialist.specialist_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "saturn_fbc.pig_stack.health_json",
        lambda: {"model_id": "ui-venus-2-9b-q4km-local"},
    )
    payload = propose_visual_action()
    assert payload["configured"] is True
