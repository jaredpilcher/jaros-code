---
id: EXT-016
title: Tool-Use-Judgment Eval (2B judge diagnosis)
status: covered
priority: high
implementation:
  - file: harness/judgment_eval.py
    ranges:
      - - 1
        - 130
  - file: evals/judgment/scenarios.json
    ranges:
      - - 1
        - 200
  - file: tests/test_judgment_eval.py
    ranges:
      - - 1
        - 120
---

### [REQ-1] Scenarios file — realistic FAILED-solve states with expected-action oracle

A JSON file `evals/judgment/scenarios.json` holds 8-10 scenarios.
Each scenario is a dict with:
- `id`: short identifier (e.g. "syntax-indent")
- `failure_class`: one of the defined failure classes
- `intent`: a plausible function-building intent string
- `name`: a plausible Python function name
- `feedback`: a realistic failure-feedback string (test runner output or exception)
- `expected_action`: one of the REAL action keys: `code`, `gherkin`, `repair`, `done`
- `rationale`: a one-sentence justification for the expected action

Coverage requirement: at least one scenario per failure class:
- `syntax` — IndentationError / SyntaxError / unmatched paren in generated code -> `repair`
- `logic` — code runs, self-tests fail on wrong output (off-by-one / wrong operator) -> `code`
- `import` — NameError / missing import or helper in generated code -> `repair` or `code` (documented)
- `all_pass` — all self-tests pass -> `done`
- `bad_tests` — self-tests contradict the intent or are malformed -> `gherkin`
- At least 3 additional scenarios covering variations or edge cases

Scenarios must be GENERIC and honest — not fitted to any benchmark item.

#### Acceptance Criteria
- [ ] `evals/judgment/scenarios.json` exists and is valid JSON
- [ ] Each scenario has `id`, `failure_class`, `intent`, `name`, `feedback`, `expected_action`, `rationale`
- [ ] `expected_action` is always one of `{code, gherkin, repair, done}`
- [ ] At least 8 scenarios total
- [ ] All 5 required failure classes are covered
- [ ] At least one scenario per class

### [REQ-2] Runner — load scenarios, call real judge, score, report

`harness/judgment_eval.py` is a standalone runnable module that:
1. Loads `evals/judgment/scenarios.json`
2. For each scenario, calls `_judge_revision(intent, name, fb, temp=0.0)` from
   `harness.behavioral_solve` (the REAL 2B judge — no mock in the live run)
3. Parses the returned action (it may be raw text; handle gracefully — fall through to
   the same `next((a for a in _REV if a in out), "code")` logic the caller already uses)
4. Scores chosen-vs-expected (bool `ok`)
5. Prints a per-scenario table: `scenario | failure_class | expected | got | ok`
6. Prints overall accuracy: `N/M correct (P%)`
7. Prints a per-class breakdown: for each `failure_class`, `N_correct/N_total`
8. Returns (or makes accessible) the per-scenario results as a list of dicts for
   programmatic use (unit tests use this)

Running command: `python -m harness.judgment_eval`

#### Acceptance Criteria
- [ ] `harness/judgment_eval.py` exists and is importable without Jetson (`python -c "import harness.judgment_eval"`)
- [ ] `python -m harness.judgment_eval` runs end-to-end when the Jetson is up
- [ ] Per-scenario table printed to stdout
- [ ] Overall accuracy line printed
- [ ] Per-class breakdown printed
- [ ] Module exposes `run_eval(judge_fn=None)` callable for unit-test injection

### [REQ-3] Unit test — offline, stub judge, schema + scorer validation

`tests/test_judgment_eval.py` validates the eval OFFLINE (no Jetson, no LLM):
1. Loads `evals/judgment/scenarios.json` and checks schema for every scenario
2. Confirms `expected_action` is always in `{code, gherkin, repair, done}`
3. Monkeypatches / stubs `_judge_revision` via the `run_eval(judge_fn=...)` injection
   point to return a fixed action (e.g. always "code")
4. Calls `run_eval(judge_fn=stub)` and confirms:
   - Scenarios with expected "code" score `ok=True`
   - Scenarios with expected anything else score `ok=False`
   - Overall accuracy matches the count of "code"-expected scenarios
5. The test imports `harness.judgment_eval` cleanly (ast.parse, no import error)

`python -m pytest tests/test_judgment_eval.py -q` must pass with no Jetson running.

#### Acceptance Criteria
- [ ] `tests/test_judgment_eval.py` exists
- [ ] `pytest tests/test_judgment_eval.py -q` passes offline
- [ ] Schema validation covers all required fields
- [ ] Stub-judge injection works via `run_eval(judge_fn=...)`
- [ ] Scoring correctness validated against known stub output
- [ ] No LLM or network call in the test
