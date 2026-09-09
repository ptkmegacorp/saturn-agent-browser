# OpenClaw comparison

How [OpenClaw](https://docs.openclaw.ai/tools/browser) handles browser automation and credentials, and what Saturn Frontier Browser Control (FBC) should borrow.

**Context:** Live Indeed testing on Saturn (2026-09-04) hit Google OAuth “insecure browser” and Cloudflare Turnstile loops in our isolated Playwright Chromium + CDP daemon. OpenClaw documents the same failure class and routes around it with **profile selection**, not stealth patches alone.

## Current source-backed direction (2026-09-09)

The canonical reuse/build decision is [OPENCLAW_INTEGRATION_BUILD_PLAN.md](OPENCLAW_INTEGRATION_BUILD_PLAN.md), pinned to OpenClaw `73b4086ff658973fb9ae07fa208c49ca8de82a67`. It records inspected panel/client/operation-ownership/screencast/relay source and concrete adoption gates.

Current target: dedicated trusted Chrome profile, selected-tab OpenClaw-derived extension relay, same-profile authenticated-session continuation, Saturn Auth credential coordination and the `saturn-fbc-browser-web-ui` Pi capsule. The Firefox cookie bridge, profile-switching sequence and priority list below are earlier research alternatives. Preserve the live authenticated tab through continuation. Community vault projects below are separate from the inspected first-party OpenClaw implementation.

## TL;DR

| OpenClaw lesson | Saturn FBC today | Recommended |
|-----------------|------------------|-------------|
| Default = isolated agent browser | ✅ Isolated Chromium tenant | Keep |
| Bot-sensitive login = real browser / manual | ❌ Same browser for everything | Add `host-firefox` + `manual-bootstrap` profiles |
| Captcha / 2FA = stop, human fixes | ✅ `stop_reason: captcha` | Keep; document in Indeed runbook |
| Credentials never in model context | ✅ KeePass broker + `credential_policy` | Keep |
| Session via cookies, not vault passwords | ⚠️ Documented for Indeed | Keep; add cookie-bridge design |
| Real Chrome optional per profile | ❌ Bundled Chromium only | Phase: `channel=chrome` on isolated profile |

See [`browser-profiles.md`](browser-profiles.md) for the Saturn dual-lane design sketch.

---

## OpenClaw’s three browser profiles

OpenClaw does **not** use one browser for all tasks. Docs: [Browser tool](https://docs.openclaw.ai/tools/browser), [Browser login](https://docs.openclaw.ai/tools/browser-login).

| Profile | What it is | When OpenClaw uses it |
|---------|------------|------------------------|
| **`openclaw`** (default) | Isolated managed Chromium/Brave/Chrome, own user-data dir, CDP + Playwright, orange UI accent | General automation, form fill, scraping |
| **`user`** | Attach to **your real Chrome** via Chrome DevTools MCP | You are at the machine; approve “Allow remote debugging?” once |
| **`chrome`** | Drive **your real signed-in Chrome** via **OpenClaw browser extension** (no CDP attach prompt) | Existing logins matter; user away from desk (Telegram, etc.) |

Agent tool default: isolated `openclaw`. For logged-in / bot-sensitive work: `profile="chrome"` or `profile="user"`.

**Saturn mapping:** Our headed daemon + CDP attach is equivalent to OpenClaw’s **`openclaw`** profile only. We have no `user` or `chrome` lane yet.

---

## Login and bot-detection doctrine

From OpenClaw’s browser-login guidance:

- **Sign in manually** in the host browser profile. **Do not give the model credentials.**
- Automated logins **trigger anti-bot defenses** and can lock accounts.
- Use the **host browser (manual login)** for X/Twitter and **other bot-sensitive sites**.
- **Sandboxed** (isolated) browser sessions are **more likely** to trigger bot detection.
- Report **login / 2FA / captcha** as **manual action** — do not guess.

This matches what we observed on Indeed:

- Google SSO → `accounts.google.com/v3/signin/rejected` (Playwright Chromium flagged)
- Indeed home → Cloudflare Turnstile loop with CDP-enabled daemon

OpenClaw’s answer is **not** “we beat Cloudflare.” It is **use the right profile** and **stop for human intervention**.

---

## Credential handling (parallel designs)

### ocvault (community)

[KeePass agent-only vault + policy daemon](https://github.com/apetersson/ocvault) — same shape as Saturn’s `Agent.kdbx` broker:

- Separate `.kdbx` from personal vault
- Daemon gates `keepassxc-cli` with domain/policy rules
- Agent never sees plaintext secrets

### openclaw-credential-vault (community)

[Domain-pinned placeholders + session injection](https://github.com/karanuppal/openclaw-credential-vault):

- Agent types `$vault:indeed-login` in a password field
- Vault resolves only on allowed domains
- **`browser-session`** mode injects cookies so the agent never sees session material

### Saturn FBC

| Concern | Saturn approach |
|---------|-----------------|
| Disposable signups | `Agent.kdbx` broker fill (`credential_policy: request_only`) |
| Real accounts (Indeed) | Human login + Chromium profile cookies (`credential_policy: none`) |
| Placeholders (`{{password}}`, TOTP) | Not implemented; narrow future addition |
| Cookie injection from vault | Not implemented |

For Indeed, Saturn and OpenClaw converge: **cookies in browser profile, not vault passwords**.

---

## Technical stack overlap

| Piece | OpenClaw | Saturn FBC |
|-------|----------|------------|
| Local loopback control | Gateway browser service | CLI + browser daemon |
| CDP | Per-profile port range (e.g. 18800+) | `127.0.0.1:9222` |
| Playwright | Snapshots, act, evaluate (toggleable) | Venus visual loop (screenshot → action) |
| `executablePath` | Real Chrome/Brave per profile | Bundled Chromium only (`profile.py`) |
| Navigation policy | Allowlists, SSRF checks | Contract `origin_allowlist` |
| Cookie import | macOS: copy cookies from system Chrome → managed profile | Not implemented |
| Extension relay | `chrome` profile drives real tabs | Not implemented |
| Traces / audit | Browser panel, snapshots | `traces/<run-id>/` JSONL + redacted screenshots |
| Doctor / health | `openclaw browser doctor` | `browser status`, `status` |

---

## What OpenClaw would do for Indeed

```text
1. Job discovery        → web_search / web_fetch / Indeed MCP (search only)
2. Login / Cloudflare   → profile="chrome" or manual login in host browser
3. Easy Apply fill      → continue in the SAME authenticated profile/tab
4. Submit               → human (same as Saturn contracts)
```

Our current Indeed runbook opens sign-in in the **same isolated CDP browser** that Cloudflare flags. OpenClaw would call that the wrong profile for step 2.

---

## Gaps to close on Saturn (priority order)

1. **Document dual-lane workflow** — [`browser-profiles.md`](browser-profiles.md) (design); update [`indeed.md`](indeed.md) with Cloudflare / Google SSO warnings.
2. **`manual-bootstrap` mode** — human logs in with CDP **off**; agent attaches only after `browser session-ready`.
3. **`host-firefox` lane** — human auth in real Firefox (`firefox.sh`); IP sanity check; optional cookie bridge later.
4. **Real Chrome on isolated profile** — install Google Chrome; `channel="chrome"` or Patchright; reduces but does not eliminate bot checks.
5. **Cookie bridge** — export selected cookies Firefox → isolated Chromium (fragile; explicit human approval).
6. **Chrome extension relay** (longer term) — OpenClaw `chrome` profile equivalent for remote apply while away from HDMI.

---

## Anti-detect note

OpenClaw docs emphasize **profile choice and manual login**, not Patchright/rebrowser as the primary story. Stealth Chromium can help the **isolated** lane after session exists; it does not replace a real-browser login path for Google-linked or Cloudflare-gated sites.

Saturn options (when we harden the isolated lane):

- Patchright + `channel="chrome"`
- `browser start` without `--remote-debugging-port` during human bootstrap
- Avoid Google SSO in agent browser; prefer site-native email/password where possible

---

## References

- [OpenClaw browser tool](https://docs.openclaw.ai/tools/browser)
- [OpenClaw browser login](https://docs.openclaw.ai/tools/browser-login)
- [ocvault](https://github.com/apetersson/ocvault)
- [openclaw-credential-vault](https://github.com/karanuppal/openclaw-credential-vault)
- Saturn: [`indeed.md`](indeed.md), [`browser-profiles.md`](browser-profiles.md)
