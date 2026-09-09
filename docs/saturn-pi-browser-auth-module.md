# Saturn Pi browser/Auth integration — migration reference

Canonical planned capsule: **`saturn-fbc-browser-web-ui`**, used with **Saturn Auth** and **Saturn FBC**. Current build instructions: [shared integration plan](OPENCLAW_INTEGRATION_BUILD_PLAN.md), [UI plan](../../saturn-pi/modules/saturn-fbc-browser-web-ui/BUILD_REFACTOR_PLAN.md), [Auth plan](../../saturn-auth/BUILD_REFACTOR_PLAN.md).

The `saturn-frontier-browser-auth` name and routes below describe the existing autofill spike. Runtime migration remains queued.

## What it is

| Piece | Location |
|-------|----------|
| Feature capsule | `~/projects/saturn-pi/modules/saturn-frontier-browser-auth/` |
| Frontier browser | `~/projects/saturn-agent-browser` |
| CLI | `~/bin/saturn-frontier-browser-control` |

`saturn-frontier-browser-auth` currently tests same-origin autofill submission and returns field lengths. The new capsule will supply the full browser panel plus Saturn Auth cards/forms; Saturn Auth coordinates protected delivery to FBC's bound browser adapter.

Design reference: [`grok-in-chat-autofill.md`](grok-in-chat-autofill.md).

## Architecture (target)

```text
FBC Playwright run → credential_required
        ↓
saturn-fbc-browser-web-ui Auth card / local form
        ↓
User: iOS autofill + Face ID on same-origin fields
        ↓
Saturn Auth: bound request, approval, protected credential path (planned)
        ↓
FBC adapter revalidates origin/session, fills, verifies → profile session persists
        ↓
Agent continues; transcript shows status only
```

The panel uses remote browser pixels; credential autofill uses actual same-origin HTML fields. Cross-domain saved-entry selection and Face ID behavior require real Safari/PWA tests. Follow Auth's pending vault-write verification decision before enabling KeePassXC storage writes.

## Current status (2026-09-08)

| Milestone | Status |
|-----------|--------|
| Module scaffold + docs | Done |
| iOS autofill spike (overlay + `/test` page) | Done — **device verification pending** |
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
| Standalone (Safari tab test) | `https://your-tailscale-serve-host.example/api/modules/saturn-frontier-browser-auth/test` |
| PWA overlay | Saturn Pi home → pill **FBC auth spike** |
| Status JSON | `https://your-tailscale-serve-host.example/api/modules/saturn-frontier-browser-auth/status` |

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

Full capsule docs: `~/projects/saturn-pi/modules/saturn-frontier-browser-auth/README.md`
