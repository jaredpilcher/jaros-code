---
id: EXT-009
title: Agentic master loop (the agent that wields the tools) + working/long-term memory
status: partial
priority: high
implementation:
  - file: harness/agent_loop.py     # REQ-1 master loop
  - file: harness/spec_loop.py      # the jarify-flow (default) + plan-mode + memory anchoring
  - file: harness/project_memory.py # REQ-3 long-term memory
  - file: harness/agentic_eval.py   # REQ-6 multi-step eval
  - file: harness/build_eval.py     # REQ-6 build eval
---

This spec serves **Tenets 1, 4 & 5** of PRIME-001. EXT-002/003/004/008 gave the system
its *tools* (fix, find, run, refactor, navigate, locate, build) — but a human will not
run `/usages`, `/rename`, `/build` by hand. The missing piece is the **agent that wields
the tools**: from ONE natural-language request, plan a sequence of tool calls, execute
them, **observe** each result, and **replan** when reality diverges from the plan. This
is Claude Code's single-threaded master loop (`nO`) + the `TodoWrite` working-memory,
reconstructed on the small local model.

Honest framing (Tenet 3): planning/replanning *quality* is capped by the 2B — it is not
Opus. The two-plane discipline is what makes this usable anyway: the model only emits an
**inert plan** (and inert replans); the **deterministic, test-gated tools** do every
side effect. So each step is reliable even when the sequencing is imperfect, and the
honest measure is a **multi-step eval** (HumanEval cannot measure planning — it is
single-function). This spec also maps the remaining Claude-Code features we should adopt
(memory, plan-mode, context compaction, checkpoints) to jaros-code's constraints.

### [REQ-1] Master loop: plan → act → observe → replan  (DONE)

`agent_loop(request, cwd)` turns one request into a TODO via the planner, executes each
step with deterministic tools (find/read/run/fix), observes the result, and REPLANS the
remaining work on a failed step. The planner is injectable so the loop mechanics are
tested without the model.

#### Acceptance Criteria
- [x] plan → act → observe → replan-on-failure, bounded by `max_steps`
- [x] only the model plans/replans (inert); tools perform all side effects (two-plane)
- [x] deterministic tests of the loop (execute, run-to-completion, replan-on-failure)
- [x] wired as `/agent <request>` in the CLI

### [REQ-2] Working memory (short-term): the live TODO  (PARTIAL)

A structured TODO (step, status, observation) is the loop's working memory. Next: carry
a compact **scratchpad** of prior observations into each replan (Claude Code re-injects
the todo + recent tool output after every step so the model never loses the thread).

#### Acceptance Criteria
- [x] TODO with per-step status + observation, returned to the caller
- [ ] observations from completed steps fed into the planner on each replan
- [ ] the loop surfaces the live TODO as it runs (progress visibility)

### [REQ-3] Long-term memory: the harness reads/writes its own project memory  (DONE)

Claude Code anchors on `CLAUDE.md` every session. jaros-code's harness has no memory of
its own — each invocation is stateless. Add a persistent, harness-owned memory (e.g.
`.jcode/memory.md` in the user's repo): read at the start of an `/agent` run to anchor
conventions/commands, and append durable learnings (only via the deterministic tool
plane, never silent I/O).

#### Acceptance Criteria
- [x] read a project memory file at the start of an agentic run and feed it to the fix model
- [x] append a learning entry on a notable outcome (append_memory + /remember)
- [x] absent file is a no-op (graceful)

### [REQ-4] Plan mode: show the plan (with tests per phase) before acting  (DONE)

Claude Code's plan mode proposes phases before execution. Add a dry-run that renders the
TODO without executing, so a human can approve/edit before the agent touches anything.

#### Acceptance Criteria
- [x] `/agent --plan` renders the structured-flow plan without side effects
- [ ] each "fix"/"build" phase names the test that will gate it

### [REQ-5] Context compaction for long loops  (TODO)

Long agentic runs overflow the 2B's small context. Deterministically compact the
working memory (keep the request + the TODO + the last N observations; summarize older
ones) before each planner call. Claude Code's `/compact`, scoped to our tiny context.

#### Acceptance Criteria
- [ ] planner input stays within a bounded token budget regardless of step count
- [ ] compaction is deterministic (drop/summarize oldest observations first)

### [REQ-6] Multi-step eval: measure the agentic capability  (DONE)

HumanEval (single-function) cannot measure planning. Add a `locate → fix → test`
multi-step eval: seed a repo with a fault, give `agent_loop` the high-level request, and
score whether the loop drives the tools to green. This is the honest metric for EXT-009.

#### Acceptance Criteria
- [x] ≥3 multi-step scenarios scored end-to-end (agentic_eval 3, build_eval 7)
- [x] recorded to the trend history (suite="agentic"/"build") so `/trend` shows them separately

### [REQ-7] `/agent` as the default NL entry; checkpoint the whole run  (PARTIAL: checkpoint+/undo done; default-routing TODO)

Make a plain request route to `agent_loop` (not just single-action orchestration), and
snapshot the repo before the run so the user can undo the agent's *entire* run (Claude
Code's checkpoints), reusing the existing `_snapshot`/`_restore`.

#### Acceptance Criteria
- [ ] a multi-action plain request routes to `/agent`
- [ ] a whole-run snapshot taken before execution; `/undo` restores it

### Claude-Code features already covered (no new work)
- **Hooks / PreToolUse checkpoint** → the two-plane `gate`/`validate()` + the `shell.exec`
  denylist already gate every side effect before it runs.
- **Sub-agents** → the orchestrator/dispatcher already routes to single-purpose agents;
  the loop can call them as steps.
- **Per-change checkpoints** → `_snapshot`/`_restore` + the test-gated revert in
  refactor/multi_file already roll back failed changes.
- **MCP / external servers** → intentionally OUT (Tenet 2: local-only, no network from
  the harness).
