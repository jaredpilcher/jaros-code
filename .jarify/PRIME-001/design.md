# PRIME-001 — System Architecture

`jaros-code` is a fleet of single-purpose reasoning agents (each calling
`gemma2:2b`) whose only output is inert `Decision` data, executed by a deterministic
tool plane on top of the Jaros runtime. This document maps the system-wide
architecture the Intent demands. Feature specs (`EXT-00x`) decompose individual
tenets into requirements, design, and tasks.

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
     ├── EXT-003  orchestration / bounded coding loop (handoff + outer driver)
     ├── EXT-004  operator terminal UX (Claude-Code-like front-end)
     └── EXT-005  self-evaluation & monitoring (parity benchmarks, health)
```

Every `EXT` serves exactly one tenet of the Intent and must never contradict a
higher tenet. New capability is added by widening the fleet and sharpening the
tools — never by reaching for a larger model.
