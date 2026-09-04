"""Validate browser actions against an authority contract."""

from __future__ import annotations

from saturn_fbc.contract import AuthorityContract, BrowserAction

SUBMIT_LIKE = frozenset({"submit", "send", "purchase", "upload_sensitive", "change_security_settings"})


class ActionRejectedError(Exception):
    """Raised when an action violates the authority contract."""

    def __init__(self, message: str, *, action: BrowserAction | None = None) -> None:
        super().__init__(message)
        self.action = action


def normalize_action_type(action_type: str) -> str:
    return action_type.strip().lower()


def validate_action(contract: AuthorityContract, action: BrowserAction) -> BrowserAction:
    """Ensure action type is allowed and not blocked."""
    action_type = normalize_action_type(action.type)

    if action_type in {normalize_action_type(b) for b in contract.blocked_actions}:
        raise ActionRejectedError(
            f"Action '{action_type}' is blocked by contract",
            action=action,
        )

    allowed = {normalize_action_type(a) for a in contract.allowed_actions}
    if action_type not in allowed:
        raise ActionRejectedError(
            f"Action '{action_type}' is not in allowed_actions",
            action=action,
        )

    if action_type in SUBMIT_LIKE:
        raise ActionRejectedError(
            f"Action '{action_type}' is submit-like and forbidden",
            action=action,
        )

    return action.model_copy(update={"type": action_type})


def is_submit_like(action: BrowserAction) -> bool:
    return normalize_action_type(action.type) in SUBMIT_LIKE
