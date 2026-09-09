# Trusted-browser refactor and reconfiguration plan

**Project:** Saturn Frontier Browser Control (FBC)  
**Status:** approved direction; implementation pending  
**Primary target:** improve success on Indeed and similarly bot-sensitive sites through a normal persistent browser session, human authentication, and extension-based control  
**Audience:** implementation agents, reviewers, and operators

---

## Current integration direction (2026-09-09)

Read [OPENCLAW_INTEGRATION_BUILD_PLAN.md](docs/OPENCLAW_INTEGRATION_BUILD_PLAN.md) first. It owns current cross-project build order, pinned upstream source evidence, shared security bindings and acceptance gates. FBC works alongside **Saturn Auth** and the **`saturn-fbc-browser-web-ui`** Saturn Pi capsule.

The two-lane design below remains the target. Its bespoke extension/protocol tree, native-messaging action transport, HDMI-only login ownership and phase order are earlier proposals superseded where the shared plan specifies OpenClaw reuse and remote UI integration. Preserve reusable upstream extension/relay code and its tests, with a dedicated Saturn extension identity and selected-tab access. Evaluate an FBC-owned JS/TS sidecar before rewriting upstream machinery in Python. Native messaging handles bootstrap; authenticated relay transport carries browser operations.

HDMI remains the initial sensitive-login/challenge surface. The Pi capsule supplies protected Auth forms and ordinary browser viewing/control; any remote sensitive viewer requires the shared plan's separate security review. Saturn Auth owns credential approval/provider coordination; FBC owns protected browser adaptation, verification and task continuation.

## 1. Goal

Convert Saturn FBC from a single Playwright-launched Chromium lane into a two-lane browser system:

1. **Isolated automation lane** — retain the current Playwright browser for fixtures, disposable sessions, and ordinary low-risk forms.
2. **Trusted browser lane** — use a stable Chrome-family browser, a dedicated persistent profile, human login/challenge handling, and a local extension relay for subsequent bounded agent actions.

The trusted lane should preserve the browser session that Cloudflare accepted. Saturn’s authority contracts, domain checks, trace records, credential isolation, and human Submit boundary remain active above both lanes.

## 2. Why this refactor exists

### Observed on Saturn on 2026-09-04

- Google SSO rejected the current Playwright Chromium tenant.
- Indeed-native email/password login succeeded.
- Indeed then presented a persistent Cloudflare “Verify you are human” loop after a manual challenge attempt.
- The recorded FBC login run stopped at step 1 with `stop_reason: captcha`:
  - `traces/20260905T010707Z-1c7f483e/trace.jsonl`
- An operator reported that the same Indeed workflow succeeded through the OpenAI Codex desktop app’s browser on Linux.
- The Saturn browser service was stopped after the test.

### Current browser shape

- Dependency: Playwright 1.62.
- Browser: Playwright **Chrome for Testing 151.0.7922.34**.
- Profile: `~/.local/share/saturn-frontier-browser-control/chromium/`.
- Launch: `playwright.chromium.launch_persistent_context(...)`.
- Persistent daemon: CDP exposed on `127.0.0.1:9222` from browser startup.
- Run control: `connect_over_cdp(...)`.
- Viewport: fixed `1280×720`.
- Stable Google Chrome/Chromium package: absent during inspection.
- Host Firefox: available.

Relevant implementation:

- `src/saturn_fbc/browser/profile.py`
- `src/saturn_fbc/browser/daemon.py`
- `src/saturn_fbc/browser/session.py`
- `src/saturn_fbc/browser/executor.py`
- `src/saturn_fbc/browser/capture.py`
- `src/saturn_fbc/browser/interceptor.py`
- `src/saturn_fbc/cli.py`

### OpenAI reference architecture

OpenAI publicly documents two browser paths:

- The Codex/ChatGPT built-in browser uses its own persistent profile and supports direct sign-in. Full CDP access is an optional Developer-mode capability requiring explicit approval.
- The browser extension controls an existing signed-in Chrome, Edge, Brave, Opera, or Vivaldi tab.

References:

- <https://developers.openai.com/codex/app/browser>
- <https://developers.openai.com/codex/chrome-extension>

Public documentation leaves the built-in browser engine, anti-bot modifications, and partner allowlisting unspecified. The strongest reproducible architectural difference is a normal browser session whose login and challenge occur before agent control.

## 3. Target architecture

```text
                         Frontier / visual specialist (UI-Venus)
                               |
                     Authority contract cage
                  allowlist | action policy | trace
                               |
                    BrowserBackend interface
                         /              \
                        /                \
       isolated-playwright          trusted-extension
       -------------------          -----------------
       Chrome for Testing           Stable Chrome/Brave
       dedicated test profile       dedicated Indeed profile
       Playwright launch             ordinary browser launch
       CDP daemon                    human login/challenge
       fixtures/general forms        extension relay after warmup
```

### Lane A: `isolated-playwright`

Keep the current implementation for:

- local fixtures;
- httpbin and selenium.dev smoke tests;
- disposable, low-risk accounts;
- websites that accept the current Playwright surface.

### Lane B: `trusted-extension`

Add a dedicated stable-browser profile for:

- human Indeed login;
- Cloudflare challenge completion;
- persistent account cookies and storage;
- agent observation and bounded form filling through an extension relay;
- human review and final submission in the same tab.

The browser starts as an ordinary user-launched process. Login and challenge handling happen while agent control is detached. The extension connects only after the operator marks the session ready.

## 4. Architectural decisions

| Decision | Selected approach | Reason |
|---|---|---|
| Browser executable | Stable Google Chrome first; Brave as fallback | Closest match to OpenAI’s documented extension path |
| Browser profile | Dedicated FBC trusted profile | Preserves isolation from the daily browser and keeps cookies persistent |
| Login ownership | Human on HDMI | Aligns with site security checks and keeps credentials outside model context |
| Agent connection | Manifest V3 extension plus authenticated local relay | Preserves the accepted live tab without automation launch flags |
| Transport | Native Messaging preferred; authenticated loopback WebSocket fallback | Native Messaging provides narrow local process access |
| Session transfer | Keep cookies inside the trusted profile | Preserves browser-bound storage and reduces fragile cookie migration |
| CAPTCHA handling | Pause control and route to the human | Maintains policy and site boundaries |
| Submission | Human confirmation and click | Preserves the existing authority contract |
| Playwright lane | Retained as a separate backend | Protects working tests and ordinary automation workflows |

## 5. Backend interface refactor

The current `BrowserSession` directly depends on Playwright `Page` and `BrowserContext`. Introduce a backend-neutral interface before adding the extension.

Proposed files:

```text
src/saturn_fbc/browser/backends/
├── __init__.py
├── base.py
├── playwright_backend.py
└── extension_backend.py
```

Proposed protocol:

```python
class BrowserBackend(Protocol):
    backend_id: str

    def start(self) -> None: ...
    def status(self) -> dict: ...
    def current_url(self) -> str: ...
    def current_title(self) -> str: ...
    def observe(self) -> BrowserObservation: ...
    def execute(self, action: BrowserAction) -> ActionResult: ...
    def capture_screenshot(self, destination: Path) -> Path: ...
    def close(self) -> None: ...
```

`BrowserSession` should own policy, tracing, and stop reasons. Each backend should own browser-specific capture and actuation.

### Preserve these layers above the backend

- `AuthorityContract`
- `intercept_action(...)`
- origin allowlist enforcement
- blocked-action enforcement
- password-field policy
- trace writing and screenshot redaction
- success verification
- CAPTCHA detection and stop reason
- pre-submit boundary

## 6. Trusted extension design

Proposed new tree:

```text
extension/
├── manifest.json
├── service-worker.js
├── content-script.js
├── options.html
└── README.md

src/saturn_fbc/extension/
├── __init__.py
├── protocol.py
├── relay.py
├── native_host.py
└── state.py

config/
├── trusted-browser.env
└── native-messaging-host.template.json

scripts/
├── install-trusted-browser-profile.sh
├── install-extension-native-host.sh
└── launch-trusted-browser.sh
```

### Extension command vocabulary

Keep the protocol typed and narrow:

- `status`
- `get_page_state`
- `capture_visible_tab`
- `click_index`
- `type_index`
- `select_index`
- `scroll`
- `navigate`
- `pause_control`

The relay should reject arbitrary JavaScript and arbitrary shell commands. DOM indexing may supplement screenshots as hints; the visual specialist loop is screenshot-first (Venus `venus_browser.py` pattern).

### Extension security requirements

- Dedicated extension ID and dedicated browser profile.
- Native Messaging host allowlisted to that extension ID.
- Loopback fallback bound to `127.0.0.1` with a random 256-bit session token stored mode `0600`.
- Contract domain checked in Python and again inside the extension before each action.
- Active-tab URL included in every response.
- Password fields represented as redacted metadata.
- Secret values excluded from extension logs, Python logs, screenshots, and model context.
- Operator-visible connected/paused indicator.
- Challenge detection automatically changes the connection to `human_required`.
- Final-submit controls remain blocked by the authority contract.

## 7. Configuration model

Add:

```bash
SATURN_FBC_BROWSER_BACKEND=isolated-playwright
SATURN_FBC_TRUSTED_EXECUTABLE=/usr/bin/google-chrome-stable
SATURN_FBC_TRUSTED_PROFILE=~/.local/share/saturn-frontier-browser-control/trusted-chrome
SATURN_FBC_TRUSTED_RELAY=native-messaging
SATURN_FBC_TRUSTED_STATE=~/.local/share/saturn-frontier-browser-control/trusted-browser-state.json
```

Add an optional contract field:

```json
{
  "browser_backend": "trusted-extension"
}
```

Accepted values:

- `isolated-playwright`
- `trusted-extension`

Existing contracts default to `isolated-playwright` for backward compatibility. Indeed login and Easy Apply contracts should select `trusted-extension` after the trusted lane reaches its acceptance gates.

## 8. Proposed CLI

```bash
# Inspect both lanes
saturn-frontier-browser-control browser profiles
saturn-frontier-browser-control browser trusted status

# Launch ordinary stable browser with dedicated profile
saturn-frontier-browser-control browser trusted start

# Human logs in and completes any challenge on HDMI

# Connect extension relay after the accepted session is warm
saturn-frontier-browser-control browser trusted session-ready

# Pause agent control for a human gate
saturn-frontier-browser-control browser trusted pause

# Resume after human review
saturn-frontier-browser-control browser trusted resume

# Close trusted browser and relay
saturn-frontier-browser-control browser trusted stop

# Run a bounded contract in the trusted tab
saturn-frontier-browser-control run \
  --backend trusted-extension \
  --contract contracts/indeed-easy-apply-JOBKEY.json
```

The current `browser start|stop|status|restart` commands continue to address the isolated Playwright daemon during migration. A later compatibility pass may expose both under explicit profile names.

## 9. Phased implementation

Every phase has a gate. Record results in this file or a linked test report before continuing.

### Phase 0 — Baseline experiment

1. Install a stable Chrome-family browser through the system package path.
2. Create a fresh dedicated trusted profile.
3. Launch it with ordinary browser flags, agent relay detached, and a normal viewport.
4. Human completes Indeed-native login and Cloudflare.
5. Human navigates several job and account pages.
6. Close and reopen the profile; verify session persistence.

**Gate:** Indeed remains usable through normal navigation and profile restart.

**Failure interpretation:** A challenge in this phase points toward account, network, browser-profile reputation, or broader site policy. Preserve screenshots and timestamps; pause implementation until the baseline is understood.

### Phase 1 — Backend abstraction

1. Add `BrowserBackend` and observation/result data classes.
2. Move existing Playwright-specific behavior into `PlaywrightBackend`.
3. Keep public CLI behavior stable.
4. Run the full existing test suite.

**Gate:** Existing local, httpbin, selenium, broker, daemon, contract, and CLI tests pass through `isolated-playwright`.

### Phase 2 — Read-only extension relay

1. Build the MV3 extension and local relay.
2. Implement status, URL/title, DOM digest, and screenshot capture.
3. Add connected/paused UI state.
4. Test only on local fixtures and httpbin.

**Gate:** The trusted backend can observe a page and produce a redacted trace without write actions.

### Phase 3 — Bounded actions on fixtures

1. Implement click, type, select, scroll, and navigate.
2. Route every action through the existing contract interceptor.
3. Exercise final-submit blocking and domain-change stopping.
4. Exercise password-field redaction.

**Gate:** Local fixture tests match the Playwright backend’s safety behavior.

### Phase 4 — Warm-session Indeed observation

1. Human starts and authenticates the trusted browser.
2. Human marks the session ready.
3. Agent performs read-only observation and one bounded navigation.
4. Challenge appearance triggers `human_required` and pauses the relay.

**Gate:** The accepted Indeed session survives extension connection and read-only use.

### Phase 5 — Indeed draft fill

1. Use one Easy Apply contract with fake or explicitly approved profile data.
2. Fill fields in draft mode.
3. Stop on résumé upload, challenge, review, or Submit.
4. Human reviews the complete trace and browser state.

**Gate:** Form fields are correct, session remains usable, and the Submit boundary holds.

### Phase 6 — Operational hardening

1. Add user-systemd relay service.
2. Add crash recovery and stale-state cleanup.
3. Add install/uninstall scripts and extension version checks.
4. Add status health checks and clear operator messages.
5. Add a rollback command that disables the extension and returns FBC to the isolated backend.

**Gate:** Restart, update, pause/resume, and rollback tests pass.

### Phase 7 — Optional experiments

Evaluate these only after the trusted extension lane has measured results:

- Patchright with stable Chrome in an isolated profile.
- Manual bootstrap followed by CDP attachment.
- Brave as the trusted executable.
- Firefox extension parity.
- Narrow cookie import as a recovery tool.

## 10. Test plan

### Unit tests

- backend selection and defaults;
- extension protocol schema;
- token and origin validation;
- active-tab domain mismatch;
- action allowlist and blocked actions;
- password-field redaction;
- CAPTCHA/challenge transition to `human_required`;
- final-submit interception;
- state-file permissions and stale-state handling.

### Integration tests

- local fixture observation through both backends;
- equivalent numbered DOM digest for key form controls;
- click/type/select through the trusted relay;
- browser restart with profile persistence;
- extension disconnect/reconnect;
- relay crash while the browser remains open;
- contract trace completeness.

### Live tests

Use this order:

1. `file://` fixture
2. `https://httpbin.org/forms/post`
3. `https://www.selenium.dev/selenium/web/web-form.html`
4. Indeed read-only page
5. Indeed Easy Apply draft

Live tests use human supervision, low action counts, ordinary pacing, and a single account.

## 11. Acceptance criteria

The conversion is complete when:

1. `isolated-playwright` retains all current passing behavior.
2. `trusted-extension` launches a dedicated stable-browser profile without Playwright launch or remote-debugging flags.
3. Human authentication and challenge completion occur while agent control is paused.
4. The extension attaches to the already-authenticated tab and preserves the accepted session.
5. Visual specialist receives screenshots and executes bounded actions through the same contract cage (Venus parse/execute).
6. Domain changes, password fields, CAPTCHA, uploads, and Submit produce the expected stop or human gate.
7. Cookies stay inside the trusted browser profile.
8. Traces remain useful and redact sensitive content.
9. Browser and relay status are visible through the CLI.
10. A documented rollback restores the isolated-only configuration.

## 12. Failure modes and responses

| Failure | Response |
|---|---|
| Stable browser baseline receives the Cloudflare loop | Stop the experiment; collect page, timestamp, browser version, profile age, and network path |
| Extension connection triggers a new challenge | Pause relay; compare extension enabled/disabled runs; reduce permissions and action surface |
| Challenge appears during a run | Emit `human_required`, detach control, preserve tab and trace |
| Browser profile becomes repeatedly challenged | Retire that profile from live testing and create a fresh dedicated profile after a cooldown |
| Extension loses connection | Stop actions, keep browser open, report relay health |
| Active tab leaves the contract domain | Reject action and emit `domain_change` |
| Page structure defeats indexed DOM actions | Escalate to the frontier or human; visual specialist remains a later bounded backend |
| Stable Chrome update changes extension behavior | Pin tested minimum version and rerun the integration suite |
| Native Messaging install fails | Use authenticated loopback transport for the development spike |

## 13. Scope boundaries

Initial conversion scope includes:

- one dedicated trusted browser profile;
- human authentication and challenge handling;
- extension-based observation and bounded actions;
- Indeed Easy Apply draft filling;
- human-controlled upload and submission;
- existing contract, trace, and credential policies.

Later scope includes:

- cross-browser extension parity;
- multi-profile orchestration;
- cookie migration tools;
- unattended consequential actions;
- visual-coordinate control;
- anti-detection patch experiments.

## 14. Rollback

1. Stop the trusted relay.
2. Disable the FBC trusted-browser extension.
3. Set `SATURN_FBC_BROWSER_BACKEND=isolated-playwright`.
4. Keep the trusted profile directory for operator-controlled recovery.
5. Run the local and live smoke tests against the isolated backend.
6. Record the failed phase and evidence in this plan.

Rollback should preserve both browser profiles and all traces.

## 15. Agent handoff protocol

An implementation agent should:

1. Read this file, `README.md`, `REFACTOR_PLAN.md`, `docs/indeed.md`, and `docs/browser-profiles.md`.
2. Inspect `git status --short`; the repository contains ongoing user changes.
3. Identify the first incomplete phase and implement only that phase.
4. Preserve current CLI compatibility and the isolated Playwright lane.
5. Keep each write batch focused and add tests with the implementation.
6. Run `git diff --check` and the relevant pytest targets.
7. Update this file with:
   - phase status;
   - changed files;
   - commands run;
   - test results;
   - observed browser result;
   - remaining risks.
8. Leave live Indeed submission and challenge handling with the human operator.

### Handoff prompt

```text
Continue the Saturn Frontier Browser Control trusted-browser conversion.
Read TRUSTED_BROWSER_REFACTOR_PLAN.md and the linked project docs, inspect the
current working tree, and implement only the first incomplete phase. Preserve
all existing user changes and the isolated Playwright backend. Add focused
tests, run the documented verification, and update the plan with exact results.
Keep authentication, Cloudflare challenges, uploads, and final submission under
human control.
```

## 16. Current next step

Execute **package 1 — Inventory + contracts + reuse spike** in the shared integration plan. Perform the stable-browser human baseline before live trusted-extension automation; retain that phase's measured acceptance gate. Record exact results and revise the earlier detailed implementation layout after the upstream dependency/transport decision.
