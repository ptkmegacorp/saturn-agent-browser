"""Saturn Agent Browser CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from saturn_agent_browser import __version__
from saturn_agent_browser.broker import broker_status, create_credential
from saturn_agent_browser.browser.daemon import (
    browser_daemon_status,
    ensure_daemon_for_headed_run,
    restart_browser,
    start_browser,
    stop_browser,
)
from saturn_agent_browser.browser.trusted import (
    list_browser_profiles,
    start_trusted,
    stop_trusted,
    trusted_status,
)
from saturn_agent_browser.browser import leases
from saturn_agent_browser.browser import sensitive
from saturn_agent_browser.browser import verifications
from saturn_agent_browser.browser.view import capture_snapshot, navigate_tab, read_view, set_panel_control
from saturn_agent_browser.config import load_config
from saturn_agent_browser.contract import load_contract
from saturn_agent_browser.escalate import dispatch_luna
from saturn_agent_browser.runner import load_last_run, run_contract, status
from saturn_agent_browser.skeleton import run_skeleton
from saturn_agent_browser.specialist import SpecialistNotConfiguredError, propose_visual_action

app = typer.Typer(no_args_is_help=True, help="Saturn Agent Browser")
browser_app = typer.Typer(no_args_is_help=True, help="Persistent headed Chromium daemon")
trusted_app = typer.Typer(no_args_is_help=True, help="Trusted Google Chrome lane (CDP :9223 for Pi snapshots)")
app.add_typer(browser_app, name="browser")
browser_app.add_typer(trusted_app, name="trusted")


@app.callback()
def _load_env() -> None:
    load_config()


def _json_out(payload: dict | list) -> None:
    typer.echo(json.dumps(payload, indent=2))


@browser_app.command("start")
def browser_start_cmd(
    wait_timeout: float = typer.Option(30.0, help="Seconds to wait for CDP health"),
) -> None:
    _json_out(start_browser(wait_timeout=wait_timeout))


@browser_app.command("stop")
def browser_stop_cmd() -> None:
    _json_out(stop_browser())


@browser_app.command("status")
def browser_status_cmd() -> None:
    _json_out(browser_daemon_status())


@browser_app.command("restart")
def browser_restart_cmd(
    wait_timeout: float = typer.Option(30.0, help="Seconds to wait for CDP health after restart"),
) -> None:
    _json_out(restart_browser(wait_timeout=wait_timeout))


@browser_app.command("profiles")
def browser_profiles_cmd() -> None:
    _json_out(list_browser_profiles())


@trusted_app.command("status")
def trusted_status_cmd() -> None:
    _json_out(trusted_status())


@trusted_app.command("start")
def trusted_start_cmd(
    url: str = typer.Option("chrome://newtab/", "--url", help="Initial tab (no javascript: URLs)"),
) -> None:
    if url.strip().lower().startswith("javascript:"):
        _json_out({"ok": False, "error": "invalid_url"})
        raise typer.Exit(code=1)
    result = start_trusted(url=url)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@trusted_app.command("stop")
def trusted_stop_cmd() -> None:
    _json_out(stop_trusted())


@browser_app.command("view")
def browser_view_cmd(
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    """Read-only tabs/status for the Saturn Pi snapshot panel."""
    _json_out(read_view(lane))


@browser_app.command("snapshot")
def browser_snapshot_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    out: Path = typer.Option(..., "--out", help="PNG destination path"),
    generation: str | None = typer.Option(
        None, "--generation", help="Expected document_generation from browser view"
    ),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    result = capture_snapshot(tab_id, expected_generation=generation, lane=lane)
    if not result.get("ok"):
        _json_out({k: v for k, v in result.items() if k != "png"})
        raise typer.Exit(code=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result["png"])
    _json_out(
        {
            "ok": True,
            "path": str(out),
            "tab_id": result["tab_id"],
            "document_generation": result["document_generation"],
            "url": result["url"],
            "title": result["title"],
        }
    )


@browser_app.command("control")
def browser_control_cmd(
    mode: str = typer.Option(..., "--mode", help="human or agent"),
) -> None:
    result = set_panel_control(mode)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("navigate")
def browser_navigate_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    url: str = typer.Option(..., "--url", help="http(s) URL on the panel allowlist"),
    generation: str = typer.Option(..., "--generation", help="Expected document_generation"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    result = navigate_tab(tab_id, url, generation, lane=lane)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("lease-acquire")
def browser_lease_acquire_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    operator: str = typer.Option("saturn-pi-operator", "--operator", help="Human operator login"),
    run_id: str | None = typer.Option(None, "--run-id", help="Bound task/run id"),
    generation: str | None = typer.Option(None, "--generation", help="Bound document_generation"),
    ttl: int = typer.Option(300, "--ttl", help="Lease seconds (30-3600)"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    result = leases.acquire(
        lane=lane, tab_id=tab_id, operator=operator, run_id=run_id,
        document_generation=generation, ttl_sec=ttl,
    )
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("lease-release")
def browser_lease_release_cmd(
    lease_id: str = typer.Option(..., "--lease-id", help="Lease id from lease-acquire"),
) -> None:
    result = leases.release(lease_id=lease_id)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("lease-list")
def browser_lease_list_cmd(
    lane: str | None = typer.Option(None, "--lane", help="Filter by lane"),
) -> None:
    _json_out({"ok": True, "leases": leases.list_active(lane=lane)})


@browser_app.command("sensitive-mark")
def browser_sensitive_mark_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
    reason: str = typer.Option("credential_entry", "--reason", help="Why the target is sensitive"),
) -> None:
    result = sensitive.mark(lane=lane, tab_id=tab_id, reason=reason)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("sensitive-clear")
def browser_sensitive_clear_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    _json_out(sensitive.clear(lane=lane, tab_id=tab_id))


@browser_app.command("verification-request")
def browser_verification_request_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    generation: str = typer.Option(..., "--generation", help="Live document_generation"),
    reason: str = typer.Option(..., "--reason", help="Blocker: login, mfa, consent, challenge"),
    task_id: str | None = typer.Option(None, "--task-id", help="Requesting task id"),
    run_id: str | None = typer.Option(None, "--run-id", help="Bound run id"),
    expects: str | None = typer.Option(None, "--expects", help="Expected completion condition"),
    auth_request_id: str | None = typer.Option(None, "--auth-request-id", help="Linked Saturn Auth request"),
    ttl: int = typer.Option(300, "--ttl", help="Handoff seconds (60-3600)"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    result = verifications.request(
        lane=lane, tab_id=tab_id, document_generation=generation, reason=reason,
        task_id=task_id, run_id=run_id, expects=expects,
        auth_request_id=auth_request_id, ttl_sec=ttl,
    )
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("verification-list")
def browser_verification_list_cmd(
    state: str = typer.Option("pending", "--state", help="pending or all"),
    lane: str | None = typer.Option(None, "--lane", help="Filter by lane"),
    sync: bool = typer.Option(False, "--sync", help="Revalidate against the live view first"),
) -> None:
    _json_out(verifications.list_handoffs(state=state, lane=lane, sync=sync))


@browser_app.command("verification-sync")
def browser_verification_sync_cmd(
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    _json_out(verifications.sync_lane(lane=lane))


@browser_app.command("verification-resolve")
def browser_verification_resolve_cmd(
    handoff_id: str = typer.Option(..., "--handoff-id", help="Handoff id from verification-request"),
    decision: str = typer.Option(..., "--decision", help="done or cancelled"),
    note: str | None = typer.Option(None, "--note", help="Short resolution note"),
) -> None:
    result = verifications.resolve(handoff_id=handoff_id, decision=decision, note=note)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("tap")
def browser_tap_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    x: float = typer.Option(..., "--x", help="Remote CSS pixel x"),
    y: float = typer.Option(..., "--y", help="Remote CSS pixel y"),
    generation: str = typer.Option(..., "--generation", help="Live document_generation"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    from saturn_agent_browser.browser import interact

    result = interact.tap(tab_id, x, y, generation, lane=lane)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@browser_app.command("scroll")
def browser_scroll_cmd(
    tab_id: str = typer.Option(..., "--tab-id", help="Exact tab id from browser view"),
    direction: str = typer.Option("down", "--direction", help="up or down"),
    amount: int = typer.Option(400, "--amount", help="Pixels (50-4000)"),
    generation: str = typer.Option(..., "--generation", help="Live document_generation"),
    lane: str = typer.Option("isolated", "--lane", help="isolated or trusted"),
) -> None:
    from saturn_agent_browser.browser import interact

    result = interact.scroll(tab_id, direction, generation, amount, lane=lane)
    _json_out(result)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@app.command("version")
def version_cmd() -> None:
    typer.echo(__version__)


@app.command("status")
def status_cmd() -> None:
    _json_out(status())


@app.command("validate-contract")
def validate_contract_cmd(path: Path) -> None:
    contract = load_contract(path)
    _json_out({"ok": True, "task_id": contract.task_id, "mode": contract.mode.value})


@app.command("run-skeleton")
def run_skeleton_cmd(
    contract: Path | None = typer.Option(None, help="Authority contract JSON"),
    headless: bool = typer.Option(False, "--headless", help="Headless Chromium (default: headed on HDMI)"),
) -> None:
    ensure_daemon_for_headed_run(headless)
    trace_dir = run_skeleton(contract_path=contract, headless=headless)
    _json_out({"trace_dir": str(trace_dir), "mode": "skeleton"})


@app.command("run")
def run_cmd(
    contract: Path = typer.Option(..., "--contract", help="Authority contract JSON"),
    headless: bool = typer.Option(False, "--headless", help="Headless Chromium (default: headed on HDMI)"),
    skip_gpu: bool = typer.Option(False, help="Deprecated no-op (GPU tenant removed 2026-09-12)"),
    skeleton: bool = typer.Option(False, help="Scripted skeleton instead of visual specialist loop"),
) -> None:
    ensure_daemon_for_headed_run(headless)
    mode = "skeleton" if skeleton else "visual"
    result = run_contract(
        contract,
        headless=headless,
        skip_gpu=skip_gpu,
        mode=mode,
    )
    _json_out(
        {
            "trace_dir": str(result.trace_dir),
            "stop_reason": result.stop_reason.value,
            "steps": result.steps,
            "message": result.message,
            "escalation_path": str(result.escalation_path) if result.escalation_path else None,
            "credential_handle": result.credential_handle,
            "mode": mode,
        }
    )


@app.command("wait")
def wait_cmd() -> None:
    last = load_last_run()
    if not last:
        _json_out({"status": "idle"})
        return
    _json_out({"status": "done", "last_run": last.__dict__})


@app.command("last")
def last_cmd() -> None:
    last = load_last_run()
    if not last:
        typer.echo("{}", nl=False)
        return
    _json_out(last.__dict__)


@app.command("abort")
def abort_cmd() -> None:
    _json_out({"aborted": True, "note": "Runs are process-local; abort clears no remote state yet."})


@app.command("escalate-last")
def escalate_last_cmd(
    dry_run: bool = typer.Option(True, help="Print packet only unless --no-dry-run"),
    no_dry_run: bool = typer.Option(False, "--no-dry-run"),
) -> None:
    last = load_last_run()
    if not last or not last.escalation_path:
        raise typer.Exit(code=1)
    path = Path(last.escalation_path)
    if not path.is_file():
        raise typer.Exit(code=1)
    packet_data = json.loads(path.read_text(encoding="utf-8"))
    from saturn_agent_browser.escalate import EscalationPacket

    packet = EscalationPacket(**packet_data)
    response = dispatch_luna(packet, dry_run=dry_run and not no_dry_run)
    _json_out({"packet": packet_data, "response": response})


@app.command("broker-status")
def broker_status_cmd() -> None:
    _json_out(broker_status())


@app.command("broker-setup")
def broker_setup_cmd() -> None:
    """Print KeePass Agent vault setup checklist (run scripts/setup-keepass-agent-vault.sh first)."""
    from saturn_agent_browser.broker.vault import setup_status

    _json_out(setup_status())


@app.command("broker-create")
def broker_create_cmd(
    domain: str = typer.Option(..., "--domain", help="Site domain (e.g. greenhouse.io)"),
    username: str = typer.Option(..., "--username", help="Login email or username"),
    label: str = typer.Option(..., "--label", help="Human-readable label for this account"),
) -> None:
    """Create a KeePass Sites entry with a broker-generated password. Returns handle only."""
    handle = create_credential(domain, username, label)
    _json_out(
        {
            "handle": handle.handle,
            "domain": handle.domain,
            "username": handle.username,
            "status": handle.status,
        }
    )


@app.command("specialist-status")
def specialist_status_cmd() -> None:
    try:
        propose_visual_action()
    except SpecialistNotConfiguredError as exc:
        _json_out({"configured": False, "message": str(exc)})


if __name__ == "__main__":
    app()
