"""KeePassXC Agent vault access for the privileged broker."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from saturn_agent_browser import config

DEFAULT_KDBX = Path("~/keepass/Agent.kdbx")
DEFAULT_KEY_FILE = Path.home() / ".config" / "saturn-agent-browser" / "agent-vault.key"
SITES_GROUP = "Sites"


def agent_kdbx_path() -> Path:
    raw = config.get("AGENT_KDBX")
    return Path(raw) if raw else DEFAULT_KDBX


def vault_key_file() -> Path:
    raw = config.get("AGENT_VAULT_KEY_FILE")
    return Path(raw) if raw else DEFAULT_KEY_FILE


def vault_ready() -> bool:
    return agent_kdbx_path().is_file() and vault_key_file().is_file()


def read_master_password() -> str:
    path = vault_key_file()
    if not path.is_file():
        raise RuntimeError(f"Agent vault key file missing: {path}")
    password = path.read_text(encoding="utf-8").strip()
    if not password:
        raise RuntimeError(f"Agent vault key file is empty: {path}")
    return password


def _run_cli(args: list[str], *, password: str, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["keepassxc-cli"]
    if quiet and args:
        cmd.extend([args[0], "-q", *args[1:]])
    else:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        input=f"{password}\n",
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass(frozen=True)
class CredentialRecord:
    handle: str
    username: str
    password: str
    url: str | None = None


def entry_path(domain: str, username: str, label: str) -> str:
    safe_label = label.replace(" ", "-")
    safe_domain = domain.replace("/", "-")
    safe_user = username.replace("/", "-")
    return f"{SITES_GROUP}/{safe_domain}--{safe_user}--{safe_label}"


def ensure_sites_group() -> None:
    password = read_master_password()
    kdbx = agent_kdbx_path()
    result = _run_cli(["mkdir", str(kdbx), SITES_GROUP], password=password)
    if result.returncode != 0 and "exists" not in (result.stderr + result.stdout).lower():
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "mkdir Sites failed")


def create_entry(domain: str, username: str, label: str, *, length: int = 24) -> CredentialRecord:
    if not vault_ready():
        raise RuntimeError(f"Agent vault not ready: {agent_kdbx_path()} + {vault_key_file()}")
    ensure_sites_group()
    password = read_master_password()
    kdbx = agent_kdbx_path()
    path = entry_path(domain, username, label)
    result = _run_cli(
        [
            "add",
            str(kdbx),
            path,
            "-u",
            username,
            "--url",
            f"https://{domain}",
            "--generate",
            "-L",
            str(length),
            "-l",
            "-U",
            "-n",
            "-s",
        ],
        password=password,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "keepassxc-cli add failed")
    record = load_entry(path)
    return CredentialRecord(handle=path, username=record.username, password=record.password, url=record.url)


def create_entry_with_password(
    domain: str,
    username: str,
    label: str,
    entry_password: str,
    *,
    url: str | None = None,
) -> CredentialRecord:
    """Create a vault entry with a known password (disposable fixture vaults)."""
    if not vault_ready():
        raise RuntimeError(f"Agent vault not ready: {agent_kdbx_path()} + {vault_key_file()}")
    if not entry_password:
        raise RuntimeError("entry password required")
    ensure_sites_group()
    master = read_master_password()
    kdbx = agent_kdbx_path()
    path = entry_path(domain, username, label)
    target_url = url or f"https://{domain}"
    result = subprocess.run(
        [
            "keepassxc-cli",
            "add",
            "-q",
            "-p",
            "-u",
            username,
            "--url",
            target_url,
            str(kdbx),
            path,
        ],
        input=f"{master}\n{entry_password}\n{entry_password}\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "keepassxc-cli add failed")
    record = load_entry(path)
    return CredentialRecord(handle=path, username=record.username, password=record.password, url=record.url)


def load_entry(handle: str) -> CredentialRecord:
    password = read_master_password()
    kdbx = agent_kdbx_path()
    result = _run_cli(
        ["show", "-a", "Password", "-a", "UserName", "-a", "URL", str(kdbx), handle],
        password=password,
        quiet=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"entry not found: {handle}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"unexpected keepassxc-cli show output for {handle}")
    entry_password, username = lines[0], lines[1]
    url = lines[2] if len(lines) > 2 else None
    return CredentialRecord(handle=handle, username=username, password=entry_password, url=url)


def setup_status() -> dict:
    kdbx = agent_kdbx_path()
    key_file = vault_key_file()
    return {
        "agent_kdbx": str(kdbx),
        "agent_kdbx_exists": kdbx.is_file(),
        "vault_key_file": str(key_file),
        "vault_key_file_exists": key_file.is_file(),
        "vault_ready": vault_ready(),
        "keepassxc_cli": _which("keepassxc-cli"),
        "needs_you": _needs_you(kdbx, key_file),
    }


def _which(name: str) -> str | None:
    from shutil import which

    path = which(name)
    return path


def _needs_you(kdbx: Path, key_file: Path) -> list[str]:
    steps: list[str] = []
    if not kdbx.is_file() or not key_file.is_file():
        steps.append("Run: ./scripts/setup-keepass-agent-vault.sh")
    if vault_ready():
        steps.append("Back up ~/.config/saturn-agent-browser/agent-vault.key (Agent vault master password)")
        steps.append("Optional: keepassxc & → open Agent.kdbx → verify Sites group; change master password if you want")
    steps.append("Do not put Personal.kdbx or its password in agent paths")
    return steps
