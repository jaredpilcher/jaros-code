# jaros-code — System & Approach Handoff

A working brief for an agent picking this up. Read `.jarify/PRIME-001/intent.md` and
`design.md` first — they are the constitution. This doc summarizes what exists and *how
we improve it*.

## 1. What this is and the goal

**jaros-code** is a software-development harness built on the **Jaros** runtime. The
goal: **match or exceed Claude Code (as run on Claude Opus 4.8) at real coding work,
while every reasoning call is served by a single small LOCAL model at zero paid
inference.** Today that model is `gemma2:2b` (1.6 GB, via Ollama); a migration to a small
Gemma 4 (`gemma4:e2b-it-qat`) on a Jetson Orin Nano via **llama.cpp** is in flight.

The wager: small models haven't been useful for dev work because their *harnesses* are
thin, not because the models are incapable. A deterministic, reproducible harness that
decomposes work into many tiny agent decisions — each backed by a deterministic tool —
can close the gap a single big prompt to a big model cannot.

## 2. Governance — PRIME-001, five ordered tenets (never weaken a lower one for a higher)

1. **Two-plane discipline.** The model emits only inert `Decision` data (JSON). A
   deterministic execution plane performs every side effect. No file write / shell / network
   originates from a model output.
2. **Small-model-only, zero paid inference.** All reasoning is one local small model. No
   cloud/paid model ever, not even as fallback. "Needs a bigger model" → decompose instead.
3. **Reproducible & honest.** Hash-chain logged, byte-identically replayable with zero model
   calls. Never hide, round away, or fabricate a result. A failing test is reported failing.
4. **Spec-first (the jarify way).** Behavior is governed by `.jarify/` specs; code traces to
   requirements via `index.json`; spec + code change in the same commit; stale specs are
   defects. The harness builds the *user's* software the same way it was built (convergence
   on the user's intent).
5. **Claude-Code-like UX.** Familiar transparent terminal feel — but UX never overrides the
   tenets above it.

When a change would violate a tenet, **STOP and flag it** — don't silently resolve.

## 3. Architecture (the two planes)

```
 REASONING PLANE   many tiny single-purpose agents; each makes ONE judgement via the
                   local model and emits inert JSON Decisions (no side effects)
        │ Decision data
        ▼
 DECISION GATE     deterministic validate() per tool → accept / reject
        ▼
 EXECUTION PLANE   deterministic tools (the clerk) perform the host effect, then record
                   fs.read fs.list fs.grep fs.find write_file apply_patch shell.exec …
        ▼
 DURABLE STATE     hash-chained decision log → replay reconstructs byte-identical state
                   with ZERO model calls (Tenet 3)
```

## 4. What's built

**Agents (10, in `.jaros-data/agents/`)** — each single-purpose:
`rewriter` (whole-file edit, the workhorse), `editor` (surgical OLD/NEW), `test_reader`
(PASS/FAIL judgement), `test_writer` (generative: intent→tests), `orchestrator` (routes
plain-language CLI requests), `navigator`, `commander`, `config_editor`,
`dockerfile_editor`, `markdown_editor`.

**Tools (10, in `.jaros-data/tools/`)** — deterministic, safety-gated:
`fs.read fs.list fs.grep fs.find py.symbols py.check json.check write_file apply_patch
shell.exec`. (`_codesafety.py` is a shared denylist helper.)

**Orchestration (`harness/coding_loop.py`)**:
- `fix_loop` — bounded edit→test→judge. **Repair regime** (existing buggy code):
  feedback-iteration + escalating temperature. **Implement regime** (a `NotImplementedError`/
  `pass` stub): the **strategy cascade** (see §6).
- `mutation_repair_loop` — **deterministic, model-free** boundary-bug repair: try each
  single-operator mutation (`<`↔`<=`, `±1`), test-select the first that passes. Cracks
  off-by-one bugs the model cannot reason about.
- `build_from_intent` (`harness/intent_loop.py`) — the **generative spine**: writes its own
  tests, implements them, scores against a **hidden oracle** the agents never see. Two
  metrics: `self_pass` (own tests) vs `oracle_pass` (intent fidelity). The `self✓/oracle✗`
  quadrant is the un-gameable "misread the intent" signal.

**Evals (`evals/`)**: 35 authored coding tasks (tiers 1–3) + 2 from-intent tasks + external
benchmarks with loaders — **HumanEval** (164), **MBPP** (974), **MultiPL-E** js/rs (the real
multi-language bar). Datasets are gitignored (fetched, not vendored). Loaders:
`harness/humaneval.py`, `mbpp.py`, `multipl_e.py`. Each verified deterministically with a
known-good reference solution before being trusted.

**CLI (`harness/cli.py`)** — Claude-Code-like REPL. Slash commands (`/fix /run /grep /ls
/read /find /symbols /files /patch /status /report /trend /agents /tools`) plus plain-language
routing via the orchestrator. Run: `python -m harness.cli` (or `scripts/jcode.ps1` / `.sh`).
Currently **single-action** routing; growing toward multi-step plans.

**Continuous runner (`scripts/run_forever.py`)** — forever loop: eval → report → heartbeat.
Hot-reloads new agent/tool/eval *files*; **harness *code* changes need a runner restart.**

**Reporting & metrics (`harness/report.py`, `eval_runner.py`, `honesty.py`)**: pass rate +
Wilson 95% CI, per-tier, frontier tier + difficulty ratchet, growth census, **wiring usage**
(every agent→tool edge that fires; orphan detection), model-call telemetry (proof the local
model does the work), an **honesty audit** (flags CRITICAL/STAGNATION/MISLEADING/UNUSED), and
an **orchestration/wiring-quality** block (see §6). Phone reports via `PushNotification` on a
30-min schedule (quiet hours 02:00–08:00).

**Pluggable backend (`JCODE_LLM_BACKEND`)**: `ollama` (default, `/api/generate`) or
`llamacpp` (`harness/llamacpp_client.py`, OpenAI-compatible `/v1/chat/completions`). Both
local. Switch via `LLAMACPP_HOST`.

**Safety**: `shell.exec` denylist (no network egress / destructive / privilege-escalation),
`_codesafety` denylist on generated code (no `os.system`/`subprocess`/`eval`/etc.), and a 15s
cap on test execution so a generated infinite loop can't hang the loop.

## 5. The method — the convergence loop (run forever, supervisor-owned)

```
MEASURE → DIAGNOSE → DISCOVER → PLACE → WIRE → RE-MEASURE → PRUNE   (repeat forever)
```
- **MEASURE** honestly: evals (repair pass-rate AND generative self-vs-oracle), census, wiring.
- **DIAGNOSE**, don't guess: probe the *raw* model output to see *which grain* failed and *why*
  before changing anything.
- **DISCOVER** the next "type of sand" (grain) the failure demands. The mountain needs many
  *distinct* grain types, not many copies of one.
- **PLACE** it via **plane-placement triage**: a judgement the small model can reliably make
  (classify, pick a file, transform-by-example, read a result) → a **tiny agent**; something it
  can't (count, arithmetic, operator semantics, exhaustive search) → a **deterministic tool**,
  usually generate-and-test. **Wire it so it actually fires (no orphans).**
- **RE-MEASURE & PRUNE**: keep only what moves a real metric; revert net-negative changes
  (never ship them).

## 6. Hard-won principles (the crux — internalize these)

- **"Stop giving ants boulders."** Capability comes from composing many tiny agents + sharp
  deterministic tools, not a bigger model.
- **Decomposition has two directions.** "Decompose further" is NOT only "more/tinier agents."
  When a grain's *core* is a judgement the small model genuinely can't make, slicing it thinner
  just reproduces the failure — move the work to the **deterministic plane**. *Proven:* a
  single-operator off-by-one defeated every model-side decomposition (a line-locator
  hallucinated line 6 of a 3-line file); a model-free mutation-repair cracked it.
- **The cascade insight (biggest capability win so far).** Individually-marginal strategies
  (best-of-N, few-shot) each looked like noise AND traded tasks (regressions) because each
  *replaced* the baseline. But they're **complementary** — each solves problems the others
  miss. A **test-gated cascade** (try plain → few-shot → high-temp, accept the first that passes
  the test) takes their **union** and is **strictly non-regressing**. Proven out-of-sample on
  HumanEval[40:60]: baseline 13/20 → cascade 17/20 (+4, zero regressions). This is the thesis
  working: cheap diverse attempts + deterministic verification = compounded capability.
- **Honesty is the moat.** External benchmarks (not self-authored) are the real bar; a hidden
  oracle keeps the generative path un-gameable. Always say what a number *measures* — "97% on
  35 self-authored tasks" is NOT "97% of the way to Opus-4.8."
- **Four watched signal families** (the definition of progress): **capability** (pass rate +
  oracle fidelity), **growth** (agents/tools/evals counts), **orchestration/wiring quality**
  (`leverage` = solved-per-agent and distinct wired edges — measurable because Jaros logs every
  decision; a rise at flat agent count = better wiring), and **health** (no orphans, no
  net-negative). Activity is never the metric; the trend is.
- **The ratchet.** When the eval suite saturates (frontier = null), that's a *defect in the
  suite* (too easy), not a victory — harden it or lean on external benchmarks.

## 7. Honest current state & limitations

- Authored suite: ~94–97% on 35 tasks (gemma2:2b) — but small, noisy, and near-saturated even
  after hardening. The real bar is external.
- HumanEval: cascade beats baseline on an easy out-of-sample slice; the *hard* problems still
  fail and the full-164 number (which will be far lower) hasn't been run end-to-end yet.
- **Breadth is the big gap.** Essentially Python-only (one JS task proven via MultiPL-E
  plumbing); **zero multi-file tasks, zero frameworks.** It's a strong *Python single-function +
  repair* harness, a long way from Claude-Code breadth across languages/frameworks/paradigms.
- **Known metric flaw:** `leverage = solved/agents` is sensitive to suite size (more tasks →
  higher leverage even without better wiring). Needs normalizing (e.g. pass-rate-per-agent).

## 8. In flight — model migration to the Jetson

Switching from `gemma2:2b` (slow on the dev box's CPU) to small **Gemma 4** (`gemma4:e2b-it-qat`,
instruction-tuned, ~4.3 GB) on a **Jetson Orin Nano** (aarch64, GPU) served by **llama.cpp**.
- Ollama on the dev box was upgraded 0.24→0.30.9; the e2b model pulled and smoke-tested locally
  (clean direct output, ~27s/call on CPU — the Jetson GPU should be much faster).
- A parser fix was needed: gemma4 closes the file sentinel with `>>>` not `FILE>>>`; the rewriter
  now accepts both (and is greedy so a `>>>` in a docstring doesn't truncate).
- **llama.cpp client is built and tested** (no server needed yet). Handoff is one step once the
  Jetson `llama-server` is up: `JCODE_LLM_BACKEND=llamacpp` and
  `LLAMACPP_HOST=http://192.168.1.183:<port>`. A `health()` probe verifies the endpoint first.
- SSH to the Jetson is set up key-only (`ssh jetson`); the password is no longer needed.
- **Next:** stand up llama-server on the Jetson (bind `--host 0.0.0.0`, `-it` gguf, chat
  endpoint), `health()` it, run a speed+correctness smoke test, then switch the runner and
  **re-baseline** (history keeps a `model` field so old gemma2 runs stay distinguishable).

## 9. Suggested next moves (priority order)

1. Finish the Jetson/llama.cpp migration + re-baseline on the new model.
2. Run the **full external benchmarks** (HumanEval-164, an MBPP slice, MultiPL-E js) for honest
   numbers — the authored suite is saturated.
3. **Breadth**: prove a 2nd/3rd language end-to-end (Rust via MultiPL-E is downloaded but the
   harness isn't wired for its test assembly yet), add the first **multi-file** task, grow the
   orchestrator toward **multi-step plans** (find→read→fix→run).
4. Widen the cascade with a **plan-then-code** strategy (strictly additive — can only grow the
   union).
5. Fix the `leverage` metric (normalize for suite size).

## 10. Where things live / how to run

- Repo: `C:\Users\jared\Documents\GitHub\jaros-code`
- Governance: `.jarify/PRIME-001/` (`intent.md`, `design.md`), features `EXT-001`…`EXT-008`.
- Agents `.jaros-data/agents/`, tools `.jaros-data/tools/`, model config `.jaros-data/config/llm.json`.
- Harness `harness/` (coding_loop, eval_runner, report, honesty, cli, ollama_client,
  llamacpp_client, humaneval, mbpp, multipl_e, intent_loop, notify).
- Evals `evals/coding_tasks/`, `evals/intent_tasks/`, datasets `evals/benchmarks/` (gitignored).
- Run the CLI: `python -m harness.cli`. Run the forever loop: `python scripts/run_forever.py`.
- Tests: `python -m pytest -q` (110 passing). Commit LOCALLY only; footer
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## 11. Safety rails (do not cross)

All inference LOCAL small-model only, zero paid/cloud ever. From the harness: no internet
egress/writes, no installs, no ungated model-generated shell, no modifying files outside the
repo, no weakening safety gates. Commit locally only; never commit secrets, datasets, or
runtime artifacts. Pointing inference at the Jetson on the LAN is the intended *local* path, not
internet egress.
