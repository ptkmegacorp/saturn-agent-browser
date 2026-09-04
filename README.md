# Saturn browser-agent build

## What we are building

A **frontier-directed, local browser worker** for ordinary web work: navigating job sites, creating one-off accounts, filling non-sensitive forms, collecting information, and stopping at the point where the operator must review or submit.

The frontier model owns intent, planning, writing, and unusual-page reasoning. Saturn carries the repeated browser load locally. **V1 driver is Spark-X2.5 4B** (structured Playwright actions from compact DOM/a11y). A small **visual / browse-trained specialist** (e.g. Fara1.5-4B) is an **open slot** for later — fallback when on-screen clicking is required. Playwright is the deterministic control plane. KeePassXC is the offline credential vault.

This is not an autonomous “do anything online” agent. It is a constrained browser subsystem with explicit authority boundaries, audit records, and a manual gate for consequential actions.

## Focused V1

**Goal:** execute low-risk browser micro-tasks after a frontier model decomposes them, while keeping credentials and final submission authority outside model context.

### Components

| Component | V1 responsibility |
|---|---|
| Frontier model | Creates a task plan; writes application material; delegates a bounded subgoal; resolves exceptions from a compact browser-state report. |
| Spark-X2.5 4B | Default local inner-loop. Compact DOM/a11y → one structured Playwright action. Dedicated pig-stack profile **`saturn-frontier-browser-control`**. A run switches pig-stack to this profile and **hides HUD overlay**; both stay that way after the run (switch back manually with `pig-stack switch` if needed). |
| Visual specialist (slot) | **Not required for V1.** Later: small browse-trained CUA (Fara1.5-4B or similar) for screenshot → `click(x,y)` when DOM is useless. Same Playwright cage. |
| Playwright | Sole browser actuator. Captures screenshots/DOM state, validates results, maintains this project’s Chromium profile, writes the action trace. |
| Credential broker | Privileged local service. **Default fill path.** OS CSPRNG, KeePassXC store, Playwright fill inside the broker. Toggle `CREDENTIAL_FILL=keepassxc-browser` if needed. |
| KeePassXC + browser extension | Offline vault. Installed only into this project’s Chromium profile if used. |

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

## Browser operation loop (V1)

1. Frontier produces a bounded subgoal and policy.
2. Playwright opens this project’s Chromium profile and captures URL, screenshot (for logs), compact DOM/a11y facts, and task state.
3. **Spark** proposes one structured action. Default observation is a **numbered a11y snapshot** (`OBSERVATION_MODE=a11y_indexed`); CSS / mixed modes are config switches, not a rewrite.
4. Playwright executes only permitted actions and verifies the expected state change where possible.
5. If Spark fails schema, DOM check fails, or the target is not in the a11y tree: **escalate to Luna** (V1). Later, optionally hand that step to the visual specialist instead.
6. Stop on success, step budget, domain change, credential request, captcha, policy boundary, or final-submit boundary.

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

## Observation modes (pluggable)

Spark sees a compact page digest, not pixels. Default is numbered accessibility nodes. Change `config/observation.env` without redesigning Playwright:

| `OBSERVATION_MODE` | Digest |
|--------------------|--------|
| `a11y_indexed` (V1) | `[12] textbox "Email"` — Spark emits `click`/`type` with that index |
| `css` | selectors in the digest |
| `mixed` | a11y + css hints |

## Bounded live test (phase 5)

One short public form, no account, no submit:

- Contract: `contracts/live-httpbin-form.json`
- URL: `https://httpbin.org/forms/post`
- Allowlist: `httpbin.org` only
- `max_steps`: 10, `mode`: `draft`, Submit blocked
- Fake values only (`saturn-test@example.invalid`)

Local fixtures come first. This is the only live web target in V1.

## Build order

1. **Playwright skeleton:** dedicated profile, action schema, screenshots/DOM capture, allowlist, action log, final-submit interceptor.
2. **Spark adapter:** switch to this pig-stack profile, **hide HUD overlay**, structured JSON loop on fixtures (profile stays switched).
3. **Verifier layer:** field-value checks, URL/state checks, loop detector, compact escalation packet to the frontier.
4. **Credential broker:** default fill path (togglable to KeePassXC-Browser).
5. **Bounded live test:** `contracts/live-httpbin-form.json` — fill httpbin sample form, **do not submit**.
6. **(Later, optional)** Visual specialist adapter.

## Success criteria

- Spark completes bounded navigation/form-prefill on fixtures without frontier intervention most of the time.
- The system never records or exposes a plaintext vault password to a model.
- Every action is attributable to a task, policy, page state, and result.
- The frontier is called for planning, anomalies, and writing—not every browser click.
- Submission remains intentionally human-controlled.

## Model choice

| Slot | V1 | Later |
|------|----|--------|
| Frontier | Luna (`saturn-agent-dispatch ask`, `gpt-5.6-luna`) | same |
| Inner loop | **Spark-X2.5 4B** via pig-stack profile **`saturn-frontier-browser-control`** | same unless we replace the profile’s recipe |
| Visual / browse-trained | **open** — not loaded | Fara1.5-4B or similar; still this GPU tenant |

Spark is a text tool-caller, not a CUA. It gets a compact a11y/DOM digest, not pixels. This project does **not** share the live HUD GGUF: `saturn-frontier-browser-control run` switches pig-stack to this profile and **disables HUD overlay**; it does not switch back automatically.

## Harness (Cursor only)

CLI: `~/bin/saturn-frontier-browser-control`. Cursor skill only — **not** wired into Pig/Pi. Commands: `status`, `browser start|stop|status|restart`, `run --contract`, `wait`, `last`, `abort`, `escalate-last`.

Headed runs attach to a **persistent browser daemon** (CDP). Start it explicitly with `browser start`, or let `run` / `run-skeleton` auto-start when `SATURN_FBC_BROWSER_MODE=daemon`. Headless/CI uses ephemeral launch-close (`--headless` or `SATURN_FBC_BROWSER_MODE=ephemeral`).

## Build plan

Phases, GPU tenant, Chromium isolation, Cursor CLI: [BUILD_PLAN.md](./BUILD_PLAN.md).
