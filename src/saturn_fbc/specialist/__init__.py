"""Visual/browse-trained specialist slot (Phase 6 — not loaded in V1)."""

from __future__ import annotations


class SpecialistNotConfiguredError(RuntimeError):
    pass


def propose_visual_action(*args, **kwargs):
    raise SpecialistNotConfiguredError(
        "Visual specialist slot is open. Configure Fara1.5-4B or similar in Phase 6."
    )
