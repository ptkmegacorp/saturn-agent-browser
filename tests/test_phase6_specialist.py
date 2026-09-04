"""Phase 6: visual specialist slot stub."""

from __future__ import annotations

import pytest

from saturn_fbc.specialist import SpecialistNotConfiguredError, propose_visual_action


def test_specialist_not_configured():
    with pytest.raises(SpecialistNotConfiguredError):
        propose_visual_action()
