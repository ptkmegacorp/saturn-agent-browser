# Browser profiles (design sketch)

**Status:** design / not implemented  
**Goal:** Mirror [OpenClaw’s multi-profile model](openclaw-comparison.md) on Saturn — isolated agent browser for bounded runs, separate lane for human login on bot-sensitive sites (Indeed, Google SSO, Cloudflare).  
**Implementation handoff:** [`../TRUSTED_BROWSER_REFACTOR_PLAN.md`](../TRUSTED_BROWSER_REFACTOR_PLAN.md)

Today Saturn FBC has **one profile**: isolated Playwright Chromium + persistent CDP daemon (`~/.local/share/saturn-frontier-browser-control/chromium/`). That is correct for httpbin fixtures and disposable signups. It is the **wrong default** for Indeed login bootstrap when Turnstile or Google OAuth blocks the automation browser.

---

## What is CDP?

**CDP (Chrome DevTools Protocol)** is the wire protocol Chrome/Chromium exposes for debugging and automation. Tools connect to a loopback port (we use `127.0.0.1:9222`) to:

- drive clicks, typing, navigation
- capture screenshots and DOM
- attach multiple controllers to one browser

Our daemon always starts Chromium with `--remote-debugging-port=9222`. Playwright’s `connect_over_cdp()` is how the visual specialist loop controls the window.

**Why it matters for Indeed:** Cloudflare and Google detect automation signals tied to CDP / Playwright Chromium (`navigator.webdriver`, debug port open, etc.). A headed window on HDMI **still looks like a bot** to Turnstile if CDP is on — which is why manual clicks looped on Sep 4.

**OpenClaw / Codex rule:** human login happens **before** CDP attach (or in a completely separate real browser). Agent control is for step 3 (fill), not step 2 (login + Turnstile).

---

## Profile overview

| Profile | ID | Browser | CDP during login | Agent (visual specialist) can drive | Session storage |
|---------|-----|---------|------------------|-------------------------|-----------------|
| **Isolated** (current default) | `isolated` | Playwright bundled Chromium | Always on (daemon) | Yes | `…/chromium/` |
| **Manual bootstrap** | `manual-bootstrap` | Same Chromium tenant | **Off** until `session-ready` | After human marks ready | `…/chromium/` |
| **Host Firefox** | `host-firefox` | Real Firefox via `firefox.sh` | Never | No (human only) | Firefox profile |
| **Host Chrome** (future) | `host-chrome` | System Google Chrome + extension or MCP attach | Optional / extension relay | Later | Chrome profile |

**Rule of thumb (from OpenClaw):**

- **Bot-sensitive login** → `host-firefox` or `manual-bootstrap`
- **Bounded form fill after login** → `isolated` (or `manual-bootstrap` once session is warm)
- **Never** type real Indeed passwords through visual specialist or the KeePass broker

---

## Architecture

```text
                    ┌─────────────────────────────────────┐
                    │  Cursor / Luna (frontier)           │
                    │  contract + profile selector        │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
  profile=isolated          profile=manual-bootstrap    profile=host-firefox
  (daemon + CDP)            (no CDP → human → CDP on)   (firefox.sh only)
         │                         │                         │
         ▼                         ▼                         ▼
  Playwright Chromium         Playwright Chromium         Firefox on :0
  SATURN_FBC CDP :9222        bootstrap window            Personal.kdbx / PM
         │                         │                         │
         └──────── cookie bridge (optional, phase 3) ──────┘
                                   │
                                   ▼
                         visual specialist run --contract (isolated attach)
                         human Submit on HDMI
```

---

## Profile: `isolated` (shipped)

**What:** Current behavior. `browser start` → daemon with `--remote-debugging-port=9222` → `run` attaches over CDP.

**Use for:**

- Local fixtures, httpbin, selenium.dev
- Disposable account signups (broker fill)
- Easy Apply **after** Indeed session cookies exist and Cloudflare is not looping

**Env (existing):**

```bash
SATURN_FBC_BROWSER_PROFILE=isolated   # default when unset
SATURN_FBC_BROWSER_MODE=daemon
SATURN_FBC_CDP_PORT=9222
```

**Do not use for:** First-time Indeed login with Google SSO or active Cloudflare challenge.

---

## Profile: `manual-bootstrap` (proposed)

**What:** Human logs into the **same** isolated Chromium user-data dir, but the daemon starts **without** `--remote-debugging-port`. CDP is enabled only after the human confirms the session is ready. Reduces “automation browser” fingerprint during login.

**Workflow:**

```bash
# 1. Start bootstrap window (no CDP, no visual specialist attach)
saturn-frontier-browser-control browser bootstrap start
# Opens headed Chromium on HDMI; state: bootstrap_active, cdp_enabled=false

# 2. Human on HDMI: navigate to Indeed, log in, pass 2FA/Turnstile
#    Do NOT run `run` during this step.

# 3. Mark session ready → daemon restarts or hot-enables CDP
saturn-frontier-browser-control browser session-ready
# state: cdp_enabled=true, cdp_url=http://127.0.0.1:9222

# 4. Agent runs as today
saturn-frontier-browser-control run --contract contracts/indeed-easy-apply-JOBKEY.json

# 5. Stop when done
saturn-frontier-browser-control browser stop
```

**CLI additions (sketch):**

| Command | Behavior |
|---------|----------|
| `browser bootstrap start` | Launch persistent context, **no** CDP; write `browser-state.json` with `phase: bootstrap` |
| `browser session-ready` | Verify window alive; re-launch or signal daemon to add CDP port; `phase: agent` |
| `browser bootstrap cancel` | Close without enabling CDP |

**State file extension:**

```json
{
  "profile": "manual-bootstrap",
  "phase": "bootstrap",
  "cdp_enabled": false,
  "pid": 12345,
  "user_data_dir": "~/.local/share/saturn-frontier-browser-control/chromium",
  "started_at": "2026-09-05T01:00:00Z"
}
```

**Implementation notes:**

- `profile.py`: `launch_bootstrap_context()` — same as `launch_persistent_context` but never pass `--remote-debugging-port`
- `daemon.py`: two-phase daemon or subprocess handoff: bootstrap process exits → agent daemon starts with same `user_data_dir`
- `acquire_browser_context()`: if `phase=bootstrap`, refuse attach with clear error (“call browser session-ready after human login”)
- Contract field (optional): `"browser_profile": "manual-bootstrap"` — CLI ensures bootstrap phase before `run`

**Limits:** Still bundled Chromium; may still fail Google SSO. Helps Cloudflare cases where CDP + automation flags are the trigger.

---

## Profile: `host-firefox` (proposed)

**What:** Human authentication in **real Firefox** on HDMI — not Playwright. Used for IP sanity checks, Indeed login when isolated profile is burned, or accounts tied to Google SSO.

**Workflow:**

```bash
# 1. Open Indeed in Firefox (host skill — not saturn-fbc daemon)
FF=~/pig-mono/extensions/firefox/firefox.sh
$FF open-url https://secure.indeed.com/auth

# 2. Human logs in with password manager (Personal.kdbx / Firefox PM)
# 3. Confirm site works — no Cloudflare loop in normal browser

# 4a. Manual apply path: stay in Firefox; no visual specialist (out of scope for FBC run)
# 4b. Agent fill path: optional cookie bridge → isolated profile (phase 3)
#     saturn-frontier-browser-control browser import-cookies --from firefox --domain indeed.com
#     saturn-frontier-browser-control browser start
#     saturn-frontier-browser-control run --contract contracts/indeed-easy-apply-JOBKEY.json
```

**CLI additions (sketch):**

| Command | Behavior |
|---------|----------|
| `browser profile host-firefox open <url>` | Wrapper around `firefox.sh open-url` |
| `browser import-cookies --from firefox --domain <domain>` | Export cookies for domain from Firefox sqlite → inject into Chromium profile (human confirms) |

**Contract field:**

```json
{
  "browser_profile": "host-firefox",
  "human_steps": [
    "Log in via Firefox using browser profile host-firefox",
    "Run browser import-cookies if agent fill is needed"
  ]
}
```

`run` with `browser_profile: host-firefox` alone should **fail fast** with instructions — visual specialist cannot drive Firefox today.

**Why Firefox first:** Already on Saturn, trusted for daily browsing, separate from automation fingerprint. Chrome extension relay (OpenClaw `chrome` profile) is a later phase.

---

## Profile: `host-chrome` (future)

OpenClaw’s `user` (CDP attach to real Chrome) and `chrome` (extension relay) profiles.

**Prerequisites:**

- Install Google Chrome on Saturn
- Optional: OpenClaw-style browser extension or Chrome DevTools MCP attach
- Policy: user approves attach prompt on HDMI

**Isolated lane improvement (related, not a separate profile):**

```bash
# config/chromium.env (future)
SATURN_FBC_BROWSER_CHANNEL=chrome
# profile.py: launch_persistent_context(..., channel=os.environ.get("SATURN_FBC_BROWSER_CHANNEL"))
```

Use real Chrome binary for the **isolated** user-data dir — not the user’s daily profile. Reduces “insecure browser” for some OAuth flows; does not replace manual bootstrap for Cloudflare.

---

## Contract integration

Add optional top-level field to authority contracts:

```json
{
  "browser_profile": "isolated",
  "subgoal": "…",
  "origin_allowlist": ["indeed.com"]
}
```

| Value | `run` behavior |
|-------|----------------|
| `isolated` (default) | Require daemon + CDP; attach as today |
| `manual-bootstrap` | Require `phase=agent` or auto-fail with bootstrap instructions |
| `host-firefox` | Fail fast on `run`; emit human_steps for Firefox login |
| `host-chrome` | Not implemented |

Indeed contracts:

| Contract | Recommended `browser_profile` |
|----------|-------------------------------|
| `indeed-login-bootstrap.json` | `manual-bootstrap` or `host-firefox` |
| `indeed-easy-apply.*.json` | `isolated` (after session warm) |

---

## Implementation phases

The successful Indeed run in the OpenAI Codex desktop browser changes the experiment order. First reproduce the trusted-browser shape with a stable Chrome-family browser and a dedicated persistent profile. Keep automation detached during sign-in and Turnstile. Then add an extension relay so the same live tab and cookies remain in place. This tests the highest-value architectural difference before stealth patches or cookie transfer.

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| **0** | Docs: `openclaw-comparison.md`, this file, Indeed warnings | Done |
| **1** | Dedicated stable Chrome-family profile; human login with automation/CDP detached | Small–medium |
| **2** | Extension relay proof of concept on the already-authenticated tab | Medium–large |
| **3** | `SATURN_FBC_BROWSER_PROFILE` env + contract field validation | Small |
| **4** | `browser bootstrap start` / `session-ready` / state `phase` | Small–medium |
| **5** | Patchright + stable Chrome isolated experiment | Medium |
| **6** | Firefox → Chromium cookie import only as a fallback | Medium; fragile |

---

## Indeed runbook (dual-lane)

```text
Discovery (Luna / URLs / Indeed MCP)     →  no browser profile
IP / account sanity check                →  host-firefox
First login / Cloudflare / Google SSO    →  host-firefox OR manual-bootstrap
Easy Apply form fill                     →  isolated (cookies in chromium/)
Submit application                       →  human on HDMI (any browser)
```

If isolated profile is flagged (Turnstile loop persists after bootstrap):

1. Stop using `…/chromium/` for Indeed until cleared or profile reset.
2. Verify Indeed works in **host-firefox**.
3. Fresh `manual-bootstrap` or new chromium user-data subdir for Indeed-only tenant.

---

## Security (unchanged)

- Real Indeed password: human + browser cookies only — not `Agent.kdbx`, not `task_data`, not traces.
- Cookie import: explicit CLI command; log domains imported; no model involvement.
- `host-firefox` uses personal Firefox profile — never attach visual specialist to it.

---

## Related

- [`openclaw-comparison.md`](openclaw-comparison.md)
- [`indeed.md`](indeed.md)
- Firefox display skill: `~/.cursor/skills/firefox/SKILL.md`
- Daemon refactor: `REFACTOR_PLAN.md`
