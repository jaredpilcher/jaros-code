# jaros-code — Architecture & How It Works

A software-development harness built on **Jaros** that aims to reach Claude-Code-on-
Opus-4.8 quality while every reasoning call is served by a single small local model —
**Gemma 4 2B (`e2b`)** via llama.cpp on the Jetson Orin Nano — at zero inference cost.
(Legacy Ollama `gemma2:2b` path remains selectable for back-compat.)
The wager: *small models underperform because their harnesses are thin, not because the models are incapable.*

This document is the written-up, honest picture of the whole system. It is governed by
`.jarify/PRIME-001` (the prime directive) and the `EXT-00x` specs.

## 1. The two planes (Jaros)

```text
  REASONING PLANE  — single-purpose Gemma 4 2B (e2b) agents emit inert Decision data only
        │  Decision (JSON: id, source, type, payload)
        ▼
  DECISION GATE    — deterministic validate() per tool (+ safety gates)
        │
        ▼
  EXECUTION PLANE  — deterministic tools perform the host effect, then record it
        │
        ▼
  DURABLE STATE    — hash-chained decision log → byte-identical replay, 0 model calls
```

The arrow only points down. No agent holds a file/shell/network handle; every effect is
a deterministic tool. The model proposes; a deterministic clerk decides what runs.

## 2. The coding loop (EXT-003)

```text
  fix_loop(target, instruction, test_cmd, max_iters):
    for round 1..max_iters:
      content   = fs.read(target)                      # tool
      symbols   = py.symbols(target)                   # tool → agent context (.py)
      edit      = <specialist>.decide({content, instruction, symbols, feedback, temp, seed})
      apply edit via code.write_file / code.apply_patch # tool (safety-gated)
      ok?       = py.check / json.check(target)         # tool — catch broken syntax early
      output    = shell.exec(test_cmd)                  # tool — run the tests
      verdict   = test-reader.decide({output})          # agent
      if tests exit 0: SOLVED                            # ground truth = exit code, not the verdict
```

Key properties:
- **Ground truth is the test exit code**, never the model's verdict (a hallucinated PASS
  cannot count — PRIME-001 Tenet 3).
- **Error feedback + temperature escalation:** round 1 is greedy (temp 0, repeatable);
  retries get the previous failure output as feedback and escalate temperature/seed so a
  deterministically-wrong answer can be escaped.
- **Retry budget matters:** raising `max_iters` 2→3 moved the full-suite pass rate
  **67% → 83%** (round 1 is often wasted on a format/syntax error; the 3rd attempt
  recovers via feedback).

## 3. Specialist agents + dispatcher (EXT-007 / REQ-6)

Capability comes from MANY small specialists, not a few broad agents. A deterministic
**dispatcher** routes each target to the right specialist:

```text
  target type        specialist            edit tool          syntax guard
  ─────────────────  ───────────────────   ────────────────   ─────────────
  .py / code         rewriter              code.write_file    py.check
  .json/.yaml/.ini…  config-editor         code.write_file    json.check
  (override)         editor (surgical)     code.apply_patch   py.check
```

The fleet (single-purpose reasoning agents): `rewriter` (whole-file code), `config-editor`
(config files), `editor` (surgical OLD→NEW), `test-reader` (PASS/FAIL verdict), `commander`
(one shell command), `navigator` (search term → fs.grep). The roadmap (EXT-007/TASK-9)
continues splitting by domain: `dockerfile-editor`, `python_fixer`, regex/algorithm helpers,
architecture/spec agents — each wired so it fires (no orphans).

## 4. Deterministic tools (EXT-001)

```text
  read-only (replay-safe): fs.read · fs.list · fs.grep · fs.find · py.symbols ·
                           py.check · json.check
  effectful (recorded):    code.write_file · code.apply_patch · shell.exec
```

**Safety gates (unattended-safe):**
- `shell.exec` (REQ-7) refuses network egress (curl/wget/ssh/git push/pip install/URLs),
  destructive ops (rm -rf/format/dd/shutdown), and privilege escalation.
- **Generated code** (REQ-11) is scanned before being written: `code.write_file`/
  `code.apply_patch` refuse content with process/network/destructive/dynamic-exec ops.

So both the *commands* and the *code the model writes* are gated.

## 5. Evaluation & honesty (EXT-005)

- A suite of isolated coding tasks (`evals/coding_tasks/*.json`), each run in a throwaway
  temp dir; solved iff its real tests pass (exit 0). Tiers ramp difficulty; the suite is
  meant to keep getting harder (the ratchet) and to incorporate real public benchmarks
  (HumanEval adapter included).
- **Pass rate carries a Wilson 95% CI** that narrows as the suite grows → the parity
  number gets *more accurate over time*.
- **Growth census:** counts of agents/tools/evals/specs, tracked over time (must rise,
  with quality; orphans pruned).
- **Wiring telemetry:** which agent→tool edges actually fire — used to find and remove
  orphans (agents/tools that never fire).
- **Model-call telemetry:** every Gemma 4 2B (`e2b`) call is counted and logged to
  `model_calls.log` — undeniable proof the local model does the work.
- **Honesty audit (EXT-007/REQ-5):** mechanically flags CRITICAL (0 model calls),
  MISLEADING (tiny suite as headline), STAGNATION (flat pass rate), UNUSED (orphans). The
  supervisor must act on flags — capability (pass rate) is the metric, activity is not.

## 6. Continuous operation

```text
  scripts/run_forever.py   (background, forever)   eval → report → heartbeat → repeat
        │ heartbeat.json / REPORT.md / model_calls.log
        ▼
  Claude supervisor loop   (~every cycle)          read metrics → honesty audit →
                                                   make ONE real improvement → commit
```

Two layers: the runner continuously *measures*; the supervisor *improves* (jarify way),
strictly local — it never pushes, installs, or touches the network (`SAFETY.md`). Reports
go to the owner's phone every 30 min outside 02:00–08:00.

## 7. Current honest state

- Full suite: **20/24 = 83%** on Gemma 4 2B (`e2b`) / llama.cpp (95% CI 64–93%); was 67% before the
  retry-budget fix.
- Census: ~6 agents, ~10 tools, ~25 evals, 7 EXT specs; orphans being wired-in or pruned.
- ~80+ deterministic unit tests pass.
- Target: 100% on hard, recognized benchmarks (Claude-Code-on-Opus-4.8 parity), proven —
  not claimed.

See `docs/CATALOG.md` for the live agent/tool/eval catalog, and `.jarify/` for the specs.
