# Implementation Tasks

### [TASK-1] Scenarios file — realistic FAILED-solve states with expected-action oracle

`evals/judgment/scenarios.json` holds 8-10 generic, honest scenarios (not fitted to any
benchmark item), each a realistic failed-solve state with the correct action a competent
2B judge should take, covering every defined failure class at least once.

#### Steps
1. Author `evals/judgment/scenarios.json` as valid JSON: a list of scenario dicts, each with
   `id`, `failure_class`, `intent`, `name`, `feedback`, `expected_action`
   (one of `code`/`gherkin`/`repair`/`done`), and `rationale`.
2. Cover the `syntax` class (IndentationError/SyntaxError/unmatched paren -> `repair`),
   `logic` class (self-tests fail on wrong output -> `code`), `import` class
   (NameError/missing import -> `repair` or `code`, documented), `all_pass` class (all
   self-tests pass -> `done`), and `bad_tests` class (self-tests contradict the intent or
   are malformed -> `gherkin`), each with at least one scenario.
3. Add at least 3 additional scenarios covering variations or edge cases within those
   classes, bringing the total to at least 8 scenarios, all generic and not tuned to a
   specific benchmark item.

#### Implements
- [REQ-1] Scenarios file — realistic FAILED-solve states with expected-action oracle

### [TASK-2] Runner — load scenarios, call the real judge, score, report

`harness/judgment_eval.py` is a standalone runnable module that loads the scenarios file,
calls the real `_judge_revision` 2B judge for each scenario, scores chosen-vs-expected, and
prints a per-scenario table plus overall and per-class accuracy breakdowns.

#### Steps
1. Implement `harness/judgment_eval.py` (lines 22-134) to load
   `evals/judgment/scenarios.json` and, for each scenario, call
   `_judge_revision(intent, name, fb, temp=0.0)` from `harness.behavioral_solve` (the real
   judge, no mock, in a live run).
2. Parse the judge's returned action, handling raw text gracefully by falling through to the
   same `next((a for a in _REV if a in out), "code")` logic the caller already uses
   elsewhere.
3. Score each scenario's chosen action against its `expected_action` (bool `ok`), and print
   a per-scenario table (`scenario | failure_class | expected | got | ok`), an overall
   accuracy line (`N/M correct (P%)`), and a per-`failure_class` breakdown
   (`N_correct/N_total`).
4. Expose `run_eval(judge_fn=None)` as a callable entry point returning the per-scenario
   results as a list of dicts, usable both from `python -m harness.judgment_eval` and from
   unit tests via dependency injection.

#### Implements
- [REQ-2] Runner — load scenarios, call real judge, score, report

### [TASK-3] Offline unit test — schema and scorer validation

`tests/test_judgment_eval.py` validates the eval entirely offline (no Jetson, no LLM,
no network) by checking the scenarios file's schema and exercising the scorer through the
`run_eval(judge_fn=...)` injection point with a stubbed judge.

#### Steps
1. In `tests/test_judgment_eval.py` (lines 9-231), load `evals/judgment/scenarios.json` and
   assert every scenario has the required fields and that `expected_action` is always one of
   `{code, gherkin, repair, done}`.
2. Stub `_judge_revision` via `run_eval(judge_fn=...)` to return a fixed action (e.g. always
   `"code"`), call `run_eval(judge_fn=stub)`, and assert scenarios expecting `"code"` score
   `ok=True` while all others score `ok=False`.
3. Assert the computed overall accuracy matches the count of `"code"`-expected scenarios
   given the stub.
4. Assert `harness.judgment_eval` imports cleanly with no import error and without a Jetson
   connection, so `pytest tests/test_judgment_eval.py -q` passes with no Jetson running.

#### Implements
- [REQ-3] Unit test — offline, stub judge, schema + scorer validation
