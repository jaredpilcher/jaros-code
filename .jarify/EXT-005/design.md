# EXT-005 — Convergence Evaluation Harness

The eval harness turns "are we getting closer to Claude Code?" into a number we can
watch move. It runs the same `fix_loop` an operator uses, over a suite of isolated
coding tasks, and records the pass rate as the convergence signal.

```text
  evals/coding_tasks/*.json            harness/eval_runner.py
  ───────────────────────────          ─────────────────────────────────────────
  { id, instruction,                   for each task:
    target, test_cmd,                     mkdtemp() ── write files ── isolated
    files:{name:content} }                fix_loop(target, instr, test_cmd, cwd)
                                          record {id, solved, attempts}
                                       ───────────────────────────────────────────
                                       scorecard: passRate, perTask, model, secs
                                          │
                                          ├─► artifacts/eval/scorecard-<ts>.json
                                          └─► artifacts/eval/history.jsonl  (trend)
```

## Why this is the right signal

- It exercises the **whole stack** the user cares about: agents + tools + loop +
  the real model — not a unit mock. A pass means gemma2:2b, inside this harness,
  actually produced working code.
- It is **honest** (Tenet 3): a task counts as solved only when its tests truly
  pass (exit 0); the runner never massages the number.
- It is **external-facing-ready**: the same runner shape will later wrap public
  benchmarks (SWE-bench/HumanEval), so our yardstick converges on a recognized one.

## Growth

The suite starts small and is meant to become extensive — every new bug class, every
regression a swarm agent fails, becomes a task. The trend line across `history.jsonl`
is how we monitor, run over run, that more/smaller agents + sharper tools move us
toward Claude-Code-on-Opus-4.8.
