"""Scripted skeleton fill (no model) for Phase 1."""

from __future__ import annotations

from pathlib import Path

from saturn_fbc.browser.capture import capture_a11y_indexed
from saturn_fbc.browser.session import BrowserSession
from saturn_fbc.config import resolve_headless
from saturn_fbc.contract import AuthorityContract, BrowserAction, StopReason, load_contract
from saturn_fbc.verify import _field_value


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = PROJECT_ROOT / "contracts" / "local-form.json"
DEFAULT_FIXTURE = PROJECT_ROOT / "fixtures" / "local-form.html"


def fixture_url(path: Path | None = None) -> str:
    target = (path or DEFAULT_FIXTURE).resolve()
    return target.as_uri()


def _find_index_by_hint(snapshot, *hints: str) -> int | None:
    hints_lower = [h.lower() for h in hints]
    for node in snapshot.nodes:
        blob = f"{node.get('role', '')} {node.get('name', '')}".lower()
        if any(h in blob for h in hints_lower):
            return int(node["index"])
    return None


def _find_index_for_field(snapshot, field_name: str) -> int | None:
    target = field_name.lower()
    for node in snapshot.nodes:
        name = str(node.get("name", "")).lower()
        role = str(node.get("role", "")).lower()
        if target in name or name == target:
            if role in ("textbox", "textarea", "input", "combobox", "searchbox") or "text" in role:
                return int(node["index"])
    return _find_index_by_hint(snapshot, field_name)


def remaining_task_fields(page, contract: AuthorityContract, snapshot) -> dict[str, str]:
    remaining: dict[str, str] = {}
    for key, value in contract.task_data.items():
        actual = _field_value(page, key)
        if not (actual or "").strip():
            remaining[key] = str(value)
    return remaining


def next_type_action(contract: AuthorityContract, snapshot, remaining: dict[str, str]) -> BrowserAction | None:
    for key, value in remaining.items():
        idx = _find_index_for_field(snapshot, key)
        if idx is not None:
            return BrowserAction(type="type", index=idx, text=value)
    return None


def build_fill_plan(contract: AuthorityContract, snapshot) -> list[BrowserAction]:
    remaining = {key: str(value) for key, value in contract.task_data.items() if value}
    plan: list[BrowserAction] = []
    while remaining:
        action = next_type_action(contract, snapshot, remaining)
        if action is None:
            break
        plan.append(action)
        for key in list(remaining):
            if _find_index_for_field(snapshot, key) == action.index:
                remaining.pop(key)
                break
    return plan


def run_skeleton(
    *,
    contract_path: Path | str | None = None,
    fixture_path: Path | None = None,
    headless: bool | None = None,
) -> Path:
    """Open fixture, fill fields, stop before submit, return trace dir."""
    contract = load_contract(contract_path or DEFAULT_CONTRACT)
    url = contract.start_url or fixture_url(fixture_path)

    headless = resolve_headless(headless)

    with BrowserSession(contract, headless=headless) as session:
        page = session.page
        assert page is not None
        page.goto(url, wait_until="domcontentloaded")

        snap = capture_a11y_indexed(page)
        session.observe()

        for action in build_fill_plan(contract, snap):
            session.act(action)
            snap = capture_a11y_indexed(page)

        session.stop(
            StopReason.PRE_SUBMIT_BOUNDARY,
            message="Stopped before Submit per contract policy",
        )

        return session.trace.trace_dir
