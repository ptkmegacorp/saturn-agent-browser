# Saturn browser-agent build

*2026-09-12: hard-cut rename from `saturn-frontier-browser-control` / `saturn-fbc` / `saturn_fbc` to `saturn-agent-browser` / `saturn_agent_browser` — old names removed without shims.*

## Current cross-project build handoff (2026-09-09)

Read [OpenClaw integration build plan](docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md) for the current coordinated direction, pinned source reuse map and agent work packages.

- **Saturn Agent Browser** owns the browser engine, profiles/cookies, task authority and authentication verification.
- **Saturn Auth** owns credential providers, authentication approval and protected delivery coordination: [plan](../saturn-auth/BUILD_REFACTOR_PLAN.md).
- **`saturn-agent-browser-web-ui`** is the planned Saturn Pi browser/approval feature capsule: [plan](../saturn-pi/modules/saturn-agent-browser-web-ui/BUILD_REFACTOR_PLAN.md).

These components operate together. Existing agent-browser paths/CLI and isolated Playwright behavior stay in place. OpenClaw-derived extension/relay/panel implementation and extraction of credential ownership into Saturn Auth are queued work. The sections below include existing V1 design context; the shared plan governs the new integration sequence.

## What we are building

A **frontier-directed, local browser worker** for ordinary web work: navigating job sites, creating one-off accounts, filling non-sensitive forms, collecting information, and stopping at the point where the operator must review or submit.

Two tiers only:

| Tier | Name | Role |
|------|------|------|
| **Frontier model** | Cursor, Luna, etc. | Intent, planning, writing, exception handling |
| **Visual specialist** | *Reserved* — future local VLM loop (see note under Observation) | Screenshot + frontier subgoal → browser action |

Playwright is the deterministic control plane. KeePassXC is the offline credential vault.

**Spark-X2.5 4B is retired** from this project — no DOM/a11y inner loop.

This is not an autonomous “do anything online” agent. It is a constrained browser subsystem with explicit authority boundaries, audit records, and a manual gate for consequential actions.

## Focused V1

**Goal:** execute low-risk browser micro-tasks after a frontier model decomposes them, while keeping credentials and final submission authority outside model context.

### Components

| Component | Responsibility |
|---|---|
| **Frontier model** | Task plan; application copy; bounded subgoal; resolves escalations. |
| **Visual specialist** | *Reserved for a future local visual specialist; see `models/potential-models/ui-venus-2-official-pipeline.md`. No pig-stack / llama-server wiring ships in this tree.* |
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
3. **Visual specialist** step is *reserved* (see note under Observation); no model call ships in this tree.
4. **Contract cage** rejects disallowed actions before Playwright executes.
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
| Profile (cookies, storage, extensions) | `~/.local/share/saturn-agent-browser/chromium/` |
| Playwright Chromium **binary** | `~/.local/share/saturn-agent-browser/playwright-browsers/` (`PLAYWRIGHT_BROWSERS_PATH`) |
| Headed default | `config/browser.env` — `DISPLAY=:0`, `SATURN_AGENT_BROWSER_HEADLESS=0`, `SATURN_AGENT_BROWSER_BROWSER_MODE=daemon` |
| Browser daemon | User systemd `saturn-agent-browser.service` or subprocess; CDP on `127.0.0.1:9222`; state in `browser-state.json` |
| Window class (i3) | `SaturnAgentBrowser` |
| Launch | Playwright persistent context with that user-data dir; **no** `channel="chrome"` / `channel="chromium"` |

## Trusted Chrome (shipped 2026-09-09)

Official **Google Chrome stable** (`/usr/bin/google-chrome-stable`, 153.0.8010.36 on Saturn) with a dedicated agent-browser profile. The window lives on HDMI (`SaturnTrustedChrome`). Saturn Pi **Browser** (not **Browser auth**) snapshots this lane over loopback CDP **`:9223`**. Isolated Playwright Chromium stays on **`:9222`**. Extension relay is **not** installed. the operator’s daily Firefox/Chrome profiles are unused.

CDP on the dedicated profile is the compromise that lets SSH / iPhone see the real Chrome tab. `--headless` remains forbidden. Chrome 136+ only allows remote debugging with a non-default `--user-data-dir` (this profile). `browser trusted start` restarts Chrome if it is running without a healthy CDP.

| Resource | Path / rule |
|----------|-------------|
| Profile | `~/.local/share/saturn-agent-browser/trusted-chrome/` |
| Binary | `/usr/bin/google-chrome-stable` (`scripts/install-google-chrome.sh`) |
| Sandbox | `/opt/google/chrome/chrome-sandbox` setuid root (`4755`) — no `--no-sandbox` |
| Window class | `SaturnTrustedChrome` |
| CDP | `http://127.0.0.1:9223` (`SATURN_AGENT_BROWSER_TRUSTED_CDP_PORT`) |
| CLI | `browser trusted start\|status\|stop` · `browser profiles` · `browser view\|snapshot\|navigate --lane trusted` |
| Forbidden | `--headless`, Playwright user-data dir, daily browser profile |

```bash
./scripts/install-google-chrome.sh
./scripts/install-trusted-browser-profile.sh
saturn-agent-browser browser trusted start
saturn-agent-browser browser view --lane trusted
```

KeePassXC-Browser is **optional** (`CREDENTIAL_FILL=keepassxc-browser`). Default is broker fill. If used, the extension is installed **only** into this profile.

## Observation

> Visual specialist (local VLM loop) is reserved for a future iteration.
> See `models/potential-models/ui-venus-2-official-pipeline.md` for the UI-Venus 2 pipeline reference.
> No pig-stack / llama-server wiring ships in this tree; `run-skeleton` is the working scripted path.

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
saturn-agent-browser browser start
saturn-agent-browser run --contract contracts/indeed-easy-apply-JOBKEY.json
# Review on HDMI; you Submit.
```

Use `credential_policy: "none"` on Indeed contracts — login is cookie-based, not KeePass broker fill.

## Build order

1. **Playwright skeleton:** dedicated profile, action schema, screenshots, allowlist, trace.
2. **Visual specialist loop:** *reserved* — see note under Observation. No pig-stack / llama-server wiring ships in this tree.
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
| Visual specialist | *Reserved* — see note under Observation (reference: `models/potential-models/ui-venus-2-official-pipeline.md`) |
| Alternates | Holo2 4B (efficiency), MolmoPoint 8B (point-only) |

No pig-stack / llama-server wiring ships in this tree; runs never switch GPU profiles or hide overlays.

## Harness (Cursor only)

CLI: `~/bin/saturn-agent-browser`. Cursor skill only — **not** wired into Pig/Pi. Commands: `status`, `browser start|stop|status|restart`, `browser trusted start|stop|status`, `browser profiles`, `browser view|snapshot|navigate|control`, `run --contract`, `wait`, `last`, `abort`, `escalate-last`. The Saturn Pi capsule calls `view` / `snapshot` / `navigate` (CLI default lane is **isolated**; the Pi panel defaults to **trusted**).

Headed runs attach to a **persistent browser daemon** (CDP). Start it explicitly with `browser start`, or let `run` / `run-skeleton` auto-start when `SATURN_AGENT_BROWSER_BROWSER_MODE=daemon`. Headless/CI uses ephemeral launch-close (`--headless` or `SATURN_AGENT_BROWSER_BROWSER_MODE=ephemeral`).

## Status

V1 scaffold is **on Saturn** (2026-09): isolated Chromium, authority contracts, broker. Visual-specialist loop is reserved (see note under Observation); `run-skeleton` is the working scripted path. Spark retired 2026-09-06; GPU-tenant (pig-stack) wiring removed 2026-09-12.

**2026-09-09 evening:** trusted Chrome + Pi snapshot panel are live. Auth option-1 HITL (the-internet Approve → fill → verified login) still stands. Not done: OpenClaw extension relay, streaming/inspect, Indeed login measured on this CDP-on-dedicated-profile shape, Face ID for vault writes.
