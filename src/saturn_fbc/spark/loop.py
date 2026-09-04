"""Spark observe/act loop on fixtures and live contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from saturn_fbc.browser.capture import capture_a11y_indexed
from saturn_fbc.browser.interceptor import current_url_allowed
from saturn_fbc.browser.session import BrowserSession
from saturn_fbc.config import resolve_headless
from saturn_fbc.contract import AuthorityContract, StopReason, load_contract
from saturn_fbc.escalate import build_packet, dispatch_luna, write_escalation
from saturn_fbc.pig_stack import TenantState, acquire_tenant, release_tenant
from saturn_fbc.spark.client import SparkClient
from saturn_fbc.skeleton import next_type_action, remaining_task_fields
from saturn_fbc.verify import check_success, verify_step


@dataclass
class RunResult:
    trace_dir: Path
    stop_reason: StopReason
    steps: int
    message: str | None = None
    escalation_path: Path | None = None


def run_spark_loop(
    contract: AuthorityContract,
    *,
    headless: bool | None = None,
    skip_gpu: bool = False,
    dry_run_spark: bool = False,
    max_retries_per_step: int = 1,
) -> RunResult:
    headless = resolve_headless(headless)

    tenant: TenantState | None = None
    if not skip_gpu:
        tenant = acquire_tenant()

    client = SparkClient()
    step_records = []
    recent_action_sigs: list[str] = []
    stop_reason = StopReason.MAX_STEPS
    message: str | None = None
    escalation_path: Path | None = None

    try:
        with BrowserSession(contract, headless=headless) as session:
            page = session.page
            assert page is not None
            if contract.start_url:
                page.goto(contract.start_url, wait_until="domcontentloaded")

            for step_num in range(1, contract.max_steps + 1):
                if not current_url_allowed(contract, page.url):
                    stop_reason = StopReason.DOMAIN_CHANGE
                    message = f"URL left allowlist: {page.url}"
                    session.stop(stop_reason, message=message)
                    break

                snap = capture_a11y_indexed(page)
                observe = session.observe()
                step_records.append(observe)

                verification = verify_step(
                    contract,
                    page,
                    step_count=step_num,
                    recent_actions=recent_action_sigs,
                )
                if verification.stop_reason == StopReason.CAPTCHA:
                    stop_reason = StopReason.CAPTCHA
                    message = "Captcha detected"
                    session.stop(stop_reason, message=message)
                    break

                if verification.stop_reason == StopReason.MAX_STEPS:
                    stop_reason = StopReason.MAX_STEPS
                    message = "Step budget exhausted"
                    session.stop(stop_reason, message=message)
                    break

                if verification.stop_reason == StopReason.ESCALATE:
                    packet = build_packet(
                        contract,
                        url=page.url,
                        failed_checks=verification.failed_checks,
                        steps=step_records,
                        a11y_snippet=snap.digest,
                        screenshot_path=observe.screenshot_path,
                        message="Loop detector triggered escalation",
                    )
                    escalation_path = write_escalation(session.trace.trace_dir, packet)
                    stop_reason = StopReason.ESCALATE
                    message = verification.failed_checks[0]
                    session.stop(stop_reason, message=message)
                    break

                success = check_success(contract, page)
                if success.ok and contract.success_checks and step_num >= 1:
                    stop_reason = StopReason.SUCCESS
                    message = "Success checks satisfied"
                    session.stop(stop_reason, message=message)
                    break

                if dry_run_spark:
                    stop_reason = StopReason.PRE_SUBMIT_BOUNDARY
                    message = "dry_run_spark: observation only"
                    session.stop(stop_reason, message=message)
                    break

                remaining = remaining_task_fields(page, contract, snap)

                spark = client.propose_action(
                    contract,
                    digest=snap.digest,
                    url=page.url,
                    last_steps=recent_action_sigs,
                    remaining_fields=remaining or None,
                )
                if spark.action is None:
                    if max_retries_per_step <= 0:
                        packet = build_packet(
                            contract,
                            url=page.url,
                            failed_checks=[f"Spark parse error: {spark.parse_error}"],
                            steps=step_records,
                            a11y_snippet=snap.digest,
                            screenshot_path=observe.screenshot_path,
                            message="Spark returned invalid JSON",
                        )
                        escalation_path = write_escalation(session.trace.trace_dir, packet)
                        stop_reason = StopReason.ESCALATE
                        message = spark.parse_error
                        session.stop(stop_reason, message=message)
                        break
                    max_retries_per_step -= 1
                    continue

                action = spark.action
                if remaining and action.type in {"scroll", "wait"}:
                    fallback = next_type_action(contract, snap, remaining)
                    if fallback is not None:
                        action = fallback
                record = session.act(action)
                step_records.append(record)
                sig = f"{action.type}:{action.index}:{action.text or action.url}"
                recent_action_sigs.append(sig)

                if record.error:
                    packet = build_packet(
                        contract,
                        url=page.url,
                        failed_checks=[record.error],
                        steps=step_records,
                        a11y_snippet=snap.digest,
                        screenshot_path=observe.screenshot_path,
                        message="Playwright action failed",
                    )
                    escalation_path = write_escalation(session.trace.trace_dir, packet)
                    stop_reason = StopReason.ESCALATE
                    message = record.error
                    session.stop(stop_reason, message=message)
                    break

            else:
                stop_reason = StopReason.MAX_STEPS
                message = "Step budget exhausted"
                session.stop(stop_reason, message=message)

            return RunResult(
                trace_dir=session.trace.trace_dir,
                stop_reason=stop_reason,
                steps=len(step_records),
                message=message,
                escalation_path=escalation_path,
            )
    finally:
        if tenant is not None:
            release_tenant(tenant)


def run_contract_path(
    path: Path | str,
    *,
    headless: bool | None = None,
    skip_gpu: bool = False,
    dry_run_spark: bool = False,
) -> RunResult:
    contract = load_contract(path)
    return run_spark_loop(
        contract,
        headless=headless,
        skip_gpu=skip_gpu,
        dry_run_spark=dry_run_spark,
    )
