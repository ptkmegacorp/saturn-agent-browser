# Saturn frontier browser control — build plan

**Status:** plan only (2026-09-04). Spec: [README.md](./README.md).  
**Host:** Saturn, RTX 3060 12 GB, `DISPLAY=:0`. This project is a **GPU tenant**: pig-stack profile `saturn-frontier-browser-control` owns `:8091` for the duration of a run.

Constrained browser subsystem. Luna plans and writes. **Spark-X2.5 4B** drives structured Playwright actions in V1. Visual/browse-trained specialist is an **open slot**. Playwright is the only actuator. KeePassXC holds secrets. Humans own submit.

---

## What we are *not* building in V1

- Do not point any model at `Personal.kdbx`. Agent vault + broker only.
- Do not generate passwords in Luna, Spark, or a specialist.
- Do not bypass CAPTCHA, anti-bot, or KeePassXC unlock UX.
- Do not load a visual CUA until the specialist slot is explicitly filled (still under this GPU tenant).
- Do not leave HUD running during a run: switch **to** this pig-stack profile, **`pig-stack overlay hide`**. Leave profile switched after exit/abort (no auto-restore).
- Do not give Cursor click/type/screenshot tools (frontier client uses the JSON CLI only).

---

## Isolated Chromium tenant

This project does not share a browser with anything else on Saturn.

| Resource | Designated location |
|----------|---------------------|
| Persistent profile | `~/.local/share/saturn-frontier-browser-control/chromium/` |
| Playwright browser binaries | `~/.local/share/saturn-frontier-browser-control/playwright-browsers/` |
| Env | `config/chromium.env` (sourced by all launch scripts) |
| i3 / WM class | `SaturnFrontierBrowser` |

Hard rules for every launch:

1. Set `PLAYWRIGHT_BROWSERS_PATH` to this project’s browsers dir. Do **not** use `~/.cache/ms-playwright`.
2. Playwright **bundled** Chromium via `launch_persistent_context(user_data_dir=...)`. Never `channel="chrome"` / `chromium`, never `/usr/bin/chromium-browser`.
3. `user_data_dir` is **only** the path above.
4. Args include `--class=SaturnFrontierBrowser`.
5. KeePassXC-Browser only if `CREDENTIAL_FILL=keepassxc-browser`, and only in **this** user-data dir.

`scripts/install-agent-profile.sh` creates the directories (mode `0700`). It does not launch a browser.

---

## GPU tenant (this project owns the card)

While `saturn-frontier-browser-control` is running, **nothing else** should hold llama-server. HUD overlay is **hidden**. HUD Pig, Ornith, TMax, etc. are displaced.

| Piece | This project |
|-------|----------------|
| pig-stack profile | `saturn-frontier-browser-control` |
| Host profile file | `~/.config/pig-stack/profiles/saturn-frontier-browser-control.env` |
| Project pin | `config/pig-stack.env` |
| Recipe / GGUF | same Spark-X2.5 4B Q4 as `spark25q4`, **separate session dirs** |
| Endpoint | `127.0.0.1:8091` (the only llama-server) |
| pig-io sessions | `~/.pig/agent/sessions/pig-io/saturn-frontier-browser-control` (not HUD `spark25q4`) |

Run lifecycle:

```text
1. Record current pig-stack profile; pig-stack overlay hide
2. pig-stack switch saturn-frontier-browser-control
3. Observe/act loop against :8091
4. (no auto-restore — profile stays on saturn-frontier-browser-control)
```

Do not run ComfyUI / doc-tts / a second llama on the 3060 during a run. Specialist (later) is another profile **in this tenant**, not a parallel `:8000`.

---

| Constraint | Implication |
|------------|-------------|
| 12 GB VRAM | One GGUF. This tenant’s Spark (or later specialist recipe). |
| Spark is text-only | Default digest: numbered a11y (`OBSERVATION_MODE`). CSS/mixed are toggles. Screenshots in traces only. |
| Specialist slot | Separate pig-stack profile in this tenant, or a recipe swap; still exclusive GPU. |
| KeePassXC installed, vaults empty | Broker phase 4. |
| Luna via `saturn-agent-dispatch ask` | Frontier is `gpt-5.6-luna` (CPU/API, not the 3060). |
| Headed Chromium | This project’s Chromium only. |

---

## Target loop (V1)

```text
Luna (saturn-ask)
  → TaskPlan + AuthorityContract (JSON)
Playwright
  → this project’s Chromium
  → numbered a11y snapshot (default; mode is config)
Spark-X2.5 4B  (:8091 saturn-frontier-browser-control)
  → one structured BrowserAction
Playwright
  → allowlist / budget / no-submit interceptor
  → execute or reject
  → verify
  → continue | escalate to Luna | stop (…)
Credential broker (privileged, default fill)
  → Agent.kdbx; in-process Playwright fill; handle/ok/fail only
  → toggle CREDENTIAL_FILL=keepassxc-browser if needed
Human
  → unlock vault, approve fill, approve any submit
```

**Later (optional specialist):** another pig-stack profile in this tenant → screenshot → `click(x,y)` → same Playwright mapper. V1 escalates to Luna instead.

---

## Repo layout (create as phases land)

```text
saturn-frontier-browser-control/
├── README.md
├── BUILD_PLAN.md
├── config/chromium.env
├── config/pig-stack.env
├── config/observation.env        ← a11y_indexed default; css|mixed later
├── config/credentials.env        ← CREDENTIAL_FILL=broker (toggle keepassxc-browser)
├── contracts/live-httpbin-form.json
├── src/saturn_fbc/
│   ├── contract.py
│   ├── browser/              ← Playwright profile, capture, interceptor
│   ├── actions.py            ← structured action schema + allowlist
│   ├── spark/                ← OpenAI-compat client → JSON action
│   ├── specialist/           ← empty slot; visual CUA later
│   ├── verify.py
│   ├── escalate.py
│   └── broker/               ← privileged; not imported by Spark path
├── traces/<run-id>/
├── fixtures/
└── scripts/
    ├── run-skeleton.sh
    ├── run-spark-loop.sh
    └── install-agent-profile.sh
```

Traces: mode `0700`. Never log password fields, TOTP, or KeePassXC CLI stdout that contains secrets.

---

## Phase 0 — contracts and fixtures (no GPU, no live web)

**Done when:** contract JSON validates; forbidden actions fail unit tests; local HTML fixture opens in **this** Chromium without a model.

1. Freeze schemas:
   - `AuthorityContract` (README + `task_id`, `run_id`, `mode`: `read-only` | `draft`).
   - `BrowserAction` (structured): `{type, index?, selector?, url?, text?, ...}` — `index` is the a11y node id when `OBSERVATION_MODE=a11y_indexed`; selector used in css/mixed. Only `allowed_actions`.
   - `StepRecord`, `StopReason` as before (`escalate` includes Spark schema fail).
2. Local fixture: multi-field form + fake “account created” page + Submit that the interceptor **blocks**.
3. `scripts/install-agent-profile.sh` for Chromium dirs.

**Exit tests:** contract round-trip; `submit` / off-allowlist `navigate` raise; interceptor never submits.

---

## Phase 1 — Playwright skeleton

**Done when:** `scripts/run-skeleton.sh` scripted (no model) fill on the fixture, stop before submit, JSONL trace.

Same table as before: dedicated profile, capture, allowlist, masked screenshots, submit interceptor, loop detector, headed `:0` / headless tests.

Install Playwright Chromium into **this** `PLAYWRIGHT_BROWSERS_PATH` only.

---

## Phase 2 — Spark adapter (fixtures only)

**Done when:** Spark on `:8091` (profile `saturn-frontier-browser-control`) drives the fixture observe/act loop with structured JSON.

1. Hide HUD overlay; `pig-stack switch saturn-frontier-browser-control` (owns GPU). Pin alias/base_url from `config/pig-stack.env`.
2. Prompt: subgoal, allowlist, observation digest (`OBSERVATION_MODE`, default numbered a11y), last K steps → **one JSON action**. Parse fail → retry once → escalate.
3. Playwright executes only validated actions.
4. Test **only** on `fixtures/`. Restore previous pig-stack profile **and overlay** when the script exits.

Do not use HUD’s `spark25q4` session dir or leave Ornith loaded “because it’s close enough.”

**Exit tests:** 3 fixture runs; majority hit pre-submit success_checks without Luna; bad JSON never clicks Submit.

---

## Phase 3 — Verifier + Luna escalation

| Check | Fail → |
|-------|--------|
| URL still on allowlist | `domain_change` stop |
| Named fields match task data | compact packet to Luna |
| Success_checks all true | `success` |
| Missing a11y target / Spark schema fail | escalate (V1). Later: specialist slot |
| Captcha / bot wall | `captcha` stop |

Escalation packet: url, last N actions, screenshot path, failed checks, a11y snippet, one `ask`. `saturn-agent-dispatch ask` with a fresh consult session if large.

Frontier is not in the inner click loop.

**Exit tests:** wrong field → Luna packet, no submit; off-domain → stop; loop detector on fixture.

---

## Phase 4 — Credential broker

Privileged process; Spark/Luna never import it.

**Prereq:** `Agent.kdbx` at `~/keepass/Agent.kdbx`.

**Default:** `CREDENTIAL_FILL=broker`. The broker fills via Playwright in-process. Secrets never enter Spark/Luna. KeePassXC-Browser is a toggle (`CREDENTIAL_FILL=keepassxc-browser`) and, if used, lives only in this Chromium user-data dir.

API: `credential.create` / `fill` / `status` — return handles and ok/fail only. CSPRNG passwords via `keepassxc-cli` inside the broker.

At signup/login, Playwright emits `credential_required` and **stops the Spark loop**.

---

## Phase 5 — One bounded live test

Contract: `contracts/live-httpbin-form.json`.

- Public sample form only: `https://httpbin.org/forms/post`
- Allowlist: `httpbin.org`
- `max_steps`: 10, `mode`: `draft`, `credential_policy`: `none`
- Fake values (`Saturn Test`, `saturn-test@example.invalid`)
- **Do not submit.** Interceptor blocks Submit.

Local fixtures stay the development loop. This is the only live web target in V1. After the run, pig-stack stays on this profile.

**Success (V1):** Spark fixture majority without Luna; live httpbin fill matches `success_checks`; Submit never activated; no secrets in traces; JSONL complete; escalate count << steps.

---

## Phase 6 — Visual specialist slot (not V1)

When DOM is not enough:

- Candidate: **Fara1.5-4B** (smallest Fara; screenshot CUA; `left_click(x,y)`; MIT). Or another small browse-trained model.
- Adapter maps specialist output onto Playwright mouse/keyboard. Same allowlist and submit interceptor.
- GPU: still this tenant — `pig-stack switch` to a specialist profile here, not a second process on the 3060.
- Fill this slot only after phase 2–3 are boring.

---

## Harness exposure (Cursor only)

```text
~/bin/saturn-frontier-browser-control    JSON CLI
Cursor skill                     ~/.cursor/skills/saturn-frontier-browser-control/SKILL.md
```

Not exposed to Pig/Pi. Frontier commands: `status`, `run --contract`, `wait`, `last`, `abort`, `escalate-last`.

---

## Suggested calendar

| Phase | Effort |
|-------|--------|
| 0–1 | Days: schema + fixture + interceptor |
| 2 | Days: Spark JSON loop on fixture |
| 3 | Days: verifier + Luna escalate |
| 4 | Days: Agent.kdbx + broker |
| 5 | One live test: httpbin sample form, no submit |
| 6 | Only if needed |

---

## Pointers

| What | Where |
|------|--------|
| Product spec | this repo `README.md` |
| Spark profile | `~/.config/pig-stack/profiles/saturn-frontier-browser-control.env` + this repo `config/pig-stack.env` |
| KeePassXC | `~/saturn-reminders/keepassxc-setup.md` |
| Luna | `saturn-agent-dispatch ask` |

---

## First implementation ticket

**Phase 0+1 only:** schemas, local fixture, this Chromium, scripted fill, submit interceptor, JSONL trace. No Spark loop yet, no specialist download, no KeePass, no Luna.
