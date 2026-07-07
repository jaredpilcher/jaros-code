# Implementation Tasks

### [TASK-1] Core behavioral solve loop — 2B-authored Gherkin, comprehension-pinned, two-plane discipline

The core Slice-1a loop has the 2B author everything (Gherkin behavior, tests, and code)
while the deterministic plane only runs tests and maintains pointers: given a task, the 2B
first reads the task intent literally and pins the exact behavioral case it names (avoiding
intent misreads such as the `exactly_n` case), authors Gherkin from that pinned case,
derives self-tests from the Gherkin, then writes code to satisfy those tests, iterating to
green with alignment enforced at every seam (Gherkin↔task, tests↔Gherkin, code↔tests,
code↔Gherkin).

#### Steps
1. Implement a comprehension step in `harness/behavioral_solve.py` (lines 140-340) that
   reads the task intent literally and pins the exact case it specifies before any Gherkin
   is authored.
2. Author Gherkin behavior for the task from the pinned case, ensuring every model-side
   step (Gherkin, tests, code, edits/deletes) originates from a 2B call, never from a
   harness-authored template.
3. Derive self-tests from the authored Gherkin, then generate code against those fixed
   self-tests, iterating until they pass.
4. Enforce alignment checks at each seam (Gherkin↔task, tests↔Gherkin, code↔tests,
   code↔Gherkin), treating executable tests as hard checkpoints and 2B self-reviews as soft
   checkpoints.
5. Ensure no file write, test run, or other side effect is performed directly from a model
   output — every side effect flows through the deterministic tool plane
   (`harness/commit_replay.py`, lines 370-400 for the driving loop).

#### Implements
- [REQ-1] The 2B authors every layer; the harness only runs tests and keeps pointers
- [REQ-2] Behavioral solve loop: Gherkin → tests → code → fix
- [REQ-3] Gherkin comprehension step pins the exact behavior the intent names

### [TASK-2] Multi-function localization with a target cap

The solve localizes and attempts every changed function in a commit rather than a single
target, applying a target cap (>4 functions) so large multi-target commits stay tractable
instead of ballooning the per-commit run.

#### Steps
1. Identify every changed function in the commit under evaluation in
   `harness/behavioral_solve.py`.
2. Drive the Gherkin → self-test → code loop (TASK-1) independently for each identified
   function.
3. Apply a target cap so commits touching more than 4 functions are limited or skipped,
   keeping the per-commit run bounded.

#### Implements
- [REQ-4] Multi-function localization with a target cap

### [TASK-3] Parse-gated syntax repair on every code generation

Every code generation — behavioral or otherwise — flows through the parse-gated
syntax-repair stage (the pass1/body_completer lineage) so logically-correct-but-
syntactically-broken output is repaired before it is ever scored.

#### Steps
1. Route each code-generation call in the behavioral solve loop through the shared
   parse-gated syntax-repair stage rather than scoring raw model output directly.
2. Repair parseable-after-fix code (e.g. indentation, stray tokens) without altering its
   intended logic.
3. Re-parse/validate the repaired code before it is handed to the test runner or scored.

#### Implements
- [REQ-5] Parse-gated syntax repair on every code generation

### [TASK-4] Unified code-gen chokepoint across eval and product paths

Both the EXT-012 behavioral layers and the pass1/body_completer repair lineage flow through
the same code-gen chokepoint (`g_code`), so every generation in both the eval path and the
`/build` product path inherits the identical proven layer stack, and new layers are always
tested forward atop the full union of previous layers rather than against a bare baseline.

#### Steps
1. Route the behavioral layers (TASK-1 through TASK-3) and the repair lineage through one
   shared `g_code` chokepoint instead of duplicating generation logic per path.
2. Ensure the eval path (`harness/commit_replay.py`) and the product `/build` path invoke
   the same chokepoint so they inherit an identical layer stack.
3. When adding a new layer, test it forward atop all previously-proven layers rather than
   against a bare, layer-less baseline.

#### Implements
- [REQ-6] Unified code-gen chokepoint across eval and product paths

### [TASK-5] Held-out generalization gating; integrate-or-prune by measurement

Every layer or idea earns its place strictly by measurement on held-out commits it was
never tuned on: a layer that lifts the held-out pass rate is integrated as permanent, and a
net-negative layer is reverted. Naive self-reviews, the unguarded sign-off, and the
baseline-ensemble were all measured this way and pruned.

#### Steps
1. Gate each candidate layer's integration decision on held-out commits it was never tuned
   against, reusing the held-out split from EXT-011.
2. Integrate a candidate layer as a permanent part of the solve loop only when it measurably
   lifts the held-out pass rate.
3. Revert/prune any layer measured to be net-negative (recorded cases: naive self-reviews,
   the unguarded sign-off, and the baseline-ensemble).
4. Report pass@1 honestly with a Wilson CI for each gating measurement.

#### Implements
- [REQ-7] Held-out generalization gating; integrate-or-prune by measurement

### [TASK-6] Honest oracle with no test leakage

The 2B's self-generated tests are scaffolding derived only from the visible intent; the
hidden repo oracle (red→green) is the sole score and is never shown to the model during
generation, so there is no leakage of expected outputs into the solve.

#### Steps
1. Derive self-tests solely from the visible task intent in `harness/behavioral_solve.py`,
   never from the hidden repo oracle.
2. Score solely on the hidden repo oracle (red→green, reusing EXT-011's oracle), kept
   entirely separate from the self-test scaffolding.
3. Verify no code path exposes the hidden oracle's tests or expected outputs to the solving
   prompt at any stage.

#### Implements
- [REQ-8] Honest oracle with no test leakage

### [TASK-7] Cross-repo generalization (more-itertools and toolz)

The behavioral loop is evaluated across more-itertools and toolz, reporting per-repo and
combined honest pass@1 with Wilson CIs, to demonstrate the lift generalizes rather than
overfitting a single repository.

#### Steps
1. Run the behavioral solve loop (TASK-1 through TASK-6) against both more-itertools and
   toolz task corpora via `run_gherkin_jaros_multi` (EXT-011 TASK-6/7).
2. Report per-repo pass@1 with Wilson CIs alongside the combined pass@1 across both repos.
3. Confirm the measured lift holds (matches or beats baseline) on both repos individually,
   not just in aggregate.

#### Implements
- [REQ-9] Cross-repo generalization

### [TASK-8] Persisted symbol-anchored Gherkin index

A persisted Gherkin index holds one entry per code unit — the behavioral description plus a
pointer anchored to a qualified symbol name + file, not raw line numbers. The deterministic
tool plane resolves symbol→line-range via AST and re-resolves after every edit ("sync
anchors"), so pointers stay exact while the 2B owns the behavioral content; the index is
bootstrapped once and reused across runs.

#### Steps
1. Define a persisted Gherkin index structure with one entry per code unit, storing the
   behavioral description plus a symbol pointer (qualified name + file).
2. Implement AST-based symbol→line-range resolution in the deterministic tool plane, and
   re-resolve every entry's pointer after each edit to keep anchors exact ("sync anchors").
3. Bootstrap the index for all existing code units on first run and persist it so subsequent
   runs reuse it instead of re-deriving behavior from scratch.

#### Implements
- [REQ-10] Persisted symbol-anchored Gherkin index

### [TASK-9] Whole-repo bootstrap, reconcile, and multi-file changes

The loop bootstraps Gherkin across a whole repo and reconciles existing behavior across
multiple units for a given task (keep / modify / delete each neighbor, preserving
unchanged behavior), including multi-file changes; a deleted behavior propagates end to
end — a test asserting the behavior is gone, and code that removes it.

#### Steps
1. Bootstrap Gherkin descriptions for every existing code unit in the target repo, seeding
   the persisted index (TASK-8).
2. For a given task, reconcile each existing Gherkin entry as keep / modify / delete,
   preserving the behavior of units the task does not intend to change.
3. Apply reconciled changes across multiple files in one task when the task spans more than
   one unit/file.
4. Propagate a "delete" reconciliation end to end: add a test asserting the behavior is gone
   and remove the corresponding code across the affected files.

#### Implements
- [REQ-11] Whole-repo bootstrap, reconcile, and multi-file changes

### [TASK-10] Generate-and-test — select best-of-N candidates by the model's own self-tests

A deterministic generate-and-test mechanism proposes N candidate implementations via varied
seeds on the code-writer agent, runs each against the model's own visible-spec-derived
self-tests (never the hidden oracle), then deterministically selects the best candidate:
first to pass all self-tests, else the highest pass-count with ties broken by lowest index.
The tool is built and additive but not wired into the default solve path pending held-out
measurement (TASK-5's integrate-or-prune gate).

#### Steps
1. Implement the `code.generate_and_test` tool (`.jaros-data/tools/generate_and_test_tool.py`,
   lines 41-119) with `validate()` rejecting empty or non-list candidate payloads.
2. Implement `execute()` to select the first candidate that passes all of the model's
   self-tests, falling back to the highest-pass-count candidate with ties broken by lowest
   index — selection itself makes no model call.
3. Implement `generate_and_test_solve()` in `harness/generate_test_solve.py` (lines 58-187)
   and the corresponding driver logic in `harness/commit_replay.py` (lines 906-1204) to
   generate N candidates via varied seeds, run the model's own spec-derived self-tests
   against each, and apply the deterministic selection — using only the visible spec, never
   the hidden oracle.
4. Keep the tool and harness helper additive: do not modify the default solve path until the
   mechanism is measured on held-out commits per TASK-5's integrate-or-prune gate.

#### Implements
- [REQ-12] Generate-and-test generation — select best-of-N candidates by the model's own self-tests

### [TASK-11] Stronger-oracle self-test augmenter — docstring-example assertions

Because weak self-test oracles previously caused a best-of-N regression (5/37, per the
EXT-012 design PRUNE lesson), a deterministic augmenter strengthens the model's self-tests
by parsing the target function's visible docstring for `>>> ` example lines and appending
each as a concrete `assert` statement, giving the fix-loop a better red signal on wrong
candidates. Activated only via an opt-in `--augment` flag; the default solve path is
unchanged pending held-out measurement.

#### Steps
1. Implement the `code.augment_selftests` tool
   (`.jaros-data/tools/selftest_augmenter_tool.py`, lines 59-211) with `validate()`
   rejecting non-string `name`, `source`, or `self_tests` payload fields.
2. Implement `execute()` to parse `>>> expr` / expected-value pairs from the target
   function's visible docstring (sourced from the parent repo, never the hidden oracle) and
   append a correctly-asserting test function to the model's self-tests.
3. Fall back unchanged (`augmented=False`, `examples_found=0`) when the source has no
   docstring, and no-op gracefully when the docstring has no `>>> ` lines.
4. Validate the augmented test output is parseable Python (`ast.parse` clean) before use,
   and never read, import, or reference the hidden oracle (`test_more.py` / redgreen) from
   this tool.
5. Wire a `--augment` flag into the `commit_replay --gherkin-loop --jaros` CLI path
   (`harness/commit_replay.py`, lines 762-903) that activates the augmented self-tests
   without changing the default (unaugmented) solve.

#### Implements
- [REQ-13] Stronger-oracle self-test augmenter — docstring-example assertions
