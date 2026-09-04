"""Load configuration from project config/*.env files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_env_files() -> dict[str, str]:
    merged: dict[str, str] = {}
    if not CONFIG_DIR.is_dir():
        return merged
    for path in sorted(CONFIG_DIR.glob("*.env")):
        for key, value in dotenv_values(path).items():
            if value is not None:
                merged[key] = value
    return merged


def _expand_config_paths() -> None:
    """Resolve ${HOME} / ${SATURN_FBC_SHARE} after merging env files."""
    share = os.environ.get("SATURN_FBC_SHARE")
    if share:
        os.environ["SATURN_FBC_SHARE"] = os.path.expandvars(os.path.expanduser(share))
    for key in ("SATURN_FBC_CHROMIUM_USER_DATA", "PLAYWRIGHT_BROWSERS_PATH"):
        val = os.environ.get(key)
        if val:
            os.environ[key] = os.path.expandvars(val)


@lru_cache(maxsize=1)
def load_config() -> dict[str, str]:
    """Merge config/*.env and apply to os.environ (without overriding existing)."""
    merged = _load_env_files()
    for key, value in merged.items():
        os.environ.setdefault(key, value)
    _expand_config_paths()
    return dict(os.environ)


def get(key: str, default: str | None = None) -> str | None:
    load_config()
    return os.environ.get(key, default)


def require(key: str) -> str:
    value = get(key)
    if value is None:
        raise RuntimeError(f"Required config key missing: {key}")
    return value


def share_dir() -> Path:
    return Path(require("SATURN_FBC_SHARE"))


def chromium_user_data_dir() -> Path:
    return Path(require("SATURN_FBC_CHROMIUM_USER_DATA"))


def playwright_browsers_path() -> Path:
    return Path(require("PLAYWRIGHT_BROWSERS_PATH"))


def wm_class_name() -> str:
    return require("SATURN_FBC_NAME")


def browser_mode() -> str:
    """``daemon`` (attach to persistent browser) or ``ephemeral`` (launch-close)."""
    load_config()
    mode = (os.environ.get("SATURN_FBC_BROWSER_MODE", "daemon") or "daemon").lower()
    if mode not in ("daemon", "ephemeral"):
        return "daemon"
    return mode


def cdp_port() -> int:
    load_config()
    raw = os.environ.get("SATURN_FBC_CDP_PORT", "9222") or "9222"
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 9222


def cdp_url() -> str:
    return f"http://127.0.0.1:{cdp_port()}"


def browser_state_path() -> Path:
    return share_dir() / "browser-state.json"


def observation_mode() -> str:
    return get("OBSERVATION_MODE", "a11y_indexed") or "a11y_indexed"


def default_headless() -> bool:
    """True when SATURN_FBC_HEADLESS requests headless mode."""
    load_config()
    return (os.environ.get("SATURN_FBC_HEADLESS", "0") or "0").lower() in ("1", "true", "yes")


def resolve_headless(headless: bool | None) -> bool:
    """CLI/script explicit flag wins; else config/browser.env default."""
    if headless is not None:
        return headless
    return default_headless()


def headed_hold_seconds() -> int:
    load_config()
    raw = os.environ.get("SATURN_FBC_HOLD_SECONDS", "3") or "3"
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def traces_dir() -> Path:
    return PROJECT_ROOT / "traces"
