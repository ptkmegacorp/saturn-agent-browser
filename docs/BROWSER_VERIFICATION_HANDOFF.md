# Browser verification handoff — implementation specification

Status: planned next user-facing capability. Existing approval/login proof and Chrome snapshot panel are foundations. This document specifies implementation; device/browser acceptance requires tests.

## Intent

When a Saturn Pi task reaches browser authentication or verification, offer one clear **Open verification** action that presents the exact live tab/popup where human input is required. The owner enters credentials, selects an account, completes MFA/challenges or approves consent, then FBC verifies the result and resumes the bounded task.

This is a reusable default handoff across browser tasks. Keep it in the existing `saturn-agent-browser-web-ui` capsule with small explicit core seams. Use the current shared module panel, agent-browser session ownership and Saturn Auth lifecycle. Follow ``SATURN_CONVENTIONS.md` in your Saturn dotfiles`.

## Roles and entrypoint

- **FBC:** detects a blocker or accepts an explicit task request; owns the real browser tab/popup, live generations, human-control lease, protected input/observation and task continuation.
- **Saturn Auth:** owns credential-use approvals and protected provider delivery. Existing KeePassXC approval remains available as an option. Human challenges/consent can use a handoff with an associated Auth request only when relevant.
- **Pi capsule:** renders the task-linked attention card and exact browser surface, with trusted origin, reason, requesting task, human-control state, expiry and Cancel/Done controls. Pending Auth cards appear in context alongside that surface.

Proposed internal operation: `request_browser_verification`. Agree its exact schema with current callers before coding. Inputs: authenticated caller/user, task/run, profile/browser session, tab, current document generation, validated origin, blocker reason, expected completion condition, expiry and optional Auth request ID. Return an opaque handoff ID and sanitized state.

Only validated host/task requests can create handoffs; webpage text is untrusted. Repeated detection deduplicates against the live task/binding. Reuse this operation from FBC and other authorized browser-task callers as evidence warrants.

## User flow

1. Pause agent input and invalidate queued actions when a blocker is detected. Emit a task-linked verification event to the authenticated Pi session.
2. Show **Open verification** in task/chat context and a pending badge on Browser. If the browser panel is already showing that task, select the blocked tab/popup and show the request inline. Automatic foreground opening may be enabled for the active task with an explicit preference; preserve user focus on unrelated work. A suspended/background PWA restores pending requests on reconnect.
3. Acquire an exclusive, expiring human lease bound to user, run, profile, session and target. Present the actual remote page and trustworthy browser-origin chrome. Pause/revoke agent control before any human action.
4. Offer the applicable path: use an existing KeePassXC credential (explicit approval); or interact directly with the remote page / HDMI window for typing, account selection, MFA, consent and challenge handling.
5. Treat **Done** as a request to verify. FBC checks the intended authenticated app/page and current bindings independently. Keep the task paused on failure, timeout, unknown outcome or renewed challenge.
6. Release human input and resume only after verified completion and current task-authority checks. Cancel/disconnect/expiry releases the viewing/input lease while retaining recoverable pending task state and browser session.

## Exact page and iPhone input feasibility

Display pixels from the same Saturn browser session holding the task's cookies. Opening the same URL in iPhone Safari creates a separate browser session; transferring that login back requires a separately designed supported mechanism. Arbitrary login sites can block iframe embedding, so the existing remote-browser view is the starting presentation surface.

A screenshot-only panel currently provides viewing. This feature needs a tested protected interaction path: coordinate clicks, scrolling, text/IME entry, key events and popup selection. Start with bounded refreshed snapshots if usable; add streaming when measured interaction latency requires it. Test on the real iPhone.

Remote pixels supply the exact page. **Decision 2026-09-12: the same-origin protected credential form path is abandoned.** iOS Passwords matches saved entries to the *form's origin* (Saturn Pi), not the remote page's origin, so a Pi-local form can never offer or file the target site's credentials — entry selection would match Pi, and saves would file under Pi. No WebKit workaround exists within our dedicated-Chrome + PWA shape. Credential entry stays on the real browser window (HDMI / same-tab extension relay when it ships); Pi keeps Approve-existing-vault-entry plus view/verify. Passkeys/security keys and cross-device WebAuthn need their own feasibility test; some flows will retain an explicit local/device handoff.

Google SSO requires an app → identity-provider → app transaction, with bounded popup/redirect ownership, account/consent handling and independent app-session verification. Site acceptance is measured per browser lane. Human challenge completion remains the supported policy; persistent blocking routes to the owner with a sanitized reason.

## Security and observation boundary

Before presenting sensitive interaction, introduce a **human-only browser channel** distinct from agent observations and ordinary snapshot access:

- Suspend agent screenshots, DOM reads, traces, inspect/annotation and generic agent input for the sensitive target. Invalidate queued/cached frames and revoke previous media access.
- Authorize each human frame/input against user, lease, profile/session/tab and live document generation. Use private same-origin transport, bounded payloads, short-lived capabilities, cache prevention and explicit cleanup. Keep frames/secret input out of chat attachments, logs, telemetry and persisted UI state.
- Exempt only the authorized human viewer from the capture suspension. Existing generic snapshot endpoints must fail safely for sensitive targets. Redact credentials and OAuth codes/tokens in URL metadata and errors.
- Revalidate origin and document at protected input/fill. Redirect permission and credential-delivery permission remain separate. Stop secret delivery on a changed document; update the visible origin and rebind explicitly as the human follows legitimate redirects.
- Control leases are per target/run/operator and expire/revoke on ownership loss. Global human/agent flags can remain compatibility state during a tested migration; authoritative ownership comes from the scoped lease.
- Existing credential use follows ordinary explicit approval. Adding credentials/data to KeePassXC retains the separately gated Face ID/passcode verification policy.

## Implementation order and acceptance

1. **Shared browser safety foundation:** reuse backend live document generations in panel operations; enforce redirect outcomes and sensitive-mode gates; add scoped human-control leases. Test same-URL reload, navigation between approval/input, tab replacement, competing controllers and disconnect/expiry. Auth's existing secure fill path stays covered.
2. **Contextual presentation:** route a fixture blocker to the shared panel with the exact target and inline approval. Test multiple tabs/pending requests, stale notifications, cancelled popup and PWA reconnect. Existing manual Browser and Browser Auth entrypoints remain usable during migration.
3. **Protected human interaction:** implement the least capable useful input/view path and test a synthetic fixture end to end on iPhone. Inspect artifacts for secret exposure, verify failure paths and measure request-to-open / input-to-view latency.
4. **One owner-approved SSO/verification trial:** test human account selection/consent/MFA as available, record browser build/transport/site and outcome. Google/Cloudflare acceptance on Chrome/CDP remains an explicit experiment. Port the OpenClaw-derived extension lane and evaluate it against the same baseline where required.

Success: a task requests verification, the iPhone opens the exact page, the owner completes it, independent verification succeeds and the bounded task resumes. A screenshot or approval click alone records its narrower milestone.

## Handoff record

### 2026-09-11 — step 1 safety foundation (backend, fixture-tested)

Changed files (all in `saturn-agent-browser`, working tree):

- `src/saturn_agent_browser/browser/generations.py` (new) — server-side doc-generation
  store `(lane, target_id) -> {url, seq, generation}`, persisted 0600 beside
  browser state. Same-URL reloads now bump via `bump()`; `observe()` stays
  stable on cheap polling; `evict_stale()` drops closed/replaced tabs.
- `src/saturn_agent_browser/browser/leases.py` (new) — scoped expiring human leases
  `lease_<hex>` bound to operator/run/lane/tab/optional generation (30–3600s,
  default 300). Competing acquire revokes; global control flag kept as compat.
- `src/saturn_agent_browser/browser/sensitive.py` (new) — sensitive-target flag set.
- `src/saturn_agent_browser/browser/view.py` — panel ops now use the generation store
  instead of the URL hash; `navigate_tab` bumps after goto (same-URL reload
  invalidates) and enforces post-navigate redirect allowlist, returning
  `origin_not_allowed` + fresh generation on escape; `capture_snapshot`
  fails safe with `sensitive_blocked` unless human mode + active lease;
  sensitive `navigate_tab` requires an active lease (`lease_required`).
- `src/saturn_agent_browser/cli.py` — `browser lease-acquire|lease-release|lease-list`,
  `browser sensitive-mark|sensitive-clear`.
- `tests/test_browser_safety_foundation.py` (new, 13 tests) —
  same-URL reload bump, URL-change bump, stale eviction, lane isolation,
  lease acquire/validate/release/revoke/mismatch/stale-doc, sensitive
  snapshot gate with/without lease, redirect-escape enforcement,
  same-URL navigate bump. `tests/test_browser_view.py` mocks updated to the
  `(cdp_url, lane)` list signature.

Commands/results: `.venv/bin/python -m pytest tests/ -q` (excluding the
pre-existing broken installed-shim `test_cli_harness.py`, live-httpbin,
option1 browser-login, and specialist suites): **80 passed, 1 skipped**.
`git diff --check` clean. Fixture-only; no live browser, no iPhone yet.

Remaining for step 1 acceptance: Pi capsule endpoints for
lease-acquire/release + sensitive-mark/clear passthrough (done 2026-09-11,
see below); device tests for same-URL reload, approval→input navigation,
tab replacement, competing controllers, disconnect/expiry. Then step 2
(contextual presentation: fixture blocker → shared panel with exact target
+ inline approval).

### 2026-09-11 — step 1 capsule passthrough (fixture-tested)

Pi capsule `saturn-agent-browser-web-ui` now exposes the foundation:

- `fbc-view-client.js` — `acquireLease / releaseLease / listLeases /
  markSensitive / clearSensitive`, HTTP (`/v1/leases`, `/v1/sensitive/*`)
  with CLI fallback (`browser lease-acquire|lease-release|lease-list`,
  `browser sensitive-mark|sensitive-clear`).
- `module.js` — `POST /lease/acquire`, `POST /lease/release`,
  `GET /leases` (sanitized: lane/tab/run/expiry only, no lease ids or
  operator logins), `POST /sensitive/mark`, `POST /sensitive/clear`.
  `/navigate` conflict set extended with `lease_required`.
- Test fake extended with in-memory leases + sensitive set (incl.
  `sensitive_blocked` snapshots); new
  `modules/saturn-agent-browser-web-ui/test/lease-sensitive.test.js`
  (5 tests: invalid tab, acquire→list→release, unknown release 409,
  mark→agent-block→clear→snapshot, invalid mark).

Results: Pi capsule dir `node --test` **11 passed** (4 suites); FBC suite
**80 passed, 1 skipped** (same exclusions as before). `git diff --check`
clean in both trees. Step 1 backend + capsule plumbing complete;
remaining acceptance is on-device (iPhone) runs.

### 2026-09-11 — step 2 contextual presentation (fixture-tested)

FBC `browser/verifications.py` (new): `vh_<hex>` handoffs bound to the
live (lane, tab, generation, origin). Request validates tab exists,
generation matches live (else `stale_document`), origin is http(s) and
equals the live tab origin (else `origin_mismatch`); disconnected browser
rejected. Repeated detection dedupes on (run, tab, generation, reason).
`sync` revalidates pending against the live view (reload → `stale`,
closed tab → `gone`, expiry → `expired`); terminal states sticky;
`resolve` accepts `done`/`cancelled` only from pending. Sanitized views
carry no secrets. CLI: `browser verification-request|list|sync|resolve`.
`tests/test_browser_verifications.py` (12 tests).

Pi capsule: `fbc-view-client.js` request/list/resolve (HTTP + CLI),
`module.js` `POST /verification/request`, `GET /verifications`
(sanitized, `?lane=&state=&sync=`), `POST /verification/resolve`.
`browser-panel.js` renders pending handoffs as a banner: compact
"Show blocked tab" row for other tabs (selects the exact tab on tap),
full card for the shown tab (reason/origin/expects/expiry, linked Auth
approval state fetched inline, Done/Cancel). Pending count badge on the
Browser pill. No automatic foreground open — badge + banner only, focus
preserved. Test fake gained `/v1/verifications*` + `/test/set-tabs`;
`test/verification-handoff.test.js` (6 tests: exact-tab + auth link,
stale/unknown rejection, dedupe, multi-tab listing, popup-gone on sync +
done resolve, reconnect restore via fresh capsule).

Results: Pi capsule dir **17 passed** (5 suites); FBC suite **92 passed,
1 skipped**. `git diff --check` clean. Remaining: on-device runs of the
banner (exact-tab select, inline approval, Done/Cancel, reconnect), then
step 3 (protected human interaction: least-capable input/view path).

### 2026-09-11 — step 3 protected interaction, least-capable path (fixture-tested)

FBC `browser/interact.py` (new), deliberately separate from the agent
runner (`browser/executor.py`): `tap(tab, x, y, generation)` and
`scroll(tab, direction, amount, generation)` require human mode AND a live
lease on (lane, tab) — no lease, no input, closed failure. Generation must
match live; every input bumps the generation (cached frames invalidate).
Post-input re-read reports `origin_changed` instead of blocking: taps may
legitimately land cross-origin (SSO app → IdP), so the panel rebinds
explicitly while secret-delivery paths (which revalidate separately) stay
closed until rebound. Coordinates are remote CSS pixels with an abuse
guard (finite, 0–10000), not a precision promise. CLI: `browser tap`
/ `browser scroll`. `tests/test_browser_interact.py` (8 tests: gates,
bad coords/direction, click+wheel + bump, stale rejection, origin-change
report, sensitive-tab-with-lease allowed).

Pi capsule: `fbc-view-client.js` tapTab/scrollTab (HTTP + CLI),
`module.js` `POST /interact/tap|scroll` (400 validation / 409 gates /
503 backend, sanitized result). `browser-panel.js`: Take control acquires
an input lease for the shown tab, Release control gives it back; tapping
the snapshot posts scaled coords (natural/displayed scale, approximation
noted in code until viewport-sync lands); wheel over the image scrolls
(throttled, clamped 50–2000px); stale/lease-lost produce resync hints,
origin moves report rebind. Test fake gained `/v1/interact/*`;
`test/protected-interaction.test.js` (4 tests: gate order, tap+resync+
replay-stale, bad coords/direction, scroll+resync).

Results: Pi capsule dir **21 passed** (6 suites); FBC suite **100 passed,
1 skipped**. `git diff --check` clean. Known limitation: agent-runner
observation suspension on human lease is policy, not yet backend-enforced
— runner pause on lease is tracked future work. Remaining: on-device
trial of tap/scroll on a synthetic fixture (artifact inspection for
secret exposure, failure paths, request-to-open/input-to-view latency),
then the owner-approved SSO/verification trial (step 4).

### 2026-09-11 — scroll-lag diagnosis + fix (measured)

Owner report (desktop mouse, Brave on Saturn): scrolling unusable, cannot
reach bottom. Measured instead of guessed:

- Backend healthy: `view` 0.34s, `snapshot` 0.87s (452×941 PNG), `scroll`
  end-to-end 1.06s. Chrome idle. Zero interact errors in Pi logs. Scroll
  storm provably arrived (generation counter at doc-41+).
- Baseline client cycle **9.67s / 5 ticks ≈ 1.9s per tick backend-only**
  (scroll + snapshot + resync via CLI); with capsule exec + view call the
  phone saw ~2.5–3s per wheel event, serial. Trackpad/mouse bursts queue
  behind that while infinite-scroll appends DOM per scroll. ~0.7s of every
  backend call is bare python startup (no persistent FBC HTTP service yet).

Fix (Pi capsule, no backend change):

- `wheel-coalescer.js` (new, pure, unit-tested): burst window 700ms merges
  into one scroll (net sign → direction, magnitude clamped 50–2000).
- `browser-panel.js`: wheel events feed the coalescer; each flush refreshes
  the **snapshot only** (was: full view + verification sync per event);
  every 5th input does a full resync; busy-flush folds back into the next
  window instead of queueing. Taps keep the full reload (may navigate).
- Wiring proven by `test/panel-wheel.test.js` (new, jsdom + loader stub
  for the `/core` import): 8 wheel events → exactly 1 scroll POST +
  snapshot refresh + **zero** additional view calls.
  `test/wheel-coalescer.test.js` (6 tests: merge, net sign, clamps,
  invalid input, flushNow, separate bursts).

Results: Pi capsule dir **28 passed** (8 suites); FBC suite unchanged
**100 passed, 1 skipped**. Structural follow-ups retained: persistent FBC
HTTP sidecar (removes ~0.7s startup per op), screencast (removes
snapshot-per-input). Desktop-mouse note: 700ms window suits notch bursts;
tune `windowMs` if flicks feel grouped wrong.

### 2026-09-11 — native-scroll fight + optimistic feedback (live)

Owner: still unresponsive; Brave shows the PWA page's own scrollbar
competing with the snapshot. Two compounding causes confirmed by design
review: (1) wheel events outside the image (or racing it) scrolled the
hosting page natively — the "second scrollbar"; (2) snapshot architecture
has a ~2s/update floor, so every input felt dead until the pixels returned.

Fix (Pi capsule only):

- `style.css`: `.mod-fbc-browser-frame` gets `overscroll-behavior: contain;
  touch-action: none`, body gets `contain` — the frame is a remote view,
  wheel/touch there never scrolls the hosting page.
- Wheel/touch listeners moved from the image to the frame (capture all
  input over the view). Touch drags forward into the same coalescer.
- Optimistic shift: the snapshot translates instantly under finger/wheel
  (clamped ±600px) while the backend round trip runs; `pendingShiftY`
  clears on fresh-image load (and on clear). Taps map back out of the
  shift before scaling, so aim stays true mid-gesture.
- `test/panel-wheel.test.js` extended (frame dispatch, synchronous
  transform assert, touch-drag merge test) with a jsdom + loader stub for
  the `/core` import; `test/stubs/core-module-panel.js` +
  `test/fbc-loader.mjs` are test-only.

Results: capsule dir **29 passed**; deploy + verify OK; fixture moved to
the finite `/large` table page (infinite-scroll has no bottom by design).
Operator screenshot confirms the live panel on the new code. Honest cap:
feel is now instant-motion + ~2s settle; true sub-second tracking needs
screencast (step-3 follow-up, OpenClaw pieces already mapped).

Record changed files, commands/tests, synthetic vs live results, actual-device evidence, remaining limitations and rollback. Keep the shared integration plan's current checkpoint authoritative; this document owns the verification feature details. Runtime code and deployments require a separate implementation step.
