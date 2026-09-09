# Saturn FBC + Saturn Auth + Saturn Pi browser UI — integration handoff

Status: planned implementation; documentation research completed 2026-09-09. Runtime remains unchanged.

## Canonical names and ownership

These three components work in conjunction:

| Component | Location | Responsibility |
|---|---|---|
| Saturn FBC | `~/projects/saturn-agent-browser` | Browser lifecycle, profiles/cookies, tabs, observations, automation, authority contracts, authentication verification and task continuation |
| Saturn Auth | `~/projects/saturn-auth` | Authentication request lifecycle, credential providers, user approval, protected delivery coordination, vault-write policy |
| `saturn-fbc-browser-web-ui` | `~/projects/saturn-pi/modules/saturn-fbc-browser-web-ui` | Planned Saturn Pi feature capsule: browser panel, human control, task status and Saturn Auth cards |

FBC remains independently usable through its existing CLI. The UI capsule lives in Saturn Pi and talks to FBC and Saturn Auth through small authenticated internal seams. Preserve existing project paths, Python package `saturn_fbc`, CLI `saturn-frontier-browser-control`, and service `saturn-fbc-browser.service`.

Canonical companion plans:

- Auth: `~/projects/saturn-auth/BUILD_REFACTOR_PLAN.md`
- UI: `~/projects/saturn-pi/modules/saturn-fbc-browser-web-ui/BUILD_REFACTOR_PLAN.md`
- Trusted lane: `../TRUSTED_BROWSER_REFACTOR_PLAN.md` (apply the precedence note there).

This document owns integration order, shared bindings and upstream reuse decisions. Component plans own implementation detail. Earlier cookie-transfer and bespoke-relay proposals are historical alternatives; the current first target preserves the authenticated tab/profile and adapts OpenClaw's extension machinery.

## Verified current state

- Saturn Auth contains a status/plan CLI and a planning scaffold.
- FBC contains Playwright browser/daemon code, authority contracts and direct credential-broker integration. Inspect `src/saturn_fbc/credentials.py`, `broker/`, `browser/`, `runner.py` and their tests before extraction.
- Saturn Pi's existing `modules/saturn-frontier-browser-auth` is an autofill spike: its HTTP submit returns field lengths. Device verification and credential relay are pending.
- The new UI capsule directory currently contains planning documentation only. Registration, runtime rename, migration and deployment are future work.
- FBC and Pi have substantial pre-existing working-tree changes. Preserve them. Runtime verification was outside this documentation pass.

## Pinned OpenClaw research and reuse map

Repository: https://github.com/openclaw/openclaw

Inspected revision: `73b4086ff658973fb9ae07fa208c49ca8de82a67`.
Source links below use that revision. Verify upstream dependency closure and tests before copying. Record each copied/adapted file, source path, revision, local destination and modifications in a local provenance manifest. Include the upstream MIT license (OpenClaw Foundation copyright) and applicable third-party notices with copied code. Review each dependency's license separately.

Base: `https://github.com/openclaw/openclaw/blob/73b4086ff658973fb9ae07fa208c49ca8de82a67/`

| Upstream path relative to base | Observed behavior / reuse decision |
|---|---|
| `ui/src/components/browser/browser-panel.ts` | Lit custom element, tabs/URL bar, docked or embedded panel, presentation/connection lifecycle. Adapt into Pi's capsule lifecycle. |
| `ui/src/components/browser/browser-client.ts` | Typed `browser.request` envelope, tabs/start/navigate/act/screenshot/screencast, authenticated media fetching, stable tab aliases. Replace Gateway/media dependencies with explicit Saturn endpoints. |
| `ui/src/components/browser/browser-panel-operation-ownership.ts` | Lifecycle epochs, stale capture rejection, ordered per-tab navigation, route-bound clients. High-priority code and test reuse. These client guards complement server-side authorization. |
| `ui/src/components/browser/browser-panel-controller-input.ts` | Coordinate input, keyboard filtering, wheel coalescing, inspect/annotation modes. Adapt under Saturn's input permissions and sensitive-mode gate. |
| `ui/src/components/browser/browser-screencast-client.ts` | WebSocket metadata plus binary JPEG frames with remote CSS dimensions; malformed-frame shutdown. Reuse with bounded payloads and Saturn transport validation. |
| `extensions/browser/src/browser/screencast/session.ts` | Playwright/CDP stream, navigation epochs, viewer authority revocation, 2 MiB backpressure threshold, delayed frame acknowledgements, teardown. Reuse lifecycle concepts/code after backend capability spike. |
| `extensions/browser/chrome-extension/modules/relay-tab-groups.js` | Group-based tab selection and creation-race checks; this helper belongs to the larger relay authorization system. Import its related lifecycle/authorization code and tests together. |
| `extensions/browser/src/browser/chrome-mcp-session.ts` | Session leases, cached/shared creation, cancellation and stale subprocess cleanup; useful optional attach backend after extension-first slice. |
| `docs/tools/chrome-extension.md` | Signed-in Chrome extension; selected/all-tab modes, pause/revoke, native bootstrap and authenticated WebSocket relay. Saturn chooses selected tabs explicitly; upstream fresh pairing defaults to all tabs. |
| `docs/tools/browser-login.md` | Human website login followed by use of the retained browser session. Site acceptance remains an empirical test. |

Additional discovered files to inspect before implementation: panel controller/render/styles/surface/target/viewport/stream/snapshot files and colocated tests; `extensions/browser/src/browser/extension-relay/`; `extensions/browser/src/browser/screencast/{tokens,wire}.ts`; native-host/bootstrap implementation and its tests. Their filenames identify research targets; detailed behavior requires source inspection.

### Portability and security decisions

- UI uses Lit, OpenClaw element/docking/i18n helpers and Gateway RPC/media services. Pi uses first-party JS feature capsules. First spike compares a capsule-local bundled Lit component with a plain-JS adaptation, then records the smallest dependency closure that retains upstream behavior/tests.
- A JS/TS browser sidecar owned by FBC is the preferred starting experiment for preserving substantial upstream code. Python FBC retains policy/runner ownership. Resolve runtime, build, local authenticated transport and process lifecycle before committing the backend layout.
- Upstream native messaging bootstraps an authenticated relay. Preserve that distinction when adapting; earlier plans describing native messaging as the complete action transport need revision.
- OpenClaw's broad `browser.request` and `evaluate` facilities require narrowing. Its panel uses evaluation for scroll/history/metrics/inspect. Implement named, validated operations for these capabilities; accept only the explicit Saturn operation allowlist from web clients.
- Use a Saturn-specific extension identity/native-host registration and dedicated profile. Remove upstream Store-ID assumptions from installation code through a reviewed adaptation. Preserve pairing proof, origin validation, revocation and reconnect tests.
- Browser-panel screenshots are remote page pixels. iOS Passwords autofill requires actual local form fields and a protected credential path. The inspected sources leave that Saturn-specific flow to implement.
- Credentials remain excluded from model inputs, chat, annotations, media history, traces, logs and generic input events. Upstream code alone establishes only the behaviors observed above; Saturn's full credential guarantee requires end-to-end tests.

## Shared flow and bindings

```text
Saturn Pi / saturn-fbc-browser-web-ui
  | browser status/view/human actions       | auth request approval/entry
  v                                        v
Saturn FBC <--- protected delivery ---> Saturn Auth ---> KeePassXC
  | owns profile + tab + document              ^ optional iPhone credential source
  | authority cage + exclusive input owner
  v
isolated-playwright OR trusted-extension (OpenClaw-derived)
```

Before writing endpoints, agree fixture-tested shapes for:

- Browser identity: profile ID, opaque browser-session ID, stable tab ID, document/navigation generation and current validated origin. Profile name/tab alias alone is insufficient to authorize delivery across replacement or restart.
- Task binding: run ID, user/consumer identity, contract reference and execution generation.
- Auth binding: opaque request ID, purpose, allowed origin, browser/task binding, expiry, requested operation (`login` or a separately approved `vault_write`), single-use approval state.
- Browser response: sanitized state, allowed capabilities, human/agent ownership, task stop reason and revision. Keep cookies, passwords, stream credentials and privileged handles out of agent-safe results.
- UI events: monotonically ordered revision or equivalent resync rule; stale clients refresh state before actions. Closing the panel releases streams/listeners/input ownership while FBC's browser profile persists.

Saturn Pi authenticates the operator and validates HTTP/WebSocket Origin and request ownership. FBC/Auth authenticate their local callers and revalidate bindings server-side. Keep ingress private through existing Tailscale Serve and loopback; the phone accesses Saturn Pi's same-origin routes. Port/service names remain a phase-0 decision.

### Input and observation ownership

FBC serializes human and agent input. Taking human control pauses the runner, invalidates queued agent actions and binds input to the selected live document. Closing/disconnecting the UI releases its lease and leaves the task paused until explicit revalidation/resume. Authentication approval grants only its declared purpose; consequential actions require their own human authority.

Sensitive mode starts before credential entry/delivery and suspends model observations, screenshot/screencast producers, DOM/inspect reads, annotations, traces of secret-bearing data and generic keyboard forwarding. Invalidate queued/cached frames and revoke prior media access; clear the UI's old frame. Credential entry uses the dedicated Auth form/route. Initial V1 human website login/challenges can use HDMI while streams are paused. Any future human-only remote sensitive viewer needs its own reviewed path. Resume observations only after protected fill, field cleanup where applicable, safe-page verification and origin/session revalidation.

## Ordered work packages and acceptance

Implement one package at a time; parallel UI work uses fixtures after shared bindings are agreed.

1. **Inventory + contracts + reuse spike.** Read source/tests and current git status across all three trees; establish existing baseline tests. Pin upstream; select dependency closure, Lit/plain-JS approach and sidecar transport; create provenance/license records when copying. Exercise minimal fixture-backed tab listing and image retrieval. Gate: written decisions, schema fixtures and exact baseline results.
2. **FBC read-only browser service.** Preserve isolated Playwright behavior; add typed status/tab/view operations and route/document bindings. Port stale-target/capture guards. Gate: unauthorized/cross-session reads, navigation races and teardown tests pass; browser survives panel close.
3. **Pi browser panel.** Register the optional `saturn-fbc-browser-web-ui` capsule; adapt tabs, URL display, snapshot view, task/connection state and capability-aware controls. Gate: module-disabled core chat works; 390×844 layout and reconnect/race tests pass. Start with snapshot capability; enable streaming only after its backend/security tests.
4. **Trusted extension + bounded control.** Reuse upstream relay/selected-tab access and tests; dedicated stable-browser profile and reviewed extension identity. Prove human bootstrap, same-tab continuation, immediate revoke, single input owner and policy enforcement. Gate: fixtures pass; human-supervised target-site baseline measured. Site acceptance is site-specific.
5. **Saturn Auth vertical slice.** Implement lifecycle/provider/browser adapter and the module's approval cards. First credential source and vault unlock policy require owner decision. Gate: synthetic login succeeds; origin replacement, expiry/replay, revoked approval and sensitive-media tests pass. Verify login independently of successful fill.
6. **iPhone credential entry / vault writes.** Resolve the Face ID/user-verification question in Auth's decision section before enabling storage writes. Validate actual Safari and installed-PWA behavior. Gate: denied/cancelled/expired verification produces zero writes; duplicate approval creates at most one entry; synthetic secrets remain isolated.
7. **Hardening and deployment.** Test process crashes, target replacement, auth-service outage, browser restart, module disposal and rollback. Run checks before a separately approved deploy. Retain profiles/vaults and record tested service configuration.

Packages 2–4 can proceed while vault-write policy is under discussion. Existing credential creation behavior needs inventory and an explicit migration decision; route the new flow through Auth before exposing it to the module.

## Agent handoff requirements

Read this plan and both component plans. Select the first incomplete package and declare scope. Inspect current source/tests and preserve user changes. Keep edits focused; coordinate actual caller changes together. Avoid speculative public plugin/versioning layers; follow Pi's `docs/AGENT_FIRST_ARCHITECTURE.md`.

For each package record: implementation status, changed files, upstream provenance, exact commands/results, fixture/live distinction, security evidence, known limitations, next package and rollback. Run `git diff --check` in Git projects, focused tests and the relevant full baseline. Saturn Auth is its own Git repository (`ptkmegacorp/saturn-auth`). Obtain human participation for live sign-in/challenges and approval before production deployment or vault writes.

Current next step: package 1. All implementation packages remain pending.
