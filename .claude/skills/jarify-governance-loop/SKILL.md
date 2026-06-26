---
name: jarify-governance-loop
description: Run the recurring Jarify governance + convergence heartbeat for any Jarify-governed repo (one with a `.jarify/` dir and a `PRIME-*` Prime Directive). Every ~30 min it audits spec↔code compliance, resolves spec/intent conflicts (Prime Directive supreme), and AUTO-STEERS the next change — maintaining a live to-do list, every change flowing through the Jarify workflow. Use to stand up or run the standing self-governance loop (this session, a restarted session, or a brand-new repo).
---

# Jarify: Governance & Convergence Loop

A recurring self-governance heartbeat for any Jarify-governed repository (a repo with a `.jarify/`
directory and a Prime Directive folder `PRIME-*/intent.md`). Run it on a fixed cadence (~every 30
minutes) to keep specs, intents, and code in **absolute compliance** AND to **continuously drive the
project forward** — discovering and queuing the next change. It is the autonomous loop that maintains
and advances the project between human messages. It is repo-agnostic: it works from the `.jarify/`
structure and the Jarify skills/agents, so it reproduces in a restarted session or a brand-new repo.

## The pursuit is UNBOUNDED — never done, never satisfied

The Prime Directive's intent is an **asymptote, not a finish line**: we will **never fully reach it, and
we must never be satisfied or declare the work "done."** Every cycle marches the system *closer* to that
intent without ever arriving — that is the entire point of the loop. **"Good enough," "done,"
"complete," "saturated," and "at the ceiling" are FORBIDDEN conclusions**; reaching for any of them is
the failure mode itself. There is ALWAYS a next change that brings the system nearer to the intent, so
the loop runs forever, always iterating toward it. Compliance keeps the march honest; convergence keeps
it moving; the march toward the intent never ends. If a cycle ever feels finished, look harder — the
gap to the intent is never zero.

## When to use
- To stand up or run the standing governance loop in any Jarify repo.
- Every ~30 minutes while working autonomously; re-arm yourself so it continues unattended.

## The cycle — do ALL of these every tick

### 1. Compliance audit (spec ↔ code)
Walk every `.jarify/<SPEC>/`. Validate that the code TIED to each spec (via `index.json` traceability)
actually satisfies its `requirements.md` — the `### [REQ-x]` blocks and their acceptance criteria — and
that the traceability is accurate (referenced files/anchors exist). Do a fast STRUCTURAL sweep every
tick (files present: requirements / intent / index; `### [REQ-x]` format; frontmatter `status` sane;
referenced files exist) PLUS ONE rotating DEEP semantic check (does the code actually meet a spec's
criteria) — coverage over time, not a 12-spec deep audit every tick. FIX any non-compliance.

### 2. Conflict resolution (specs ↔ intents ↔ Prime Directive)
Detect conflicts BETWEEN specs, and between a spec and its own requirements. RESOLVE automatically by
the spec's INTENT (`intent.md`). **If a spec has no intent, read its requirements and GENERATE the
intent you judge it to be** (consistent with the Prime Directive). **The PRIME DIRECTIVE's intent is
the supreme, ruling authority — it must NEVER be overridden.** Any conflict with the Prime Directive →
the Prime Directive wins; fix the other side. Never silently resolve a tenet conflict — if a change
would violate the Prime Directive, STOP and flag it.

### 3. Auto-steer — proactively DRIVE the next change (convergence)
This loop does not just maintain compliance; it OWNS moving the project forward between human messages.
Each tick, run the convergence step and ACT on it:
- **MEASURE → DIAGNOSE → DISCOVER → PLACE → WIRE → RE-MEASURE → PRUNE.** Measure honestly (held-out, no
  gaming); diagnose the real failure (probe the raw output); discover the next grain/change; place it
  (a judgement → an agent; a deterministic effect → a tool, per the two-plane rule); wire it (no
  orphans); re-measure; prune anything net-negative.
- **BUILD, don't defer.** If you catch yourself DESCRIBING the next improvement instead of building it
  ("teed up for next"), that IS the failure mode — build it now (through the Jarify workflow) and
  measure it this cycle.
- **Maintain a LIVE TO-DO LIST** (the task list / TaskCreate-TaskList-TaskUpdate). CHECK and UPDATE it
  EVERY tick — mark done, add newly-discovered work, re-prioritize by impact×tractability (structural /
  by-construction gaps FIRST). The list is the convergence backlog; it must never go stale.
- **Keep at least one improvement EXPERIMENT running** where the project has an experiment chain; on each
  result, act (commit the win / revert the regression) AND launch the next, so the loop self-sustains.
- **ADAPT, don't rut.** When an approach yields committed wins, double down; when it reverts repeatedly,
  STOP and switch AXES (a failure is a harness/scaffolding gap, never a model/ceiling "limit"). VARY the
  kind of work — new capability vs evals vs tools vs orchestration/wiring — and pull EXTERNAL research at
  a plateau instead of grinding the same dead end.
- A tick that finds "nothing to do" is itself a signal to look HARDER, never to idle.

### 4. Execute via the Jarify workflow — NO ad-hoc edits
Every change — a compliance fix, a conflict resolution, or the next improvement — flows through Jarify:
- `jarify-manage-specs` / `jarify-manage-tasks` / `jarify-manage-links` for the spec docs + traceability.
- the **jarify-builder** agent to implement a task (one builder per task, strictly scoped: writes code,
  runs tests, updates traceability, reports).
- the **jarify-architect** agent to validate (requirement match, design conformance, no regressions,
  strict scope, traceability) and COMMIT when it passes.
- Spec + code change in the SAME commit (spec-first; stale specs are defects).

## Operational guardrails (non-negotiable)
- READ-ONLY auditing is safe anytime. Any CODE change must be applied at a **SAFE BOUNDARY** — when a
  long-running job (an eval, a build, a training run) ENDS and before the next STARTS — never mid-run on
  a shared resource (a single GPU, a shared checkout/worktree). Spec-doc-only changes are safe anytime.
- NEVER conflict with concurrent work (another builder/session mid-task): don't edit files it is
  touching; sequence behind it.
- Where the project runs an improvement-experiment chain, keep at least one experiment running so the
  loop self-sustains; act on each result (commit/revert) and launch the next.

## Notifications & autonomy
The loop runs AUTONOMOUSLY — the **default is to ACT per the intent, not to ask.** Auto-steer and
resolve by the spec / Prime-Directive intent so the user is NOT bothered when it isn't necessary;
interrupting the user for routine progress is itself a failure of the loop's purpose. But when a
push/notification channel is available, **SURFACE what the user genuinely should know** — send a
notification for a SIGNIFICANT event:
- a significant **WIN or milestone** (a real committed improvement and what it moved; an
  external-benchmark result);
- a genuine **QUESTION or DECISION the loop cannot resolve from the intent** and that actually needs the
  user (a true ambiguity, an unresolvable conflict, an irreversible or outward-facing action);
- a **REGRESSION, breakage, or unrecoverable failure**, or a should-have-but-didn't (the chain stalled,
  no net progress in a long while);
- anything the project's **intent explicitly says must be surfaced.**
Do NOT notify for routine, healthy progress. Respect any notification policy the project's intent
specifies (e.g. quiet hours, digests, channels, time zone). The bias is strong autonomy + sparing,
high-signal notifications: act on intent; interrupt the user only when it is significant or genuinely
needed.

## Cadence
Run every ~30 minutes and RE-ARM the next tick (e.g. a scheduled wake-up) so the loop continues
unattended. Each tick, report concisely: what compliance found/fixed, what conflicts were resolved by
which intent, and what next change was queued or made — so the trend (not a feeling) is visible.
