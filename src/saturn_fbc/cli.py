"""Saturn frontier browser control CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from saturn_fbc import __version__
from saturn_fbc.broker import broker_status, create_credential
from saturn_fbc.browser.daemon import (
    browser_daemon_status,
    ensure_daemon_for_headed_run,
    restart_browser,
    start_browser,
    stop_browser,
)
from saturn_fbc.config import load_config
from saturn_fbc.contract import load_contract
from saturn_fbc.escalate import dispatch_luna
from saturn_fbc.runner import load_last_run, run_contract, status
from saturn_fbc.skeleton import run_skeleton
from saturn_fbc.specialist import SpecialistNotConfiguredError, propose_visual_action

app = typer.Typer(no_args_is_help=True, help="Saturn frontier browser control")
browser_app = typer.Typer(no_args_is_help=True, help="Persistent headed Chromium daemon")
app.add_typer(browser_app, name="browser")


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
    skip_gpu: bool = typer.Option(False, help="Do not switch pig-stack profile"),
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
    from saturn_fbc.escalate import EscalationPacket

    packet = EscalationPacket(**packet_data)
    response = dispatch_luna(packet, dry_run=dry_run and not no_dry_run)
    _json_out({"packet": packet_data, "response": response})


@app.command("broker-status")
def broker_status_cmd() -> None:
    _json_out(broker_status())


@app.command("broker-setup")
def broker_setup_cmd() -> None:
    """Print KeePass Agent vault setup checklist (run scripts/setup-keepass-agent-vault.sh first)."""
    from saturn_fbc.broker.vault import setup_status

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
