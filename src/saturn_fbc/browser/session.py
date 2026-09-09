"""BrowserSession: profile, capture, executor, interceptor, trace."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright

from saturn_fbc import config
from saturn_fbc.actions import ActionRejectedError
from saturn_fbc.browser.capture import capture_a11y_indexed, capture_screenshot
from saturn_fbc.browser.executor import execute_action
from saturn_fbc.browser.interceptor import current_url_allowed, intercept_action
from saturn_fbc.browser.profile import acquire_browser_context, release_browser_context
from saturn_fbc.browser.trace import TraceWriter
from saturn_fbc.contract import AuthorityContract, BrowserAction, StepRecord, StopReason
from saturn_fbc.credentials import is_password_type_action, policy_active


class BrowserSession:
    def __init__(
        self,
        contract: AuthorityContract,
        *,
        headless: bool = False,
        run_id: str | None = None,
        trace_base: Path | None = None,
    ) -> None:
        self.contract = contract
        self.headless = headless
        self._playwright: Playwright | None = None
        self._attached = False
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.trace = TraceWriter(run_id or contract.run_id, base_dir=trace_base)
        self.step = 0

    def __enter__(self) -> BrowserSession:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> Page:
        config.load_config()
        self._playwright, self.context, self._attached = acquire_browser_context(
            headless=self.headless,
        )
        assert self.context is not None
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        if not self.headless:
            self._focus_window()
        return self.page

    def _focus_window(self) -> None:
        display = os.environ.get("DISPLAY")
        if not display:
            return
        env = os.environ.copy()
        try:
            out = subprocess.run(
                ["xdotool", "search", "--class", config.wm_class_name()],
                capture_output=True,
                text=True,
                timeout=3,
                env=env,
                check=False,
            )
            wid = (out.stdout or "").strip().splitlines()
            if wid:
                subprocess.run(
                    ["xdotool", "windowactivate", wid[-1]],
                    capture_output=True,
                    timeout=3,
                    env=env,
                    check=False,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    def close(self) -> None:
        if not self.headless and not self._attached:
            hold = config.headed_hold_seconds()
            if hold > 0:
                time.sleep(hold)
        release_browser_context(
            self.context,
            self._playwright,
            attached=self._attached,
        )
        self.context = None
        self.page = None
        self._playwright = None
        self._attached = False

    def observe(self) -> StepRecord:
        assert self.page is not None
        snap = capture_a11y_indexed(self.page)
        shot = capture_screenshot(self.page, self.trace.trace_dir, step=self.step)
        return StepRecord(
            step=self.step,
            observation_mode=snap.mode,
            url=snap.url,
            title=snap.title,
            screenshot_path=str(shot),
            a11y_digest=snap.digest,
        )

    def act(self, action: BrowserAction) -> StepRecord:
        assert self.page is not None
        self.step += 1
        validated = intercept_action(self.contract, action)
        snap = capture_a11y_indexed(self.page)
        if policy_active(self.contract) and is_password_type_action(self.page, validated, snap):
            raise ActionRejectedError("Password fields are filled by the broker only")
        try:
            result = execute_action(self.page, validated, snapshot=snap)
            record = StepRecord(
                step=self.step,
                action=validated,
                observation_mode=snap.mode,
                url=self.page.url,
                title=self.page.title(),
                result=result,
            )
        except Exception as exc:
            record = StepRecord(
                step=self.step,
                action=validated,
                observation_mode=snap.mode,
                url=self.page.url,
                title=self.page.title(),
                error=str(exc),
            )
        self.trace.write_step(record)
        return record

    def stop(self, reason: StopReason, *, message: str | None = None) -> StepRecord:
        self.step += 1
        assert self.page is not None
        record = StepRecord(
            step=self.step,
            url=self.page.url,
            title=self.page.title(),
            result=message,
            stop_reason=reason,
        )
        self.trace.write_step(record)
        return record

    def ensure_url_allowed(self) -> None:
        assert self.page is not None
        if not current_url_allowed(self.contract, self.page.url):
            raise RuntimeError(f"Current URL not on allowlist: {self.page.url}")
