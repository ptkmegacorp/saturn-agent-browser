# Astra / Stagehand computer-use inspiration

**Captured:** 2026-09-08  
**Source:** User-provided screenshots of an X thread by Kyle Jeong. The claims below are captured as product-design inspiration and require primary-source verification before they drive an implementation decision.

## Ideas worth carrying forward

### Code-oriented browser loop

The thread describes computer use as a stateful code loop:

1. Observe the page through text, a screenshot, or both.
2. Choose an action in code.
3. Execute it against a persistent local computer/browser service.
4. Observe again and validate the intended state.
5. Continue until success, escalation, or a policy boundary.

Saturn already follows this shape: the frontier supplies the bounded subgoal; the visual specialist interprets screenshots; Playwright executes inside the authority contract; verifier checks determine success or escalation.

### Use model-native automation first, optimize the transport second

The thread’s practical lesson is that frontier models already write Playwright effectively. A productive workflow lets the model express a coherent browser operation in Playwright, then ports or compiles that operation into a faster execution layer such as Stagehand. The reported gain comes from batching related commands, which can reduce round trips and enable a task to complete in one coherent operation.

**Saturn implication:** keep Playwright as the canonical, auditable action vocabulary. Introduce batching only where a contract can validate the complete batch before execution and a post-action observation verifies the resulting page state.

### Persistent execution state

Browser and computer use are stateful. The referenced implementation keeps a Node REPL/service alive so request IDs, browser session, selected elements, and pending work remain available across actions.

**Saturn implication:** the existing persistent CDP browser daemon is the right base. The runner should preserve explicit run state and trace correlation across action batches, then recover through a fresh observation after reconnects or execution errors.

### Guardian-style safety review

The screenshots describe a two-stage review pattern:

1. A lightweight background classifier assesses workflow risk and user authorization.
2. High-risk classifications trigger a blocking reviewer that evaluates the proposed action and rationale before execution.

Saturn’s authority contract already provides the deterministic part of this model: origin allowlist, action allowlist, blocked actions, step budget, credential policy, and the pre-submit gate. A future risk classifier can create escalation packets and recommend review; the contract and explicit user confirmation remain the execution authority for consequential actions.

## Design constraints for Saturn

- Maintain the contract cage as the final enforcement point for every individual action and batch.
- Treat browser delivery success as transport evidence; verify the visible page state against `success_checks` before progressing.
- Keep passwords, OTPs, recovery codes, and vault exports outside screenshots, model context, and traces.
- Require explicit human confirmation for submissions, sends, purchases, agreements, security changes, and other external commitments.
- Record batch intent, policy decision, actions, post-action observation, and verification result in the run trace.

## Candidate experiment

Build a fixture-only `batch` executor that accepts a small Playwright action list already permitted by an authority contract. Execute the list atomically from one browser-session request, capture one post-batch screenshot, and run the existing verifier. Compare action count, browser round trips, elapsed time, trace completeness, and recovery behavior against single-action execution.

## Related Saturn docs

- [README](../README.md) — architecture, contracts, and guardrails
- [UI-Venus 2 integration plan](../../../models/potential-models/ui-venus-2-official-pipeline.md) — visual specialist loop
- [Browser grounding research](../../../models/potential-models/browser-grounding-vlm-research.md) — frontier/visual-specialist split
- [OpenClaw comparison](openclaw-comparison.md) — browser-profile and authentication doctrine
