# Design — EXT-016: Tool-Use-Judgment Eval

## Overview

This spec diagnoses ONE narrow judgement in isolation: when a function-build attempt has failed,
does the small model choose the RIGHT next action — `repair`, `code`, `gherkin`, or `done`? It is
a measurement instrument, not a capability. A held-out **scenarios file** encodes realistic
failed-solve states (one per failure class, plus edge cases), each labeled with an
expected-action oracle; a **runner** feeds each scenario's failure feedback to the real 2B judge
(`_judge_revision` from `harness.behavioral_solve`), parses the chosen action, scores chosen-vs-
expected, and reports overall accuracy plus a per-class breakdown; an **offline unit test**
validates the schema and the scorer with a stub judge so it runs with no Jetson. Scenarios must be
generic and honest — never fitted to a benchmark item.

## Components and flow

```text
  evals/judgment/scenarios.json                 harness/behavioral_solve.py
  ┌──────────────────────────────┐              ┌───────────────────────────┐
  │ [ {id, failure_class,        │              │ _judge_revision(intent,   │
  │    intent, name, feedback,   │              │   name, feedback, temp=0) │
  │    expected_action,          │              │   → raw action text       │
  │    rationale}, ... ]         │              └────────────┬──────────────┘
  │ classes: syntax→repair,      │                           │ (REAL judge; live run)
  │  logic→code, import→repair/  │                           │
  │  code, all_pass→done,        │                           │  stub judge (offline test)
  │  bad_tests→gherkin           │                           │
  └──────────────┬───────────────┘                           │
                 │ load                                       │
                 ▼                                            ▼
        harness/judgment_eval.py :: run_eval(judge_fn=None)
        ┌───────────────────────────────────────────────────────────┐
        │ for each scenario:                                         │
        │   got = parse(judge_fn(intent, name, feedback))            │
        │         └ fall through to next(a for a in _REV ...,"code") │
        │   ok  = (got == expected_action)                           │
        │ ──► per-scenario table  | failure_class | expected | got | ok │
        │ ──► overall accuracy  N/M (P%)                             │
        │ ──► per-class breakdown  class: N_correct/N_total          │
        │ ──► returns list[ {scenario, expected, got, ok} ]          │
        └───────────────────────────────────────────────────────────┘
                 ▲
                 │ injection point
        tests/test_judgment_eval.py  (offline: stub judge, schema + scorer checks, no LLM)
```

## Design choices

- **`run_eval(judge_fn=None)` injection seam.** The same runner drives the real 2B judge (live)
  and a deterministic stub (offline unit test), so scoring logic is provable with no Jetson and no
  network — honest, reproducible measurement (Tenet 3).
- **Graceful action parse.** The judge may return raw text; the runner reuses the caller's own
  `next((a for a in _REV if a in out), "code")` fallback so a malformed judgement degrades to a
  defined action rather than crashing the eval.
- **Generic scenarios only.** Each failure class is represented by a plausible, non-benchmark
  scenario, keeping the diagnosis about the judgement itself, not about any specific eval item.
