# EXT-018 Design: Gated-Thinking on the Repo Code Grain

## Motivation

The gated-thinking mechanism was proven on HumanEval (+19 pass@1) and MBPP (+14).
The core insight: the 2B model already knows how to reason, but one-shot body completion
often skips that reasoning. Spending a `<think>` pass only when the direct code
demonstrably fails the function's OWN docstring examples is efficient and honest.

This spec ports that proven lever into the repo-level code grain
(`behavioral_solve_jaros`) without changing the default path.

## Architecture

```text
attempt_gherkin_jaros(think=True)
  └─ behavioral_solve_jaros(think=True)
       ├─ Grain 1: g_gherkin  → gherkin spec
       ├─ Grain 2: g_selftests → self-tests
       ├─ Grain 3: g_code (direct)  → first code candidate
       │
       ├─ [EXT-018 GATE]  ← NEW (only when think=True)
       │     _doctest_asserts(current_src)  ← visible examples only
       │     _visible_ok(code, asserts)?
       │         YES → keep direct code (no extra LLM call)
       │         NO  → _g_code_think(...)  ← one <think> reasoning pass
       │         (no examples) → keep direct code
       │
       └─ fix-loop: run self-tests → revise on failure (max_fix iters)

CLI: --think flag
  --bar big --gherkin-loop --jaros --think  → run_gherkin_jaros_multi(think=True)
  <repo>  --gherkin-loop --jaros --think    → run_gherkin_jaros(think=True)
```

## Gated-Thinking Helper: `_g_code_think`

Defined in `harness/commit_replay.py` next to `g_code`. Identical structure
to `g_code` except the prompt includes a `<think> </think>` reasoning instruction
BEFORE the implementation output. After generation, the text before `</think>` is
stripped so only the function body is used. Inherits the proven indentation-repair
layer from `g_code`.

## Honesty Properties

- `_doctest_asserts` reads from `current_src` (VISIBLE parent source). The hidden
  red->green oracle (`task["redgreen"]`) is NEVER accessed during the solve.
- `_visible_ok` runs the candidate code against the visible examples in a subprocess.
  Any error OTHER than AssertionError (import error, timeout) returns True = don't
  think, preserving the safe default.
- The gate is opt-in (`think=False` default) — the existing path is byte-identical.

## Additive Invariant

`think=False` (the default) makes `behavioral_solve_jaros` byte-identical to its
pre-EXT-018 form. No existing tests change their expected behaviour.
