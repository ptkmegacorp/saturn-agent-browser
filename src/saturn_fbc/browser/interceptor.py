"""Navigation allowlist and submit/send interception."""

from __future__ import annotations

from urllib.parse import urlparse

from saturn_fbc.actions import ActionRejectedError, is_submit_like, validate_action
from saturn_fbc.contract import AuthorityContract, BrowserAction


def _host_allowed(host: str, allowlist: list[str]) -> bool:
    host = host.lower().removeprefix("www.")
    for entry in allowlist:
        entry = entry.lower().removeprefix("www.")
        if host == entry or host.endswith(f".{entry}"):
            return True
    return False


def validate_navigate(contract: AuthorityContract, url: str) -> None:
    """Reject navigation targets outside origin_allowlist."""
    parsed = urlparse(url)
    if parsed.scheme in ("file", ""):
        return
    if parsed.scheme not in ("http", "https"):
        raise ActionRejectedError(f"Unsupported URL scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if not _host_allowed(host, contract.origin_allowlist):
        raise ActionRejectedError(
            f"Navigation to '{host}' is outside origin_allowlist",
        )


def intercept_action(contract: AuthorityContract, action: BrowserAction) -> BrowserAction:
    """Validate action against contract; block submit/send and off-allowlist navigate."""
    validated = validate_action(contract, action)

    if is_submit_like(validated):
        raise ActionRejectedError(
            f"Interceptor blocked submit-like action: {validated.type}",
            action=validated,
        )

    if validated.type == "navigate":
        if not validated.url:
            raise ActionRejectedError("navigate requires url", action=validated)
        validate_navigate(contract, validated.url)

    return validated


def current_url_allowed(contract: AuthorityContract, url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return True
    host = parsed.hostname or ""
    return _host_allowed(host, contract.origin_allowlist)
