# EXT-009 design — Agentic master loop

## Shape (mirrors Claude Code's `nO` loop, two-plane)

```
request ─► planner(2B) ─► TODO [Step(action, arg, status, observation)]
                              │
              ┌───────────────▼──────────────────────────────┐
              │  while pending and steps < max_steps:         │
              │    step = next pending                        │
              │    ok, obs = execute_step(step, cwd)   ◄── DETERMINISTIC tools only
              │    step.status, step.observation = ...        │
              │    if not ok: TODO += planner(replan-prompt)   ◄── OBSERVE → REPLAN
              └───────────────────────────────────────────────┘
                              │
                       {todo, done, steps_run}
```

- **Model plane (inert):** the planner emits a plan (and replans) — `action ∈ {find, read,
  run, fix}` today, extensible. No side effects.
- **Tool plane (deterministic):** `execute_step` dispatches to `find_usages` / file read /
  `pytest` / `multi_file_fix` — each reliable + test-gated. Execution correctness does NOT
  depend on the 2B; only the *sequencing* does.
- **Working memory:** the `Step` list IS the TodoWrite analog. REQ-2 will feed prior
  observations back into each replan; REQ-5 will compact them for the small context.

## Why this is the right convergence target
The capability ceiling on single-function synthesis is the 2B (EXT-005 shows ~58% pass@1,
flat). Breadth + the *agentic layer* — not pass@1 — is where jaros-code becomes a usable
tool. The master loop turns a box of commands into "tell it what you want." Its honest
metric is the multi-step eval (REQ-6), not HumanEval.

## Structured flow beats free-form (measured — the jarify-flow result)
Head-to-head on the REQ-6 agentic eval (same 3 scenarios, same 2B): the **spec-driven
(jarify-flow) loop scored 3/3; the free-form `agent_loop` scored 2/3** (it skipped the fix step
on the exception scenario). A 2B is unreliable at the open-ended "what steps?" judgement, but a
DETERMINISTIC flow (verify requirement -> implement -> verify) where it only fills constrained
sub-tasks is reliable. So **`spec_driven_loop` (harness/spec_loop.py) is the DEFAULT** that
`/agent` uses; the free-form `agent_loop` is kept as a fallback for genuinely open-ended tasks.
This is the decomposition principle at the WORKFLOW level — the same reason jaros-code works at
all, applied to planning. (Owner's insight, confirmed 2026-06-21.)

## Testing
The planner is injectable, so loop mechanics are tested deterministically (no model). The
2B planner is the default; end-to-end agentic quality is measured by REQ-6's multi-step eval.

## Out of scope (Tenet 2)
MCP / external servers / network tools — the harness stays local-only. "Sub-agents" are the
existing single-purpose agents the loop can call as steps, not a new remote-execution layer.
