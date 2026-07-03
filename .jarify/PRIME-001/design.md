# PRIME-001 — System Architecture

`jaros-code` is a **multi-model** fleet of single-purpose reasoning agents. A
**model-router judge** first routes each task to the Jetson-fitting model whose measured
profile best covers its class; that model's agents then emit only inert `Decision` data,
executed by a deterministic tool plane on top of the Jaros runtime. This document maps the
system-wide architecture the Intent demands. Feature specs (`EXT-00x`) decompose individual
tenets into requirements, design, and tasks.

## The product — the end goal (owner clarification, 2026-07-03)

Everything below serves ONE product: **a CLI that BUILDS and MODIFIES complete software systems from a
sentence** — the operational meaning of "be just like Claude Code." A developer describes a system, or a
change to an existing one, in plain language at the terminal; jaros-code plans → builds → tests → ships
(or evolves) it end-to-end, locally, at $0. The router, the two planes, the swarm, and the tool library
below are the *means*; this CLI is the *end*. It is realized by the sentence→system pipeline
(`harness/system_builder.py`: `build_system` / `build_system_escalating` / `modify_system`, spec
`EXT-036`) surfaced as the `/buildsystem` and `/modifysystem` commands, and its parity is measured
end-to-end by held-out creation + modification suites graded through the CLI by independent oracles.

```text
   sentence ("build a job-queue CLI with priorities + retry" │ "add a delete command to the kv-store")
        │
        ▼   /buildsystem · /modifysystem   (the PRODUCT surface)
   ┌──────────── plan → build (topo, syntax-gated) → assemble → acceptance → repair ───────────┐
   │  routed/escalating: gemma default; on ship-failure escalate to the complex-build specialist │
   └───────────────────────────────────────────────────────────────────────────────────────────┘
        │  everything below is HOW this is served
        ▼
```

## The two planes

```text
            ┌────────────────────────── REASONING PLANE ──────────────────────────┐
            │  single-purpose agents — each makes ONE narrow judgement via         │
            │  gemma2:2b, and emits inert JSON Decisions only (no side effects)     │
            │                                                                       │
            │   [planner]   [file-picker]   [editor]   [test-reader]  [reviewer] …  │
            └───────────────────────────────┬───────────────────────────────────────┘
                                            │  Decision data (slips of paper)
                                            ▼
            ┌──────────────────────── DECISION GATE ───────────────────────────────┐
            │  deterministic validate() per tool — accept / reject the proposal      │
            └───────────────────────────────┬───────────────────────────────────────┘
                                            ▼
            ┌────────────────────────── EXECUTION PLANE ───────────────────────────┐
            │  deterministic tools (the clerk) run the host effect, then record it   │
            │   fs.read   fs.list   fs.write   shell.exec   grep   apply_patch   …    │
            └───────────────────────────────┬───────────────────────────────────────┘
                                            ▼
            ┌──────────── DURABLE STATE: hash-chained decision log + outbox ────────┐
            │  every accepted Decision recorded → replay reconstructs byte-identical │
            │  state with ZERO model calls (Tenet 3)                                  │
            └────────────────────────────────────────────────────────────────────────┘
```

The arrow only ever points down. Nothing in the reasoning plane holds a handle to
the file system, the shell, or the network — those exist solely as harness-granted
capabilities the execution plane uses (Jaros capability-safety, Tenet 1).

## The multi-model router (the outer judge)

Above the two planes sits the **model-router** (owner directive, 2026-06-28). Every task
first passes through a judge that classifies the problem and routes it to the Jetson-fitting
model whose *measured profile* best covers that class — then the harness **rewires itself** to
that model before any solving begins. Single models have real, measured class-ceilings; the
system routes *around* them instead of denying them.

```text
   task ("make test_login pass" │ a HumanEval problem │ a repo red->green commit)
        │
        ▼
   ┌──────────────────── MODEL-ROUTER JUDGE (on-device) ──────────────────────┐
   │ classify the problem's CLASS + difficulty; pick the model whose profile   │
   │ is MEASURED to cover it. Inert Decision (Tenet 1). Deterministic default  │
   │ when unsure -> a capable model, never a failure.                          │
   └───────────────────────────────┬───────────────────────────────────────────┘
                                    │  Decision: model = <name>
                                    ▼
   ┌──────────────────── MODEL REGISTRY (Jetson-fitting only) ─────────────────┐
   │  gemma-4-2b   profile{ classes:[…], tools, agents, config, prompts }       │
   │  <model-B>    profile{ classes:[…], tools, agents, config, prompts }       │
   │  <model-C>    profile{ … }                        explored best-first       │
   └───────────────────────────────┬───────────────────────────────────────────┘
                                    │
                                    ▼
   ┌──────────────── REWIRE (deterministic — the clerk, Tenet 1) ──────────────┐
   │  ensure <model> is the one served on the Jetson (swap llama.cpp if needed) │
   │  + activate THAT model's tools / agents / config / prompts                  │
   └───────────────────────────────┬───────────────────────────────────────────┘
                                    ▼
                 the two planes below, now wired for <model>
              (the orchestrator composes THAT model's agents + tools)
```

Each model's **profile** is *earned by measurement* — a model is credited with a class only
once held-out tasks show it handles that class. The roster grows **best-first** (the strongest
Jetson-fitting model first); each new model is *adapted* (its own tools/agents/config/prompts)
before it is trusted with a class. A naive swap with no adaptation regressed (0/16 where the
co-adapted baseline scored 4/16) — proof that the *adaptation*, not just the weights, is what
performs, so the rewiring is per-model and first-class. The router, the registry lookup, and
the rewire all flow through the clerk: hash-chain logged and byte-replayable (Tenet 3).

**Selection is DETERMINISTIC end-to-end (owner + external review, 2026-06-28):** the router classifies
the CLASS from deterministic features (*not* a model); a **deterministic coverage tally** (model × class
→ measured score, kept filled in by the profiler) names the best model by argmax; and when several
models cover a class, the **deterministic test gate** picks the winner — try them best-measured-first,
keep the first whose output passes the given test. **No model ever routes or chooses between models**
(model-as-judge was measured net-negative; the test, not a meta-model, harvests the decorrelated errors
of diverse small models). The roster grows **forever**, and admission is gated by **MARGINAL
COVERAGE, not general quality** (external review, 2026-07-01): a candidate is FIRST auditioned on the
exact problems the current roster *fails* — the shared failure set — and earns a slot ONLY if it covers
a class no roster member covers (its errors are **decorrelated** from the roster's). This decorrelation
gate is the **cheapest, first** step of admission, run *before* any broad profiling, because the Jetson
is serial and every slot costs a model swap; a candidate that fails the same instances earns nothing,
however high its MBPP score. Only once admitted is a model profiled across all known classes; then the
next most capable Jetson-fitting candidate is auditioned the same way, and a **new class re-profiles every
prior model** (go back, don't forget them) so the tally stays complete. Per-model adaptation includes that
model's own evals. All escalation stays on **local Jetson-fitting** models — never cloud (Tenet 2). See
EXT-021 REQ-5/REQ-6.

**The roster only earns its cost when the SYSTEM pays (external review, 2026-07-01).** Because per-model
profiles can each improve while the routed system does not, the honest system-level metric reports
end-to-end **routed** performance against **(a) the best single model** and **(b) the oracle
best-model-per-problem** on the same bar (Tenet 3): routed ≤ best-single ⇒ the roster is not paying and
the router is the bottleneck; the routed-vs-oracle gap localizes the deficit to routing *accuracy* vs
genuine *coverage*. This is the standing check that a swap-costly roster is worth its serial-Jetson price.

## The Pursuit architecture (owner directive, 2026-07-01)

The intent's PURSUIT block lands in the architecture as five additions. Everything below
is **Jaros-native**: judgments are single-purpose agents emitting inert Decisions;
watchers, schedulers, trainers, indexers, and deployments are deterministic tools with
`validate()`/`execute()`, hash-chain logged and replayable. A lever that cannot be placed
this way is a signal to extend Jaros (new tool/flow primitives), never to bypass it.

### 1. The instruments (scoreboard as harness components)
- **daily-driver runner** — executes the 80+ frequency-weighted tasks END-TO-END through
  `harness.cli` (not internals); deterministic oracles; records per-task latency;
  dev/holdout discipline enforced in the runner itself (holdout reads are logged).
- **shadow-mode parity logger** — a local, private log of the owner's real Claude Code
  tasks + a replayer that runs them against jcode; produces side-by-side rows. As it
  accumulates it becomes the headline parity instrument.
- **gap map** — `docs/GAP-MAP.md`, updated by the governance loop every tick; the
  state machine per row is data, not prose (`unmeasured → … → wall(dated, evidence)`).
- **amortization telemetry** — every serve path tags its source (memory hit /
  deterministic / precomputed / full-solve); the ratio is reported weekly.
- **Foundry ship-log** — projects started/shipped + per-project gap lists.

### 2. The training plane (execution-plane tools; models never touch it directly)
```text
  verified-solution store ──► dataset-builder tool ──► LoRA-trainer tool (owned HW)
   (every test-gated solve;     (curates (problem,        │ config = inert Decision
    every verified think-        verified-solution)       ▼
    trace; nothing thrown        pairs per class)      adapter/micro-model artifact
    away)                                                 │
                                                          ▼
                                            roster ADMISSION (same rule as any model:
                                            marginal coverage on held-out — training
                                            grants no exemption from measurement)
```
Tiers: LoRA grain-specialists (S/R emitter, localizer, test-writer) · micro-models
(router classifier, patch ranker, calibrator — trained on eval exhaust) ·
self-distillation (bare model absorbs what needed scaffolding). The store schema
persists `(problem, attempts, outcomes, winner, model, scaffold-config)` from every run.

### 3. The retrieval + analysis planes (inference-free fact sources)
- **embedder service** — a tiny embedding model resident beside the roster; index tools
  (build/refresh) run as scheduled deterministic jobs; queries serve semantic code
  search, semantic recall over the solution store, and API/doc lookup.
- **knowledge compiler** — at repo setup, compile each dependency's API surface
  (signatures, docstrings, examples mined from the dep's own tests) into a local
  fact-base; fact-injection (ladder L3) draws from it deterministically.
- **program-analysis tools** — type inference, dataflow, coverage localization,
  property-test generation, mutation operators, AST-diff mining. Each is a fact source
  for precise injection and an ingredient for reductions.
- **decode control** — the llm client supports grammar-constrained generation (GBNF):
  Decision-JSON, SEARCH/REPLACE blocks, and skeleton-constrained fills are enforced at
  decode time, making format-failure classes unemittable rather than repaired.

### 4. The always-on flows (structural advantages of a sovereign device)
- **overnight brain** — a scheduled Jaros flow: during idle hours, pre-build indexes,
  pre-generate+verify tests for uncovered functions, pre-solve TODO/FIXMEs into a
  **drawer** of test-verified candidate patches, run training jobs.
- **speculative drawer** — a watcher tool observes the working repo (saves, failing
  tests) and enqueues background solves through the NORMAL inbox path; verified results
  wait in the drawer and are offered, clearly labeled, when the operator asks.
- Both flows are ordinary Jaros jobs: gated, logged, replayable; they never write to
  the working tree without the operator's accept.

### 5. The Foundry (real builds as a standing instrument)
A sandboxed workspace where jaros-code builds diverse real software end-to-end the
jarify way (each project gets its own prime directive → specs → tasks → build →
validate). Safety gates are architectural, not advisory: dedicated workspace root,
localhost-only binding for services, resource caps, the EXT-001 shell/network gates
unchanged; any exception exists only as a per-project owner-approved manifest read by
the gate itself.

### The flywheel, end to end
```text
  gaps (Gap Map) ─► levers (IDEA-BANK / IDEA-PLAYBOOK) ─► probe ─► build (Jaros-native)
        ▲                                                             │
        │                                                             ▼
   re-measure ◄── distill into weights ◄── verified-solution store ◄── test gate
   (scoreboard)    (training plane)         (nothing thrown away)      (the judge)
```

## Why many small agents beat one big one

A single `gemma2:2b` prompt asked to "fix this bug across the repo" fails. The same
model succeeds when the work is decomposed so each call answers one bounded question:

```text
  task: "make test_login pass"
     │
     ▼
  [planner]      → Decision: which files are relevant? (names only)
     │
     ▼
  fs.read(files) → deterministic tool returns exact bytes
     │
     ▼
  [editor]       → Decision: one concrete edit (old→new) to one file
     │
     ▼
  apply_patch    → deterministic tool applies + records it
     │
     ▼
  shell.exec(pytest) → deterministic tool runs the suite, returns real output
     │
     ▼
  [test-reader]  → Decision: pass? if not, what single next edit?  ──┐
     ▲                                                                │
     └──────────────────── loop (bounded) ───────────────────────────┘
```

Each agent has a tiny, fixed prompt and a tiny output contract (often one token, a
filename, or a single old→new pair) — the regime where a 2B model is reliable. The
*intelligence of the system* lives in the decomposition and the determinism of the
tools, not in any one model call.

### Plane placement: route each grain to the plane that can do it

Decomposition is necessary but not sufficient — each grain must land on the plane that
can actually execute it. The triage:

```text
   for each grain, ask: is its CORE a judgement gemma2:2b can reliably make?
   ─────────────────────────────────────────────────────────────────────────
   YES → tiny AGENT (reasoning plane)      NO → deterministic TOOL (exec plane)
   • classify a bug class                  • count lines / arithmetic
   • pick the relevant file                • operator semantics (`<` vs `<=`)
   • transform-by-example                  • exhaustive generate-and-test
   • read a PASS/FAIL result               • anything the 2B cannot comprehend
```

A grain whose core the model cannot do is a boulder no *model-side* slice shrinks —
slicing it thinner just reproduces the same failure smaller. The fix is to move the
work across the gate into the execution plane. Proven case (EXT-003/REQ-4): a
single-operator off-by-one (`while lo < hi:` → `<=`) defeated **every** model-side
decomposition — a line-locator hallucinated line 6 of a 3-line file (2B can't count
lines); an OLD/NEW snippet prompt reproduced the bug unchanged across 5 seeds (2B can't
comprehend the off-by-one). The model-free `mutation_repair_loop` — try each candidate
operator edit, keep the first the suite accepts — cracks it on the first candidate and
generalizes to other operators (`countdown`: `>` → `>=`). Zero model calls, so it is
byte-identically reproducible (Tenet 3). This is the swarm vision intact: agents and
tools grow *together*; the craft is the routing.

**Method when a model-side pipeline stalls:** run a raw single-call probe to see exactly
what the 2B emits *before* building more agents. If the failure is genuine
incomprehension (not formatting/parsing), build a deterministic tool for that grain.
Prove generalization with a second eval of the same bug class — never game one task. And
never ship a net-negative fallback (the discarded line-number pipeline corrupted
indentation; it was removed, not committed).

### Scale: a swarm of tiny agents

The target is a **swarm — hundreds, then thousands, then tens of thousands of
agents** — every one single-purpose and tiny. Capability scales by *adding agents,
tools, and evals*, never by enlarging the model.

```text
   ┌──────────── the swarm grows along three axes (never the model) ───────────┐
   │  AGENTS   100 → 1k → 10k+   each: one judgement, one tiny prompt/contract  │
   │  TOOLS    an extensive library of deterministic verbs the agents compose   │
   │  EVALS    an extensive suite proving convergence on Claude-Code/Opus-4.8    │
   └────────────────────────────────────────────────────────────────────────────┘
```

Jaros makes this safe at scale: agents run as lightweight threads (not services),
each holds only harness-granted capabilities, and the hash-chained decision log
keeps a swarm of thousands reproducible and attributable. A bigger problem is met
with a wider swarm, sharper tools, and more evals — full stop.

### The convergence loop (supervisor-owned, continuous)

Capability is grown by a standing loop, not a one-time build. A named supervisor runs
it forever and owns the outcome: keep the system converging on parity with Claude Code
on Opus 4.8. Each turn of the loop discovers what *type of sand* the system is missing
and where it belongs.

```text
   ┌──────────────────────────── the convergence loop ───────────────────────────────┐
   │                                                                                   │
   │   MEASURE ──► DIAGNOSE ──► DISCOVER ──► PLACE ──► WIRE ──► RE-MEASURE ──► PRUNE    │
   │   (honest    (probe raw   (name the    (plane-   (no      (did a real   (drop     │
   │    evals +    model out-   missing     placement orphans) metric move?) net-zero/ │
   │    census +   put: which   grain type) triage:                          negative) │
   │    wiring)    grain, why)              agent│tool)                                │
   │      ▲                                                                      │      │
   │      └──────────────────────────── forever ◄───────────────────────────────┘      │
   └───────────────────────────────────────────────────────────────────────────────────┘
```

Worked example (this is how the loop actually ran, not a hypothetical):

```text
   MEASURE    from-intent eval running_total → self✗/oracle✗ (unsolved)
   DIAGNOSE   probe test-writer → it COMPUTED `running_total([2,3])==[1,3,6]` (wrong);
              gemma2:2b cannot do the arithmetic → impossible tests, not a bad implementer
   DISCOVER   missing grain: "ground-truth from the user's stated examples, not computed"
   PLACE      deterministic TOOL — extract_examples parses the intent's own f(x)=y lines
              (no model arithmetic); model kept only as fallback when no example is stated
   WIRE       test-writer.decide prefers extraction → code.write_file (used, not orphan)
   RE-MEASURE csv_parse 0 → self✓/oracle✓ on the first attempt; running_total's bottleneck
              MOVED to the implementer (next turn of the loop)
   PRUNE      (nothing to remove; the net-negative line-number repair was already removed)
```

The supervisor watches four honest signal families every cycle and corrects against
them: **capability** (repair pass-rate + generative self-vs-oracle fidelity), **growth**
(agents/tools/evals counts rising), **orchestration/wiring quality**, and **health**
(no orphans, no net-negative fallback shipped). Activity is never the metric; the
convergence trend is.

**Orchestration/wiring quality is itself measured — not just agent/tool count.** Because
Jaros records every agent→tool decision in the hash-chained log, the wiring graph is
auditable data. So the harness tracks, run over run: **leverage** = solved tasks per
agent (rises when wiring/orchestration improves WITHOUT adding agents — e.g. the
strategy-cascade lifted capability at a flat count of 10 agents), the count of **distinct
wired edges fired**, and **decisions composed per solved task**. A capability gain that
comes from better composition is real progress and is watched as such; "we got more
capable from the same swarm by wiring it better" is a first-class, measurable win.

### The difficulty ratchet (evals get harder and harder)

```text
   pass rate on tier T crosses the bar  ──►  escalate to tier T+1 (harder)
   ──────────────────────────────────────────────────────────────────────
   tier 1  toy single-edit bugs (home-grown)              ── master ──┐
   tier 2  multi-edit / edge-case / small algorithms                  │
   tier 3  multi-file, real refactors                                 ▼
   tier 4+ REAL public benchmarks: HumanEval → MBPP → Aider → SWE-bench
                                                  (the external, recognized bar)
```

The ratchet only turns one way. When a tier is mastered the suite escalates to a
harder tier (and, at the top, to tougher real benchmarks); we never soften it. An
eval the harness can ace is a defect in the eval suite, not a victory — hardening it
is required work. Parity is "matches Claude-Code-on-Opus-4.8 on genuinely hard,
external problems," nothing less.

## Orchestration on Jaros

- A **job** (`inbox/<id>.json` = `{id, agent, input}`) selects one agent by name.
- The daemon resolves the agent, calls `decide(input)` → `[Decision]`, gates it,
  runs the matching execution-plane handler, and writes `outbox/<id>.json`.
- Multi-step coding loops are built by composition: a tool may enqueue the next
  job (handoff), or an outer orchestrator submits the next agent's job based on the
  recorded result. Each step stays single-purpose and individually replayable.
- The **scheduler** drives recurring duties (health, self-eval, monitoring).

```text
  inbox/ ──claim──► agent.decide() ──Decision──► gate ──► tool.execute() ──► outbox/
     ▲                                                          │
     └───────────────── handoff: enqueue next job ◄─────────────┘
```

## Operator surface (Claude-Code-like)

A thin terminal front-end over the Jaros node: submit a coding task, watch the
agents' decisions and the tools' real output stream by, browse the decision log,
and replay any run. The front-end issues jobs and reads `status.json` / `outbox/`;
it never bypasses the two planes. Look and feel mirror Claude Code; authority stays
with the deterministic harness.

## Jarify all the way down (convergence on the user's intent)

`jaros-code` is a code-building tool, and the way it builds a user's system is the
way jarify is used. It operates on a user's project with the **same** jarify loop
that built the harness itself. This self-similarity is the mechanism by which every
actor — operator, agents, tools — converges on the **user's** explicit, written
intent (captured as that project's prime directive) rather than drifting. The spec
is the shared north star; jarify is what makes a fleet of small models build what
the user actually meant.

```text
   how jaros-code is built              how jaros-code builds a user's project
   ────────────────────────            ──────────────────────────────────────
   PRIME-001 (this directive)    ⇄     project PRIME directive (the user's intent)
   EXT-00x requirements/design   ⇄     feature requirements/design for the project
   tasks.md ([TASK-x])           ⇄     decomposed tasks for the project
   single-purpose agents +       ⇄     same single-purpose agents + deterministic
     deterministic tools                 tools implement one task at a time
   index.json traceability       ⇄     code traced back to the project's spec
```

The fleet mirrors the jarify roles: a **spec agent** drafts/updates requirements &
design, a **task agent** decomposes a requirement into scoped tasks, a **builder
agent** implements exactly one task, and an **architect agent** validates the task
against its requirement before commit — each a small, single-purpose `gemma2:2b`
reasoning boundary, each backed by the deterministic tools of EXT-001. Intent flows
top-down through the specs; results and traceability flow back up. Nothing acts
except in service of a written requirement that serves the prime directive.

## Spec map

```text
  PRIME-001  ── north star (this document; intent.md + design.md only)
     ├── EXT-001  deterministic tool plane (fs.read, fs.list, shell.exec, …)
     ├── EXT-002  single-purpose coding agent fleet (spec, task, builder, architect,
     │            planner, editor, test-reader, … — mirroring the jarify roles)
     ├── EXT-003  orchestration / bounded coding loop (+ REQ-4 deterministic repair)
     ├── EXT-004  operator terminal UX (Claude-Code-like front-end)
     ├── EXT-005  self-evaluation & monitoring + the supervisor convergence loop
     ├── EXT-008  from-intent build loop (generative spine, hidden-oracle scoring)
     ├── EXT-014  model-reference honesty → founding profile of the model roster
     └── EXT-021  MULTI-MODEL routing harness (registry + router judge + rewire +
                  per-model adaptation + best-first roster profiling)

  Standing operational companions of this directive (owner, 2026-07-01):
     docs/PURSUIT.md        the indefinite maximum-velocity doctrine (single entry point)
     docs/IDEA-BANK.md      queued novel levers, each with probe + kill criterion
     docs/IDEA-PLAYBOOK.md  the mechanical operators that refill the bank
     docs/GAP-MAP.md        the living steering artifact (created at bootstrap)
     .launch/PUBLISHED.md   provenance for every publicly-stated figure
  New pursuit capabilities (instruments, training plane, retrieval plane, always-on
  flows, the Foundry) are specced as new EXTs under the tenet they serve as they are
  built — spec + code in the same commit, per Tenet 4.
```

Every `EXT` serves exactly one tenet of the Intent and must never contradict a
higher tenet. New capability is added by widening the fleet and sharpening the
tools — never by reaching for a larger model.
