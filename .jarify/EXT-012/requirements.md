---
id: EXT-012
title: Behavioral Gherkin-Driven Alignment Loop (2B-authored, all layers)
status: covered
priority: high
implementation:
  - file: harness/gherkin_loop.py
    ranges:
      - - 1
        - 1
---

### [REQ-1] The 2B authors every layer; the harness only runs tests and keeps pointers

The 2B model authors EVERYTHING — Gherkin behavior, tests, and code (create/modify/delete). The
deterministic plane only runs tests and maintains exact pointers. This preserves Tenet-2
(local-2B-only reasoning) and Tenet-1 (two-plane discipline): no side effect originates from a
model output.

#### Acceptance Criteria
- [ ] The 2B generates and edits the Gherkin, tests, and code at every layer
- [ ] The deterministic plane performs only test execution and pointer maintenance
- [ ] No file write, test run, or other side effect originates directly from a model output

### [REQ-2] Behavioral solve loop: Gherkin → tests → code → fix

Given a task, the 2B reasons in a behavioral (Gherkin) layer first, derives tests from it, then writes
code to satisfy those tests, iterating to green. The core loop (Slice 1a) is Gherkin → self-tests →
code → fix, with alignment enforced at every seam (Gherkin↔task, tests↔Gherkin, code↔tests,
code↔Gherkin).

#### Acceptance Criteria
- [ ] Author Gherkin behavior for the task before generating tests
- [ ] Derive self-tests from the authored Gherkin
- [ ] Generate code against the fixed self-tests and iterate until they pass
- [ ] Enforce alignment at each seam (Gherkin↔task, tests↔Gherkin, code↔tests, code↔Gherkin)
- [ ] Treat executable tests as hard checkpoints and 2B self-reviews as soft checkpoints

### [REQ-3] Gherkin comprehension step pins the exact behavior the intent names

A comprehension step reads the intent literally and pins the exact case it names before authoring
behavior, preventing intent misreads (e.g. the `exactly_n` misread). This is an integrated default
layer of the canonical solve.

#### Acceptance Criteria
- [ ] Read the task intent literally and identify the exact case it specifies
- [ ] Pin that case into the authored Gherkin before tests are derived
- [ ] Verify the comprehension step prevents intent-misread regressions

### [REQ-4] Multi-function localization with a target cap

The solve localizes and solves every changed function in a commit (multi-function), with a target cap
(>4 functions) to keep large multi-target commits tractable.

#### Acceptance Criteria
- [ ] Identify every changed function in the commit and solve each one
- [ ] Apply a target cap so commits exceeding the cap (>4 functions) are limited/skipped
- [ ] Keep the per-commit run tractable under the target cap

### [REQ-5] Parse-gated syntax repair on every code generation

Every code-gen flows through parse-gated syntax-repair (the pass1/body_completer lineage) so generated
code that is logically correct but syntactically broken is repaired before scoring.

#### Acceptance Criteria
- [ ] Route every code generation through the parse-gated syntax-repair stage
- [ ] Repair parseable-after-fix code without altering its intended logic
- [ ] Verify repaired code is re-parsed/validated before being scored

### [REQ-6] Unified code-gen chokepoint across eval and product paths

Both the EXT-012 behavioral layers and the pass1/body_completer repairs flow through the SAME code-gen
chokepoint (`g_code`), so every generation — in both the eval and the `/build` product path — inherits
all proven layers. The eval tests forward across the full union of layers, never a new layer against a
bare baseline.

#### Acceptance Criteria
- [ ] Route both the behavioral layers and the repair lineage through one shared code-gen chokepoint
- [ ] Ensure the eval path and the product (`/build`) path inherit the identical layer stack
- [ ] Test each new layer forward atop all previously proven layers, not against a bare baseline

### [REQ-7] Held-out generalization gating; integrate-or-prune by measurement

Every layer/idea earns its place by measurement on HELD-OUT commits and is then INTEGRATED as a
permanent layer or PRUNED. Net-negative changes are reverted. Naive self-reviews, the unguarded
sign-off, and the baseline-ensemble were measured and pruned.

#### Acceptance Criteria
- [ ] Gate each candidate layer on held-out commits it was never tuned on
- [ ] Integrate a layer as permanent only when it lifts the held-out pass rate
- [ ] Revert/prune any net-negative layer (e.g. naive self-reviews, unguarded sign-off, baseline-ensemble)
- [ ] Report pass@1 honestly with a Wilson CI for each gate

### [REQ-8] Honest oracle with no test leakage

The 2B's self-generated tests are scaffolding derived from the intent only; the hidden repo oracle
(red→green) remains the only score. The model never sees the hidden oracle, so there is no leakage of
expected outputs into the solve.

#### Acceptance Criteria
- [ ] Derive self-tests solely from the visible intent, never from the hidden oracle
- [ ] Score solely on the hidden repo oracle (red→green), separate from the self-tests
- [ ] Verify the hidden oracle is never exposed to the solving prompt (no leakage)

### [REQ-9] Cross-repo generalization

The behavioral loop is evaluated across multiple repositories (more-itertools and toolz), reporting
per-repo and combined honest pass@1, to prove the lift generalizes beyond a single repo rather than
overfitting one.

#### Acceptance Criteria
- [ ] Evaluate the behavioral loop on more-itertools and on toolz
- [ ] Report per-repo and combined pass@1 with Wilson CIs honestly
- [ ] Verify the lift holds (matches or beats baseline) across repos, not just one

### [REQ-10] Persisted symbol-anchored Gherkin index

A persisted Gherkin index holds one entry per code unit: the behavioral description plus a pointer
anchored to a SYMBOL (qualified name + file). The deterministic tool plane resolves symbol→line-range
via AST and re-resolves after every edit ("sync anchors"), keeping pointers exact while the 2B owns
behavioral content. Bootstrapped for existing units and reused across runs.

#### Acceptance Criteria
- [ ] Persist a Gherkin index with one entry (behavior + symbol pointer) per code unit
- [ ] Anchor each entry to a qualified symbol name plus file (not raw line numbers)
- [ ] Resolve symbol→line-range via AST in the tool plane and re-resolve after every edit
- [ ] Bootstrap the index for all existing code units and reuse it across runs

### [REQ-12] Generate-and-test generation — select best-of-N candidates by the model's own self-tests

A deterministic generate-and-test mechanism proposes N candidate implementations (via varied
seeds on the code-writer agent), runs each against the model's own self-tests (derived from
the visible spec/intent — NEVER the hidden oracle), then selects the best candidate: first to
pass all self-tests, else highest pass-count, tie broken by lowest index (stable). Selection is
purely deterministic; no model call is made at selection time.

This tool is BUILT but NOT YET wired into the default solve path. It must be measured on
held-out commits (integrate-or-prune gate, REQ-7) before any default use. Any pass-rate
improvement must reflect the model genuinely solving more, never oracle leakage (Tenet 3 /
REQ-8).

#### Acceptance Criteria
- [ ] `code.generate_and_test` tool validate() rejects empty or non-list candidates payloads
- [ ] execute() selects the first all-pass candidate (all self-tests pass)
- [ ] execute() falls back to the highest-pass-count candidate; ties broken by lowest index
- [ ] Selection uses ONLY the model's own spec-derived self-tests; hidden oracle is never touched
- [ ] `generate_and_test_solve()` generates n candidates (varied seed), runs selftests, applies selection
- [ ] Tool and harness helper are additive; default solve path is NOT modified
- [ ] Must be measured on held-out commits before wiring into the default path (integrate-or-prune)

### [REQ-11] Whole-repo bootstrap, reconcile, and multi-file changes

The loop bootstraps Gherkin across a whole repo and reconciles existing behavior across multiple
units (keep / modify / delete neighbors, preserve-unchanged behavior) including multi-file changes. A
deleted behavior propagates: a test asserting the behavior is gone → code that removes it.

#### Acceptance Criteria
- [ ] Bootstrap Gherkin descriptions for all existing code units in the repo
- [ ] Reconcile each existing Gherkin as keep / modify / delete for a given task
- [ ] Preserve behavior that must not change while applying the task's changes
- [ ] Propagate deletions: assert the behavior is gone in tests and remove it in code across files
