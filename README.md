# Saturn browser-agent build

## Current cross-project build handoff (2026-09-09)

Read [OpenClaw integration build plan](docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md) for the current coordinated direction, pinned source reuse map and agent work packages.

- **Saturn FBC** owns the browser engine, profiles/cookies, task authority and authentication verification.
- **Saturn Auth** owns credential providers, authentication approval and protected delivery coordination: [plan](../saturn-auth/BUILD_REFACTOR_PLAN.md).
- **`saturn-fbc-browser-web-ui`** is the planned Saturn Pi browser/approval feature capsule: [plan](../saturn-pi/modules/saturn-fbc-browser-web-ui/BUILD_REFACTOR_PLAN.md).

These components operate together. Existing FBC paths/CLI and isolated Playwright behavior stay in place. OpenClaw-derived extension/relay/panel implementation and extraction of credential ownership into Saturn Auth are queued work. The sections below include existing V1 design context; the shared plan governs the new integration sequence.

## What we are building

A **frontier-directed, local browser worker** for ordinary web work: navigating job sites, creating one-off accounts, filling non-sensitive forms, collecting information, and stopping at the point where the operator must review or submit.

Two tiers only:

| Tier | Name | Role |
|------|------|------|
| **Frontier model** | Cursor, Luna, etc. | Intent, planning, writing, exception handling |
| **Visual specialist** | Local VLM on Saturn (default: **UI-Venus 2 9B**) | Screenshot + frontier subgoal → browser action |

Playwright is the deterministic control plane. KeePassXC is the offline credential vault.

**Spark-X2.5 4B is retired** from this project — no DOM/a11y inner loop.

This is not an autonomous “do anything online” agent. It is a constrained browser subsystem with explicit authority boundaries, audit records, and a manual gate for consequential actions.

## Focused V1

**Goal:** execute low-risk browser micro-tasks after a frontier model decomposes them, while keeping credentials and final submission authority outside model context.

### Components

| Component | Responsibility |
|---|---|
| **Frontier model** | Task plan; application copy; bounded subgoal; resolves escalations. |
| **Visual specialist** | Local VLM (`ui-venus-2-9b-q4km-local` on `:8091` via llama.cpp). Screenshot + contract `subgoal` → Venus `<answer>Action(...)</answer>` parse → Playwright execute. Profile **`saturn-frontier-browser-control`**. Logic ported from [UI-Venus `venus_browser.py`](https://github.com/inclusionAI/UI-Venus/blob/UI-Venus-2/models/browser/venus_browser.py). |
| **Playwright** | Sole browser actuator. Captures screenshots, validates results, maintains Chromium profile, writes trace. |
| **Credential broker** | Privileged local service. Default fill path. |

### Authority contract

Every delegated run is an object such as:

```json
{
  "subgoal": "Create an account and populate non-sensitive profile fields; stop before final submission.",
  "origin_allowlist": ["jobs.example.com"],
  "allowed_actions": ["navigate", "scroll", "click", "type", "select"],
  "blocked_actions": ["submit", "send", "purchase", "upload_sensitive", "change_security_settings"],
  "max_steps": 18,
  "credential_policy": "request_only",
  "success_checks": ["account-created page present", "visible field values match task data"]
}
```

Playwright rejects anything outside this contract, even if a model emits it.

## Account and password flow

The frontier model can decide that a new one-off account is useful and can propose a human-readable account label. It must **not** generate the password itself.

1. Frontier requests `credential.create(domain, username, label)`.
2. The privileged broker uses the OS CSPRNG to produce a long unique password (default: 24+ random characters), writes a KeePassXC entry, and returns only a record handle/status.
3. Browser navigates to the approved domain. At signup/login, Playwright stops at `credential_required`.
4. The broker fills the matching record (`CREDENTIAL_FILL=broker` default). The agent receives only confirmation that the page is authenticated.
5. The authenticated session stays in **this project’s** Chromium profile. Logout and expiry are recoverable.

## Browser operation loop

1. Frontier produces a bounded subgoal and policy (authority contract).
2. Playwright opens this project's Chromium profile and captures **screenshot** + URL + trace metadata.
3. **Visual specialist** (UI-Venus 2 on llama-server `:8091`) receives screenshot history + task; model emits `<answer>Click(point=(x,y))</answer>` (or Type, Scroll, …).
4. **`parse_action()` / `execute()`** (ported from Venus) map normalized 0–999 coords to viewport and run Playwright; contract cage rejects disallowed actions.
5. On parse failure, captcha, `CallUser()`, or policy boundary: **escalate to frontier**.
6. Stop on `Finished()`, success checks, step budget, domain change, credential request, or pre-submit boundary.

Use `run-skeleton` for scripted fills without loading the VLM.

## V1 guardrails

- **This project’s Chromium only.** Dedicated user-data directory and a Playwright-bundled Chromium binary owned by this repo. Never the operator’s daily Firefox/Chrome, never system `/usr/bin/chromium`, never another project’s Playwright cache.
- Site/domain allowlist per run; external navigation pauses the task.
- No password, TOTP seed, recovery code, or vault export in model context, prompts, screenshots, or logs.
- Run logs retain action metadata, URLs, redacted screenshots, DOM hashes/selected facts, and verification outcomes—not typed secret values.
- Default no-submit policy. Explicit user confirmation is required for job applications, email sends, purchases, agreements, security changes, and anything that creates an external commitment.
- CAPTCHA/anti-bot blocks terminate the automated run; no bypass attempts.
- Use rate limits and a site-specific action budget to prevent loops and accidental spam.

## Isolated Chromium (this project only)

| Resource | Path / rule |
|----------|-------------|
| Profile (cookies, storage, extensions) | `~/.local/share/saturn-frontier-browser-control/chromium/` |
| Playwright Chromium **binary** | `~/.local/share/saturn-frontier-browser-control/playwright-browsers/` (`PLAYWRIGHT_BROWSERS_PATH`) |
| Headed default | `config/browser.env` — `DISPLAY=:0`, `SATURN_FBC_HEADLESS=0`, `SATURN_FBC_BROWSER_MODE=daemon` |
| Browser daemon | User systemd `saturn-fbc-browser.service` or subprocess; CDP on `127.0.0.1:9222`; state in `browser-state.json` |
| Window class (i3) | `SaturnFrontierBrowser` |
| Launch | Playwright persistent context with that user-data dir; **no** `channel="chrome"` / `channel="chromium"` |

KeePassXC-Browser is **optional** (`CREDENTIAL_FILL=keepassxc-browser`). Default is broker fill. If used, the extension is installed **only** into this profile.

## Observation

The **visual specialist** consumes **screenshots** (multi-turn history per Venus loop). Optional a11y digest is a hint only — not a separate DOM inner loop.

Integration plan: [`models/potential-models/ui-venus-2-official-pipeline.md`](../../models/potential-models/ui-venus-2-official-pipeline.md)

## Terminology

| Term | Meaning |
|------|---------|
| **Frontier model** | Remote planner (Cursor, Luna). Owns *what* to do. |
| **Visual specialist** | Local VLM on Saturn. Owns *where* on screen (and short-horizon actions). Also called **grounding model** when point-only (MolmoPoint). |
| **CUA** | Computer-use agent — full screenshot→action (Venus, Holo2). |

Research: [`models/potential-models/browser-grounding-vlm-research.md`](../../models/potential-models/browser-grounding-vlm-research.md) · Venus port plan: [`ui-venus-2-official-pipeline.md`](../../models/potential-models/ui-venus-2-official-pipeline.md)

## Bounded live test (phase 5)

One short public form, no account, no submit:

- Contract: `contracts/live-httpbin-form.json`
- URL: `https://httpbin.org/forms/post`
- Allowlist: `httpbin.org` only
- `max_steps`: 10, `mode`: `draft`, Submit blocked
- Fake values only (`saturn-test@example.invalid`)

Local fixtures come first. This is the only live web target in V1.

## Indeed job applications (primary real-world target)

Indeed has **no GOG-style CLI** for job seekers — official APIs and the Indeed MCP connector cover **search**, not apply. Our apply path is **browser + authority contracts**.

**Recommended workflow (OpenClaw / Codex):** Firefox for Indeed login + Cloudflare → warm session → visual specialist fill → you Submit. **Do not** use `browser start` for Indeed login (CDP triggers Turnstile loops).

| What | Where |
|------|-------|
| Full runbook + CDP explainer | [`docs/indeed.md`](docs/indeed.md) |
| Trusted-browser conversion handoff | [`TRUSTED_BROWSER_REFACTOR_PLAN.md`](TRUSTED_BROWSER_REFACTOR_PLAN.md) |
| Browser profiles (dual-lane design) | [`docs/browser-profiles.md`](docs/browser-profiles.md) |
| OpenClaw comparison | [`docs/openclaw-comparison.md`](docs/openclaw-comparison.md) |
| Saturn Pi in-chat auth module | [`docs/saturn-pi-browser-auth-module.md`](docs/saturn-pi-browser-auth-module.md) |
| Reusable applicant facts | [`profiles/indeed-applicant.json`](profiles/indeed-applicant.json) |
| Open sign-in (human owns login) | [`contracts/indeed-login-bootstrap.json`](contracts/indeed-login-bootstrap.json) |
| Per-job template | [`contracts/indeed-easy-apply.template.json`](contracts/indeed-easy-apply.template.json) |

```bash
# 1. Login in Firefox — NOT Saturn CDP daemon (see docs/indeed.md)
~/pig-mono/extensions/firefox/firefox.sh open-url https://secure.indeed.com/auth
# Human: Indeed email/password, pass Cloudflare, confirm jobs load.

# 2. Easy Apply fill — only after warm Saturn session (or skip if profile flagged)
cp contracts/indeed-easy-apply.template.json contracts/indeed-easy-apply-JOBKEY.json
# Edit start_url + task_data (merge profiles/indeed-applicant.json)
saturn-frontier-browser-control browser start
saturn-frontier-browser-control run --contract contracts/indeed-easy-apply-JOBKEY.json
# Review on HDMI; you Submit.
```

Use `credential_policy: "none"` on Indeed contracts — login is cookie-based, not KeePass broker fill.

## Build order

1. **Playwright skeleton:** dedicated profile, action schema, screenshots, allowlist, trace.
2. **Venus browser loop:** port prompt / `parse_action` / `execute` from `venus_browser.py`; call llama-server `:8091` (OpenAI-compatible multimodal chat). Replace interim generic JSON client.
3. **Verifier layer:** checks, loop detector, escalation packet to frontier.
4. **Credential broker**
5. **Bounded live test**

## Success criteria

- Visual specialist completes bounded navigation/form-prefill on fixtures with frontier subgoals.
- The system never records or exposes a plaintext vault password to a model.
- Every action is attributable to a task, policy, page state, and result.
- The frontier is called for planning, anomalies, and writing—not every browser click.
- Submission remains intentionally human-controlled.

## Model choice

| Slot | Model |
|------|-------|
| Frontier | Luna / Cursor |
| Visual specialist | **UI-Venus 2 9B Q4_K_M** + mmproj via **llama.cpp** (`saturn-frontier-browser-control` profile, `:8091`) |
| Alternates | Holo2 4B (efficiency), MolmoPoint 8B (point-only) |

A run switches pig-stack to this profile and **hides HUD overlay**; profile stays switched after exit.

## Harness (Cursor only)

CLI: `~/bin/saturn-frontier-browser-control`. Cursor skill only — **not** wired into Pig/Pi. Commands: `status`, `browser start|stop|status|restart`, `run --contract`, `wait`, `last`, `abort`, `escalate-last`.

Headed runs attach to a **persistent browser daemon** (CDP). Start it explicitly with `browser start`, or let `run` / `run-skeleton` auto-start when `SATURN_FBC_BROWSER_MODE=daemon`. Headless/CI uses ephemeral launch-close (`--headless` or `SATURN_FBC_BROWSER_MODE=ephemeral`).

## Status

V1 scaffold is **on Saturn** (2026-09): isolated Chromium, authority contracts, broker, llama-server recipe + weights. **Venus loop port** (prompt/parser/executor from `venus_browser.py`) is the active integration step — interim generic JSON client is deprecated. Spark retired 2026-09-06.
