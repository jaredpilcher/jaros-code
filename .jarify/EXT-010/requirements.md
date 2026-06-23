---
id: EXT-010
title: Real-world robustness — hardening for real repos + real input
status: complete
priority: high
implementation:
  - file: harness/multi_file.py    # REQ-1/REQ-2 test-run timeout handling + configurable budget
  - file: harness/agent_loop.py    # REQ-1 run-action timeout guard
  - file: harness/agentic_eval.py  # REQ-1 _pytest_passes timeout guard
  - file: harness/cli.py           # REQ-1 handle() guards; REQ-3 /files + /grep arg parsing
  - file: harness/mbpp.py          # REQ-4 targeted test (test_* collection)
  - file: harness/humaneval.py     # REQ-4 targeted test (defensive)
---

Serves **Tenet 5** (Claude-Code-like UX — never crash on the user) and **Tenet 3** (honest: the
authored evals can't catch these, so dogfooding finds them). All fixes verified against the real
jaros-code repo + malformed input; the 161-test CI stays green (behavior on the authored evals is
unchanged — only failure/edge paths differ).

### [REQ-1] No unhandled crash on real input or slow suites  (DONE)

A command, or a test run inside the fix/build/refactor flow, must never dump a traceback or kill
the session. A slow real suite (jaros-code's own is ~45s) exceeding the test timeout, or any
unexpected exception in a command, must degrade gracefully.

#### Acceptance Criteria
- [x] `multi_file._run` catches `subprocess.TimeoutExpired` → non-green run, not a crash
- [x] `agent_loop` run-action and `agentic_eval._pytest_passes` likewise guard the timeout
- [x] `cli.handle` is guarded in BOTH the REPL (survives to the next command) and the one-shot
  entry (clean `error:` line + exit 1), so a bad command never shows a traceback

### [REQ-2] Test-gating is usable on real repos  (DONE)

The hard 30s test-run timeout made every test-gated flow (fix, build, **refactor**) spuriously
report "suite not green" on any repo whose suite is slower — including jaros-code's own.

#### Acceptance Criteria
- [x] the test-run timeout is a realistic default (120s) and env-configurable (`JCODE_TEST_TIMEOUT_S`)
- [x] verified: `_run('.', 'pytest')` returns green (~47s) on the real repo where the 30s cap timed out;
  `/rename` and `/move` complete their before/after gate on the real suite

### [REQ-3] CLI argument parsing matches user intent  (DONE)

`<pattern> [path]` commands split on whitespace, so a natural multi-word pattern or a path-glob was
mis-parsed and silently returned nothing.

#### Acceptance Criteria
- [x] `/files harness/*.py` splits the dir + glob (was 0 → 26 files)
- [x] `/grep def fix_loop` greps the whole phrase, only peeling a trailing arg that is a real path
  (was 0 → finds it); `/grep TODO harness` still scopes to the path

### [REQ-4] Benchmark scoring is correct for `test_*` entry points  (DONE)

A task whose function is named `test_*` (e.g. MBPP's `test_duplicate`) was spuriously failed: the
generated test's `from solution import test_duplicate` made pytest **collect the imported function
as a test**, call it with no args, and error the whole suite — scoring correct code as wrong.

#### Acceptance Criteria
- [x] MBPP/HumanEval run the real test explicitly (`pytest test_solution.py::test_mbpp` /
  `::test_humaneval`) so the imported entry point isn't collected
- [x] verified: mbpp_19 (`test_duplicate`) flips FAIL → PASS; no regression at the 40-task slice
