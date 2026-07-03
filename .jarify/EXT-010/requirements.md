---
id: EXT-010
title: Real-world robustness — hardening for real repos + real input
status: covered
priority: high
implementation:
  - file: harness/multi_file.py    # REQ-1/REQ-2 test-run timeout handling + configurable budget; REQ-5 import-closure root; REQ-6 minimal-diff pass
  - file: harness/agent_loop.py    # REQ-1 run-action timeout guard
  - file: harness/agentic_eval.py  # REQ-1 _pytest_passes timeout guard
  - file: harness/cli.py           # REQ-1 handle() guards; REQ-3 /files + /grep arg parsing
  - file: harness/mbpp.py          # REQ-4 targeted test (test_* collection)
  - file: harness/humaneval.py     # REQ-4 targeted test (defensive)
  - file: tests/test_ext010_multifile_localize.py  # REQ-5 regression test
  - file: tests/test_ext010_minimal_diff.py        # REQ-6 regression test
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

### [REQ-5] Multi-file fault localization must resolve candidates against the target root, not the process CWD  (DONE)

`harness/multi_file.candidate_files` finds the files that could hold a fault by walking the
import graph reachable from the failing test. But it seeds the BFS frontier with the *bare*
`test_file` name and reads it with `Path(cur).read_text()` — relative to the PROCESS cwd, not
the target repo `cwd`/`root`. When the harness runs a repo in an isolated dir (every eval, every
SWE-bench/daily-driver run — process cwd ≠ target root), the seed read raises `OSError`, the
import closure is never walked, and `candidate_files` returns `[]`. For the common case of an
ASSERTION failure — where the traceback names ONLY the test file (which is correctly excluded) —
the import closure is the *sole* path to the culprit, so `multi_file_fix` finds no candidates
and reports "no candidate fixed it" in ~1s WITHOUT EVER CALLING THE MODEL. This silently
mislabels a fixable cross-file fault as unsolved and blocks the entire multi-file capability on
any isolated run. Root the closure walk at `root`.

#### Acceptance Criteria
- [x] `candidate_files` seeds its import-closure BFS with the test file resolved against `root`
  (e.g. `root / Path(test_file).name`), so the seed is readable regardless of process cwd
- [x] For a cross-file assertion fault (bug in `geometry.py`, failing test in `test_shapes.py`
  importing `shapes.py` importing `geometry.py`), `candidate_files` returns the import-closure
  files (`shapes.py`, `geometry.py`) — not `[]`
- [x] A regression test (`tests/test_ext010_multifile_localize.py`) sets up that 3-file scenario
  in a temp dir, runs from a DIFFERENT process cwd, and asserts the closure files are found
- [x] No regression to existing multi_file behavior; full suite stays green

### [REQ-6] Minimal-diff pass — drop redundant edits after all-green (Claude-Code-parity clean diffs)  (DONE)

MEASURED gap (docs/GAP-MAP.md #3): `multi_file_fix` keeps edits CUMULATIVELY — any candidate edit that
strictly REDUCES the failing-test count is kept, and it returns the moment the suite goes all-green. So when
a partial-progress edit (e.g. a symptom patch on a CALLER) is kept and a LATER edit (the ROOT-cause fix) then
turns everything green, BOTH edits are kept even though the caller patch is now REDUNDANT. Claude Code emits a
MINIMAL diff (just the root fix); jaros-code leaves the extra hunk. This is a pure two-plane DETERMINISTIC
quality gap — no model, no reasoning — fixable by a test-gated minimization (delta-debugging) pass that removes
any kept edit not necessary to keep the suite green.

#### Acceptance Criteria
- [x] `harness/multi_file.py::multi_file_fix` captures the ORIGINAL contents of the repo at the start (before
  any edit) and, upon reaching all-green, runs a minimization pass BEFORE returning solved
- [x] Minimization: for each KEPT file's edit (iterate in reverse-kept order), temporarily REVERT that file to
  its original content and re-run `test_cmd`; if the suite is STILL all-green the edit was redundant → keep it
  reverted and drop it from the kept set; otherwise restore the fixed content (the edit is necessary). The pass
  is purely deterministic + test-gated (no model call)
- [x] Invariant: the repo ALWAYS ends all-green with the MINIMAL necessary edit set — never leaves the repo
  failing, never drops a necessary edit (each drop is re-verified by a green run)
- [x] The returned dict reports the minimal `fixed` list plus a new `dropped` field naming any removed-redundant
  edits (diagnosable); `solved` stays True
- [x] Backward compatible: when only ONE edit was kept (the common case), minimization is a no-op that cannot
  drop the sole necessary edit (reverting it fails the suite → restored)
- [x] Offline test (`tests/test_ext010_minimal_diff.py`, NO model): construct a temp-dir scenario where
  `multi_file_fix` (with a stubbed/canned fix_loop, or a direct minimization-helper test) ends with a redundant
  caller edit AND the root edit both applied; assert the minimization DROPS the redundant caller edit, the suite
  stays green, and the necessary root edit is retained. Full suite stays green.
