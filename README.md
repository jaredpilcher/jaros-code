# jaros-code

**Claude Code for extremely small models.** A software-development agent harness, built on the
**Jaros** runtime, that aims to feel like Claude Code — plan a task, navigate code, fix bugs,
build features, run tests — while **every reasoning call is served by a single small _local_
model at zero inference cost**. The default model is **Gemma 4 `e2b` (a ~2B model)** served by
`llama.cpp` on a **Jetson Orin Nano**. No paid or cloud model is ever used, not even as a fallback.

## The idea

Frontier coding agents lean on a frontier model's reasoning to drive a free-form agent loop. A 2B
can't carry that. jaros-code's bet is that the techniques which make a tiny model _usable_ are
themselves a distinct harness philosophy:

- **Two-plane discipline.** The model only emits inert `Decision` data; a deterministic, **test-
  gated** execution plane (tools) performs every side effect. A wrong generation reverts instead
  of shipping.
- **Decompose, don't escalate.** When the 2B can't reliably make a judgement, push it into the
  deterministic plane instead of reaching for a bigger model.
- **Structure over free-form planning (the "jarify-flow").** Measured head-to-head, a *structured*
  decompose→implement→verify flow beat a free-form agent loop **3/3 vs 2/3** on the same 2B — the
  model is unreliable at choosing *what steps to take*, but reliable at small, checkable sub-tasks
  behind a fixed flow. So planning is the **decomposition principle at the workflow level**.

The result: a private, local, zero-cost coding agent. The deterministic half is as reliable as any
tool; the generative half is 2B-capped but **safe** (test-gated). It is *not* a Claude-Code
replacement for hard, ambiguous work — but "navigate/refactor reliably + fix and build well-scoped
code, all on a Jetson at zero cost" is a real tool.

## What it can do (measured honestly)

| Capability | How it's measured | Result |
|---|---|---|
| Single-function synthesis | HumanEval pass@1 | ~58% (the 2B ceiling; ~76% within the retry budget) |
| Multi-step repair (locate→fix→test) | agentic eval | 3/3 |
| Multi-function generation (build me X) | build eval, hidden-oracle scored | 6/7 |
| Code intelligence / refactoring | deterministic | 100% reliable (it's AST/git, not the model) |

The honest progress signal is **breadth + the agentic evals**, not HumanEval pass@1 — that's pinned
at the 2B ceiling. `/trend` shows both.

## CLI

```
python -m harness.cli                 # interactive REPL
python -m harness.cli "/status"       # one command and exit
```

A human types one plain request and the agent drives the tools. Highlights:

- **`/agent <request>`** — the agentic loop: classify → (fix flow | build flow) → implement →
  verify. `/agent --plan <request>` previews the plan without touching anything; `/undo` reverts
  a whole run (checkpoints).
- **`/build <func> <intent>`** — generative: write tests from the intent, then implement.
- **Code intelligence (deterministic, 100% reliable):** `/usages /defn /callers /deadcode /map
  /about /locate` and refactors `/rename /move` (test-gated — can't silently break behavior).
- **`/remember` / `/memory`** — persistent project memory (`.jcode/memory.md`).
- **`/trend`** — pass-rate history + breadth (census) growth.

Plain-language phrasings route deterministically too ("rename X to Y", "where is X used",
"tell me about X").

## Architecture

```
request ─► model (inert Decision/plan) ─► gate/validate ─► deterministic tools (side effects) ─► hash-chained, replayable log
```

Agents are single-purpose (one narrow judgement each); tools are deterministic with
`validate()`+`execute()`. Capability comes from composing many small agents and tools, not one big
agent or a bigger model. The whole run is reproducible and byte-replayable.

## Governance

The repo is governed by `.jarify/` specifications; **`PRIME-001` is the Prime Directive**. Its five
ordered, non-negotiable tenets: (1) two-plane discipline, (2) small-model-only, (3) reproducible &
honest, (4) spec-first, (5) Claude-Code-like UX — where a lower tenet is never weakened for a
higher one. See `CLAUDE.md` for the working agreement.

## Running the model node

```
pwsh scripts/serve.ps1     # boot the llama.cpp node (Windows)
bash scripts/serve.sh      # POSIX
```

Inference defaults to the Jetson llama.cpp endpoint (`JCODE_LLM_BACKEND=llamacpp` +
`LLAMACPP_HOST`); a local Ollama `gemma2:2b` path remains selectable.

---

*Every reasoning call here cost $0 and ran on a 2B model on a Jetson. That's the whole point.*
