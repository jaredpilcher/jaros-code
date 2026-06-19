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

## Spec map

```text
  PRIME-001  ── north star (this document; intent.md + design.md only)
     ├── EXT-001  deterministic tool plane (fs.read, fs.list, shell.exec, …)
     ├── EXT-002  single-purpose coding agent fleet (planner, editor, test-reader, …)
     ├── EXT-003  orchestration / bounded coding loop (handoff + outer driver)
     ├── EXT-004  operator terminal UX (Claude-Code-like front-end)
     └── EXT-005  self-evaluation & monitoring (parity benchmarks, health)
```

Every `EXT` serves exactly one tenet of the Intent and must never contradict a
higher tenet. New capability is added by widening the fleet and sharpening the
tools — never by reaching for a larger model.
