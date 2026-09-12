"""Visual specialist — local VLM (UI-Venus 2) for screenshot → browser action.

Reserved for a future local visual specialist; see models/potential-models/ui-venus-2-official-pipeline.md.
"""

from __future__ import annotations

from saturn_agent_browser.specialist.client import (
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
            "Visual specialist not configured (reserved for a future local visual "
            "specialist; see models/potential-models/ui-venus-2-official-pipeline.md)."
        )
    from saturn_agent_browser.pig_stack import health_json

    return {"configured": True, **health_json()}


__all__ = [
    "SpecialistNotConfiguredError",
    "VisualSpecialistClient",
    "VisualSpecialistResponse",
    "propose_visual_action",
    "specialist_configured",
]
