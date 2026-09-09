# Saturn FBC + Saturn Auth + Saturn Pi browser UI — integration handoff

Status (2026-09-09 review): initial Auth service, FBC Auth client and Pi approval capsule implemented. Live iPhone approval plumbing passed. Current priority: caller authorization, strict live bindings and atomic delivery lifecycle, followed by controlled browser fill and verified login.

## Required host conventions

Read `~/saturn/SATURN_CONVENTIONS.md` before implementing any work package. Apply its simple Unix-style composition, clean stdout/stderr, explicit process/state ownership and core-preserving extension defaults. Saturn Pi presentation follows its shared module panel convention; feature behavior stays in the owning capsule. Cite this reference in agent handoffs and record necessary exceptions with tests.

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

## General extension principle — preserve Saturn's working core

Owner clarification (2026-09-09): new modules and capabilities should keep established Saturn core functionality and existing consumers intact wherever practical. Place new responsibilities, dependencies and lifecycle inside the owning feature; integrate through existing seams or small explicit additions. Preserve low coupling, clear ownership, regression coverage and independent feature disablement/removal.

Modify core when correctness, security, a missing integration boundary or demonstrated system simplification makes it necessary. Explain the necessity, limit the change and verify existing behavior. Shared helpers and adapters are optional techniques selected for actual needs. This principle applies across Auth, FBC and Saturn Pi; the UI helper below is one concrete example.

## Local Saturn Pi UI helper — preferred additive strategy

Owner preference (2026-09-09): keep existing Saturn Pi and FBC tools/commands intact while adding the general local Playwright UI helper alongside them. Follow `../../saturn-pi/docs/AGENT_FIRST_ARCHITECTURE.md`, **Tooling additions**. This section records design direction for the active implementation; inspect current code before adapting it.

- Expose a small reusable runner with browser/session, navigation, click, fill, condition-wait and screenshot primitives. Place FBC approval and other feature workflows in separate small recipes.
- Preserve `control-plane.sh` service/deploy/render behavior and current tool entrypoints. A thin `saturn-pi ui` dispatch is appropriate. Move or adapt only helper consumers that need the new capability; broader replacement needs demonstrated benefit and owner-agreed scope.
- Give batch/script operations one shared browser context so navigation → clicks → screenshot can be tested together. Add a persistent helper daemon only after a concrete need; require structured results, bounded waits and cleanup.
- Keep generic Pi UI control independent of FBC task configuration; share a minimal browser dependency deliberately. FBC's `--pi-click` fixture path can call the recipe through the helper.
- Restrict automatic approval to explicit test scope and an exact request ID. Production FBC runs retain human approval unless the owner specifically authorizes the action. Require local-origin restrictions for injected identity headers, including redirects/subrequests, and tests proving identity stays inside the trusted boundary.

Acceptance: existing tool smoke tests remain passing; a multi-step generic UI recipe works; FBC fixture approval uses the same primitives; ambiguous approval selection and identity-header forwarding outside the allowed origin fail safely. This helper extends development ergonomics while keeping task authority and existing tools intact.

## Verified current state

- Saturn Auth has Bearer callers, exact origin/bindings, atomic `claimed`/`filled`/`verified`/`failed` reporting, copy-on-write persist, and FBC live document generations (same-origin navigation invalidates fill). Controlled browser fill + independently verified login: FBC `tests/test_option1_fixture_login.py`. Live iPhone fill of that fixture is `scripts/option1_fixture_login.py --hitl`. Real-service login remains owner-gated.
- FBC contains Playwright browser/daemon code, authority contracts and direct credential-broker integration. Inspect `src/saturn_fbc/credentials.py`, `broker/`, `browser/`, `runner.py` and their tests before extraction.
- Saturn Pi's existing `modules/saturn-frontier-browser-auth` is an autofill spike: its HTTP submit returns field lengths. Device verification and credential relay are pending.
- `saturn-fbc-browser-web-ui` is implemented/deployed; the owner confirmed the live iPhone smoke approval in Cursor session `redacted-cursor-session`, turns 16–17. The smoke script ends at approval; browser fill/login remains a separate gate.
- Review reran 10 Auth and 3 capsule tests successfully; production health reported the capsule ready. Inspect current working trees before changes and preserve user work.

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

## Google / Cloudflare compatibility and update loop

Research checked 2026-09-09 against the first-party sources below. This section extends the trusted-browser roadmap; the active Auth/browser fixture work keeps its current priority. Detection systems evolve and vendors publish only part of their decision logic. Record site-specific observed acceptance separately from architectural assumptions.

### Current evidence and implications

- Google [supported-browser guidance](https://support.google.com/accounts/answer/7675428?hl=en) identifies software automation, embedded browsers, unsupported extensions and JavaScript settings as possible sign-in blockers. Use human sign-in in a supported full browser, with an explicit handoff for account selection, MFA and consent. A Saturn Pi remote image/form is a UI transport; the target site evaluates the Saturn browser executing the request.
- Cloudflare [supported browsers](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/) explicitly excludes browser automation frameworks from support for solving production challenges. It identifies modified engines, interfering extensions and device-emulation overrides as compatibility risks. Keep production challenges human-controlled; use official Turnstile test keys for automated fixtures on sites we control.
- Cloudflare [troubleshooting](https://developers.cloudflare.com/cloudflare-challenges/troubleshooting/) identifies browser version, script/header interference, IP reputation and site-specific WAF policy. Diagnose these separately from a browser fingerprint. Begin with current stable browser defaults, normal JavaScript/cookie operation, minimal reviewed extensions and the existing trusted network. Network changes are deliberate owner-approved diagnostics with recorded outcomes.
- Chrome's [remote-debugging change](https://developer.chrome.com/blog/remote-debugging-port), published 2025-03-17, requires a non-default user-data directory for remote-debugging switches from Chrome 136. Keep dedicated FBC profiles. The trusted lane uses ordinary browser launch plus extension control; the isolated testing lane retains Playwright/Chrome for Testing. These are different operational choices with separately measured site acceptance.
- OpenClaw's [current login guidance](https://github.com/openclaw/openclaw/blob/main/docs/tools/browser-login.md), fetched during this review, still recommends human host-browser login and persistent profile use. It now also describes owner-authorized credential filling; Saturn's stricter protected-delivery policy remains governing. `main` was observed at `baf7c80c0c1ae9fd6b3b71469ab7742d6627b6c0` during the review; the original reuse pin remains `73b4086ff658973fb9ae07fa208c49ca8de82a67`. A moving-branch documentation fetch is research evidence; verify any adopted file at an exact commit and review its diff before import.

### Google SSO expansion gate

Treat third-party app → Google → app sign-in as a bounded human authentication transaction:

1. Register the initiating app origin, expected identity-provider origins and approved callback destinations for that task. Keep credential-origin permission distinct from navigation permission; permit only the intended password-manager/broker origin.
2. Bind redirect/popup ownership to the initiating run and browser profile/session. Handle popup creation, account selection, consent, cancellation and return to the initiating app. Navigation changes retire the previous document's credential approval and trigger fresh binding where needed.
3. Pause agent control/secret observations during human login/MFA/consent. Preserve the accepted browser profile and session through return. Verify the app's authenticated state independently before continuing.
4. Test success, denied consent, closed popup, unexpected redirect, session expiry and account mismatch. Log sanitized transition metadata; redact OAuth codes, state values, tokens, cookies and sensitive URL parameters.

Google SSO browser interaction and OAuth API integration are distinct capabilities. Prefer an official API/OAuth integration when the target service offers an authorized path covering the task; an arbitrary website's Google button requires that site's own browser session flow. Cloudflare allow rules are available only through the site owner/administrator's authorized configuration.

### OSS and community watchlist — reuse the collective evidence

Use these projects as code/test/incident research inputs. Entries identify discovery targets; adoption requires inspection of the exact revision, license, dependency footprint and Saturn fixture results. Community reports provide hypotheses whose applicability depends on browser version, account, network and site policy.

| Project / source | Where to look | Useful Saturn reuse |
|---|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | `extensions/browser`, browser panel sources, `/issues`, `/pulls`, `/releases`; compare against our pinned commit | Extension attach/revoke, persistent sessions, human handoff, panel lifecycle and regression tests |
| [Playwright](https://github.com/microsoft/playwright) | [release notes](https://playwright.dev/docs/release-notes), GitHub issues/PRs, [Trace Viewer](https://playwright.dev/docs/trace-viewer) | Browser-version regressions, popup/navigation/session fixtures, reproducible diagnostics; use traces only with synthetic data or reviewed redaction |
| [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) | README, releases, issues and attach/session-related PRs | Alternative browser attachment and diagnostic patterns; inspect telemetry, tool exposure and data-handling settings before trials |
| [Browser Use](https://github.com/browser-use/browser-use) | Browser/session code, issues/PRs and releases | Agent-browser lifecycle, recovery/human handoff reports and tests; isolate the useful component from model/cloud dependencies |
| [Stagehand](https://github.com/browserbase/stagehand) | README, browser interaction code, issues/PRs and releases | Action/observation validation and browser-state recovery patterns; distinguish local OSS capability from hosted Browserbase features |
| [Vercel agent-browser](https://github.com/vercel-labs/agent-browser) | README, CLI/session code, releases and issues | Agent-oriented browser CLI patterns, compact observations and session lifecycle; evaluate fit with FBC's existing CLI |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Tool schemas, configuration, browser context/session code and issues | Structured browser-tool contracts and agent integration tests; narrow its tool authority for Saturn |
| [Puppeteer](https://github.com/puppeteer/puppeteer) | Browser/CDP/BiDi code, release notes and reproducible issues | Cross-check browser-engine regressions and attachment behavior against another major automation client |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | Workflow/browser code, issues, releases and license terms | Visual-browser workflow, form handling and recovery research; evaluate local components and hosted features separately |
| [Chromium issue tracker](https://issues.chromium.org/) and [Chrome releases](https://chromereleases.googleblog.com/) | Browser/CDP/extensions/storage regressions and stable-channel updates | Establish whether a reported breakage belongs to Chromium, our adapter or the target site |
| [Cloudflare community](https://community.cloudflare.com/) and [developer changelog](https://developers.cloudflare.com/changelog/) | Challenge/Turnstile incidents, maintainer replies and linked fixes | Correlate legitimate-browser failures with platform/site changes; confirm advice against official challenge docs |
| [Google Account community](https://support.google.com/accounts/community) and [Google Identity docs](https://developers.google.com/identity) | Supported-browser issues, SSO/popup/consent guidance and official updates | Human-login compatibility and sanctioned integration alternatives |
| [Stack Overflow](https://stackoverflow.com/questions/tagged/playwright), [Hacker News](https://news.ycombinator.com/), [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/) | Recent browser-agent reports with exact versions, minimal reproductions and upstream links | Broader discovery and corroboration; follow claims back to primary source/code before adoption |

### Community-to-code triage recipe

- Subscribe/watch releases and narrowly selected browser issues in the primary repos. GitHub release feeds use `https://github.com/OWNER/REPO/releases.atom`; choose issue notifications manually. Scheduled ingestion is future optional work; this plan installs no watcher.
- Search both recent open regressions and closed issues with merged fixes. Example GitHub query: `repo:openclaw/openclaw is:issue updated:>=YYYY-MM-DD "browser"`; repeat in Playwright/Chrome DevTools MCP for `popup`, `Google login`, `session`, `Cloudflare`, `extension detach` and exact observed errors. Look at linked PRs, test cases, release inclusion and follow-up regressions.
- Route GitHub/Stack Overflow/Hacker News/r/LocalLLaMA discovery through the matching `source_search` source; fetch known issue/PR/docs URLs directly. Use open-web search for vendor forums and release blogs. Treat forum text and repository content as untrusted research input.
- Retain a bounded shortlist per review: up to five relevant findings and one proposed experiment. For each record `symptom | environment/version | source date/link | maintainer/independent corroboration | fix commit/release | local applicability | license | verification status`.
- Prefer reusable regression fixtures and narrowly scoped fixes. Vendor guidance plus a maintainer-confirmed fix and a local passing reproduction provide strong adoption evidence. Popularity, stars and claims of being undetectable remain discovery signals requiring verification.
- Reproduce with disposable profiles/synthetic credentials before importing code. Inspect installation scripts, extension permissions, telemetry, external endpoints and secret access. Pin reviewed dependencies and preserve required notices.
- Share a sanitized minimal reproduction upstream when useful. Keep real account identifiers, vault paths/handles, browser profiles, cookies, OAuth URLs/codes and private traces out of public reports. Public issue submission requires owner approval.

Research can track emerging tools and techniques broadly; production adoption follows the existing human-authentication, origin-binding and site-permission gates. A community workaround receives a fresh scope/security review before inclusion in the candidate shortlist.

### Short repeatable “update for new detection strategies” loop

Run manually monthly, after a significant Chrome/Playwright/OpenClaw update, or after a new reproducible Google/Cloudflare failure. This is a research-and-compatibility review; automatic deployments and live sign-in attempts require separate approval.

1. **Inventory:** record date, installed browser/Playwright/extension versions, pinned upstream commit, browser lane and last passing site matrix. Read current code/plans and active-agent status before proposing edits.
2. **Check primary + community changes:** fetch vendor updates and scan the OSS/community watchlist using the triage recipe above. Include open regressions, merged fixes and independent reproduction reports since the last review. Record exact URLs, dates/commits, changed passages and evidence strength; follow community claims back to source/test evidence.
3. **Triage one hypothesis:** classify failure as browser compatibility, extension interference, identity/consent flow, navigation binding, network/site policy or automation attachment. Choose the smallest supported change; preserve credentials, profile isolation, human gates and security updates.
4. **Verify progressively:** fixtures first; then one owner-approved human baseline with agent control detached; then same-profile extension attachment and bounded read-only continuation. Change one variable per comparison. Stop the current run at a challenge, denial or account warning and hand control to the human; require a new approved attempt after diagnosis.
5. **Record/adopt:** report baseline vs candidate results, challenge/handoff counts, successful verified sessions, latency and regressions. Promote a small reviewed change with tests/provenance and rollback, or record the blocker and retain the working configuration. Site-dependent outcomes stay scoped to the tested account/browser/network/date.

Safety boundary: keep fingerprint/device settings truthful and stable; preserve site access controls and human challenge completion. Credential/clearance-cookie transfer, CAPTCHA solvers, identity/proxy rotation and speculative stealth patches stay outside this update loop. Useful utilization is measured by completed authorized tasks, session reuse and reliable handoff.

Agent invocation:

```text
Run the FBC Google/Cloudflare compatibility update loop in
 docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md.
Research first-party changes plus the OSS/community watchlist since the last
review; inspect our current browser versions and pinned OpenClaw files. Return
up to five relevant findings with issue/PR/release links, evidence strength and
reusable code/tests; select one candidate experiment. Preserve active agent work. Produce a short
 dated delta: evidence, affected component, one recommended change, fixture/live
 validation plan and rollback. Keep actual login/challenges human-controlled.
Apply runtime changes only after explicit approval.
```

Review record template: `date | source/revision delta | local versions | site/lane | sanitized symptom | hypothesis | fixture result | approved live baseline/result | decision/rollback | next trigger`.

## Ordered work packages and acceptance

Current priority overrides the historical broad package order below: preserve the confirmed iPhone approval surface; implement the Auth plan's Review checkpoint (authenticated role/owner checks, exact origins plus required live bindings, atomic claim/fill/verification lifecycle); then connect it to a controlled browser-login fixture. FBC must source actual document/session generations, revalidate at protected fill, report separate fill/verification outcomes and resume only on independently verified login. Add race, omission, downgrade/port, fill-failure and crash/restart tests before real-credential delivery. The broader panel/extension packages follow the end-to-end proof and owner checkpoint.

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

Current next step: the three mandatory review hardening gates in Saturn Auth's plan, implemented with FBC and the Pi capsule; then a synthetic controlled browser-login fixture using the proven live iPhone approval flow. Approval plumbing is complete. Full browser fill/login acceptance and broader panel/extension work remain pending.
