---
id: EXT-018
title: Gated-thinking on the repo code grain
status: covered
priority: high
implementation:
  - file: harness/behavioral_solve.py
    ranges:
      - - 140
        - 340
  - file: harness/commit_replay.py
    ranges:
      - - 370
        - 400
---

### [REQ-1] Gated-thinking in behavioral_solve_jaros

When `think=True`, after the first direct code generation in `behavioral_solve_jaros`,
parse the target function's VISIBLE docstring examples from `current_src` (using
`_doctest_asserts` from `pass1_eval`). If there ARE examples and the generated code
FAILS them (`_visible_ok == False`), regenerate ONCE using a `<think>` reasoning
prompt via `_g_code_think`. If no examples exist, or the direct code passes them,
keep the direct result. When `think=False` (the default), behaviour is byte-identical
to the existing path.

HONEST: the visible docstring examples ONLY GATE when to think. The hidden
red->green oracle is NEVER read during solve — it only scores at the end.

#### Acceptance Criteria
- [ ] `behavioral_solve_jaros` accepts a `think: bool = False` keyword argument.
- [ ] When `think=True` and current_src has docstring examples that the generated code fails, `_g_code_think` is called exactly once to regenerate.
- [ ] When `think=True` and the generated code PASSES the examples, `_g_code_think` is NOT called.
- [ ] When `think=True` and `current_src` has NO docstring examples, `_g_code_think` is NOT called.
- [ ] When `think=False` (default), no think logic runs — default path is byte-identical.
- [ ] `_g_code_think` is defined in `harness/commit_replay.py` and produces valid Python or empty string.

### [REQ-2] --think CLI flag for the commit-replay evaluator

An opt-in `--think` flag on the `commit_replay` CLI activates the gated-thinking
path for all gherkin-loop + jaros runs. It mirrors the existing `--retrieve` and
`--jaros` flags in style and wiring. When absent, the default path is unchanged.

#### Acceptance Criteria
- [ ] `--think` is recognised in both the single-repo (`--gherkin-loop --jaros`) and multi-repo (`--bar big --gherkin-loop --jaros`) CLI paths.
- [ ] `attempt_gherkin_jaros`, `run_gherkin_jaros`, and `run_gherkin_jaros_multi` each accept `think: bool = False` and thread it down to `behavioral_solve_jaros`.
- [ ] The result banner includes a `+think` tag when `--think` is active (mirrors `+retrieve`).
- [ ] The exact measurement command `python -m harness.commit_replay --bar big --gherkin-loop --jaros --think` runs without error.
