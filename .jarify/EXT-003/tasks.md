# Implementation Tasks

### [TASK-1] Faithful Jaros runtime wrapper

A `Runtime` class registers the EXT-001 deterministic tools plus the built-in `advance`
handler, then routes every agent-emitted Decision through the real Jaros gate
(`validate_decision`) and executor (`executor.apply`) before recording it, so the coding
loop is byte-identically replayable and every side effect is validated and logged.

#### Steps
1. Implement `Runtime` in `harness/coding_loop.py` (lines 112-377) that registers custom
   tools from `.jaros-data/tools` and the `advance` handler on construction.
2. Validate every incoming Decision at the gate (`validate_decision`) before touching the
   host; a rejected Decision returns a reason string instead of executing.
3. Apply accepted Decisions via `executor.apply` and return the tool's real output to the
   caller.
4. Record each accepted Decision to a durable `DecisionLog` under the data dir's `state/`
   directory.

#### Implements
- [REQ-1] Faithful Jaros runtime wrapper

### [TASK-2] Bounded edit→test→judge loop with a transparent transcript

`fix_loop` composes the `editor` agent, `code.apply_patch`, `shell.exec`, and the
`test-reader` agent into a bounded iteration loop over a target file and a test command,
printing a Claude-Code-like per-round transcript so the operator can see exactly what the
harness is doing at each step.

#### Steps
1. Implement `fix_loop` in `harness/coding_loop.py` (lines 686-884): each round reads the
   target file, passes bounded content to the `editor` agent, applies the returned edit
   through the `Runtime`, runs the test command via `shell.exec`, and feeds the captured
   output to `test-reader`.
2. Stop iterating as soon as `test-reader` judges PASS, or after `max_iters` rounds are
   exhausted; report the final outcome and the number of attempts used.
3. Print a per-round header naming the active model/provider, each agent's emitted
   Decision type, and each tool's real result summary as the loop runs.
4. Print the final PASS/FAIL verdict and attempt count once the loop terminates.

#### Implements
- [REQ-2] Bounded edit→test→judge loop
- [REQ-3] Claude-Code-like transcript

### [TASK-3] Deterministic boundary-mutation repair fallback

For the boundary/off-by-one bug class (`<` vs `<=` and similar), the fix moves out of the
model plane entirely: `boundary_repair_candidates` enumerates every single-operator
mutation deterministically, and `mutation_repair_loop` applies and tests each one via the
Runtime, keeping the first candidate that passes — a byte-identically reproducible repair
with no reasoning call involved.

#### Steps
1. Implement `boundary_repair_candidates` in `harness/coding_loop.py` (part of lines
   499-563) as a pure function that yields one single-operator edit per candidate
   (`<`↔`<=`, `>`↔`>=`, `±1`), de-duplicated and stably ordered.
2. Implement `mutation_repair_loop` to apply each candidate via `code.write_file` through
   the Runtime, run the suite via `shell.exec`, and return success on the first candidate
   that makes the tests pass.
3. On total failure, restore the original file so a failed repair never leaves the
   repository in a worse state.
4. Wire `mutation_repair_loop` as the `fix_loop` fallback path for `.py` bug-fixes that the
   whole-file rewriter (TASK-2) could not crack.

#### Implements
- [REQ-4] Deterministic boundary-mutation repair fallback

### [TASK-4] Strategy-diverse cascade for the implement regime

When `fix_loop` detects an implement-regime target (a `NotImplementedError`/`pass` stub),
it drives a cascade of complementary generation strategies — plain greedy, plain warm,
few-shot, few-shot warm, and two high-temperature attempts — from the clean stub, all in
the body-completer mode, and the deterministic test gate selects the first attempt that
passes. Because acceptance is test-gated, the result is a strictly non-regressing union of
what the strategies solve individually; multi-file and multi-fault repair build on the same
loop.

#### Steps
1. Extend `fix_loop`'s regime detection in `harness/coding_loop.py` (lines 686-884) to
   recognize a `NotImplementedError`/`pass` stub and switch to the strategy cascade instead
   of single-attempt feedback iteration.
2. Widen the attempt budget to cover the full strategy set (greedy, warm, few-shot,
   few-shot warm, high-temp x2) when in the implement regime, driving every attempt through
   the `body`-only completer mode (output only the function body, spliced after the given
   signature+docstring) rather than whole-file regeneration.
3. Leave repair tasks (existing buggy code) on the unchanged feedback-iteration path.
4. Implement `harness/multi_file.py` (`multi_file_fix`, wired as CLI `/fixrepo`) to locate
   candidate files deterministically (traceback files + import graph reachable from the
   failing test) and try `fix_loop` on each candidate on a clean snapshot, reverting a
   non-helping attempt before trying the next.
5. Add an opt-in `keep_partial` flag to `fix_loop` (default off, so single-file behavior is
   byte-identical) that, on overall failure, keeps the attempt with the fewest test
   failures, enabling `multi_file_fix` to fix multi-fault, cross-file bugs cumulatively.

#### Implements
- [REQ-5] Strategy-diverse cascade for the implement regime

### [TASK-5] Scoped rename — identifier-only renaming via tokenize

`rename_symbol` in `harness/refactor.py` renames only Python NAME (identifier) tokens
equal to the target symbol, using `tokenize` to find NAME-token spans and doing
position-based replacement, so comments, docstrings, and string literals that happen to
contain the same text are left untouched — matching the precision of a Claude-Code-style
rename instead of a crude word-boundary regex over the whole file.

#### Steps
1. Rewrite the renaming core in `harness/refactor.py` (lines 54-78, 99-119) to walk Python
   `tokenize` output per file and collect NAME-token spans equal to `old`, replacing them in
   reverse order per line/offset so spans stay valid (no `untokenize` reformatting — the
   rest of the file stays byte-identical apart from the renamed identifiers).
2. Skip a file that fails to tokenize (`SyntaxError`) safely instead of crashing the whole
   rename.
3. Keep the existing whole-repo, test-gated behavior: the suite must be green before
   renaming, and a red suite after renaming reverts via the existing snapshot mechanism;
   preserve the return-dict shape (`renamed`/`occurrences`/`files`/`note`).
4. Count `occurrences` only from renamed identifier tokens, never from string/comment hits.
5. Add `harness/refactor.py` to this spec's traceability (`index.json`) and to the
   frontmatter `implementation` list, since it was previously untraced.

#### Implements
- [REQ-6] Scoped rename — don't rename inside comments/docstrings/strings

### [TASK-6] Deterministic double-application repair fallback

For self-composition call-chain bugs where a value is passed back through the same
function a second time (e.g. tax/discount applied twice), `double_application_repair_candidates`
detects the redundant-application shape deterministically and
`double_application_repair_loop` unwraps it without ever touching the inner function's own
body — avoiding the float-rounding false-negatives that a full model rewrite produced.

#### Steps
1. Implement `double_application_repair_candidates` in `harness/coding_loop.py` (lines
   566-683) as a pure function that detects, per function, both the intermediate-variable
   shape (`v = fn(...)` ... `fn(v, ...)`) and the fully-nested shape (`fn(fn(...), ...)`),
   yielding one unwrap candidate per occurrence, de-duplicated and stably ordered, never
   touching the function's own definition/body.
2. Implement `double_application_repair_loop` (lines 859-871) mirroring
   `mutation_repair_loop`: apply each candidate via `code.write_file` through the Runtime,
   run the suite via `shell.exec`, and keep the first candidate that makes the tests pass.
3. On total failure, restore the original file so the repair never leaves a worse file.
4. Wire `double_application_repair_loop` as the first attempt in the `fix_loop` fallback
   chain (tried before boundary-mutation repair), falling through unaffected to TASK-3 when
   no candidate exists or none passes.

#### Implements
- [REQ-7] Deterministic double-application repair fallback (self-composition call-chain bugs)
