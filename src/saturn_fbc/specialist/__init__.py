"""Visual specialist — local VLM (UI-Venus 2) for screenshot → browser action."""

from __future__ import annotations

from saturn_fbc.specialist.client import (
    VisualSpecialistClient,
    VisualSpecialistResponse,
    specialist_configured,
)


class SpecialistNotConfiguredError(RuntimeError):
    pass


def propose_visual_action() -> dict:
    """Health probe for CLI specialist-status."""
    if not specialist_configured():
        raise SpecialistNotConfiguredError(
            "Visual specialist not ready. Switch pig-stack to saturn-frontier-browser-control "
            "(UI-Venus 2 9B Q4_K_M on :8091)."
        )
    from saturn_fbc.pig_stack import health_json

    return {"configured": True, **health_json()}


__all__ = [
    "SpecialistNotConfiguredError",
    "VisualSpecialistClient",
    "VisualSpecialistResponse",
    "propose_visual_action",
    "specialist_configured",
]
