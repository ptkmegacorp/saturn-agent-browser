# Saturn Pi browser/Auth integration — migration reference

Canonical planned capsule: **`saturn-agent-browser-web-ui`**, used with **Saturn Auth** and **Saturn FBC**. Current build instructions: [shared integration plan](OPENCLAW_INTEGRATION_BUILD_PLAN.md), [UI plan](../../saturn-pi/modules/saturn-agent-browser-web-ui/BUILD_REFACTOR_PLAN.md), [Auth plan](../../saturn-auth/BUILD_REFACTOR_PLAN.md).

The `saturn-frontier-browser-auth` name and routes below describe the existing autofill spike. Runtime migration remains queued.

## What it is

| Piece | Location |
|-------|----------|
| Feature capsule | `saturn-pi` → `modules/saturn-frontier-browser-auth/` |
| Frontier browser | this repo checkout |
| CLI | `saturn-agent-browser` on PATH |

`saturn-frontier-browser-auth` currently tests same-origin autofill submission and returns field lengths. The new capsule will supply the full browser panel plus Saturn Auth cards/forms; Saturn Auth coordinates protected delivery to FBC's bound browser adapter.

Design reference: [`grok-in-chat-autofill.md`](grok-in-chat-autofill.md).

## Architecture (target)

```text
FBC Playwright run → credential_required
        ↓
saturn-agent-browser-web-ui Auth card (approve existing vault entry)
        ↓
User: explicit Approve on Pi; or type directly in the real browser window
        ↓
Saturn Auth: bound request, approval, protected credential path
        ↓
FBC adapter revalidates origin/session, fills, verifies → profile session persists
        ↓
Agent continues; transcript shows status only
```

**Decision 2026-09-12: the "local form + iOS autofill" leg is abandoned.** iOS Passwords binds entries to the form's origin (Saturn Pi), never the remote page's origin, so Pi-local fields can neither offer nor save the target site's credentials. The diagram above is the supported shape: vault-approval or direct typing, no Pi-local credential fields.

The panel uses remote browser pixels. **iOS-autofill-via-local-form abandoned 2026-09-12** (origin-bound matching makes cross-site offer/save impossible from Pi). Credential entry happens in the real browser window; Pi keeps approval + view/verify. Follow Auth's pending vault-write verification decision before enabling KeePassXC storage writes.

## Current status (2026-09-08)

| Milestone | Status |
|-----------|--------|
| Module scaffold + docs | Done |
| iOS autofill spike (overlay + `/test` page) | Retired 2026-09-12 — origin-bound matching blocks the path; kept as same-origin mechanics reference only |
| Playwright relay from PWA submit | Not started |
| KeePass broker integration | Planned extraction/adaptation behind Saturn Auth; FBC retains browser adapter |

## Enable on Saturn Pi

Add to `~/.config/saturn-pi/env`:

```bash
SATURN_PI_FRONTIER_BROWSER_AUTH=1
```

Restart:

```bash
systemctl --user restart saturn-pi
```

## iOS spike URLs

| Surface | URL |
|---------|-----|
| Standalone (Safari tab test) | `https://<your-tailscale-serve-host>/api/modules/saturn-frontier-browser-auth/test` |
| PWA overlay | Saturn Pi home → pill **FBC auth spike** |
| Status JSON | `https://<your-tailscale-serve-host>/api/modules/saturn-frontier-browser-auth/status` |

### Device test log

Fill in after iPhone run:

| Check | Safari tab | Home-screen PWA |
|-------|------------|-----------------|
| Autofill sheet on username focus | | |
| Face ID unlock fills fields | | |
| Submit returns lengths only | | |
| Password cleared after submit | | |

## Related FBC docs

- [`browser-profiles.md`](browser-profiles.md) — isolated vs trusted browser lanes
- [`openclaw-comparison.md`](openclaw-comparison.md) — login doctrine
- [`indeed.md`](indeed.md) — human-owned login bootstrap today

## Module README

Full capsule docs: `saturn-pi/modules/saturn-frontier-browser-auth/README.md`
