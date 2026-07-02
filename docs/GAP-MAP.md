# GAP-MAP — the Claude-Code capability surface, every gap in exactly one state

**The steering wheel of THE PURSUIT** (`docs/PURSUIT.md` §2.7 / §9.3). Work always flows to the
highest **(impact × tractability)** gap here. Living document — updated every cycle; never "done."

**States (exactly one per row):**
`unmeasured → probed → lever-named → in-progress → closed(number) → wall(dated, evidence)`

- **unmeasured** — no honest number yet.
- **probed** — a cheapest-falsifier probe has run; we know roughly where it stands.
- **lever-named** — the next mechanism to try is identified (with its escalation-ladder rung).
- **in-progress** — that lever is being built/measured now.
- **closed(number)** — parity-or-better vs Claude-Code-on-Opus-4.8 on a held-out instrument, with the number.
- **wall(date, evidence)** — no Jetson-fit path found across the FULL escalation ladder (L0–L8); DATED, revisited on every new model/method. A bookmark, never a conclusion.

Escalation ladder rungs referenced below: L0 prompt/format · L1 decompose/control-flow · L2 plane-shift · L3 precise-retrieval/fact-injection · L4 experience-recall · L5 reduction · L6 routing/new-model · L7 LoRA · L8 micro-model/distill · L9 dated wall.

> **v0 (2026-07-01)** — seeded from the session's measured results at tag `baseline-pursuit` (pending). Numbers are honest current state, NOT parity claims; NO row is `closed` (nothing yet matches Claude Code end-to-end). The daily-driver suite (§9.2) will replace these ad-hoc numbers with the frequency-weighted parity instrument.

---

## Capability surface

| # | Gap | State | Current honest number / evidence | Next lever (rung) |
|---|-----|-------|----------------------------------|-------------------|
| 1 | **Repo navigation / understanding** | probed | `/map` repo-map built (Aider-derived, `harness/repo_map.py`); no held-out parity number vs CC | daily-driver nav slice (§9.2) → measure (impact HIGH, tractable) |
| 2 | **Bounded single-file edits** | in-progress | SWE-bench-Lite easy-slice **5/8**; HumanEval-40 code-gen gemma 33/40, qwen 36/40 (routed +3); SEARCH/REPLACE + best-of-N + parser/line-level fallbacks | L3 fact-injection probe (django-11964 comprehension-vs-generation, in flight) → LoRA S/R emitter (L7) |
| 3 | **Multi-file edits** | probed | hard multi-step-repo (more-itertools multi-function) measured 0 across roster; single-file dominates current wins | L5 reduction library + L1 decomposition per-file |
| 4 | **Refactors** | probed | refactor/navigation family had committed wins earlier (authored suite); no held-out CC-parity number | daily-driver refactor slice (§9.2) |
| 5 | **Test write / run / fix loops** | in-progress | `solve_with_repair` built (best-of-N repair, test-gated); measured limited lift on hard slice; test-gate as judge is the workhorse | property-based test-gen (L2/§5C) + fix-iteration latency budget |
| 6 | **Debugging from failure** | lever-named | gold-free localization built (traceback L3 / coverage-trace); works for CRASH-class, not wrong-output (needs reasoning) | traceback→fix wiring on a real failing test (Docker) |
| 7 | **Long-horizon tasks (bootstrap→ship)** | unmeasured | no instrument yet — benchmarks can't measure it | **the Foundry** (§5G) — build real software end-to-end, binary ship/no-ship grading |
| 8 | **Repo-scale context** | lever-named | generic context injection measured **net-negative** (do not repeat); precise dep-signature retrieval ~parity | semantic retrieval plane (§5B, PRECISE only) + program-analysis fact-sources (§5C) |
| 9 | **git / shell tool breadth** | probed | deterministic tools exist (fs.read/list/write, shell.exec, grep, apply_patch, code.search_replace); breadth vs CC unmeasured | Gap-list vs CC's tool surface → fill by frequency |
| 10 | **Interactivity / latency** | unmeasured | no Jetson latency budget instrumented yet (scoreboard #4) | instrument p50/p95 per command class on the Jetson (§9 census) |
| 11 | **Robustness / recovery** | probed | test-gate + validate() gates + process-tree-kill guards; no held-out robustness number | error-recovery slice in daily-driver suite |

## Cross-cutting measured walls (dated bookmarks, never conclusions)

- **wall(2026-07-01) — hard multi-step-repo algorithm synthesis** for the 2–4B Jetson-fit roster. Evidence: pass@k 0/7 (`9856d52`), decomposition 0/8 (`ff7726f`), maximal-help 0/6 (`5006e42`), decorrelated-reasoner 0/6, collaboration 0/6, experiment-loop 0/6; cell #35 un-throttled qwen3+repair **1/2 NEUTRAL** (`baseline-pursuit`, task #35 — task2's 3-function running-median all fail). **Revisit** on: any new Jetson-fit reasoning-distilled model (L6), a LoRA specialist (L7), a reduction library (L5), or the comprehension-vs-generation probe flipping (L3). NOT yet L8 (distillation untried on this class).

## Steering note

**Measured 2026-07-01 (daily-driver instrument, live gemma):** the **fix-single-file-to-pass-a-given-failing-test** category is a HARNESS STRENGTH — 9/9 on authored tasks up to moderate algorithmic difficulty (merge-intervals, deep-flatten, dedup-order), because `fix_loop`'s test-gated best-of-N iteration extracts the solution (same mechanism as SWE-bench 5/8). This is NOT a CC-parity claim (authored, single-file, a failing test handed in) — it is a calibration: **authoring more fix-with-test tasks no longer discriminates.**

**Consequent redirect — invest where there is NO failing test to iterate against** (that is where CC's edge over a test-gated 2B shows): **#4 refactor** (behavior-preserving), **build-from-intent** (held-out oracle, no test shown), **#3 multi-file**, and **#1 navigate via the REAL CLI** (not a raw-model answer_fn). Next concrete step: extend the daily-driver runner routing for build-from-intent + refactor (a jarify-builder task) — those categories will discriminate and produce the first meaningful parity number. Then latency (#4/#10) + Foundry (#7) for the long-horizon gaps benchmarks can't see. Bootstrap remaining: solution-store (§9.4), embedder/LoRA/distill probes (§9.5/6, Jetson-only training).
