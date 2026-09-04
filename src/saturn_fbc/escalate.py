"""Compact escalation packets for Luna / saturn-agent-dispatch."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from saturn_fbc.contract import AuthorityContract, StepRecord


@dataclass
class EscalationPacket:
    contract_task_id: str
    url: str
    failed_checks: list[str]
    last_actions: list[str]
    a11y_snippet: str
    screenshot_path: str | None
    message: str

    def to_prompt(self) -> str:
        return (
            f"Browser task {self.contract_task_id} needs frontier help.\n"
            f"URL: {self.url}\n"
            f"Failed checks: {', '.join(self.failed_checks) or '(none)'}\n"
            f"Recent actions: {', '.join(self.last_actions) or '(none)'}\n"
            f"A11y snippet:\n{self.a11y_snippet}\n"
            f"Screenshot: {self.screenshot_path or '(none)'}\n"
            f"Context: {self.message}\n"
            "Suggest the next bounded browser subgoal or policy adjustment. Do not propose submit."
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "contract_task_id": self.contract_task_id,
                "url": self.url,
                "failed_checks": self.failed_checks,
                "last_actions": self.last_actions,
                "a11y_snippet": self.a11y_snippet,
                "screenshot_path": self.screenshot_path,
                "message": self.message,
            },
            indent=2,
        )


def build_packet(
    contract: AuthorityContract,
    *,
    url: str,
    failed_checks: list[str],
    steps: list[StepRecord],
    a11y_snippet: str,
    screenshot_path: str | None,
    message: str,
) -> EscalationPacket:
    actions = []
    for step in steps[-5:]:
        if step.action:
            actions.append(f"{step.action.type} idx={step.action.index}")
        elif step.result:
            actions.append(step.result)
    return EscalationPacket(
        contract_task_id=contract.task_id,
        url=url,
        failed_checks=failed_checks,
        last_actions=actions,
        a11y_snippet=a11y_snippet[:2000],
        screenshot_path=screenshot_path,
        message=message,
    )


def dispatch_luna(packet: EscalationPacket, *, dry_run: bool = False) -> str:
    if dry_run:
        return packet.to_prompt()
    cmd = [
        "saturn-agent-dispatch",
        "ask",
        "--model",
        "gpt-5.6-luna",
        packet.to_prompt(),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        if result.returncode == 0:
            return result.stdout.strip()
        return f"dispatch failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
    except FileNotFoundError:
        return packet.to_prompt()
    except subprocess.TimeoutExpired:
        return "dispatch timed out"


def write_escalation(trace_dir: Path, packet: EscalationPacket) -> Path:
    path = trace_dir / "escalation.json"
    path.write_text(packet.to_json(), encoding="utf-8")
    return path
