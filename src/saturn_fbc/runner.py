"""Run orchestration and last-run state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from saturn_fbc import config
from saturn_fbc.contract import StopReason, load_contract
from saturn_fbc.pig_stack import status_payload
from saturn_fbc.skeleton import run_skeleton
from saturn_fbc.visual.loop import RunResult, run_contract_path


STATE_FILE = config.PROJECT_ROOT / ".last-run.json"


@dataclass
class LastRun:
    trace_dir: str
    stop_reason: str
    steps: int
    message: str | None = None
    escalation_path: str | None = None
    contract_path: str | None = None


def _save_last_run(result: RunResult, *, contract_path: Path | None = None) -> None:
    payload = LastRun(
        trace_dir=str(result.trace_dir),
        stop_reason=result.stop_reason.value,
        steps=result.steps,
        message=result.message,
        escalation_path=str(result.escalation_path) if result.escalation_path else None,
        contract_path=str(contract_path) if contract_path else None,
    )
    STATE_FILE.write_text(json.dumps(asdict(payload), indent=2), encoding="utf-8")


def load_last_run() -> LastRun | None:
    if not STATE_FILE.is_file():
        return None
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return LastRun(**data)


def run_contract(
    contract_path: Path,
    *,
    headless: bool | None = None,
    skip_gpu: bool = False,
    mode: str = "visual",
) -> RunResult:
    if mode == "skeleton":
        trace_dir = run_skeleton(contract_path=contract_path, headless=headless)
        result = RunResult(
            trace_dir=trace_dir,
            stop_reason=StopReason.PRE_SUBMIT_BOUNDARY,
            steps=0,
            message="skeleton mode",
        )
    else:
        result = run_contract_path(
            contract_path,
            headless=headless,
            skip_gpu=skip_gpu,
        )
    _save_last_run(result, contract_path=contract_path)
    return result


def status() -> dict:
    from saturn_fbc.browser.daemon import browser_daemon_status

    payload = status_payload()
    last = load_last_run()
    payload["last_run"] = asdict(last) if last else None
    payload["browser_daemon"] = browser_daemon_status()
    return payload
