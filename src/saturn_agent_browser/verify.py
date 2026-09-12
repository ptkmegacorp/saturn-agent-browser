"""Post-action verification and success checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from playwright.sync_api import Page

from saturn_agent_browser.contract import AuthorityContract, StopReason


@dataclass
class VerificationResult:
    ok: bool
    failed_checks: list[str] = field(default_factory=list)
    stop_reason: StopReason | None = None


def _field_value(page: Page, field_name: str) -> str | None:
    selectors = [
        f"input[name='{field_name}']",
        f"textarea[name='{field_name}']",
        f"#{field_name}",
        f"[name='{field_name}']",
    ]
    for sel in selectors:
        locator = page.locator(sel)
        if locator.count() > 0:
            try:
                return locator.first.input_value(timeout=1000)
            except Exception:
                return locator.first.inner_text(timeout=1000)
    return None


def detect_captcha(page: Page) -> bool:
    text = page.content().lower()
    markers = ("captcha", "recaptcha", "hcaptcha", "verify you are human", "bot detection")
    return any(m in text for m in markers)


def check_success(contract: AuthorityContract, page: Page) -> VerificationResult:
    failed: list[str] = []
    for check in contract.success_checks:
        lowered = check.lower()
        if "submit was not activated" in lowered:
            continue
        if "url still on" in lowered or "url on" in lowered:
            host_match = re.search(r"on\s+([\w.-]+)", lowered)
            if host_match:
                host = host_match.group(1)
                if host not in page.url.lower():
                    failed.append(check)
            continue
        if "visible value is" in lowered:
            m = re.match(r"(\w+)\s+visible value is\s+(.+)", lowered)
            if m:
                field, expected = m.group(1), m.group(2).strip()
                actual = _field_value(page, field)
                if (actual or "").strip().lower() != expected.lower():
                    failed.append(f"{check} (got {actual!r})")
            continue
        if "field filled" in lowered:
            field = lowered.split()[0]
            key_map = {
                "name": "name",
                "email": "email",
                "phone": "phone",
                "comments": "comments",
                "custname": "custname",
                "custtel": "custtel",
                "custemail": "custemail",
            }
            lookup = key_map.get(field, field)
            actual = _field_value(page, lookup)
            if not actual:
                failed.append(check)
            continue
    return VerificationResult(ok=not failed, failed_checks=failed)


def verify_step(
    contract: AuthorityContract,
    page: Page,
    *,
    step_count: int,
    recent_actions: list[str],
) -> VerificationResult:
    if detect_captcha(page):
        return VerificationResult(ok=False, failed_checks=["captcha detected"], stop_reason=StopReason.CAPTCHA)

    if step_count >= contract.max_steps:
        return VerificationResult(ok=False, failed_checks=["max_steps reached"], stop_reason=StopReason.MAX_STEPS)

    if len(recent_actions) >= 6 and len(set(recent_actions[-3:])) == 1:
        return VerificationResult(
            ok=False,
            failed_checks=["loop detector: repeated action"],
            stop_reason=StopReason.ESCALATE,
        )

    success = check_success(contract, page)
    if success.ok and contract.success_checks:
        success.stop_reason = StopReason.SUCCESS
    return success
