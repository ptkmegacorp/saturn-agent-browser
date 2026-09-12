"""Launch Playwright persistent context for this project's Chromium tenant."""

from __future__ import annotations

import os

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from saturn_agent_browser import config
from saturn_agent_browser.browser import state as browser_state

_DAEMON_START_HINT = (
    "Headed run requires the browser daemon. Start it with: "
    "saturn-agent-browser browser start"
)


def _chromium_args(*, include_cdp: bool = False) -> list[str]:
    wm_class = config.wm_class_name()
    args = [f"--class={wm_class}"]
    if include_cdp and os.environ.get("SATURN_AGENT_BROWSER_CDP_PORT"):
        args.append(f"--remote-debugging-port={config.cdp_port()}")
    return args


def launch_persistent_context(
    *,
    headless: bool = False,
    playwright: Playwright | None = None,
    remote_debugging_port: int | None = None,
) -> tuple[Playwright | None, BrowserContext]:
    """Open this project's isolated Chromium profile."""
    config.load_config()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(config.playwright_browsers_path())

    user_data = config.chromium_user_data_dir()
    user_data.mkdir(parents=True, exist_ok=True)

    if remote_debugging_port is not None:
        chromium_args = _chromium_args(include_cdp=False) + [
            f"--remote-debugging-port={remote_debugging_port}"
        ]
    else:
        chromium_args = _chromium_args(include_cdp=False)

    owns_playwright = playwright is None
    pw = playwright or sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(user_data),
        headless=headless,
        args=chromium_args,
        viewport={"width": 1280, "height": 720},
        accept_downloads=False,
    )
    return (pw if owns_playwright else None), context


def launch_daemon_context(
    *,
    headless: bool = False,
    playwright: Playwright | None = None,
) -> tuple[Playwright | None, BrowserContext]:
    """Open isolated Chromium with CDP enabled for the persistent daemon."""
    config.load_config()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(config.playwright_browsers_path())

    user_data = config.chromium_user_data_dir()
    user_data.mkdir(parents=True, exist_ok=True)

    owns_playwright = playwright is None
    pw = playwright or sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(user_data),
        headless=headless,
        args=_chromium_args(include_cdp=True),
        viewport={"width": 1280, "height": 720},
        accept_downloads=False,
    )
    return (pw if owns_playwright else None), context


def connect_over_cdp(cdp_url: str) -> tuple[Playwright | None, BrowserContext, bool]:
    """Attach Playwright to a running Chromium CDP endpoint (does not own the browser)."""
    config.load_config()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(config.playwright_browsers_path())

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url, is_local=True)
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError(f"CDP browser at {cdp_url} has no browser contexts")
    return pw, contexts[0], True


def acquire_browser_context(
    *,
    headless: bool,
    prefer_daemon: bool = True,
) -> tuple[Playwright | None, BrowserContext, bool]:
    """Launch ephemeral Chromium or attach to the headed browser daemon."""
    config.load_config()
    mode = config.browser_mode()

    if headless or mode == "ephemeral":
        pw, context = launch_persistent_context(headless=headless)
        return pw, context, False

    if browser_state.daemon_running():
        cdp_url = browser_state.read_cdp_url()
        pw, context, attached = connect_over_cdp(cdp_url)
        return pw, context, attached

    if prefer_daemon:
        raise RuntimeError(_DAEMON_START_HINT)

    pw, context = launch_persistent_context(headless=False)
    return pw, context, False


def close_context(context: BrowserContext, playwright: Playwright | None) -> None:
    context.close()
    if playwright is not None:
        playwright.stop()


def release_browser_context(
    context: BrowserContext | None,
    playwright: Playwright | None,
    *,
    attached: bool,
) -> None:
    """Release a context from a run; detach only when attached to the daemon."""
    if context is None:
        if playwright is not None:
            playwright.stop()
        return
    if attached:
        if playwright is not None:
            playwright.stop()
        return
    close_context(context, playwright)
