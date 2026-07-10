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
