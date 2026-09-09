# Indeed job search workflow

**Target use case:** log into Indeed once, keep the session in a browser profile visual specialist can use, let visual specialist + Luna drive Easy Apply form fills, and **you** click Submit on HDMI.

There is **no GOG-style Indeed CLI** for job seekers. Indeed’s official MCP connector (Claude only, beta) covers **search and profile read**, not apply. Applying still requires a real browser — this project.

## Bot-sensitive login (read this first)

Isolated Playwright Chromium + CDP (our default daemon) is **often blocked** on Indeed:

| Blocker | Symptom | What to do |
|---------|---------|------------|
| Google SSO | “This browser or app may not be secure” | Use Indeed email/password, or log in via **Firefox** (`host-firefox` lane) |
| Cloudflare Turnstile | “Verify you are human” loop | Stop agent runs; use **manual-bootstrap** or **host-firefox** — see [`browser-profiles.md`](browser-profiles.md) |
| CDP / automation fingerprint | Captcha on every navigation | Do not run `run` during login; enable CDP only after session is warm |

OpenClaw uses the same split: isolated browser for automation, **real browser for login**. Comparison: [`openclaw-comparison.md`](openclaw-comparison.md).

## OpenClaw / Codex strategy (required — avoids Turnstile)

This is the doctrine we follow after the Sep 2026 live test. **Do not log into Indeed in the Saturn CDP daemon** — that path caused Google SSO rejection and Cloudflare Turnstile loops.

```text
1. Discovery        → Luna / URLs / Indeed MCP (no browser, or Firefox)
2. Login + Turnstile → YOU in a normal browser (Firefox today) — NO CDP, NO agent run
3. Easy Apply fill  → Saturn visual specialist ONLY after session is warm
4. Submit           → YOU on HDMI (contract blocks submit)
```

Same model as ChatGPT/Codex “take over browser”: **human owns auth and bot checks; agent gets cookies, not passwords.**

| Step | OpenClaw | Codex | Saturn today |
|------|----------|-------|--------------|
| Bot-sensitive login | `profile=chrome` or host browser | Built-in browser, human types | **Firefox** (`host-firefox`) |
| Automation | Isolated `openclaw` profile | After handoff | Saturn daemon **after** warm session |
| During login | No agent, no CDP attach | Pause automation | **No `run`, no CDP** |

### What is CDP?

**CDP (Chrome DevTools Protocol)** is how Playwright and our agent **remote-control** Chromium. When the Saturn browser daemon runs, it launches Chromium with `--remote-debugging-port=9222`. Playwright connects to that port to click, type, screenshot, and read the page.

Sites like Google and Cloudflare treat **CDP-attached / automation Chromium** as a bot — even while you click manually on HDMI. That is why Turnstile kept looping on Sep 4: the window was always in “agent mode.”

**Rule:** CDP is for **bounded agent runs after login**, not for the login itself.

### Do NOT (this caused our failure)

```bash
# Wrong for Indeed login — CDP on from the start
saturn-frontier-browser-control browser start
saturn-frontier-browser-control run --contract contracts/indeed-login-bootstrap.json
# Then log in on HDMI → Cloudflare Turnstile loop likely
```

Also avoid **Sign in with Google** in any automation-tagged browser.

### Do today (until `manual-bootstrap` ships)

```bash
# 1. Login + pass Cloudflare in REAL Firefox — no CDP, no agent
~/pig-mono/extensions/firefox/firefox.sh open-url https://secure.indeed.com/auth
# You: Indeed email/password (not Google SSO), complete any challenge, confirm jobs load.

# 2. Easy Apply fill — only if Saturn profile already has a warm Indeed session
#    (If Turnstile ever looped in the Saturn profile, reset or skip Saturn for login.)
saturn-frontier-browser-control browser start
saturn-frontier-browser-control run --contract contracts/indeed-easy-apply-JOBKEY.json

# 3. You Submit on HDMI
```

**If Saturn browser never got a clean Indeed session:** browse and apply manually in Firefox until `manual-bootstrap` or trusted Chrome lane lands (`TRUSTED_BROWSER_REFACTOR_PLAN.md`).

### Target (when implemented)

`manual-bootstrap`: open headed Chromium **without** CDP → you login + Turnstile → `browser session-ready` → then agent attaches. Same OpenClaw split, one profile.

- Google SSO was rejected in the Playwright Chromium tenant.
- Indeed-native email/password login succeeded, then Indeed presented a persistent Cloudflare “Verify you are human” loop even after the operator completed the challenge manually.
- An operator reported that the same Indeed workflow succeeded through the OpenAI Codex desktop app’s browser on Linux.
- The A/B result points to the Saturn browser/control surface or its session reputation as the primary cause; the account and network path remained usable through Codex.

[OpenAI’s browser documentation](https://developers.openai.com/codex/app/browser) says its built-in browser has a separate persistent profile, supports direct human sign-in, and exposes full CDP through an optional Developer mode with explicit approval. Its [browser extension](https://developers.openai.com/codex/chrome-extension) can control an existing signed-in Chrome-family tab. Public documentation leaves the built-in browser engine, anti-bot modifications, and any Indeed/Cloudflare allowlisting unspecified, so those explanations remain hypotheses.

**Recommended lanes:**

1. **Login / Cloudflare** → dedicated stable Chrome-family profile with automation detached; Codex’s built-in browser is the observed working reference
2. **Easy Apply fill** → extension relay into that same authenticated tab (planned); human/Codex operation until it ships
3. **Generic low-risk forms** → current isolated Playwright Chromium
4. **Submit** → you on HDMI

## Recommended pattern: human login + profile cookies

Same idea as ChatGPT agent “take over browser” / secure sign-in:

1. **You** type password, 2FA, and captcha on HDMI — in **Firefox or a no-CDP bootstrap window**, not in the Saturn CDP daemon.
2. **Session cookies** persist in the browser profile you used.
3. **Agent runs** assume you are already logged in; they fill forms and stop before Submit.

KeePass `Agent.kdbx` broker fill is for **disposable agent-created accounts**. For your real Indeed account, prefer **cookie persistence** over vault passwords.

| Step | Who | What |
|------|-----|------|
| Login + Cloudflare (once) | You in **Firefox** (today) | Password manager; no Google SSO; no agent |
| Session storage | Browser profile | Cookies / localStorage |
| Find jobs | Luna / search / manual URL | Not this doc |
| Fill Easy Apply | visual specialist + contract | Only after warm session; Saturn daemon |
| Submit application | You on HDMI | Intentionally blocked by contract |

## One-time session bootstrap

**Use the OpenClaw / Codex flow above.** Do not use the block below for first-time Indeed login.

<details>
<summary>Legacy bootstrap (fixtures only — not for Indeed login)</summary>

```bash
cd ~/projects/saturn-agent-browser
saturn-frontier-browser-control browser start
saturn-frontier-browser-control run --contract contracts/indeed-login-bootstrap.json
```

This opens Indeed with **CDP already enabled** — acceptable for navigation smoke tests, **not** for passing Cloudflare Turnstile.

</details>

If you already have a warm Indeed session in the Saturn Chromium profile (no active Turnstile):

## Applicant profile JSON

Reusable applicant facts live in **`profiles/indeed-applicant.json`**. Copy fields into each job contract’s `task_data`, or have Luna merge profile + job-specific answers when drafting a contract.

Do **not** put Indeed passwords in this file. Login is human + cookies only.

```bash
cat profiles/indeed-applicant.json
```

## Per-job Easy Apply contract

1. Copy the template:

   ```bash
   cp contracts/indeed-easy-apply.template.json contracts/indeed-easy-apply-JOBKEY.json
   ```

2. Edit:

   - `task_id` — short label (e.g. `indeed-acme-pm-2026-03`)
   - `start_url` — job posting URL (`jk=` key from Indeed)
   - `task_data` — merge from `profiles/indeed-applicant.json` plus job-specific screening answers
   - `subgoal` — one line for visual specialist (role, company, stop-before-submit)

3. Run:

   ```bash
   saturn-frontier-browser-control validate-contract --path contracts/indeed-easy-apply-JOBKEY.json
   saturn-frontier-browser-control run --contract contracts/indeed-easy-apply-JOBKEY.json
   saturn-frontier-browser-control last    # trace + stop_reason
   ```

4. Review the filled form on HDMI. **You** click Submit.

## Contract defaults for Indeed

| Field | Value | Why |
|-------|-------|-----|
| `origin_allowlist` | `["indeed.com"]` | Block navigation off-site |
| `credential_policy` | `"none"` | Human already logged in; no broker password fill |
| `blocked_actions` | includes `submit`, `upload_sensitive` | Human owns submit; resume upload TBD |
| `mode` | `"draft"` | Non-destructive fill |
| `max_steps` | `25`–`40` | Easy Apply can be multi-page |

## Resume upload (not automated yet)

Indeed Easy Apply often wants a résumé file. `upload_sensitive` is blocked by default. Until we add a human-approved upload path:

- Prefer Indeed’s saved profile résumé when the site offers it, or
- Paste résumé text into text fields where allowed, or
- Upload the file yourself on HDMI after visual specialist stops.

## When runs stop (expected)

| `stop_reason` | Meaning | Action |
|---------------|---------|--------|
| `success` | Success checks met, form filled | Review + Submit on HDMI |
| `pre_submit_boundary` | Hit submit gate | Review + Submit on HDMI |
| `captcha` | Bot check detected | You solve on HDMI, re-run |
| `escalate` | visual specialist stuck | `escalate-last` → Luna suggests next subgoal |
| `max_steps` | Step budget exhausted | Increase `max_steps` or split into two contracts |
| `domain_change` | Left indeed.com | Fix URL or allowlist |

## Discovery vs apply (split stack)

| Layer | Tool | Applies? |
|-------|------|----------|
| Job search | Indeed MCP (Claude connector), manual URLs, Luna research | No |
| Apply | **saturn-frontier-browser-control** | Fill only; human submits |

Optional later: thin `saturn-indeed search` wrapper upstream. Apply stays in this repo.

## Security notes

- Indeed password never belongs in contracts, `task_data`, traces, or `Agent.kdbx` for this workflow.
- Use **Personal.kdbx** / Firefox for human browsing; **Agent.kdbx** only for throwaway signups elsewhere.
- Traces redact password fields in screenshots; still avoid putting secrets in `task_data`.

## Related files

| File | Purpose |
|------|---------|
| `profiles/indeed-applicant.json` | Reusable applicant `task_data` |
| `contracts/indeed-login-bootstrap.json` | Open sign-in; human owns login |
| `contracts/indeed-easy-apply.template.json` | Per-job copy template |
| `docs/browser-profiles.md` | Dual-lane design (`isolated`, `manual-bootstrap`, `host-firefox`) |
| `docs/openclaw-comparison.md` | How OpenClaw splits browser modes |
