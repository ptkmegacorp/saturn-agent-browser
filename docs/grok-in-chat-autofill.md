# Grok Bot in-chat autofill / login

Reference note on xAI Grok Bot’s **in-chat credential bridge** — a pattern for agent cloud browsers that need login without full remote-desktop takeover or exposing secrets to the LLM.

**Captured:** 2026-09-08

---

## What it is

When a Bot’s cloud browser reaches a login wall or form that needs credentials (e.g., United.com in the demo), Grok surfaces a **secure action card or form UI directly inside the conversation** instead of forcing a full Agent Computer takeover.

Example prompt copy:

> United.com needs your login info. Enter it here and I’ll take care of the rest.

The card includes username/password (and OTP where applicable) fields plus quick options for any password manager — Apple Passwords, 1Password, Bitwarden, system autofill, etc.

---

## How autofill works

1. Cloud browser hits a login wall on domain X.
2. Chat shows a scoped in-chat form card for domain X.
3. Form fields are engineered to trigger the **device’s native autofill service**:
   - iOS/macOS → standard Passwords autofill sheet
   - Other platforms → configured password-manager extension or OS autofill service
4. User selects the correct vault entry (domain suggested automatically).
5. On Apple devices, selection prompts **Face ID or Touch ID** to unlock the local keychain / Secure Enclave. Biometric check stays entirely on-device; the password never leaves the secure enclave until the manager injects it. Same pattern for third-party managers that support biometrics (1Password, etc.).
6. Credentials fill into the in-chat fields. User taps Submit/Continue.
7. Filled values inject **only** into the specific page currently open in the Bot’s shared cloud browser for that exact domain (the UI notes this restriction).
8. Session cookie is established on the **persistent cloud computer**, so future tasks by any of the user’s Bots can reuse the authenticated session without repeating login.

---

## Security model

| Layer | Behavior |
|-------|----------|
| LLM / transcript | Never sees plaintext password or OTP |
| Biometric unlock | Stays on-device (Secure Enclave / password manager) |
| Injection scope | Locked to the open page for that exact domain |
| Session reuse | Cookie lives on persistent cloud browser |

Secrets stay out of chat transcript and model context.

---

## Limitations (as of capture date)

- **Passkeys not supported yet** — email/password + OTP autofill only
- Works wherever the OS exposes standard autofill APIs (desktop and mobile apps)
- Requires a password manager or OS keychain the user already trusts

---

## vs. full computer takeover

Previous flow: user leaves chat, takes over the remote Agent Computer, types credentials manually, hands control back.

New flow: user stays **in-thread**, uses **existing password-manager + biometric habits**, and still establishes a **durable authenticated session** on the agent’s cloud browser without secrets entering model context.

---

## Saturn FBC relevance

Saturn Frontier Browser Control uses a different surface with the same principle — **credentials never in model context**:

| Grok Bot | Saturn FBC |
|----------|------------|
| In-chat HTML form → OS autofill → scoped injection into cloud browser tab | KeePass broker (`credential_policy: request_only`) → privileged local fill into isolated Chromium |
| User biometrics via Apple Passwords / 1Password / Bitwarden | Broker generates/stores secrets; models get handles only |
| Persistent cloud browser session reuse | Isolated Chromium profile at `~/.local/share/saturn-frontier-browser-control/chromium/` |
| Chat-native UX on mobile/desktop | CLI + HDMI-headed daemon; Indeed uses Firefox warm-login + cookie session (see [`indeed.md`](indeed.md)) |

**Design question for Saturn Pi PWA:** whether iOS Safari can reliably trigger autofill from an in-chat form that forwards values to a remote Playwright session — worth a spike against WebKit `autocomplete` and Credential Management constraints on iPhone.

**Related docs:**

- [`grok-login-handoff.md`](grok-login-handoff.md) — why the pause-and-resume login pattern unlocks real agent work
- [`saturn-pi-browser-auth-module.md`](saturn-pi-browser-auth-module.md) — Saturn Pi capsule `saturn-frontier-browser-auth` + iOS spike
- [`openclaw-comparison.md`](openclaw-comparison.md) — OpenClaw profile lanes and login doctrine
- [`browser-profiles.md`](browser-profiles.md) — dual-lane trusted vs isolated browser design
- [`indeed.md`](indeed.md) — human-owned login bootstrap for bot-sensitive sites
