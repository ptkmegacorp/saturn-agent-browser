# Refactor plan: persistent browser daemon (Option 1)

**Status:** in progress (2026-09-04)  
**Goal:** Headed Saturn Frontier Chromium stays on HDMI until explicitly stopped. Visual specialist / skeleton **runs attach** over CDP instead of launch-and-close each time.

---

## Relationship to the current build (2026-09-09)

This file covers the isolated Playwright daemon refactor. The coordinated browser/Auth/UI build is specified in [docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md](docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md), used with Saturn Auth's build plan and Saturn Pi's `saturn-agent-browser-web-ui` capsule plan. Preserve the existing daemon and CLI while adding the OpenClaw-derived trusted backend and UI service seams. Inspect current source/tests to establish completion of the phases below; their original status labels are historical planning context.

## Problem

Today every `run` / `run-skeleton`:

1. `launch_persistent_context(...)`
2. executes contract
3. `context.close()` → window disappears

Headed defaults (`DISPLAY=:0`, `SATURN_AGENT_BROWSER_HOLD_SECONDS`) only delay the close. Users want a **display appliance** that persists across runs.

---

## Target architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  saturn-agent-browser.service  (user systemd, DISPLAY=:0)     │
│  browser-daemon.py                                          │
│    launch_persistent_context + --remote-debugging-port      │
│    write state → ~/.local/share/.../browser-state.json      │
│    SIGTERM → graceful context.close()                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ CDP http://127.0.0.1:<port>
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   run (Venus)      run-skeleton          browser status
   connect_over_cdp  connect_over_cdp      read state file
   work…             work…
   disconnect        disconnect            (no close)
```

### State file (`browser-state.json`)

```json
{
  "pid": 12345,
  "cdp_url": "http://127.0.0.1:9222",
  "headless": false,
  "started_at": "2026-09-04T23:30:00Z",
  "user_data_dir": "~/.local/share/saturn-agent-browser/chromium"
}
```

Path: `~/.local/share/saturn-agent-browser/browser-state.json` (mode 0600).

---

## Phases

### Phase A — Daemon core

| Item | Path / command |
|------|----------------|
| State helpers | `src/saturn_agent_browser/browser/state.py` — read/write/clear, pid alive check |
| Daemon entry | `src/saturn_agent_browser/browser/daemon.py` — launch, write state, signal loop |
| CDP port | `config/browser.env` → `SATURN_AGENT_BROWSER_CDP_PORT=9222` |
| Launch args | `profile.py` — add `--remote-debugging-port=<port>` when daemon mode |
| Systemd unit | `config/saturn-agent-browser.service` |
| Install helper | `scripts/install-browser-service.sh` |

Daemon must source `chromium.env` + `browser.env`, set `PLAYWRIGHT_BROWSERS_PATH`, use isolated user-data dir.

### Phase B — CDP attach for runs

| Item | Change |
|------|--------|
| `profile.py` | `connect_over_cdp()`, `acquire_browser_context(headless, *, prefer_daemon=True)` |
| `session.py` | `detach: bool` — on close, disconnect only (no `context.close()`) when attached |
| `skeleton.py` / `visual/loop.py` | Use `acquire_browser_context`; headed + daemon running → attach |
| Auto-start | Headed run when daemon down: `browser start` via subprocess OR clear error with hint |

**Default policy (headed Saturn):**

- `SATURN_AGENT_BROWSER_BROWSER_MODE=daemon` (default in `browser.env`)
- Headed runs require daemon; auto-start daemon if not running
- Headless runs / tests: `SATURN_AGENT_BROWSER_BROWSER_MODE=ephemeral` or `--headless` → old launch-close path

### Phase C — CLI

```bash
saturn-agent-browser browser start   # systemd-run or foreground
saturn-agent-browser browser stop
saturn-agent-browser browser status
saturn-agent-browser browser restart
```

`status` JSON includes `browser_daemon: { running, pid, cdp_url, headless }`.

Remove / repurpose `SATURN_AGENT_BROWSER_HOLD_SECONDS` for daemon mode (no-op when attached).

### Phase D — Tests & docs

| Item | Notes |
|------|-------|
| `tests/test_browser_daemon.py` | state file, mock pid, attach path with `skip_gpu` |
| `tests/test_phase1_skeleton.py` | keep `headless=True` ephemeral |
| `scripts/smoke-cli.sh` | `browser status` before headed demo |
| `README.md`, `SKILL.md` | daemon workflow |

---

## Non-goals (this refactor)

- Multi-tab orchestration beyond first context/page
- KeePass extension in daemon (unchanged)
- Pig/Pi tool wiring (still Cursor-only)
- Visual specialist CDP (later)

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Stale state after crash | `browser start` checks pid + CDP HTTP `/json/version`; stale → clear + relaunch |
| Port 9222 in use | Configurable `SATURN_AGENT_BROWSER_CDP_PORT`; fail with clear message |
| `connect_over_cdp` closes browser on `browser.close()` | **Never** call `close()` on attached browser; disconnect Playwright only |
| Profile lock (two launches) | Daemon exclusive; runs only attach |
| CI tests | `SATURN_AGENT_BROWSER_BROWSER_MODE=ephemeral` + `headless=True` in pytest |

---

## Acceptance criteria

1. `browser start` → Chromium visible on `:0`, stays after command returns.
2. `run --contract contracts/local-form.json` → fills form, **window remains**.
3. Second `run` reuses same window/profile (cookies persist).
4. `browser stop` → window closes, state file cleared.
5. Headless `run --headless` still works ephemeral for CI.
6. `pytest` passes with ephemeral mode.

---

## Implementation order

1. Phase A (daemon + state + service)
2. Phase B (attach path + session detach)
3. Phase C (CLI)
4. Phase D (tests, docs, skill)
