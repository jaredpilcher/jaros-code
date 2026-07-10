# Implementation Tasks

### [TASK-1] Build the filesystem oracle (`harness/fs_oracle.py`)

Deterministic, model-free filesystem verifier mirroring `datastore_oracle`'s independence discipline —
the Phase-0 blocker that unlocks the largest slice (files/OS, ETL-join, codegen, static-site-generator).

#### Steps
1. Create `harness/fs_oracle.py` with a `seed_tree(root, spec)` helper that materializes a declarative
   tree (list of `{path, bytes}` files + implied subdirs) under a caller-provided temp `root`.
2. Add `run_and_inspect(root, entrypoint, argv, checks, timeout=...)` that runs the built entrypoint in
   `root` via the existing `secure_exec` sandbox with process-tree teardown (reuse
   `server_oracle._kill_tree`), then evaluates each post-condition by reading the tree independently.
3. Support post-condition kinds: `path_exists`, `path_absent`, `file_bytes_equal` (exact),
   `dir_members_equal` (exact sorted set) — OS-independent (normalize to forward slashes; sort where
   required). No host-path leakage into any prompt.
4. Add `tests/test_ext059_fs_oracle.py` proving a correct built stub passes and a no-op / wrong-bytes /
   wrong-paths stub fails each relevant post-condition; run offline via `run_with_heartbeat`.
5. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-1 to the new file ranges;
   flip `requirements.md` frontmatter `status` toward `partial`.

#### Implements
- [REQ-1] Filesystem oracle (`fs_oracle`)

### [TASK-2] Add exact-stdout / exit-code / empty-output check variants

Extend the suite check vocabulary beyond substring-contains so error-paths, exact serialization forms,
and empty-output cases are honestly scored — pairs with TASK-1 to complete the Phase-0 substrate.

#### Steps
1. In `harness/system_suite.py` (or an imported `checks` helper), add dispatch for `exact_stdout`,
   `expect_rc`, and `empty_output` check kinds through the existing `_run_single_check` seam without
   altering existing substring-contains behavior.
2. Implement each comparison (full-stdout equality; process exit-code assertion; empty-stdout assertion)
   with an unambiguous pass/fail and a helpful mismatch message.
3. Add `tests/test_ext059_check_variants.py` proving each variant discriminates (extra-output fails
   `exact_stdout`; rc=0 fails `expect_rc:2`; any print fails `empty_output`) and that a prior
   substring-contains task still passes unchanged.
4. Update `.jarify/EXT-059/index.json` mapping REQ-2 to the new ranges.

#### Implements
- [REQ-2] Exact-stdout / exit-code / empty-output check variants

### [TASK-3] Build the import-driver oracle (`harness/import_driver.py`)

A verifier that imports a built module/package in a fresh sandboxed subprocess and exercises a pinned
public API — for the reusable-library task class (import-and-call, not stdin→stdout). Unlocks domain F.

#### Steps
1. Create `harness/import_driver.py` with `drive_import(root, module, api_calls, checks, timeout=..., injected=None)`:
   render a small stdlib-only driver snippet that `sys.path`-inserts `root`, imports the built module by
   name, calls the contract-named public API (function/class) with oracle-chosen arguments, and reports
   each result via a unique sentinel line the oracle greps (never the module's own printing).
2. Run that driver in a fresh subprocess through the existing `secure_exec` sandbox (scrubbed env,
   resource caps, process-tree teardown via `server_oracle._kill_tree` in `finally`), mirroring
   `fs_oracle.run_and_inspect`'s launch convention.
3. Support injected dependencies for determinism (e.g. an injected `clock`/`sleep` seam for retry/cache
   libraries) via a small pre-amble the driver installs before calling the API — never wall-clock.
4. Grade declarative post-conditions: `returns_equals` (sentinel value equals expected), `raises`
   (a named exception type is raised), `call_count` (an injected spy recorded N calls). Never raises.
5. Add `tests/test_ext059_import_driver.py`: a correct library module passes; a broken one (wrong return,
   wrong call-count, missing raise) fails the relevant post-condition; injected-clock determinism proven.
   Offline (no model calls). Update `.jarify/EXT-059/index.json` (REQ-3) + check REQ-3 boxes.

#### Implements
- [REQ-3] Import-driver oracle (`import_driver`)

### [TASK-4] Build the agent-loop oracle (`harness/agent_oracle.py`)

Grades a built AGENT's ORCHESTRATION (not its reasoning) so agent systems -- a high-priority real-
system class, including jaros-code itself -- can be honestly verified: inject a scripted stub model
+ controlled tool sandbox, drive a goal, and assert the tool-call sequence + termination.

#### Steps
1. Create `harness/agent_oracle.py` with a local stdlib `http.server` stub that serves scripted
   OpenAI-compatible `/v1/chat/completions` responses (tool-call or final-answer turns, in order)
   and a `/tool/<name>` endpoint that records every tool invocation (name + args, in order) and
   returns a canned observation -- the injection seam is the pinned `OPENAI_BASE_URL`/`MODEL_URL`
   env-var contract (the built agent reads its model endpoint from there; its tools hit the tool-
   sandbox endpoint via `JAROS_TOOL_URL`; the goal is passed as `argv[1]`).
2. Add `drive_agent(root, entry, *, script, tools, goal, env=None, max_steps=..., startup_timeout=...,
   python_exe=...) -> dict` that starts the stub on an ephemeral localhost port, launches
   `python <entry> <goal>` sandboxed (reusing `secure_exec._scrubbed_env`/`_make_preexec_fn` and
   `server_oracle._kill_tree`), waits bounded by `timeout`/`max_steps`, and returns
   `{"ok", "tool_calls", "final", "steps", "terminated", "note", "port"}`. ALWAYS tears the stub
   server down (`shutdown()` + `server_close()`) and kills the agent process tree in a `finally`
   block; never raises.
3. Add `check_agent(result, *, expect_tool_calls, expect_final_contains=None, expect_terminated=True)
   -> (bool, note)` -- a pure, never-raise grader over the captured evidence (ordered tool-call
   name+args match, termination, final-answer substring).
4. Add `tests/test_ext059_agent_oracle.py`: a correct hand-written agent fixture (loops against the
   stub, invokes tools, feeds observations back, prints a final sentinel) passes via `check_agent`;
   a broken fixture (wrong tool call) is caught; `drive_agent` never raises on a crashing/hanging
   agent and leaves the stub port free afterward; a multi-step script exercises the loop +
   observation-feedback; max_steps enforcement is proven. Offline only (no real model). Run only
   `python -m pytest tests/test_ext059_agent_oracle.py -q`.
5. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-6 to the new file
   ranges; `requirements.md` status stays `partial` (REQ-4/REQ-5 remain open).

#### Implements
- [REQ-6] Agent-loop oracle (`agent_oracle`)

### [TASK-5] Build the state-machine / lifecycle oracle (`harness/state_machine_oracle.py`)

A deterministic, model-free verifier that grades whether a built system enforces a legal state
machine — the highest-leverage substrate gap (unblocks order/shipment/fulfillment/RMA/
prescription/claim/dispute/moderation/appointment/subscription lifecycle classes). The honesty
core: illegal transitions (ship-before-pay, cancel-after-delivered) must be REJECTED, not silently
allowed.

#### Steps
1. Create `harness/state_machine_oracle.py` defining the declarative spec shape: `states` (list),
   `initial` (state name), `transitions` (dict of `"<from_state>:<action>" -> <to_state>`, anything
   unlisted is illegal), a `drive` script (ordered list of `{"action", "args": [...], "kwargs": {...},
   "expect": "accept"|"reject"}` ops), and `expect_final` (state name).
2. Implement `grade_state_machine(root, *, module, entity, spec, python_exe=None, timeout=...) ->
   (accepted: bool, note: str)`: build one `harness.import_driver.drive_import` `api_calls` list that
   (a) constructs the entity once (`target=entity`, bound to a call id), (b) calls each drive-script
   op's action as a method on that bound instance in order, then reads a final `state` property call —
   reusing `drive_import`'s sandboxed-subprocess launch, sentinel protocol, and `_kill_tree` teardown
   as-is (no reimplementation).
3. After `drive_import` returns, evaluate the modeled state machine against the driver's
   sentinel-reported per-call results/raised-exceptions purely in Python (no subprocess call here):
   walk `drive` in order tracking an expected "shadow" state from `transitions`; for each
   `expect:"accept"` op assert the call did NOT raise; for each `expect:"reject"` op assert the call
   DID raise (or returned a documented `ok=False`-shaped failure marker) — an illegal transition that
   the driven entity silently allowed is a caught FAILURE, not a pass; assert the shadow-tracked final
   state equals `expect_final`.
4. Add small helpers `validate_spec(spec) -> (bool, note)` (checks `states`/`initial`/`transitions`/
   `drive`/`expect_final` shape before driving) and wrap the whole grading path in a top-level
   try/except so `grade_state_machine` NEVER raises — any malformed spec, uncallable entity, or
   crashing/garbage fixture is an honest `(False, note)`.
5. Add `tests/test_ext059_state_machine_oracle.py` (offline, hand-written fixtures, no model call):
   (a) a CORRECT order-lifecycle fixture class (states `created/paid/shipped/delivered/cancelled`,
   legal paths `created->paid->shipped->delivered` and `created->cancelled`, illegal `ship`
   before `pay` and illegal `cancel` after `delivered`) passes; (b) a BROKEN fixture that ALLOWS
   ship-before-pay is caught (`accepted=False`) — the flagship honesty test; (c) a fixture that
   reaches the wrong final state fails; (d) the oracle never raises on a crashing/garbage fixture.
   Run only `python -m pytest tests/test_ext059_state_machine_oracle.py -q`.
6. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-7 to the new file
   ranges; `requirements.md` status stays `partial` (REQ-4/REQ-5 remain open).

#### Implements
- [REQ-7] State-machine / lifecycle oracle (`state_machine_oracle`)

### [TASK-6] Build the conservation / no-oversell invariant oracle (`harness/conservation_oracle.py`)

A deterministic, model-free verifier that grades whether a built system preserves a CONSERVED
quantity under a driven operation sequence -- the #4 highest-leverage substrate gap (unblocks
inventory stock reservation, WMS bins, returns/refunds, loyalty points, escrow, wallet-balance
classes). The honesty core: operations that would VIOLATE conservation (oversell, overdraw,
double-spend) must be REJECTED, not silently allowed.

#### Steps
1. Create `harness/conservation_oracle.py` defining the declarative spec shape: `quantities` (list
   of named zero-arg entity reader methods, e.g. `available`/`reserved`), `initial` (dict of
   quantity name -> starting numeric value), a `drive` script (ordered list of `{"action",
   "args": [...], "kwargs": {...}, "expect": "accept"|"reject", "deltas": {...}}` ops, where
   `deltas` is required on `accept` ops and must sum to zero across `quantities` -- the
   conservation law encoded structurally in the spec), and `expect_final` (dict of quantity name
   -> ending numeric value). Mirror `harness/state_machine_oracle.py`'s shadow-tracking approach
   (there over a symbolic state; here over a numeric per-quantity dict) and its module docstring
   style.
2. Implement `grade_conservation(root, *, module, entity, spec, python_exe=None, timeout=...,
   mem_mb=512) -> (accepted: bool, note: str)`: build one `harness.import_driver.drive_import`
   `api_calls` list that (a) constructs the entity once, (b) for each drive-script op calls the
   action then reads every quantity reader back, (c) after the whole script, reads every quantity
   one more time -- reusing `drive_import`'s sandboxed-subprocess launch, sentinel protocol, and
   `_kill_tree` teardown as-is (no reimplementation of `harness/import_driver.py`).
3. Render the `checks` list purely in Python before driving (no subprocess call in this step): walk
   `drive` tracking a shadow quantities-dict from `spec['initial']`; for each `expect:"accept"` op
   assert the action call did NOT raise AND every quantity reader equals the shadow value after
   applying that op's `deltas`; for each `expect:"reject"` op assert the action call DID raise
   (`spec.get('reject_exception', 'ValueError')` by default) AND every quantity reader equals the
   UNCHANGED shadow value from before the op -- an operation that would violate conservation but is
   silently allowed is a caught FAILURE, not a pass; assert the final shadow quantities equal
   `expect_final`.
4. Add `validate_spec(spec) -> (bool, note)` (checks `quantities`/`initial`/`drive`/`expect_final`
   shape, including that every `accept` op's `deltas` sum to zero and every `reject` op declares no
   `deltas`) BEFORE anything is driven, and wrap the whole grading path in a top-level try/except so
   `grade_conservation` NEVER raises -- any malformed spec, uncallable entity, or crashing/garbage
   fixture is an honest `(False, note)`.
5. Add `tests/test_ext059_conservation_oracle.py` (offline, hand-written fixtures, no model call):
   (a) a CORRECT inventory-reservation fixture (initial stock N; `reserve`/`release` ops; REJECTS a
   reservation exceeding available stock; conserves units across `available`+`reserved`) passes;
   (b) a BROKEN fixture that ALLOWS overselling (reserves beyond available stock without raising) is
   caught (`accepted=False`) -- the flagship honesty test; (c) a fixture that silently LOSES or
   CREATES units on a legal op (invariant violated after an `accept` op) fails; (d) a fixture
   reaching the wrong final quantities fails; (e) the oracle never raises on a crashing/garbage
   fixture or spec. Run only `python -m pytest tests/test_ext059_conservation_oracle.py -q`.
6. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-8 to the new file
   ranges; `requirements.md` status stays `partial` (REQ-4/REQ-5 remain open).

#### Implements
- [REQ-8] Conservation / no-oversell invariant oracle (`conservation_oracle`)

### [TASK-7] Build the double-entry-balance invariant oracle (`harness/double_entry_oracle.py`)

A deterministic, model-free verifier that grades whether a built accounting system preserves the
double-entry invariant -- the #4 (last) of the atlas's top-four highest-leverage oracles (unblocks
~16 fintech/accounting classes: ledgers, journals, GL, wallets, escrow, statements). The honesty
core: an UNBALANCED entry (debits != credits) must be REJECTED, and total debits == total credits
always.

#### Steps
1. Create `harness/double_entry_oracle.py` defining the declarative spec shape: `accounts` (list
   of named zero-arg entity reader methods, each returning an exact integer-cents signed balance),
   `initial` (dict of account name -> starting integer-cents balance), `post_method` (the posting
   method name, default `"post"`), a `drive` script (ordered list of `{"legs": [...],
   "expect": "accept"|"reject", "args": [...], "kwargs": {...}}` ops, where each leg is a
   `{"account", "debit"|"credit"}` dict in integer cents; an `accept` op's legs must sum to zero
   once translated to signed per-account deltas -- Sigma(debits)==Sigma(credits) encoded
   structurally in the spec, mirroring `conservation_oracle`'s `deltas`-sum-to-zero law -- and a
   `reject` op's legs must NOT sum to zero), and `expect_final` (dict of account name -> ending
   integer-cents balance). Mirror `harness/conservation_oracle.py`'s shadow-tracking approach and
   module docstring style exactly.
2. Implement `grade_double_entry(root, *, module, entity, spec, python_exe=None, timeout=...,
   mem_mb=512) -> (accepted: bool, note: str)`: build one `harness.import_driver.drive_import`
   `api_calls` list that (a) constructs the entity once, (b) for each drive-script op calls the
   posting method with its `legs` (as one plain JSON-list positional argument) then reads every
   account reader back, (c) after the whole script, reads every account one more time -- reusing
   `drive_import`'s sandboxed-subprocess launch, sentinel protocol, and `_kill_tree` teardown as-is
   (no reimplementation of `harness/import_driver.py`).
3. Render the `checks` list purely in Python before driving (no subprocess call in this step): walk
   `drive` tracking a shadow per-account balance dict from `spec['initial']`; for each
   `expect:"accept"` op assert the posting call did NOT raise AND every account reader equals the
   shadow value after applying that entry's signed leg deltas; for each `expect:"reject"` op assert
   the posting call DID raise (`spec.get('reject_exception', 'ValueError')` by default) AND every
   account reader equals the UNCHANGED shadow value from before the op -- an unbalanced entry that
   is silently posted is a caught FAILURE, not a pass; assert the final shadow balances equal
   `expect_final`.
4. Add `validate_spec(spec) -> (bool, note)` (checks `accounts`/`initial`/`post_method`/`drive`/
   `expect_final` shape, including that every `accept` op's legs balance and every `reject` op's
   legs do NOT balance, and that every money value -- `initial`/leg amounts/`expect_final` -- is a
   plain integer number of cents, never `float`/`bool`) BEFORE anything is driven, and wrap the
   whole grading path in a top-level try/except so `grade_double_entry` NEVER raises -- any
   malformed spec, uncallable entity, or crashing/garbage fixture is an honest `(False, note)`.
5. Add `tests/test_ext059_double_entry_oracle.py` (offline, hand-written fixtures, no model call):
   (a) a CORRECT two-account ledger fixture (balanced entries post correctly; balances land exact
   integer cents) passes; (b) a BROKEN fixture that ACCEPTS an unbalanced entry (no balance guard
   at all) is caught (`accepted=False`) -- the flagship honesty test; (c) a fixture with wrong
   balance math (double-applies a leg's delta) fails; (d) a fixture that violates the ledger-wide
   debits==credits invariant (silently drops credit legs, creating money) fails; (e) the oracle
   never raises on a crashing/garbage fixture or spec. Run only
   `python -m pytest tests/test_ext059_double_entry_oracle.py -q`.
6. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-9 to the new file
   ranges; `requirements.md` status stays `partial` (REQ-4/REQ-5 remain open).

#### Implements
- [REQ-9] Double-entry-balance invariant oracle (`double_entry_oracle`)

### [TASK-8] Build the injectable-clock oracle (`harness/clock_oracle.py`)

A deterministic, model-free verifier that grades TIME-DEPENDENT behavior by injecting a fully
controllable clock into a built entity -- the single highest-demand missing oracle, measured
across three independent atlas research waves (39 mapped classes: SLA/deadline timers, token/
magic-link validity windows, auth lockout/backoff, digest/batch windows, accrual math, monitor/
scheduler cadence, grace-period logic, retention/expiry sweepers). The honesty core: a build must
derive every time decision from the INJECTED clock, never the real wall clock.

#### Steps
1. Create `harness/clock_oracle.py` defining the declarative spec shape: `clock_param` (the
   constructor keyword the oracle injects a `now_fn`-shaped callable under), optional
   `construct_args`/`construct_kwargs` (must not already define `clock_param`), an ordered
   `timeline` (list of `{"at": <epoch-seconds int>, "call": <method>, "args": [...],
   "kwargs": {...}, "expect": {"returns": <value>} | {"raises": "<ExceptionName>"},
   "allow_backward": <bool, optional>}` steps), and optional `expect_final` (dict of zero-arg
   entity reader method name -> expected value, checked once after the whole timeline).
2. Because the clock contract needs the injected clock MUTATED between successive calls in the
   same live subprocess -- a seam `harness.import_driver.drive_import`'s existing driver template
   has no analogue for (its clock support only fakes `time.sleep`; spies return one static
   value) -- render a small stdlib-only driver FOLLOWING `harness/import_driver.py`'s own
   template + sentinel-line-protocol pattern (a mutable `_CLOCK` holder + `_now()` closure passed
   as the injected keyword, set explicitly before every timeline call), while reusing
   `import_driver`'s audited sandboxed launch (`_launch_driver`), teardown
   (`server_oracle._kill_tree`), and post-condition grading (`_parse_sentinels`/`_eval_check`)
   UNMODIFIED. Do NOT edit `harness/import_driver.py` itself.
3. Implement `grade_clock(root, *, module, entity, spec, python_exe=None, timeout=..., mem_mb=512)
   -> (accepted: bool, note: str)`: construct the entity once with the injected clock, then for
   each timeline step set the clock to that step's `at` value and call the named method, checking
   the step's `expect` against the sentinel-reported result/raised-exception; after the whole
   script, call every `expect_final` reader (if declared) once more.
4. Add `validate_spec(spec) -> (bool, note)` (checks `clock_param`/`construct_kwargs`/`timeline`/
   `expect_final` shape, including that the timeline's `at` values are non-decreasing unless a
   step declares `allow_backward`, and that `expect` is exactly one of `returns`/`raises`) BEFORE
   anything is driven, and wrap the whole grading path in a top-level try/except so `grade_clock`
   NEVER raises -- any malformed spec, uncallable entity, construction failure, or crashing/
   garbage fixture is an honest `(False, note)`.
5. Add `tests/test_ext059_clock_oracle.py` (offline, hand-written fixtures, no model call):
   (a) a CORRECT sliding-window rate-limiter fixture passes across an ordinary jump and an
   exact-boundary jump; (b) a BROKEN fixture that secretly uses the real wall clock instead of
   the injected one is CAUGHT (`accepted=False`) -- the flagship honesty test, proven via a
   3600-simulated-second jump executed in real milliseconds; (c) an off-by-one window-boundary
   comparison bug is caught; (d) a token-validity-window fixture is proven valid then expired
   (both directions) by the same timeline, and a fixture missing its expiry check entirely is
   caught; (e) the oracle never raises on a crashing/garbage fixture, a missing entity, or a
   construction failure. Run only `python -m pytest tests/test_ext059_clock_oracle.py -q`.
6. Update `.jarify/EXT-059/index.json` (via `jarify-manage-links`) mapping REQ-10 to the new file
   ranges; `requirements.md` status stays `partial` (REQ-4/REQ-5 remain open).

#### Implements
- [REQ-10] Injectable-clock oracle (`clock_oracle`)
