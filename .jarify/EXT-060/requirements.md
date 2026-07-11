---
id: EXT-060
title: Real-systems capability suite (leaves-OFF North-Star instrument)
status: covered
priority: high
implementation: []
---

### [REQ-1] Suite scaffold + leaves-OFF pass@1 runner

A `harness/real_systems_suite.py` module with a `RealSystemTask` structure and a runner that builds each
task via `build_system` with the LEAF path disabled and grades ONLY by the task's independent oracle,
reporting pass@1 per class.

#### Acceptance Criteria
- [x] `RealSystemTask` carries name, cls, sentence, oracle_kind, and an oracle spec (declarative).
- [x] The runner builds each task with `build_system` and asserts NO leaf fingerprint fires for the spec
      (leaves-OFF); grades only by the task's own black-box oracle; reports per-class pass@1.
- [x] Honest/leak-free: expected values derive from the visible sentence; no reference implementation or
      suite-internal oracle leaks into the build prompt. A leaf-produced green is treated as a failure.

### [REQ-2] CSV→JSON group-by ETL task graded by fs_oracle

A real ETL system: read an input CSV, group by a named column, sum a numeric column, write the grouped
result to a JSON output file. Graded by `fs_oracle` (seed the input tree, run, inspect the output file
independently).

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (input path, group/sum columns, output path,
      JSON shape) with oracle-chosen values echoed by the contract (no hidden key).
- [x] Graded by `fs_oracle`: seed a CSV, run the built entrypoint, verify the output JSON file's exact
      content independently; a wrong grouping/sum is caught.

### [REQ-3] Retry/backoff decorator library task graded by import_driver

A real reusable library: a single-file `retry.py` module exporting a `retry(times, exceptions=Exception)`
decorator that re-invokes a wrapped callable up to `times` attempts on the given exception(s), sleeping
between attempts, and returns the first success (re-raising if all attempts fail). Graded by
`harness/import_driver.py`: import the built module in a fresh subprocess, apply the decorator to a
fail-then-succeed callable with an INJECTED sleep, and assert the call-count and eventual return value
with NO real wall-clock sleep.

#### Acceptance Criteria
- [x] The task's sentence is contract-exact: names the module filename (`retry.py`), the public decorator
      name + signature/semantics (attempts, which exceptions, return-first-success, re-raise-on-exhaust),
      with oracle-chosen call parameters echoed by the contract (no hidden key).
- [x] Graded by `import_driver` with an injected clock/sleep: a fail-twice-then-succeed callable wrapped
      by `retry(times=3)` returns the success and is called exactly 3 times, using no real sleep; a broken
      retry (wrong count, or gives up early) FAILS. Leaves-OFF (no leaf may count as a pass); no oracle leak.

### [REQ-4] INI-section config-query CLI task graded by the existing cli-exact oracle

A third held-out real-systems task -- an INI-section config-query CLI -- graded by the EXISTING
cli-exact exact-stdout oracle (`grade_real_system_task` `oracle_kind="cli-exact"`, reused from
`harness/system_suite.py`'s `exact_stdout` check variant, no new oracle). Leaves-OFF enforced
identically to the other two tasks; added to `REAL_SYSTEMS_TASKS`.

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (INI section/key parsing rules, exactly
      two argv args: section then key, exact stdout value + trailing newline, nonzero exit + no
      output when absent) with oracle-chosen argv/stdin/expected_stdout values echoed by the
      contract (no hidden key).
- [x] Graded by the existing cli-exact oracle (`grade_real_system_task` `oracle_kind="cli-exact"`):
      a correct INI-parsing CLI's exact stdout is verified; a wrong value/extra output is caught.
- [x] Leaves-OFF enforced (same two checks as REQ-1/REQ-2/REQ-3: static `leaf_for_spec` + post-build
      `build_path` check); no oracle leak into the build prompt.

### [REQ-5] Memoize/cache decorator library task graded by the existing import_driver oracle

A 4th held-out real-systems task -- a memoize/cache decorator library -- graded by the EXISTING
`import_driver` oracle (no new oracle code, mirrors REQ-3's `"import"` dispatch). A single-file
`memoize.py` module exports exactly one public function `memoize(maxsize=128)` that returns a
decorator; the decorated callable caches its return value keyed by its positional-argument tuple --
a repeated call with the SAME arguments returns the cached value WITHOUT re-invoking the wrapped
callable, while a call with NEW arguments does invoke it. Because `maxsize` is entirely defaulted,
`@memoize()` with zero arguments must work -- this ALSO exercises the EXT-036 REQ-45 deterministic
signature-contract-default repair on a SECOND reusable-library class (a generalization data point
beyond REQ-3's `retry.py`).

#### Acceptance Criteria
- [x] The task's sentence is contract-exact (filename `memoize.py`, the public function name +
      signature `memoize(maxsize=128)`, decorator/caching semantics, keying by the positional-
      argument tuple) with oracle-chosen call values echoed by the contract (no hidden key).
- [x] Graded by the existing `import_driver` oracle (`grade_real_system_task` `oracle_kind="import"`):
      a decorated spy invoked with the same argument twice then a different argument once must
      record exactly 2 underlying calls (the repeated call served from cache, never re-invoking the
      spy); a stub that never caches (always calls through) is caught.
- [x] Leaves-OFF enforced identically to REQ-2/REQ-3/REQ-4 (static `leaf_for_spec` + post-build
      `build_path` check); no oracle leak; added to `REAL_SYSTEMS_TASKS`.

### [REQ-6] File-organizer-by-extension CLI task graded by the existing fs oracle

A 5th held-out real-systems task, in a NEW domain -- a file-organizer CLI -- graded by the EXISTING
`fs_oracle` (no new oracle code, mirrors REQ-2's `"fs"` dispatch). A single-file `main.py` program
takes one command-line argument (a directory path) and moves every regular file directly inside
that directory (never recursing into subdirectories) into a subdirectory of that same directory
named after the file's lowercased extension with no leading dot (e.g. `report.TXT` -> `txt/
report.TXT`, preserving the file's own name and case); a file with no extension is moved into a
subdirectory named `noext`. It prints nothing on success and exits 0.

#### Acceptance Criteria
- [x] The task's sentence fully specifies the CLI contract (single directory argv, non-recursive
      immediate-children-only scope, lowercased-extension-without-dot subdirectory naming, the
      `noext` fallback for extensionless files, filename preserved unchanged, silent/exit-0 on
      success) with every oracle-checked path derivable from that same visible contract (no hidden
      key) and no leaf-library name-drop.
- [x] Graded by the existing `fs_oracle` (`grade_real_system_task` `oracle_kind="fs"`): a seeded
      directory with mixed-extension files (including an uppercase-extension file and a file with
      no extension) is correctly reorganized into per-lowercased-extension subdirectories plus
      `noext`, independently re-verified against the resulting tree; a build that fails to
      lowercase the extension, recurses into subdirectories, or leaves the originals in place is
      caught.
- [x] Leaves-OFF enforced identically to REQ-2/REQ-3/REQ-4/REQ-5 (static `leaf_for_spec` +
      post-build `build_path` check); no oracle leak; added to `REAL_SYSTEMS_TASKS`.

### [REQ-7] MODIFY half: RealSystemModifyTask + run_real_systems_modify_suite, leaves-OFF, independent-oracle-graded

EXT-060 becomes THE canonical real-systems scoreboard by adding its second half: MODIFYING an
already-working real system from a one-sentence change request, graded exactly as strictly as the
CREATE half. A `RealSystemModifyTask` dataclass (name, cls, `start_system` dict of the known-good
baseline modules, `mod_sentence`, `oracle_kind`, `oracle_spec` reusing the SAME declarative oracle
shape as `RealSystemTask`) plus a `run_real_systems_modify_suite(tasks, llm)` runner that: (1) asserts
leaves-OFF statically via `leaf_for_spec(task.mod_sentence) is None` before ever calling the model; (2)
writes `start_system` to an isolated temp root and calls `harness.system_builder.modify_system(modules,
mod_sentence, root, llm=llm)`; (3) grades the modified tree ONLY when `applied` is True, via the SAME
independent oracle dispatcher used by the CREATE half (`grade_real_system_task` — no new oracle code,
fs/cli-exact/import reused verbatim); (4) reports per-class pass@1 in the same `{"results": [...],
"aggregate": {...}}` shape as `run_real_systems_suite`. Two concrete MODIFY tasks seed
`REAL_SYSTEMS_MODIFY_TASKS`: (a) the retry/backoff library gains an optional `base_delay=0.1` keyword
parameter, graded by the import_driver oracle; (b) the INI config-query CLI gains an optional
`--default VALUE` fallback for an absent section/key, graded by the cli-exact oracle. Every
oracle-checked value in both tasks' `oracle_spec` derives from the visible `mod_sentence` (no leak).

#### Acceptance Criteria
- [x] `RealSystemModifyTask` carries name, cls, start_system, mod_sentence, oracle_kind, oracle_spec
      (declarative, same shape as REQ-1's `RealSystemTask` oracle_spec).
- [x] `run_real_systems_modify_suite` asserts leaves-OFF (`leaf_for_spec(task.mod_sentence) is None`)
      before calling `modify_system`; grades ONLY when `applied` is True; grades via the EXISTING
      `grade_real_system_task` dispatcher (no new oracle code); NEVER raises — any stage failure is an
      honest `accepted=False`.
- [x] Two concrete MODIFY tasks are added to `REAL_SYSTEMS_MODIFY_TASKS`: the retry/backoff
      `base_delay` addition (import_driver-graded) and the INI `--default VALUE` fallback addition
      (cli-exact-graded); every oracle-chosen value is derivable from the visible mod_sentence contract
      (no hidden key, no leak).
- [x] Offline-testable: a hand-authored CORRECT post-modification module passes the independent oracle;
      a hand-authored WRONG one (doesn't implement the change) is caught.

### [REQ-8] Unified canonical scoreboard runner

A single entrypoint that runs BOTH halves (CREATE via `run_real_systems_suite`, MODIFY via
`run_real_systems_modify_suite`) and reports ONE headline number: per-half pass@1 plus the combined
total pass@1 = `(create passes + modify passes) / (total create + modify tasks)`. Implemented as
`harness.real_systems_suite.run_canonical_scoreboard(*, llm, create_tasks=None, modify_tasks=None,
python_exe=None) -> dict` returning `{"create": {...}, "modify": {...}, "combined": {"n": int, "passed":
int, "pass_rate": float}}`, plus a killable subprocess-per-build runner script (mirroring the existing
`.jaros-data/realsys_build_one.py` + `.jaros-data/realsys_killable.py` pattern so a pathological
build/modify draw can't wedge the whole scoreboard run) that prints the single headline "CANONICAL
real-systems: create X/A, modify Y/B, total (X+Y)/(A+B)".

#### Acceptance Criteria
- [x] `run_canonical_scoreboard` runs both halves and returns a dict with `create`, `modify`, and
      `combined` (n/passed/pass_rate) keys; NEVER raises (per-task failures are already absorbed by
      each half's own runner).
- [x] The combined pass_rate is exactly (create passed + modify passed) / (create n + modify n),
      guarding division-by-zero when both halves are empty.
- [x] A killable subprocess-per-build runner script exists reusing the existing per-build
      subprocess-with-timeout-and-kill pattern (`.jaros-data/realsys_build_one.py` /
      `.jaros-data/realsys_killable.py`), extended (or a sibling script) to cover both CREATE and
      MODIFY tasks and print the single canonical headline.
- [x] Offline-testable: `run_canonical_scoreboard` is importable and its aggregation is correct given a
      stub llm returning a fixed correct module/modification (no real Jetson call in the test).

### [REQ-9] `oracle_kind="service"` + first REST/SQLite CRUD service CREATE task (the first SaaS rung)

The canonical scoreboard's first genuinely-SaaS-shaped task: a stdlib REST API (`http.server` +
`sqlite3` + `json`, no framework) exposing CRUD operations over an `items` resource, persisted to a
SQLite file. Graded by a NEW `oracle_kind="service"` dispatch in `grade_real_system_task` that (a) runs
the built entrypoint as a real long-lived server on an ephemeral localhost port and drives real HTTP
requests against it via the ALREADY-LANDED `harness/server_oracle.py::serve_and_check_stdlib` (no new
process-launch/teardown mechanism — reused verbatim), and (b), after the server is torn down,
INDEPENDENTLY re-opens the resulting SQLite file (reusing `harness/datastore_oracle.py`'s detection/
row-counting helpers, or a tiny inline stdlib `sqlite3` read) and asserts real persisted state — never
trusting the service's own HTTP responses for durability. `serve_and_check_stdlib`'s `http_check` dict
contract is minimally, backward-compatibly extended with an optional `json_body` key (existing checks
that omit it behave byte-identically to before) so a check can drive `POST`/`PUT` requests carrying a
real JSON request body — the previously-landed contract (`method`, `path`, `status`, `json_contains`,
`body_contains`) had no way to send a request body at all, which a REST CRUD API's `POST`/`PUT`
endpoints require to be tested honestly.

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="service"` to a new `_grade_service` grader.
      `oracle_spec` shape: `{"entry": str, "http_checks": [...], "db": {"path": str|None, "min_rows":
      int, "table": str|None} | None, "startup_timeout": float, "request_timeout": float}`.
- [x] Grading requires `serve_and_check_stdlib(...)` to report `ok=True` with every check passed; when
      `db` is present, requires an INDEPENDENT post-teardown SQLite read to satisfy the row-count
      assertion. NEVER raises — any failure at any stage is an honest `(False, note)`.
- [x] `harness/server_oracle.py`'s `http_check` dict gains an optional `json_body` key (`_do_request`
      sends it as a JSON-encoded request body with a `Content-Type: application/json` header when
      present); omitting the key is byte-identical to the prior behavior (regression-proof).
- [x] `REST_SQLITE_CRUD_TASK` (`RealSystemTask`, `oracle_kind="service"`) is added to
      `REAL_SYSTEMS_TASKS`: a contract-exact sentence (filename `main.py`, stdlib-only, `PORT` env var,
      `data.db` SQLite file, `items` resource with integer autoincrement `id` + string `name`,
      `POST`/`GET`/`GET <id>`/`DELETE <id>` semantics + status codes, persistence across restarts) with
      every oracle-checked value (paths, JSON bodies, statuses) derivable from that same visible
      sentence (no hidden key, no leak). Leaves-OFF enforced identically to every other task in this
      module (static `leaf_for_spec` + post-build `build_path` check).
- [x] Offline-testable: a hand-authored CORRECT stdlib CRUD service fixture is accepted (including the
      independent db assertion); a WRONG fixture (doesn't persist to SQLite, wrong status code, or
      missing an endpoint) is rejected; the oracle never raises on a crashing/never-binding fixture.

### [REQ-10] First REST/SQLite CRUD MODIFY task (add a `PUT` endpoint)

The canonical scoreboard's first SaaS-shaped MODIFY task: starting from a known-good baseline items
CRUD service (missing `PUT`), a one-sentence change request asks for an added `PUT /items/<id>`
endpoint that updates an item's name. Graded by the SAME `oracle_kind="service"` dispatcher REQ-9
lands — no new oracle code for the MODIFY half, mirroring how REQ-7's MODIFY tasks reused REQ-3/REQ-4's
existing oracle dispatch.

#### Acceptance Criteria
- [x] `REST_SQLITE_ADD_UPDATE_MODIFY` (`RealSystemModifyTask`, `oracle_kind="service"`) is added to
      `REAL_SYSTEMS_MODIFY_TASKS`. `start_system` is a hand-authored CORRECT baseline stdlib CRUD
      `main.py` (matching REQ-9's original contract, no `PUT`); `mod_sentence` asks for the added `PUT
      /items/<id>` endpoint (JSON body `{"name": ...}`, 200 + updated item JSON on success, 404 when
      absent) — every oracle-checked value is derivable from the visible `mod_sentence`.
- [x] `oracle_spec`'s `http_checks` cover the new `PUT` behavior AND regress the existing
      `POST`/`GET`/`DELETE`/404 behavior against the SAME running service (a modification that broke an
      existing endpoint fails the task); the `db` assertion still independently verifies persisted rows
      after the full check sequence.
- [x] Offline-testable: a hand-authored CORRECT post-modification module (baseline + `PUT`) is accepted;
      the unmodified baseline (no `PUT`) is rejected by the new checks.

### [REQ-11] `oracle_kind="agent"` + first plain-Python AGENT-SYSTEM CREATE task

The canonical scoreboard's first AGENT-shaped task -- a high-priority class since jaros-code is
itself a Jaros agent system. A `_grade_agent` grader wires the already-landed EXT-059 REQ-6
agent-loop oracle (`harness/agent_oracle.py`'s `drive_agent`/`check_agent`) into
`grade_real_system_task` under a new `oracle_kind="agent"` dispatch -- no new process-launch,
stub-model, or tool-sandbox mechanism, reusing that oracle verbatim (the same
"never trusts the built agent's own claims, only its observed control flow" discipline every other
`_grade_*` helper already follows). `PLAIN_AGENT_TASK` (`RealSystemTask`, `cls="agent"`,
`oracle_kind="agent"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
stdlib-only, single-file plain-Python agent `main.py` that implements a tool-calling loop against
the EXACT protocol `harness/agent_oracle.py` pins (reads `OPENAI_BASE_URL`, POSTs OpenAI-shape chat
completions to `f"{OPENAI_BASE_URL}/chat/completions"`, takes the goal from `sys.argv[1]`, on a
`tool_calls` response POSTs the tool's name+args as JSON to `f"{JAROS_TOOL_URL}/<tool_name>"` and
feeds the returned `"observation"` back into the next request's messages, on a final-content
response prints exactly `__JAROS_AGENT_FINAL__<content>__END__` and exits 0).

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="agent"` to a new `_grade_agent(oracle_spec,
      root, python_exe)` that maps `oracle_spec` (`{"entry": str, "script": [...], "tools": {...},
      "goal": str, "expect_tool_calls": [...], "expect_final_contains": str, "expect_terminated":
      bool (default True)}`) to `harness.agent_oracle.drive_agent(...)` then
      `harness.agent_oracle.check_agent(...)`, returning `(accepted, note)`. NEVER raises (reuses
      `agent_oracle`'s own never-raise contract) -- a missing entrypoint, malformed spec, or a
      crashing/never-terminating agent is an honest `(False, <reason>)`.
- [x] `PLAIN_AGENT_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the agent
      contract (env vars, chat-completions endpoint/shape, tool-call POST route/shape, the
      observation-feedback loop, the exact final-sentinel line + exit 0) with every oracle-checked
      value (the scripted tool-call sequence, canned tool observations, the goal string, the
      expected final substring) derivable from that same visible sentence (no hidden key, no leak
      of the oracle's internal script into the build prompt beyond what the sentence states).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written agent fixtures only): a CORRECT
      plain-Python agent fixture is accepted by `grade_real_system_task(PLAIN_AGENT_TASK, ...)`; a
      BROKEN fixture (ignores the tool observation, never terminates, or calls the wrong tool) is
      rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-12] First AGENT-SYSTEM MODIFY task: add a maximum-steps guard

The canonical scoreboard's first AGENT-shaped MODIFY task, mirroring how REQ-7/REQ-10 reuse their
CREATE half's oracle dispatch with zero new oracle code. `AGENT_ADD_STEP_GUARD_MODIFY`
(`RealSystemModifyTask`, `cls="agent-modify"`, `oracle_kind="agent"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline plain-Python agent
matching REQ-11's original contract exactly (no step guard -- it loops forever against a script
that never scripts a final turn); `mod_sentence` asks for an added maximum-steps guard pinned to a
concrete step count N (e.g. "if the agent has made N tool calls without receiving a final answer,
stop, print the final marker with a message indicating it gave up, then exit 0").

#### Acceptance Criteria
- [x] `AGENT_ADD_STEP_GUARD_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="agent"` dispatcher REQ-11 lands (no new oracle code, reusing
      `grade_real_system_task` exactly as REQ-7/REQ-10's MODIFY tasks reuse their CREATE half's
      dispatch).
- [x] `mod_sentence` pins a concrete step-count N and the exact gave-up-final-marker behavior; every
      oracle-checked value in `oracle_spec` (the all-tool-call script with no final turn, the
      expected non-termination of an UNGUARDED baseline vs. the clean termination + gave-up
      substring of a GUARDED agent) is derivable from that same visible `mod_sentence` (no hidden
      key, no leak).
- [x] Offline-testable (no real model/Jetson, hand-written agent fixtures only): a hand-authored
      GUARDED post-modification agent fixture is accepted (terminates cleanly, prints the gave-up
      final message) against an oracle script that would otherwise loop forever; the UNMODIFIED
      baseline (no guard) is rejected (never terminates within the oracle's bounded `max_steps`/
      `timeout`, exactly as `agent_oracle.drive_agent` reports honestly for a runaway loop -- never
      a hang in the test itself).
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-13] `oracle_kind="state_machine"` + first LIFECYCLE CREATE task (order state machine)

The canonical scoreboard's first LIFECYCLE-shaped task, grading whether a build enforces a legal state
machine (illegal transitions rejected, not silently allowed) — a class of real system (order/
shipment/fulfillment/RMA/subscription, etc.) EXT-059 REQ-7 built a dedicated deterministic oracle for
but that had no representative task on this scoreboard yet. A `_grade_state_machine` grader wires the
already-landed EXT-059 REQ-7 oracle (`harness/state_machine_oracle.py`'s `grade_state_machine`) into
`grade_real_system_task` under a new `oracle_kind="state_machine"` dispatch — no new process-launch or
driving mechanism, reusing that oracle verbatim (the same "never trusts the built module's own claims,
only its observed accept/reject behavior" discipline every other `_grade_*` helper already follows).
`ORDER_LIFECYCLE_TASK` (`RealSystemTask`, `cls="lifecycle"`, `oracle_kind="state_machine"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `Order` class in
`order.py` with states `created`/`paid`/`shipped`/`delivered`/`cancelled`, action methods
`pay()`/`ship()`/`deliver()`/`cancel()` that mutate state along the legal path
(`created→paid→shipped→delivered`, and `created→cancelled`), a real `state` property, and an illegal
transition (e.g. shipping before payment, or cancelling after delivery) raising `ValueError` with state
left unchanged.

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="state_machine"` to a new `_grade_state_machine
      (oracle_spec, root, python_exe)` that maps `oracle_spec` (`{"module": str, "entity": str, "spec":
      {...state-machine spec shape...}}`) to `harness.state_machine_oracle.grade_state_machine(root,
      module=..., entity=..., spec=..., python_exe=python_exe)`, returning `(accepted, note)`. NEVER
      raises (reuses `state_machine_oracle`'s own never-raise contract) — a malformed spec, a missing
      entrypoint, or a build that allows an illegal transition is an honest `(False, <reason>)`.
- [x] `ORDER_LIFECYCLE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the lifecycle
      contract (filename `order.py`, the five states, the four action methods and their legal
      transitions, the `ValueError`-on-illegal-transition + unchanged-state contract, the `state`
      property) with every oracle-checked value (the states/transitions table, the driven
      accept/reject script, `expect_final`) derivable from that same visible sentence (no hidden key,
      no leak).
- [x] The driven script exercises BOTH an illegal transition (rejected before any legal op, e.g.
      shipping an unpaid order) and the full legal path to `delivered`, plus a second illegal transition
      after reaching the terminal legal state (e.g. cancelling a delivered order) — a build that only
      ever exercises the legal path, or that allows even one illegal transition, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Order` fixture is
      accepted by `grade_real_system_task(ORDER_LIFECYCLE_TASK, ...)`; a BROKEN fixture (allows an
      illegal transition, e.g. `ship()` with no guard) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-14] First LIFECYCLE MODIFY task: add a `refund()` transition

The canonical scoreboard's first LIFECYCLE-shaped MODIFY task, mirroring how REQ-7/REQ-10/REQ-12 reuse
their CREATE half's oracle dispatch with zero new oracle code. `ORDER_ADD_REFUND_MODIFY`
(`RealSystemModifyTask`, `cls="lifecycle-modify"`, `oracle_kind="state_machine"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline `Order` matching
REQ-13's original contract exactly (no `refund()`); `mod_sentence` asks for an added `refund()`
transition legal ONLY from the `delivered` state (moving it to a new `refunded` state) and illegal
(raising `ValueError`, state unchanged) from every other state.

#### Acceptance Criteria
- [x] `ORDER_ADD_REFUND_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="state_machine"` dispatcher REQ-13 lands (no new oracle code, reusing
      `grade_real_system_task` exactly as REQ-7/REQ-10/REQ-12's MODIFY tasks reuse their CREATE half's
      dispatch).
- [x] `mod_sentence` pins the new `refund()` transition's exact legal source state (`delivered`) and
      target state (`refunded`), and its illegal-elsewhere behavior; every oracle-checked value in
      `oracle_spec` (the extended states/transitions table, a driven script exercising `refund()` both
      legally from `delivered` and illegally from an earlier state, plus a regression walk of the
      original legal/illegal transitions from REQ-13) is derivable from that same visible `mod_sentence`
      (no hidden key, no leak).
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a hand-authored CORRECT
      post-modification `Order` fixture (baseline + guarded `refund()`) is accepted; the UNMODIFIED
      baseline (no `refund()` method at all) is rejected by the new checks; a fixture that adds an
      UNGUARDED `refund()` (legal from any state) is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-15] `oracle_kind="conservation"` + first INVENTORY CREATE task (no-oversell reservation)

The canonical scoreboard's first CONSERVATION-shaped task, grading whether a build preserves a
conserved quantity under a driven operation sequence (no unit created, destroyed, or oversold) — a
class of real system (inventory stock reservation, wallet/escrow balances, loyalty points, WMS bin
transfers, etc.) EXT-059 REQ-8 built a dedicated deterministic oracle for but that had no
representative task on this scoreboard yet. A `_grade_conservation` grader wires the already-landed
EXT-059 REQ-8 oracle (`harness/conservation_oracle.py`'s `grade_conservation`) into
`grade_real_system_task` under a new `oracle_kind="conservation"` dispatch — no new process-launch or
driving mechanism, reusing that oracle verbatim. `INVENTORY_TASK` (`RealSystemTask`, `cls="inventory"`,
`oracle_kind="conservation"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
stdlib-only, single-file `Inventory` class in `inventory.py` constructed with an initial per-SKU stock
count, `reserve(qty)`/`release(qty)` methods that move units between an `available` and a `reserved`
quantity, zero-argument `available()`/`reserved()` readers, and `reserve(qty)` raising `ValueError`
(no mutation) when `qty` exceeds what is currently available — units are always conserved
(`available + reserved` never changes across any legal operation).

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="conservation"` to a new `_grade_conservation
      (oracle_spec, root, python_exe)` that maps `oracle_spec` (`{"module": str, "entity": str, "spec":
      {...conservation spec shape...}}`) to `harness.conservation_oracle.grade_conservation(root,
      module=..., entity=..., spec=..., python_exe=python_exe)`, returning `(accepted, note)`. NEVER
      raises (reuses `conservation_oracle`'s own never-raise contract) — a malformed spec, a missing
      entrypoint, or a build that oversells is an honest `(False, <reason>)`.
- [x] `INVENTORY_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the inventory contract
      (filename `inventory.py`, the constructor's initial-stock argument, `reserve(qty)`/`release(qty)`
      semantics, the `ValueError`-on-oversell-attempt + unchanged-quantities contract, the
      `available()`/`reserved()` readers) with every oracle-checked value (the initial stock, the driven
      accept/reject script and its per-op deltas, `expect_final`) derivable from that same visible
      sentence (no hidden key, no leak).
- [x] The driven script exercises BOTH an illegal oversell reservation (rejected, quantities unchanged)
      and legal reserve/release operations with their declared per-quantity deltas — a build that only
      ever exercises the legal path, or that allows the oversell, or that silently loses/creates units
      on a legal op, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Inventory` fixture
      is accepted by `grade_real_system_task(INVENTORY_TASK, ...)`; a BROKEN fixture (allows an
      oversell, e.g. `reserve()` with no guard) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-16] First INVENTORY MODIFY task: add a non-oversell-safe `backorder()`

The canonical scoreboard's first CONSERVATION-shaped MODIFY task, mirroring how REQ-7/REQ-10/REQ-12/
REQ-14 reuse their CREATE half's oracle dispatch with zero new oracle code. `INVENTORY_ADD_BACKORDER_
MODIFY` (`RealSystemModifyTask`, `cls="inventory-modify"`, `oracle_kind="conservation"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline `Inventory` matching
REQ-15's original contract exactly (no `backorder()`); `mod_sentence` asks for an added `backorder(qty)`
method that records demand beyond what is currently available WITHOUT ever reducing `available` below
zero and WITHOUT disturbing the existing `available`/`reserved` conservation — i.e. `backorder()` never
oversells committed stock, it only tracks a separate backorder-demand quantity that itself is conserved
against nothing but its own growth.

#### Acceptance Criteria
- [x] `INVENTORY_ADD_BACKORDER_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="conservation"` dispatcher REQ-15 lands (no new oracle code, reusing
      `grade_real_system_task` exactly as REQ-7/REQ-10/REQ-12/REQ-14's MODIFY tasks reuse their CREATE
      half's dispatch).
- [x] `mod_sentence` pins the new `backorder(qty)` method's exact contract (records demand beyond
      available, never mutates `available`/`reserved` themselves, exposes the recorded backorder demand
      via a new zero-argument reader); `oracle_spec.spec["quantities"]` is extended with that new
      backorder-demand quantity (with a zero-sum-safe delta convention — a `backorder()` op's own
      `deltas` entry for the new quantity nets against a matching entry so the conservation law still
      holds structurally) so the oracle's own per-op reader-vs-shadow check independently proves the
      addition leaves `available`/`reserved` conservation undisturbed while still recording backorder
      growth; every oracle-checked value is derivable from the visible `mod_sentence`.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a hand-authored CORRECT
      post-modification `Inventory` fixture (baseline + `backorder()`) is accepted; the UNMODIFIED
      baseline (no `backorder()` method at all) is rejected by the new checks; a fixture whose
      `backorder()` incorrectly mutates `available`/`reserved` is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-17] `oracle_kind="double_entry"` + first FINTECH-LEDGER CREATE task (double-entry balance)

The canonical scoreboard's first FINTECH-shaped task, grading whether a build enforces the
double-entry invariant under a driven posting sequence (an unbalanced journal entry — debits not
equal to credits — must be rejected, not silently posted) — a class of real system (ledgers,
journals, general-ledger accounts, wallets, escrow accounts, statements) EXT-059 REQ-9 built a
dedicated deterministic oracle for but that had no representative task on this scoreboard yet. A
`_grade_double_entry` grader wires the already-landed EXT-059 REQ-9 oracle
(`harness/double_entry_oracle.py`'s `grade_double_entry`) into `grade_real_system_task` under a
new `oracle_kind="double_entry"` dispatch — no new process-launch or driving mechanism, reusing
that oracle verbatim. `DOUBLE_ENTRY_LEDGER_TASK` (`RealSystemTask`, `cls="ledger"`,
`oracle_kind="double_entry"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
stdlib-only, single-file `Ledger` class in `ledger.py` over three named accounts (`cash`,
`revenue`, `expense`), a `post(legs)` method that applies a balanced list of debit/credit legs to
each account's exact-integer-cents balance, and raises `ValueError` (no mutation) when the legs
are unbalanced (sum of debits != sum of credits) — the debits-equal-credits invariant always
holds across every accepted entry.

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="double_entry"` to a new
      `_grade_double_entry(oracle_spec, root, python_exe)` that maps `oracle_spec` (`{"module":
      str, "entity": str, "spec": {...double-entry spec shape...}}`) to
      `harness.double_entry_oracle.grade_double_entry(root, module=..., entity=..., spec=...,
      python_exe=python_exe)`, returning `(accepted, note)`. NEVER raises (reuses
      `double_entry_oracle`'s own never-raise contract) — a malformed spec, a missing entrypoint,
      or a build that posts an unbalanced entry is an honest `(False, <reason>)`.
- [x] `DOUBLE_ENTRY_LEDGER_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      ledger contract (filename `ledger.py`, the three named accounts, the `post(legs)`
      debit/credit-leg contract, the `ValueError`-on-unbalanced-entry + unchanged-balances
      contract, the three zero-argument balance readers) with every oracle-checked value (the
      accounts, the driven balanced/unbalanced posting script and its expected balances,
      `expect_final`) derivable from that same visible sentence (no hidden key, no leak).
- [x] The driven script exercises BOTH an illegal unbalanced posting (rejected, every account
      balance unchanged) and multiple legal balanced postings across all three accounts — a build
      that only ever exercises the legal path, or that allows the unbalanced posting, or that
      posts a balanced entry to the wrong side of an account, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Ledger`
      fixture is accepted by `grade_real_system_task(DOUBLE_ENTRY_LEDGER_TASK, ...)`; a BROKEN
      fixture (posts an unbalanced entry with no guard) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-18] Second LIFECYCLE CREATE task, in a NEW SaaS-billing vertical (subscription state machine)

A SECOND held-out LIFECYCLE-shaped task, graded by the ALREADY-LANDED `oracle_kind="state_machine"`
dispatch REQ-13 lands (no new oracle code — reuses `_grade_state_machine` ->
`harness.state_machine_oracle.grade_state_machine` verbatim). `SUBSCRIPTION_LIFECYCLE_TASK`
(`RealSystemTask`, `cls="subscription"`, `oracle_kind="state_machine"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `Subscription` class
in `subscription.py` modeling a SaaS billing subscription with states `trialing`/`active`/
`past_due`/`canceled`/`expired`, action methods `activate()`/`payment_failed()`/`recover()`/
`cancel()`/`lapse()` that mutate state along the legal billing path (`trialing→active`,
`active→past_due`, `past_due→active`, `active`-or-`past_due`→`canceled`, `trialing→expired`), a
real `state` property, and at least one illegal transition (e.g. cancelling a still-trialing
subscription, or lapsing an already-canceled one) raising `ValueError` with state left unchanged.

#### Acceptance Criteria
- [x] `SUBSCRIPTION_LIFECYCLE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      subscription contract (filename `subscription.py`, the five states, the five action methods
      and their legal source state(s), the `ValueError`-on-illegal-transition + unchanged-state
      contract, the `state` property) with every oracle-checked value (the states/transitions
      table, the driven accept/reject script, `expect_final`) derivable from that same visible
      sentence (no hidden key, no leak).
- [x] The driven script exercises AT LEAST ONE illegal transition (rejected) alongside the full
      legal billing path — a build that only ever exercises the legal path, or that allows even
      one illegal transition, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. (The sentence deliberately names the lapse
      action `lapse()` rather than `expire()`/`expiry` — those tokens fingerprint the verified
      `ttl-store` leaf in `harness.adt_oracle`'s keyword table and would falsely trip leaves-OFF
      for an unrelated lifecycle class.)
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Subscription`
      fixture is accepted by `grade_real_system_task(SUBSCRIPTION_LIFECYCLE_TASK, ...)`; a BROKEN
      fixture (allows an illegal transition, e.g. unguarded `cancel()`) is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`.

### [REQ-19] Second CONSERVATION CREATE task, in a fintech vertical (wallet, no-overdraw balance)

A SECOND held-out CONSERVATION-shaped task, graded by the ALREADY-LANDED `oracle_kind=
"conservation"` dispatch REQ-15 lands (no new oracle code — reuses `_grade_conservation` ->
`harness.conservation_oracle.grade_conservation` verbatim). `WALLET_NO_OVERDRAW_TASK`
(`RealSystemTask`, `cls="wallet"`, `oracle_kind="conservation"`) is added to `REAL_SYSTEMS_TASKS`:
a contract-exact sentence for a stdlib-only, single-file `Wallet` class in `wallet.py` constructed
with an initial integer-cents balance, `credit(cents)`/`debit(cents)` methods that move cents
between `balance_cents` and an internal `ledger_cents` bookkeeping counter (a structural mirror pair
so the conservation law holds), and `debit(cents)` raising `ValueError` (no mutation) when `cents`
exceeds the current `balance_cents` — `balance_cents` can never go negative (an overdraw).

#### Acceptance Criteria
- [x] `WALLET_NO_OVERDRAW_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      wallet contract (filename `wallet.py`, the constructor's initial-balance argument,
      `credit(cents)`/`debit(cents)` semantics, the `ValueError`-on-overdraw-attempt +
      unchanged-quantities contract, the `balance_cents()`/`ledger_cents()` readers) with every
      oracle-checked value (the initial balance, the driven accept/reject script and its per-op
      deltas, `expect_final`) derivable from that same visible sentence (no hidden key, no leak).
- [x] The driven script exercises AT LEAST ONE illegal overdraw attempt (rejected, quantities
      unchanged) both before and after legal credit/debit operations, plus legal credit/debit
      operations with their declared per-quantity deltas — a build that only ever exercises the
      legal path, or that allows the overdraw, or that silently loses/creates cents on a legal op,
      is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Wallet`
      fixture is accepted by `grade_real_system_task(WALLET_NO_OVERDRAW_TASK, ...)`; a BROKEN
      fixture (allows an overdraw, e.g. `debit()` with no guard) is rejected; the task is a member
      of `REAL_SYSTEMS_TASKS`.

### [REQ-20] Third LIFECYCLE CREATE task, in a support/helpdesk vertical (ticket workflow state machine)

A THIRD held-out LIFECYCLE-shaped task, graded by the ALREADY-LANDED `oracle_kind="state_machine"`
dispatch REQ-13 lands (no new oracle code — reuses `_grade_state_machine` ->
`harness.state_machine_oracle.grade_state_machine` verbatim). `TICKET_WORKFLOW_TASK`
(`RealSystemTask`, `cls="ticket"`, `oracle_kind="state_machine"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `Ticket` class in
`ticket.py` modeling a support/helpdesk ticket with states `open`/`assigned`/`pending_customer`/
`resolved`/`closed`, action methods `assign()`/`await_customer()`/`respond()`/`resolve()`/
`close()`/`reopen()` that mutate state along the legal support path (`open→assigned`,
`assigned→pending_customer`, `pending_customer→assigned`, `assigned→resolved`,
`resolved→closed`, `closed→open`), a real `state` property, and TWO distinct illegal transitions
(resolving a ticket that was never assigned, and reopening a ticket that was never closed) raising
`ValueError` with state left unchanged.

#### Acceptance Criteria
- [x] `TICKET_WORKFLOW_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the ticket
      contract (filename `ticket.py`, the five states, the six action methods and their legal
      source states, the `ValueError`-on-illegal-transition + unchanged-state contract, the
      `state` property) with every oracle-checked value (the states/transitions table, the driven
      accept/reject script, `expect_final`) derivable from that same visible sentence (no hidden
      key, no leak).
- [x] The driven script exercises TWO distinct illegal transitions (rejected) alongside the full
      legal support path — a build that guards only one of the two, or that allows either illegal
      transition, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Ticket`
      fixture is accepted by `grade_real_system_task(TICKET_WORKFLOW_TASK, ...)`; a BROKEN
      fixture (allows an illegal transition, e.g. unguarded `resolve()`/`reopen()`) is rejected;
      the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-21] Third CONSERVATION CREATE task, in an events/venue-booking vertical (seat booking, no double-book)

A THIRD held-out CONSERVATION-shaped task, graded by the ALREADY-LANDED `oracle_kind=
"conservation"` dispatch REQ-15 lands (no new oracle code — reuses `_grade_conservation` ->
`harness.conservation_oracle.grade_conservation` verbatim). `SEAT_BOOKING_TASK`
(`RealSystemTask`, `cls="booking"`, `oracle_kind="conservation"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `SeatBooking` class
in `booking.py` constructed with a fixed total-seats capacity, `reserve(n)`/`release(n)` methods
that move seats between `available_seats` and `reserved_seats` (a structural mirror pair so the
conservation law holds), and `reserve(n)` raising `ValueError` (no mutation) when `n` exceeds the
current `available_seats` — seats can never be overbooked.

#### Acceptance Criteria
- [x] `SEAT_BOOKING_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the booking
      contract (filename `booking.py`, the constructor's total-seats argument,
      `reserve(n)`/`release(n)` semantics, the `ValueError`-on-overbooking-attempt +
      unchanged-quantities contract, the `available_seats()`/`reserved_seats()` readers) with
      every oracle-checked value (the initial capacity, the driven accept/reject script and its
      per-op deltas, `expect_final`) derivable from that same visible sentence (no hidden key, no
      leak).
- [x] The driven script exercises TWO distinct illegal overbooking attempts (rejected, quantities
      unchanged) — one at the very start against the initial capacity, and one mid-sequence after
      a partial release — alongside legal reserve/release operations with their declared
      per-quantity deltas; a build that only checks capacity at construction, or that allows
      either overbooking, or that silently loses/creates seats on a legal op, is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `SeatBooking`
      fixture is accepted by `grade_real_system_task(SEAT_BOOKING_TASK, ...)`; a BROKEN fixture
      (allows an overbook, e.g. `reserve()` with no guard) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-22] Second FINTECH-LEDGER CREATE task, in an accounts-receivable/invoicing vertical

A SECOND held-out FINTECH-shaped task, graded by the ALREADY-LANDED `oracle_kind="double_entry"`
dispatch REQ-17 lands (no new oracle code — reuses `_grade_double_entry` ->
`harness.double_entry_oracle.grade_double_entry` verbatim). `INVOICE_AR_TASK`
(`RealSystemTask`, `cls="invoice"`, `oracle_kind="double_entry"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `Invoicing` class
in `invoicing.py` over three named accounts (`accounts_receivable`, `revenue`, `cash`), a
`post(legs)` method that applies a balanced list of debit/credit legs to each account's
exact-integer-cents balance (issuing an invoice debits `accounts_receivable`/credits `revenue`;
receiving payment debits `cash`/credits `accounts_receivable`), and raises `ValueError` (no
mutation) when the legs are unbalanced.

#### Acceptance Criteria
- [x] `INVOICE_AR_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      accounts-receivable contract (filename `invoicing.py`, the three named accounts, the
      `post(legs)` debit/credit-leg contract, the invoice-issuance and payment-receipt posting
      conventions, the `ValueError`-on-unbalanced-entry + unchanged-balances contract, the three
      zero-argument balance readers) with every oracle-checked value (the accounts, the driven
      balanced/unbalanced posting script and its expected balances, `expect_final`) derivable from
      that same visible sentence (no hidden key, no leak).
- [x] The driven script exercises BOTH an illegal unbalanced posting (rejected, every account
      balance unchanged) and multiple legal balanced postings representing two invoices issued and
      one payment received — a build that only ever exercises the legal path, or that allows the
      unbalanced posting, or that posts a balanced entry to the wrong side of an account, is
      caught. `expect_final` is verified consistent with the debit-positive/credit-negative shadow
      math via `harness.double_entry_oracle.validate_spec` and an end-to-end dry run.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Invoicing`
      fixture is accepted by `grade_real_system_task(INVOICE_AR_TASK, ...)`; a BROKEN fixture
      (posts an unbalanced entry with no guard) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-23] Thread `spec_hint` from the real-systems MODIFY driver into `modify_system`

`harness.system_builder.modify_system` already accepts a keyword-only `spec_hint: str | None =
None` (EXT-036 REQ-52, the explicitly-flagged follow-up this task closes) and combines it with
`mod_sentence` as the spec text its deterministic repair chain's scaffold detectors
(`spec_demands_stdlib_http_service`/`spec_demands_tool_calling_agent`) inspect. The MEASURED gap:
a bare `mod_sentence` for a real MODIFY task (e.g. "Add a `PUT /items/<id>` endpoint...") does NOT
itself contain those protocol keywords, so without a hint those scaffolds never fire on a real
modify task even though they DO fire on the matching CREATE task's full sentence. `RealSystemModify
Task` gains an optional `base_sentence` field carrying the matching CREATE task's sentence, and
`run_real_systems_modify_suite`'s driver forwards it to `modify_system` as `spec_hint`.

#### Acceptance Criteria
- [x] `RealSystemModifyTask` gains an optional `base_sentence: str = ""` field, fully backward
      compatible with existing callers that don't set it.
- [x] All 6 existing modify tasks in `REAL_SYSTEMS_MODIFY_TASKS`
      (`RETRY_BASE_DELAY_MODIFY_TASK`, `INI_DEFAULT_FLAG_MODIFY_TASK`,
      `REST_SQLITE_ADD_UPDATE_MODIFY`, `AGENT_ADD_STEP_GUARD_MODIFY`, `ORDER_ADD_REFUND_MODIFY`,
      `INVENTORY_ADD_BACKORDER_MODIFY`) have `base_sentence` populated with their matching CREATE
      task's sentence.
- [x] `_run_one_modify_task` passes `spec_hint=(task.base_sentence or None)` to `modify_system`,
      so a task with an empty `base_sentence` still calls `modify_system` exactly as before
      (`spec_hint=None`).
- [x] `REST_SQLITE_ADD_UPDATE_MODIFY.base_sentence + " " + REST_SQLITE_ADD_UPDATE_MODIFY.
      mod_sentence` triggers `spec_demands_stdlib_http_service`, and
      `AGENT_ADD_STEP_GUARD_MODIFY.base_sentence + " " + AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence`
      triggers `spec_demands_tool_calling_agent` — proving the two protocol MODIFY scaffolds now
      see the full contract. The bare `mod_sentence` alone does NOT trigger the http-service
      detector (proving the gap this task closes).
- [x] Offline-testable (no real model/Jetson): every modify task has a non-empty `base_sentence`
      drawn from the CREATE roster's own sentences; the driver's `modify_system` call is verified
      to pass `spec_hint` via a monkeypatched stub; the roster size is unchanged (15 create + 6
      modify).

### [REQ-24] Fourth LIFECYCLE CREATE task, in an SLA-tiered helpdesk vertical (helpdesk ticket, distinct from the plain-ticket class)

A FOURTH held-out LIFECYCLE-shaped task, pulled from the production-systems atlas's top
impact x buildability lists, graded by the ALREADY-LANDED `oracle_kind="state_machine"`
dispatch REQ-13 lands (no new oracle code — reuses `_grade_state_machine` ->
`harness.state_machine_oracle.grade_state_machine` verbatim). `HELPDESK_SLA_TASK`
(`RealSystemTask`, `cls="helpdesk"`, `oracle_kind="state_machine"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `HelpdeskTicket`
class in `helpdesk.py` — DISTINCT from `TICKET_WORKFLOW_TASK` (REQ-20's plain support ticket)
because its defining behavior is SLA-tier ESCALATION (`escalate()`, legal ONLY from
`"triaged"`, bumps the ticket to a higher-priority tier after an SLA-window breach), states
`new`/`triaged`/`escalated`/`waiting_customer`/`resolved`/`closed`, action methods
`triage()`/`escalate()`/`resolve()`/`wait_on_customer()`/`resume()`/`close()`/`reopen()` that
mutate state along the legal SLA-escalation path, a real `state` property, and TWO distinct
illegal transitions (escalating a brand-new, never-triaged ticket, and closing a ticket that has
never been resolved) raising `ValueError` with state left unchanged.

#### Acceptance Criteria
- [x] `HELPDESK_SLA_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the SLA
      helpdesk contract (filename `helpdesk.py`, the six states, the seven action methods and
      their legal source state(s), the `ValueError`-on-illegal-transition + unchanged-state
      contract, the `state` property) with every oracle-checked value (the states/transitions
      table, the driven accept/reject script, `expect_final`) derivable from that same visible
      sentence (no hidden key, no leak); the sentence names SLA tiers/escalation explicitly as
      the distinguishing behavior from `TICKET_WORKFLOW_TASK`'s plain support ticket.
- [x] The driven script exercises TWO distinct illegal transitions (rejected) alongside the full
      legal SLA-escalation path — a build that guards only one of the two, or that allows either
      illegal transition (in particular an unguarded `escalate()` reachable from `"new"`), is
      caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `HelpdeskTicket` fixture is accepted by `grade_real_system_task(HELPDESK_SLA_TASK, ...)`; a
      BROKEN fixture (allows an illegal transition, e.g. unguarded `escalate()`) is rejected; the
      task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-25] Second cli-exact CREATE task, in an elections/voting vertical (ranked-choice instant-runoff tally)

A SECOND held-out cli-exact-shaped task (the first since REQ-4's INI-query CLI), pulled from the
production-systems atlas, graded by the ALREADY-LANDED `oracle_kind="cli-exact"` dispatch REQ-4
lands (no new oracle code — reuses `_grade_cli_exact` -> `harness.system_suite`'s `exact_stdout`
check variant verbatim). `IRV_TALLY_TASK` (`RealSystemTask`, `cls="elections"`,
`oracle_kind="cli-exact"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
stdlib-only `main.py` CLI that reads ranked-choice ballots from standard input (one
comma-separated ranked candidate list per line) and prints the instant-runoff winner after
elimination rounds, with a pinned round-tally/elimination/majority-threshold print format. The
seeded ballot fixture is built so the FIRST-round plurality leader LOSES after transfers,
proving real IRV logic (not a plurality shortcut).

#### Acceptance Criteria
- [x] `IRV_TALLY_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the IRV CLI
      contract (filename `main.py`, the stdin ballot format, the per-round tally print format,
      the strict-majority win condition, the elimination print format, the alphabetical
      candidate-ordering rule) with the oracle's `expected_stdout` fully derivable from that same
      visible contract (no hidden key, no leak).
- [x] The seeded ballot fixture (21 ballots: 10 `A,B`, 6 `B,C`, 5 `C,B`) makes the round-1
      plurality leader (`A`, 10 first-choice votes) LOSE the election after `C` is eliminated and
      its votes transfer to `B` — `expected_stdout` includes the full elimination-order printout
      (`Round 1: ...`, `Eliminated: C`, `Round 2: ...`, `Winner: B`) so a build that implements
      plain plurality (declares the round-1 leader the winner outright) is caught by an EXACT
      stdout mismatch.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT IRV `main.py`
      stub is accepted by `grade_real_system_task(IRV_TALLY_TASK, ...)`; a BROKEN stub that
      implements plurality instead of IRV is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-26] Third import-oracle CREATE task, in a payroll/tax vertical (progressive bracket withholding)

A THIRD held-out import-oracle-shaped task (after REQ-3's retry-backoff and REQ-5's memoize
libraries), pulled from the production-systems atlas, graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code — reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `TAX_WITHHOLDING_TASK` (`RealSystemTask`,
`cls="payroll"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file `compute_withholding_cents(income_cents, brackets)`
function in `withholding.py` that computes progressive-bracket tax withholding in EXACT integer
cents from a caller-supplied bracket table (no hardcoded jurisdiction), using an explicit
integer-floor-division contribution rule to remove any rounding ambiguity.

#### Acceptance Criteria
- [x] `TAX_WITHHOLDING_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      withholding contract (filename `withholding.py`, the function signature, the
      `[upper_bound_cents, rate_percent]` bracket shape including the open-ended `None`-ceiling
      last bracket, the cumulative-boundary rule, the `(portion_cents * rate_percent) // 100`
      floor-division contribution rule) with every oracle-checked value derivable from that same
      visible sentence (no hidden key, no leak); `brackets` is always supplied by the caller —
      no jurisdiction/bracket table is hardcoded anywhere in the contract.
- [x] The driven checks cover: zero income (zero withholding), an income EXACTLY at a bracket
      boundary, a MID-bracket income, and a TOP-bracket-overflow income (above every bracket's
      ceiling) — each expected value hand-verified against the pinned floor-division rule before
      being added to the roster; a build with an off-by-one bracket boundary is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `compute_withholding_cents` fixture is accepted by
      `grade_real_system_task(TAX_WITHHOLDING_TASK, ...)`; a BROKEN fixture with an off-by-one
      bracket boundary is rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-27] Fourth import-oracle CREATE task, in a legal/court-filing vertical (deadline date math)

A FOURTH held-out import-oracle-shaped task, pulled from the production-systems atlas, graded by
the SAME ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code —
reuses `_grade_import` -> `harness.import_driver.drive_import` verbatim). `COURT_DEADLINE_TASK`
(`RealSystemTask`, `cls="legal"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file
`compute_deadline(trigger_date, day_count, counting_rule, holidays)` function in `deadline.py`
that computes a filing deadline from an explicit ISO trigger date, a day count, a `"calendar"` vs
`"court"` counting rule, a fixed Saturday/Sunday weekend rule, and an explicit caller-supplied
holiday list — rolling forward to the next non-weekend/non-holiday day when the computed landing
day is a weekend or a holiday. Fully deterministic (every input is explicit; nothing depends on
"today"), so no clock/injected-time oracle seam is needed.

#### Acceptance Criteria
- [x] `COURT_DEADLINE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      deadline-math contract (filename `deadline.py`, the function signature, the ISO date
      format, the fixed Saturday/Sunday weekend rule, the caller-supplied `holidays` list with no
      built-in holiday calendar, the `"calendar"` vs `"court"` counting-rule semantics, the
      roll-forward-past-weekend/holiday landing rule) with every oracle-checked value derivable
      from that same visible sentence (no hidden key, no leak).
- [x] The driven checks cover: a baseline calendar computation with no rolling needed, a
      calendar-day landing on a Saturday that rolls forward to the following Monday, a
      court-day count that skips both weekends AND an explicit interior holiday, and a
      calendar-day landing that falls exactly on an explicit (non-weekend) holiday and must still
      roll forward — each expected date independently hand-verified with `datetime.date`
      arithmetic before being added to the roster; a build that forgets to honor `holidays` at
      all (only honors weekends) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `compute_deadline` fixture is accepted by `grade_real_system_task(COURT_DEADLINE_TASK,
      ...)`; a BROKEN fixture that forgets to honor `holidays` is rejected; the task is a member
      of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-24/25/26/27
      tasks (length 15 -> 19).

### [REQ-28] `oracle_kind="clock"` + first TIME-DEPENDENT CREATE task (account lockout/backoff)

The canonical scoreboard's first TIME-DEPENDENT-shaped task, grading whether a build derives every
time decision from an INJECTED clock rather than the real wall clock — a class of real system (auth
lockout/backoff, SLA windows, token/magic-link validity, digest/batch windows, grace periods,
retention sweepers) EXT-059 REQ-10 built a dedicated deterministic oracle (the injectable-clock
oracle) for but that had no representative task on this scoreboard yet. A `_grade_clock` grader wires
the already-landed EXT-059 REQ-10 oracle (`harness/clock_oracle.py`'s `grade_clock`) into
`grade_real_system_task` under a new `oracle_kind="clock"` dispatch — no new process-launch or driving
mechanism, reusing that oracle verbatim. `LOCKOUT_BACKOFF_TASK` (`RealSystemTask`, `cls="auth"`,
`oracle_kind="clock"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only,
single-file `LoginAttemptTracker` class (plus a `LockedOut` exception) in `lockout.py`, constructed
with a keyword-named zero-argument clock callable (`now_fn`) it must consult for EVERY time decision —
three consecutive failed attempts within a 300-second window locks the account for 600 seconds
(further attempts raise `LockedOut` while locked); a successful attempt resets the failure streak; the
lock clears once `now_fn()` reaches the recorded lock-clear time.

#### Acceptance Criteria
- [x] `grade_real_system_task` dispatches `oracle_kind="clock"` to a new `_grade_clock(oracle_spec,
      root, python_exe)` that maps `oracle_spec` (`{"module": str, "entity": str, "spec":
      {...injectable-clock spec shape...}}`) to `harness.clock_oracle.grade_clock(root, module=...,
      entity=..., spec=..., python_exe=python_exe)`, returning `(accepted, note)`. NEVER raises
      (reuses `clock_oracle`'s own never-raise contract) — a malformed spec, a missing entrypoint, or
      a build that derives its time decisions from the real wall clock instead of the injected one is
      an honest `(False, <reason>)`.
- [x] `LOCKOUT_BACKOFF_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the lockout
      contract (filename `lockout.py`, the `LockedOut` exception, the `LoginAttemptTracker(now_fn)`
      constructor's `now_fn` keyword contract explicitly stating the zero-argument-callable/injected-
      clock requirement, the 3-failures/300-second-window/600-second-lock/`is_locked()` semantics)
      with every oracle-checked value (the timeline's `at`/`call`/`args`/`expect` entries,
      `expect_final`) derivable from that same visible sentence (no hidden key, no leak); the
      sentence describes the lock as "clearing," never "expiring," and avoids every other
      leaf-fingerprinting token (cache/ttl/queue/stack/ring/buffer/memoize).
- [x] The driven timeline exercises the FLAGSHIP honesty case: three failures at `t=0/10/20` trigger
      a lock clearing at `t=620`; an attempt at `t=30` (still locked) must raise `LockedOut`; an
      attempt at `t=650` — a 620-SIMULATED-second jump from `t=30` that executes in real
      milliseconds — must succeed (the lock has cleared) — a build that secretly consults the real
      wall clock instead of the injected `now_fn` cannot tell those two calls apart and is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `LoginAttemptTracker` fixture is accepted by `grade_real_system_task(LOCKOUT_BACKOFF_TASK,
      ...)`; a BROKEN fixture that secretly uses the real wall clock (`time.time()`) instead of
      `now_fn` is rejected; a SECOND, independently BROKEN fixture with no lock guard at all is
      also rejected; `harness.clock_oracle.validate_spec` reports `(True, "ok")` for the task's own
      spec; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-29] First agent/LLM-infrastructure CREATE task, an LLM-output parsing library

A held-out task from the atlas's wave-5 agent/LLM-infrastructure research pass, graded by the
ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code — reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `OUTPUT_PARSER_TASK`
(`RealSystemTask`, `cls="agent-infra"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file `output_parser.py` module exporting three
functions — `parse_json_block(text)` (finds and parses the first ` ```json ` fenced block, tolerating
prose around it, raising `ValueError` when none is present), `parse_key_values(text)` (parses
"Key: value" lines into a dict, skipping non-matching lines), and `strip_fences(text)` (removes every
fenced-code-block marker line, returning the remaining content) — extracting structured data out of
messy, LLM-style free-text output.

#### Acceptance Criteria
- [x] `OUTPUT_PARSER_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the parsing
      contract (filename `output_parser.py`, the three function signatures/semantics, the exact
      fence-line-matching rule for `parse_json_block`/`strip_fences`, the first-colon-split rule for
      `parse_key_values`, the no-block `ValueError` case) with every oracle-checked value derivable
      from that same visible sentence (no hidden key, no leak).
- [x] The driven checks cover: a fenced block WITH a language tag (`` ```json ``) whose JSON content
      contains NESTED objects/arrays (proving line-based, not balanced-brace, extraction), the
      no-fenced-block `ValueError` case, `parse_key_values` on a mix of matching and non-matching
      lines (including a value that itself contains a colon), and `strip_fences` on text with a
      differently-tagged fence (`` ```python ``) — each expected value hand-verified against a
      scratch reference implementation before being added to the roster; a build that corrupts
      nested JSON structure (e.g. re-wraps nested values) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No leaf-fingerprinting token (queue/cache/ttl/
      expire/stack/ring/buffer/memoize) appears anywhere in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `output_parser.py` fixture is accepted by `grade_real_system_task(OUTPUT_PARSER_TASK, ...)`; a
      BROKEN fixture that returns the wrong nesting for `parse_json_block` is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`.

### [REQ-30] Second agent/LLM-infrastructure CREATE task, a schema-validation-retry loop

A SECOND held-out task from the atlas's wave-5 agent/LLM-infrastructure research pass, graded by the
ALREADY-LANDED `oracle_kind="agent"` dispatch REQ-11 lands (no new oracle code — reuses `_grade_agent`
-> `harness.agent_oracle.drive_agent`/`check_agent` verbatim). `VALIDATION_RETRY_TASK`
(`RealSystemTask`, `cls="agent-infra"`, `oracle_kind="agent"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file plain-Python agent `main.py` implementing a
Pydantic-AI-shaped validation-retry loop — it asks the stub model for structured output via
tool/function calling, validates the result LOCALLY against a required-keys schema, and on validation
failure sends the error back to the model for exactly ONE retry before finalizing. The scripted stub
model returns an INVALID payload on its first call, then a VALID one on the retry.

#### Acceptance Criteria
- [x] `VALIDATION_RETRY_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      validation-retry contract (filename `main.py`, the env-var/chat-completions/tool-call
      protocol shared with `PLAIN_AGENT_TASK`, the required-keys schema, the append-the-error-then-
      retry-once behavior, the exact final-sentinel line + exit 0) with every oracle-checked value
      (the 2-turn script, the canned tool observation, the goal string, the expected ordered
      tool-call sequence, the expected final substring) derivable from that same visible sentence (no
      hidden key, no leak).
- [x] `oracle_spec["script"]` scripts exactly TWO model turns — an INVALID structured-output
      tool-call attempt (missing a required key) then a VALID, corrected one — and
      `oracle_spec["expect_tool_calls"]` is an ORDERED, args-exact 2-entry list, so the existing
      `check_agent` call-count/args check independently proves BOTH that exactly one retry occurred
      (never zero, never more than one) and that the retry's payload is the schema-corrected one; a
      build that never retries (only one tool call) or that resubmits the same invalid payload on
      retry is caught by that same existing check, with no new oracle code.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written agent fixtures only): a CORRECT
      validation-retry agent fixture is accepted by `grade_real_system_task(VALIDATION_RETRY_TASK,
      ...)` and independently confirmed (via a direct `drive_agent` call) to make exactly 2 model
      round-trips; a BROKEN fixture that never retries on an invalid first attempt is rejected; the
      task is a member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the three
      REQ-28/29/30 tasks (length 19 -> 22).

### [REQ-31] Third import-oracle CREATE task, in a backup/ops vertical (Grandfather-Father-Son retention pruning)

A THIRD held-out import-oracle-shaped task pulled from the atlas's top impact x buildability
lists, graded by the ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle
code -- reuses `_grade_import` -> `harness.import_driver.drive_import` verbatim).
`GFS_RETENTION_TASK` (`RealSystemTask`, `cls="backup"`, `oracle_kind="import"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file
`compute_keep_dates(snapshots, keep_daily, keep_weekly, keep_monthly)` function in
`gfs_retention.py` implementing a Grandfather-Father-Son (GFS) backup retention policy -- the
union of a DAILY tier (the N most-recent dates kept outright), a WEEKLY tier (the newest snapshot
in each of the M most-recent distinct ISO calendar weeks), and a MONTHLY tier (the newest
snapshot in each of the K most-recent distinct calendar months), deduplicated so a date
qualifying for more than one tier appears only once in the returned, sorted keep-list.

#### Acceptance Criteria
- [x] `GFS_RETENTION_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the GFS
      retention contract (filename `gfs_retention.py`, the function signature, the ISO-date input
      format, the DAILY/WEEKLY/MONTHLY tier definitions including the exact ISO-week and
      calendar-month grouping rules, the union/dedup/sorted-output contract, the fewer-than-
      requested-count fallback) with every oracle-checked value derivable from that same visible
      sentence (no hidden key, no leak).
- [x] A 15-date fixture spanning three calendar months (several dates sharing the same ISO week
      or calendar month) drives the primary check, with every expected kept date hand-verified
      (via a scratch computation of the exact same grouping rule) before being added to the
      roster; a SECOND check exercises the "fewer snapshots than the policy asks" edge case (a
      policy requesting more of each tier than exist, expecting every available date kept, no
      error, no fabricated date); a build that ignores the policy and keeps every snapshot is
      caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `compute_keep_dates` fixture is accepted by `grade_real_system_task(GFS_RETENTION_TASK,
      ...)`; a BROKEN fixture that keeps every snapshot regardless of policy is rejected; the task
      is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-32] Fourth import-oracle CREATE task, in a devtools/CI vertical (CI job-matrix expansion)

A FOURTH held-out import-oracle-shaped task, graded by the SAME ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code -- reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `CI_MATRIX_TASK` (`RealSystemTask`,
`cls="devtools"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file `expand_matrix(matrix, exclude=None, include=None)`
function in `ci_matrix.py` that expands a CI job-matrix configuration (an axis-name -> list-of-
values dict) into the full deterministic cross product of job dicts, honoring an `exclude` list
(dicts naming a SUBSET of axes whose matching combos are removed) and an `include` list (extra
job dicts appended verbatim, after exclusion).

#### Acceptance Criteria
- [x] `CI_MATRIX_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the matrix-
      expansion contract (filename `ci_matrix.py`, the function signature and its `=None`
      defaults, the deterministic axis-ordering rule -- axes iterated in ascending alphabetical
      order with the alphabetically-last axis cycling fastest -- the subset-of-axes `exclude`
      semantics, the verbatim-append `include` semantics applied AFTER exclusion) with every
      oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] The driven checks hand-verify (via a scratch `itertools.product` computation) a 2x3 matrix
      with one full-axis `exclude` entry plus one `include` entry, AND a second matrix whose
      `exclude` entry names only a SUBSET of its axes (proving subset-match removes every matching
      combo, not just an exact full-axis match); a build that computes the correct cross product
      but never applies `exclude` is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `expand_matrix` fixture is accepted by `grade_real_system_task(CI_MATRIX_TASK, ...)`; a
      BROKEN fixture that computes the cross product but ignores `exclude` is rejected; the task
      is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-33] Second `oracle_kind="service"` CREATE task, in a web vertical (stdlib REST/SQLite URL shortener)

The canonical scoreboard's SECOND genuinely-SaaS-shaped task (the first since REQ-9's items CRUD
service), graded by the ALREADY-LANDED `oracle_kind="service"` dispatch REQ-9 lands (no new
oracle code -- reuses `_grade_service` -> `harness.server_oracle.serve_and_check_stdlib` plus the
independent post-teardown SQLite row assertion verbatim). `URL_SHORTENER_TASK` (`RealSystemTask`,
`cls="web"`, `oracle_kind="service"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence
for a stdlib REST/SQLite URL-shortener `main.py` (`http.server` + `sqlite3` + `json`, `PORT` env
var, `data.db` SQLite file): `POST /links` creates a shortened link and returns 201 with its
`code` (the link's SQLite autoincrement id, decimal-string form) and `url`; `GET /links/<code>`
returns the stored mapping or 404; `GET /r/<code>` redirects to the original url (301 + a
`Location` header) for a known code, or 404 for an unknown one.

#### Acceptance Criteria
- [x] `URL_SHORTENER_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      URL-shortener contract (filename `main.py`, stdlib-only, `PORT` env var, `data.db` SQLite
      file, the `code`-is-the-decimal-autoincrement-id convention, the `POST /links`/
      `GET /links/<code>`/`GET /r/<code>` semantics + status codes including the `Location`
      header on a successful redirect, persistence across restarts) with every oracle-checked
      value derivable from that same visible sentence (no hidden key, no leak).
- [x] `oracle_spec.http_checks` drives two `POST`s, a `GET /links/<code>` verifying the stored
      mapping, a `GET /links/<unknown-code>` 404, and a `GET /r/<unknown-code>` 404 -- the
      redirect endpoint is deliberately NOT exercised for a KNOWN code, because
      `harness/server_oracle.py`'s plain `urllib.request.urlopen` HTTP client transparently
      FOLLOWS a real 3xx response (it has no way to observe `status == 301`, nor does its
      `http_check` dict support a response-header assertion at all) -- checking a known code's
      redirect would make the oracle's own HTTP client dereference the arbitrary submitted URL,
      an unverifiable and hermeticity-hazardous request in a sandboxed/no-egress subprocess; the
      redirect TARGET is instead independently verified via the `GET /links/<code>` check.
      `oracle_spec.db` asserts both created rows persisted in `data.db`.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT stdlib
      URL-shortener fixture is accepted by `grade_real_system_task(URL_SHORTENER_TASK, ...)`,
      including the independent db assertion; a BROKEN fixture whose `GET /links/<code>` lookup
      is dead (always 404s, even for a code just created) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-34] Second `oracle_kind="clock"` CREATE task, in an auth vertical (access-token validity window)

The canonical scoreboard's SECOND TIME-DEPENDENT task (the first since REQ-28's account
lockout/backoff), graded by the ALREADY-LANDED `oracle_kind="clock"` dispatch REQ-28 lands (no
new oracle code -- reuses `_grade_clock` -> `harness.clock_oracle.grade_clock` verbatim).
`TOKEN_VALIDITY_TASK` (`RealSystemTask`, `cls="auth"`, `oracle_kind="clock"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `TokenIssuer`
class in `tokens.py`, constructed with a keyword-named zero-argument clock callable (`now_fn`) it
must consult for EVERY time decision -- `issue(name)` returns a token id valid for exactly 900
seconds per `now_fn`; `check(token)` returns `True` strictly within that 900-second window and
`False` at or after it, and once `False` for a token because its window has elapsed, every later
`check` for that same token also stays `False`.

#### Acceptance Criteria
- [x] `TOKEN_VALIDITY_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      token-validity contract (filename `tokens.py`, the `TokenIssuer(now_fn)` constructor's
      `now_fn` keyword contract explicitly stating the zero-argument-callable/injected-clock
      requirement, the `issue(name)`/`check(token)` semantics, the exact 900-second window, the
      never-revalidates-once-elapsed rule) with every oracle-checked value (the timeline's
      `at`/`call`/`args`/`expect` entries) derivable from that same visible sentence (no hidden
      key, no leak); the sentence says a token "is valid for 900 seconds" / its window has
      "elapsed", never "expires" (avoiding the verified `ttl-store` leaf's keyword fingerprint).
- [x] The driven timeline exercises an 899-second reading (still valid, `True`), the exact
      900-second boundary (no longer valid, `False`), and a large 3600-second jump on the SAME
      token (still `False`, proving the token never re-validates once its window has elapsed) --
      `harness.clock_oracle.validate_spec` reports `(True, "ok")` for the task's own spec.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `TokenIssuer`
      fixture is accepted by `grade_real_system_task(TOKEN_VALIDITY_TASK, ...)`; a BROKEN fixture
      that never invalidates a token (valid forever once issued) is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four
      REQ-31/32/33/34 tasks (length 22 -> 26).

### [REQ-35] Fifth LIFECYCLE MODIFY task: add an `on_hold` state to the SLA-tiered helpdesk ticket

The canonical scoreboard's MODIFY half was lopsided (26 CREATE vs only 6 MODIFY). This is the first of
FIVE new MODIFY tasks (REQ-35..39) that grow it to 11, each reusing an ALREADY-VERIFIED CREATE task's
oracle dispatch verbatim (zero new oracle code), mirroring how REQ-14/REQ-16 reuse REQ-13/REQ-15's
dispatch. `HELPDESK_ADD_STATE_MODIFY` (`RealSystemModifyTask`, `cls="helpdesk-modify"`,
`oracle_kind="state_machine"`) is added to `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a
hand-authored CORRECT baseline `helpdesk.py` matching REQ-24's `HELPDESK_SLA_TASK` contract exactly (no
`hold()`/`release()`); `mod_sentence` asks for a new `on_hold` state reachable via `hold()` from EITHER
`triaged` OR `escalated`, with `release()` returning it to `triaged` -- legal only from those source
states.

#### Acceptance Criteria
- [x] `HELPDESK_ADD_STATE_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="state_machine"` dispatcher REQ-13/REQ-24 land (no new oracle code, reusing
      `grade_real_system_task` exactly as every prior MODIFY task reuses its CREATE half's dispatch).
- [x] `mod_sentence` pins `hold()`'s two legal source states (`triaged`/`escalated`) and `release()`'s
      single legal source state (`on_hold` -> `triaged`), and the illegal-elsewhere/state-unchanged
      contract; every oracle-checked value in `oracle_spec` (the extended states/transitions table, a
      driven script exercising both hold/release from BOTH legal source states plus an illegal
      hold-from-`new`, mixed with a regression of the original legal SLA path and the original illegal
      close-from-`triaged` rejection) is derivable from that same visible `mod_sentence` (no hidden key,
      no leak).
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): the `start_system` baseline
      ALONE is accepted by `HELPDESK_SLA_TASK`'s own oracle (proves the baseline is a genuinely correct
      REQ-24 implementation); a hand-authored CORRECT post-modification fixture (baseline + guarded
      `hold()`/`release()`) is accepted by the new MODIFY oracle; the UNMODIFIED baseline is rejected;
      a fixture that adds `hold()`/`release()` correctly but regresses the original illegal
      close-from-`triaged` rejection is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-36] Second `oracle_kind="import"` MODIFY task: add an optional `cap_cents` to progressive tax withholding

The canonical scoreboard's SECOND payroll/tax "import" MODIFY task, reusing TAX_WITHHOLDING_TASK's
already-VERIFIED `oracle_kind="import"` dispatch (REQ-3/REQ-26) verbatim, mirroring how REQ-7's
`RETRY_BASE_DELAY_MODIFY_TASK` adds an optional keyword parameter to a reusable library.
`TAX_ADD_CAP_MODIFY` (`RealSystemModifyTask`, `cls="payroll-modify"`, `oracle_kind="import"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline `withholding.py`
matching REQ-26's contract exactly (no `cap_cents`); `mod_sentence` asks for an ADDITIONAL optional
`cap_cents` keyword (default `None`) that, when supplied, caps the computed withholding at `cap_cents`
without ever raising it.

#### Acceptance Criteria
- [x] `TAX_ADD_CAP_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="import"` dispatcher REQ-3/REQ-26 land (no new oracle code).
- [x] `mod_sentence` pins the new `cap_cents=None` default, the "smaller of the natural amount and
      `cap_cents`" cap rule, and the unchanged-when-omitted-or-`None` contract; `oracle_spec.api_calls`
      REUSES REQ-26's own four exact hand-verified regression values (invoked with no `cap_cents`) plus
      two NEW calls proving the cap both BINDS (a cap below the natural amount) and is a no-op (a cap
      above the natural amount never raises the result) -- every value derivable from the same visible
      `mod_sentence` (no hidden key, no leak).
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): the `start_system` baseline
      ALONE is accepted by `TAX_WITHHOLDING_TASK`'s own oracle; a hand-authored CORRECT
      post-modification fixture (baseline + `cap_cents=None` cap) is accepted by the new MODIFY oracle;
      the UNMODIFIED baseline is rejected (`TypeError` on the cap calls); a fixture that adds `cap_cents`
      with a WRONG nonzero default (regressing the original uncapped behavior) is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-37] Second `oracle_kind="cli-exact"` MODIFY task: add an alphabetical-tie-elimination rule to IRV tally

The canonical scoreboard's SECOND elections "cli-exact" MODIFY task, reusing IRV_TALLY_TASK's
already-VERIFIED `oracle_kind="cli-exact"` dispatch (REQ-25) verbatim, mirroring how REQ-10's
`INI_DEFAULT_FLAG_MODIFY_TASK` reuses the same dispatch for a config CLI. `IRV_ADD_TIE_RULE_MODIFY`
(`RealSystemModifyTask`, `cls="elections-modify"`, `oracle_kind="cli-exact"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline `main.py` implementing
REQ-25's ORIGINAL contract exactly except for one behavior REQ-25 explicitly leaves unspecified (a tie
for fewest votes, which its own ballots never exercise) -- the baseline breaks ties alphabetically
EARLIEST, a plausible but wrong guess; `mod_sentence` pins the new rule: break ties by eliminating the
candidate LATER alphabetically.

#### Acceptance Criteria
- [x] `IRV_ADD_TIE_RULE_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="cli-exact"` dispatcher REQ-25 lands (no new oracle code).
- [x] `mod_sentence` pins the new alphabetically-later tie-elimination rule and that the no-tie case is
      unchanged; `oracle_spec` is a crafted 22-ballot fixture where a tie for fewest genuinely occurs and
      the tie-break choice CHANGES the eventual winner (breaking the tie the other way would hand the win
      to a different candidate) -- the exact expected multi-round stdout (tally lines, elimination order,
      winner) was hand-recomputed and independently re-verified against a script implementing the rule.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): the `start_system` baseline
      ALONE is accepted by `IRV_TALLY_TASK`'s own oracle (its different, unexercised tie-break never
      fires on REQ-25's own no-tie ballots); a hand-authored CORRECT post-modification fixture is
      accepted by the new MODIFY oracle; the UNMODIFIED baseline is rejected (wrong tie-break, wrong
      winner); a fixture that implements the new rule correctly but regresses the original
      `Round <N>: ...` separator format is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-38] Second `oracle_kind="service"` MODIFY task: add `DELETE /links/<code>` to the URL shortener

The canonical scoreboard's SECOND web "service" MODIFY task, reusing URL_SHORTENER_TASK's
already-VERIFIED `oracle_kind="service"` dispatch (REQ-9/REQ-33) verbatim, mirroring how REQ-10's
`REST_SQLITE_ADD_UPDATE_MODIFY` adds an endpoint to a stdlib CRUD service. `SHORTENER_ADD_DELETE_MODIFY`
(`RealSystemModifyTask`, `cls="web-modify"`, `oracle_kind="service"`) is added to
`REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored CORRECT baseline `main.py` matching
REQ-33's contract exactly (no `DELETE`); `mod_sentence` asks for a `DELETE /links/<code>` endpoint that
responds 204 and genuinely removes the row (a subsequent `GET` for that code must 404), following
REQ-33's own SAFETY design (no redirect-following, `.invalid`-TLD fixture urls).

#### Acceptance Criteria
- [x] `SHORTENER_ADD_DELETE_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="service"` dispatcher REQ-9/REQ-33 land (no new oracle code).
- [x] `mod_sentence` pins the `DELETE /links/<code>` -> 204 contract, the subsequent-GET-404
      requirement, and the 404-for-unknown/already-deleted-code behavior; `oracle_spec.http_checks`
      REGRESSES REQ-33's original `POST`/`GET`/unknown-`GET /r/<code>` checks unchanged, then exercises
      the new `DELETE` both for a real link (204, then a follow-up `GET` proving it is genuinely gone)
      and for an already-deleted code (404); `oracle_spec.db` uses the SURVIVING (never-deleted) second
      link so the independent post-teardown row assertion stays honestly satisfiable.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): the `start_system` baseline
      ALONE is accepted by `URL_SHORTENER_TASK`'s own oracle; a hand-authored CORRECT post-modification
      fixture (baseline + a real `do_DELETE`) is accepted by the new MODIFY oracle; the UNMODIFIED
      baseline is rejected (`BaseHTTPRequestHandler` 501s with no `do_DELETE`); a fixture whose `DELETE`
      wipes EVERY row (no `WHERE id = ?` clause, regressing persistence) is also rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.

### [REQ-39] Second `oracle_kind="clock"` MODIFY task: add `admin_unlock()` to the account lockout policy

The canonical scoreboard's SECOND auth "clock" MODIFY task, reusing LOCKOUT_BACKOFF_TASK's
already-VERIFIED `oracle_kind="clock"` dispatch (REQ-28) verbatim, mirroring how REQ-14/REQ-16 add a new
action method to their CREATE half's baseline. `LOCKOUT_ADMIN_UNLOCK_MODIFY` (`RealSystemModifyTask`,
`cls="auth-modify"`, `oracle_kind="clock"`) is added to `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a
hand-authored CORRECT baseline `lockout.py` matching REQ-28's contract exactly (no `admin_unlock()`);
`mod_sentence` asks for `admin_unlock()`, which clears an active lock IMMEDIATELY (not merely at its
natural clear time).

#### Acceptance Criteria
- [x] `LOCKOUT_ADMIN_UNLOCK_MODIFY` is added to `REAL_SYSTEMS_MODIFY_TASKS`, graded by the SAME
      `oracle_kind="clock"` dispatcher REQ-28 lands (no new oracle code).
- [x] `mod_sentence` pins `admin_unlock()`'s immediate-clear contract (`is_locked()` false right after,
      the next `record_attempt` processed as unlocked) and its no-op-when-not-locked behavior; the
      driven timeline REGRESSES REQ-28's own t=0/10/20 (lock-triggering) and t=30 (still-locked,
      `LockedOut`) steps, then calls `admin_unlock()` at t=40 and a `record_attempt` at t=50 -- only 10
      simulated seconds later, WAY before the natural t=620 clear -- so a no-op or unwired
      `admin_unlock()` is caught (t=50 would still raise `LockedOut` under the OLD lock-clear time).
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): the `start_system` baseline
      ALONE is accepted by `LOCKOUT_BACKOFF_TASK`'s own oracle; a hand-authored CORRECT
      post-modification fixture is accepted by the new MODIFY oracle; the UNMODIFIED baseline is
      rejected (`AttributeError` on `admin_unlock`); a fixture that adds a genuinely-working
      `admin_unlock()` but regresses the original 3-failure lock threshold (weakened to 4) is also
      rejected.
- [x] Leaves-OFF enforced identically to every other MODIFY task (static
      `leaf_for_spec(task.mod_sentence) is None`); no oracle leak.
- [x] `REAL_SYSTEMS_MODIFY_TASKS` grew by exactly these five REQ-35/36/37/38/39 tasks (length 6 -> 11);
      `REAL_SYSTEMS_TASKS` (the CREATE half) is untouched by this wave (still 26).

### [REQ-40] Fifth import-oracle CREATE task, in a NEW reliability vertical (Stripe-style recovery-point request executor)

A FIFTH held-out import-oracle-shaped task pulled from the atlas's wave-7 engineering-blog-mining
"gradable-today" shortlist (`docs/PRODUCTION-SYSTEMS-ATLAS.md` EB9, simplified here to the pure
decision-table shape this shortlist targets -- no new idempotency-replay/workflow-replay oracle,
just the deterministic replay-decision logic itself), graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code -- reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `RECOVERY_POINT_TASK` (`RealSystemTask`,
`cls="reliability"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file `replay_execution(steps, recovery_point)` function in
`recovery_point.py` that replays an ordered list of `idempotent`/`non_idempotent`-tagged steps
from a saved recovery-point checkpoint -- steps before the checkpoint re-run only if idempotent
(a non-idempotent one is skipped), every step at or after the checkpoint runs unconditionally.

#### Acceptance Criteria
- [x] `RECOVERY_POINT_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the replay
      contract (filename `recovery_point.py`, the function signature, the `steps`/`recovery_point`
      shapes, the strict `i < recovery_point` vs `i >= recovery_point` decision rule, the
      idempotent-reruns/non-idempotent-skipped-before-the-point rule, the unconditional-at-or-
      after-the-point rule, the original-order/no-dedup return contract) with every oracle-checked
      value derivable from that same visible sentence (no hidden key, no leak).
- [x] Three driven checks, every expected sequence hand-verified (via a scratch walk of the exact
      same rule) before being added to the roster: `recovery_point=0` (nothing precedes it, every
      step runs); a mid-list checkpoint that skips a non-idempotent prefix step while re-running an
      idempotent one; `recovery_point == len(steps) - 1` (only the trailing step runs
      unconditionally, everything before it governed by idempotency). A build that reruns every
      step before the checkpoint regardless of idempotency (unsafely re-running a non-idempotent
      one) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `replay_execution` fixture is accepted by `grade_real_system_task(RECOVERY_POINT_TASK,
      ...)`; a BROKEN fixture that reruns every step before the checkpoint regardless of
      idempotency is rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-41] Sixth import-oracle CREATE task, in a NEW authz vertical (Discord-style layered permission-overwrite resolution)

A SIXTH held-out import-oracle-shaped task pulled from the SAME atlas wave-7 shortlist, graded by
the SAME ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code).
`PERMISSION_OVERWRITE_TASK` (`RealSystemTask`, `cls="authz"`, `oracle_kind="import"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file
`resolve_permissions(everyone_allow, everyone_deny, role_overwrites, member_allow, member_deny)`
function in `permission_overwrite.py` implementing a Discord-style layered permission-overwrite
resolution: an `@everyone` base layer, then a combined role-overwrite layer (every role's deny
bits unioned, then every role's allow bits unioned), then a member-specific layer -- each layer
clearing its deny bits before setting its allow bits, later layers overriding earlier ones.

#### Acceptance Criteria
- [x] `PERMISSION_OVERWRITE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      three-layer, deny-before-allow, `@everyone` -> role -> member precedence contract (filename
      `permission_overwrite.py`, the function signature, the bitmask/role-overwrite-list shapes,
      the union-across-roles rule, the exact clear-then-set-per-layer algorithm) with every
      oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] Three driven checks, every expected bitmask hand-verified via scratch bit math before being
      added to the roster: a member-allow overriding a role-deny on the same bit; a role-allow
      overriding an `@everyone`-deny on the same bit; a permission bit no layer ever grants staying
      clear (denied) in the result (also exercising an empty `role_overwrites` list). A build that
      applies the member layer BEFORE the role layer (the wrong precedence order) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `resolve_permissions` fixture is accepted by `grade_real_system_task(PERMISSION_OVERWRITE_
      TASK, ...)`; a BROKEN fixture applying the layers in the wrong precedence order is rejected;
      the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-42] Seventh import-oracle CREATE task, in the payroll vertical (FLSA blended-rate overtime calculator)

A SEVENTH held-out import-oracle-shaped task, reusing the `cls="payroll"` vertical
`TAX_WITHHOLDING_TASK` (REQ-26) already established, pulled from the SAME atlas wave-7 shortlist,
graded by the SAME ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle
code). `BLENDED_OVERTIME_TASK` (`RealSystemTask`, `cls="payroll"`, `oracle_kind="import"`) is
added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file
`compute_blended_overtime_pay(entries)` function in `blended_overtime.py` implementing the U.S.
FLSA blended (weighted-average) overtime rule for a worker who worked at more than one pay rate in
a single workweek: straight pay at each entry's own rate, plus (when total hours exceed 40) a
half-time premium on the blended (weighted-average) regular rate for every overtime hour, the
final total rounded to the nearest cent using round-half-up.

#### Acceptance Criteria
- [x] `BLENDED_OVERTIME_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      blended-overtime contract (filename `blended_overtime.py`, the function signature, the
      `[rate_cents, hours]` entry shape, the `total_straight_pay_cents`/`blended_regular_rate`/
      `overtime_hours`/half-time-premium formulas, the strict `> 40` overtime trigger, the
      round-half-up final-rounding rule) with every oracle-checked value derivable from that same
      visible sentence (no hidden key, no leak).
- [x] Four driven checks, every expected cents value hand-verified via scratch arithmetic before
      being added to the roster: under-40-hours (no overtime); over-40-hours at a SINGLE rate;
      over-40-hours at TWO rates (the genuinely blended case); exactly 40 hours (the boundary,
      still no overtime since the trigger is strictly `> 40`). A build that computes the overtime
      premium from only the first entry's rate instead of the true blended rate is caught (the
      single-rate check alone cannot distinguish this bug -- the two-rate check is what catches
      it).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `compute_blended_overtime_pay` fixture is accepted by `grade_real_system_task(BLENDED_
      OVERTIME_TASK, ...)`; a BROKEN fixture that uses only the first entry's rate instead of the
      blended rate is rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-43] Eighth import-oracle CREATE task, in a NEW comms vertical (Twilio-style SMS segmentation calculator)

An EIGHTH held-out import-oracle-shaped task pulled from the SAME atlas wave-7 shortlist
(`docs/PRODUCTION-SYSTEMS-ATLAS.md` EB16), graded by the SAME ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code). `SMS_SEGMENT_TASK`
(`RealSystemTask`, `cls="comms"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file `segment_sms(message)` function in
`sms_segments.py` implementing a simplified Twilio-style SMS segmentation calculator: GSM-7 (a
simplified plain-visible-ASCII-plus-newline charset for this task, stated explicitly as such)
messages fit 160 chars in one segment or split at 153/segment; any other character forces UCS-2
(70 chars single-segment, 67/segment split); the empty string is defined GSM-7, 1 segment.

#### Acceptance Criteria
- [x] `SMS_SEGMENT_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      segmentation contract (filename `sms_segments.py`, the function signature, the exact
      simplified GSM-7-encodability rule stated as a simplification with its own precise charset
      definition, the 160/153-vs-70/67 threshold pairs, the ceiling-division split-count formula,
      the empty-string special case, the `(encoding, segment_count, n)` return shape) with every
      oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] Five driven checks, every expected tuple hand-verified via scratch ceiling-division
      arithmetic before being added to the roster: exactly 160 GSM-7 chars (1 segment); 161 GSM-7
      chars (2 segments, split at 153); a message forced to UCS-2 by a single non-ASCII character
      at exactly 70 chars (1 segment) and at 71 chars (2 segments, split at 67); the empty string
      (GSM-7, 1 segment, 0 chars). A build that always applies the GSM-7 160/153 thresholds even
      for a UCS-2-encoded message is caught (its 71-char UCS-2 check regresses to 1 segment
      instead of the correct 2).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `segment_sms`
      fixture is accepted by `grade_real_system_task(SMS_SEGMENT_TASK, ...)`; a BROKEN fixture that
      uses the GSM-7 thresholds even for a UCS-2 message is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-40/41/42/43 tasks
      (length 26 -> 30).

### [REQ-44] Ninth CREATE task, in a NEW background-job-processing vertical (background-job lifecycle)

A NINTH held-out CREATE task, spreading the roster across the ALREADY-LANDED `oracle_kind="state_machine"`
dispatch REQ-13 lands (no new oracle code: reuses `_grade_state_machine` ->
`harness.state_machine_oracle.grade_state_machine` verbatim). `JOB_QUEUE_LIFECYCLE_TASK`
(`RealSystemTask`, `cls="jobs"`, `oracle_kind="state_machine"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file `Job` class in `job.py` modeling a background-job
processor's lifecycle -- `"queued"`/`"running"`/`"succeeded"`/`"failed"`/`"retrying"`/`"dead"` states,
`start()`/`succeed()`/`fail()`/`retry()`/`kill()` actions, with `start()` legal from BOTH `"queued"` (the
first attempt) and `"retrying"` (resuming after a retry) -- a shape none of the prior lifecycle tasks
(`ORDER_LIFECYCLE_TASK`/`HELPDESK_SLA_TASK`) exercises.

#### Acceptance Criteria
- [x] `JOB_QUEUE_LIFECYCLE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the six-state,
      five-action lifecycle contract (filename `job.py`, the class name, the exact legal source state(s)
      per action -- including `start()`'s two legal sources -- the `ValueError`-on-illegal-transition-
      with-unchanged-state contract, and the `state` property) with every oracle-checked value derivable
      from that same visible sentence (no hidden key, no leak).
- [x] At least TWO illegal transitions are driven and rejected, hand-verified via a scratch walk of the
      exact same transition table before being added to the roster: `succeed()` from `"queued"` (never
      started) and `retry()` from `"succeeded"` (already terminal) -- proving the guard holds both before
      any legal op and after the job has already reached its terminal state.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. The state name `"queued"` (a required literal FSM
      state) is confirmed SAFE against the real leaf classifier -- `harness.adt_oracle._KEYWORDS`/
      `_METHOD_TOKENS` never lists the bare token `"queue"`, only the full phrases `"fifo"`/
      `"first-in-first-out"` and `"priority queue"`/`"priority-queue"`, none of which this sentence ever
      forms -- verified directly via `leaf_for_spec(...) is None`, not just a literal substring scan.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Job` fixture is
      accepted by `grade_real_system_task(JOB_QUEUE_LIFECYCLE_TASK, ...)`; a BROKEN fixture that allows an
      illegal transition (e.g. `succeed()` from any state) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-45] Tenth CREATE task, in the ticketing vertical (event seat hold/confirm/release)

A TENTH held-out CREATE task, in the SAME `cls="ticketing"` vertical `SEAT_BOOKING_TASK` (REQ-21) already
established but modeling a DISTINCT three-quantity hold/confirm/release workflow (not the plain two-
quantity reserve/release flow), graded by the ALREADY-LANDED `oracle_kind="conservation"` dispatch REQ-15
lands (no new oracle code: reuses `_grade_conservation` -> `harness.conservation_oracle.grade_conservation`
verbatim). `SEAT_HOLD_TASK` (`RealSystemTask`, `cls="ticketing"`, `oracle_kind="conservation"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `SeatHold` class in
`seat_hold.py` modeling `hold(n)` (available->held), `confirm(n)` (held->sold), and `release(n)`
(held->available), over a mirror-pair bookkeeping of `available`/`held`/`sold` that always sums to
`total_seats`.

#### Acceptance Criteria
- [x] `SEAT_HOLD_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the three-quantity
      hold/confirm/release contract (filename `seat_hold.py`, the class name, the constructor shape, the
      three reader methods, the exact deltas each action causes, the `ValueError`-on-over-hold/over-
      confirm-with-unchanged-quantities contract) with every oracle-checked value derivable from that same
      visible sentence (no hidden key, no leak).
- [x] TWO illegal ops are driven and rejected, hand-verified via a scratch walk of the exact same
      available/held/sold delta bookkeeping before being added to the roster: holding MORE seats than are
      currently available, and confirming MORE seats than are currently held (mid-sequence, after a
      partial confirm has already moved the balance) -- proving the guard holds both at the very start and
      after legal ops have moved the balance.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `SeatHold` fixture is
      accepted by `grade_real_system_task(SEAT_HOLD_TASK, ...)`; a BROKEN fixture that allows an over-hold
      (never checks `available` before moving seats to `held`) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-46] Eleventh CREATE task, in the fintech vertical (AR partial-payment application ledger)

An ELEVENTH held-out CREATE task, in the SAME `cls="fintech"` double-entry vertical `INVOICE_AR_TASK`
(REQ-22) already established but modeling a DISTINCT partial-payment-application scenario (multiple
partial payments applied against a single invoice, rather than two invoices plus one full payment), graded
by the ALREADY-LANDED `oracle_kind="double_entry"` dispatch REQ-17 lands (no new oracle code: reuses
`_grade_double_entry` -> `harness.double_entry_oracle.grade_double_entry` verbatim, and the SAME
`accounts_receivable`/`revenue`/`cash` three-account shape/sign convention `INVOICE_AR_TASK` already
uses). `INVOICE_AR_AGING_TASK` (`RealSystemTask`, `cls="fintech"`, `oracle_kind="double_entry"`) is added
to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `ARPaymentLedger` class
in `ar_payment_application.py` implementing `post(legs)` over the three accounts, with an invoice issued
once and then TWO separate partial payments posted that together exactly clear the invoice's outstanding
balance to `0`.

#### Acceptance Criteria
- [x] `INVOICE_AR_AGING_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      partial-payment-application contract (filename `ar_payment_application.py`, the class name, the
      three reader methods, the `post(legs)` balanced/unbalanced posting rule, the debit-ADDS/credit-
      SUBTRACTS convention) with every oracle-checked value derivable from that same visible sentence (no
      hidden key, no leak).
- [x] An UNBALANCED posting is driven and rejected FIRST, hand-verified via `harness.double_entry_oracle.
      validate_spec` and a scratch debit/credit sum walk before being added to the roster; then one
      balanced invoice posting and TWO balanced partial-payment postings are driven, landing on
      `accounts_receivable=0` (the invoice fully applied/cleared), matching `expect_final`.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `ARPaymentLedger`
      fixture is accepted by `grade_real_system_task(INVOICE_AR_AGING_TASK, ...)`; a BROKEN fixture that
      never checks debits equal credits (accepts an unbalanced posting) is rejected; the task is a member
      of `REAL_SYSTEMS_TASKS`.

### [REQ-47] Twelfth CREATE task, in a NEW validation-library vertical (Luhn/ISBN-13/EAN-13 check digits)

A TWELFTH held-out CREATE task, in a NEW validation vertical, graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `CHECK_DIGIT_TASK` (`RealSystemTask`, `cls="validation"`,
`oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only,
single-file module `check_digits.py` defining three functions -- `luhn_valid(number)` (the standard Luhn
checksum), `isbn13_valid(s)` and `ean13_valid(s)` (the identical EAN-13 weighted 1/3 checksum, since a
real ISBN-13 code IS a valid EAN-13 number) -- each returning a `bool`.

#### Acceptance Criteria
- [x] `CHECK_DIGIT_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins all three checksum
      algorithms (filename `check_digits.py`, the three function signatures, the exact digit-doubling-
      from-the-right Luhn rule with the >9-subtract-9 correction, the exact 13-position 1/3 alternating-
      weight rule shared by `isbn13_valid`/`ean13_valid`, the non-digit/wrong-length-returns-`False`
      contract) with every oracle-checked value derivable from that same visible sentence (no hidden key,
      no leak).
- [x] Six driven checks -- a KNOWN-good and a KNOWN-bad value per algorithm, every expected boolean
      hand-verified via scratch checksum arithmetic against REAL published test vectors before being added
      to the roster: Luhn `4539148803436467` (valid, checksum total 80) / `1234567890123456` (invalid,
      checksum total 64); ISBN-13 `9780306406157` (valid, weighted sum 100) / `9780306406158` (invalid,
      weighted sum 101); EAN-13 `4006381333931` (valid, weighted sum 90) / `4006381333932` (invalid,
      weighted sum 91). A build that skips the Luhn doubling step entirely (only checks digit format) is
      caught by the `luhn_bad` check (it wrongly accepts the invalid number).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `check_digits.py`
      fixture is accepted by `grade_real_system_task(CHECK_DIGIT_TASK, ...)`; a BROKEN fixture that
      accepts a numerically-invalid Luhn number (format-only check, no real checksum) is rejected; the
      task is a member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four
      REQ-44/45/46/47 tasks (length 30 -> 34).

### [REQ-48] Thirteenth CREATE task, in a NEW fintech-calculator vertical (Net Present Value)

A THIRTEENTH held-out CREATE task, in a NEW fintech vertical distinct from the double-entry-ledger
fintech tasks above (a plain pure-function calculator, not a ledger), graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `NPV_CALCULATOR_TASK` (`RealSystemTask`,
`cls="fintech"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file module `npv.py` defining one function `npv(rate,
cashflows)` computing the standard Net Present Value (sum of `cashflows[t] / (1+rate)**t` for
every index `t`, so the `t=0` cashflow is never discounted), returning the result rounded to 2
decimal places.

#### Acceptance Criteria
- [x] `NPV_CALCULATOR_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the NPV
      contract (filename `npv.py`, the function signature, the per-index discount formula
      including the `t=0`-never-discounted rule, the round-to-2-decimal-places return contract)
      with every oracle-checked value derivable from that same visible sentence (no hidden key,
      no leak).
- [x] Three driven checks, every expected value hand-verified via independent recomputation
      (not trusted blindly) before being added to the roster: `npv(0.1, [-1000, 500, 500, 500])
      == 243.43`; `npv(0.0, [-100, 50, 50]) == 0.0`; `npv(0.05, [100]) == 100.0`. A build that
      discounts the `t=0` cashflow too (an off-by-one exponent bug) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `npv.py`
      fixture is accepted by `grade_real_system_task(NPV_CALCULATOR_TASK, ...)`; a BROKEN fixture
      that discounts the `t=0` cashflow (off-by-one exponent) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-49] Fourteenth CREATE task, in a NEW scheduling/devtools vertical (closed-interval merge)

A FOURTEENTH held-out CREATE task, in a NEW scheduling/devtools vertical, graded by the
ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `INTERVAL_MERGE_TASK`
(`RealSystemTask`, `cls="scheduling"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`:
a contract-exact sentence for a stdlib-only, single-file module `interval_merge.py` defining one
function `merge(intervals)` that merges overlapping (or merely touching) closed `[start, end]`
intervals into a sorted, non-overlapping list.

#### Acceptance Criteria
- [x] `INTERVAL_MERGE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the merge
      contract (filename `interval_merge.py`, the function signature, closed-interval semantics,
      the overlap-OR-touch merge rule, the sorted-by-start output ordering, the no-mutation and
      empty-input contracts) with every oracle-checked value derivable from that same visible
      sentence (no hidden key, no leak).
- [x] Four driven checks, every expected value hand-verified via a scratch walk before being added
      to the roster: `merge([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]`;
      `merge([[1,4],[4,5]]) == [[1,5]]` (the touching-interval case); `merge([]) == []`;
      `merge([[5,5]]) == [[5,5]]`. A build that uses a strict `<` overlap test (fails to merge
      merely-touching intervals) is caught by the touching-interval check.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `interval_merge.py` fixture is accepted by `grade_real_system_task(INTERVAL_MERGE_TASK,
      ...)`; a BROKEN fixture that fails to merge touching intervals (strict `<` overlap test) is
      rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-50] Fifteenth CREATE task, in a NEW devtools vertical (RFC 4648 Base32 codec)

A FIFTEENTH held-out CREATE task, in a NEW devtools/codec vertical, graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `BASE32_CODEC_TASK` (`RealSystemTask`,
`cls="devtools"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file module `base32_codec.py` defining `encode(data)` (a list
of byte-value integers -> an RFC 4648 Base32 `str` with standard `=` padding) and `decode(s)` (a
Base32 `str` -> a list of byte-value integers), fully round-tripping.

#### Acceptance Criteria
- [x] `BASE32_CODEC_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the codec
      contract (filename `base32_codec.py`, both function signatures using JSON-safe `list[int]`
      byte representations rather than a raw `bytes` object, the standard `A-Z2-7` alphabet with
      required `=` padding to a multiple of 8) with every oracle-checked value derivable from that
      same visible sentence (no hidden key, no leak).
- [x] Seven driven checks, every expected value hand-verified against Python's own
      `base64.b32encode`/`base64.b32decode` (the RFC 4648 reference implementation) before being
      added to the roster: `encode([]) == ""`; `encode([102]) == "MY======"`; `encode([102,111,111])
      == "MZXW6==="`; `encode([102,111,111,98,97,114]) == "MZXW6YTBOI======"`; `decode("MY======")
      == [102]`; `decode("MZXW6YTBOI======") == [102,111,111,98,97,114]`; a chained round-trip
      check (`decode` applied to the prior `encode_foobar` call's own result via a `__jaros_ref__`)
      also equals `[102,111,111,98,97,114]`. A build that strips the required `=` padding is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `base32_codec.py` fixture is accepted by `grade_real_system_task(BASE32_CODEC_TASK, ...)`; a
      BROKEN fixture that strips the `=` padding is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-51] Sixteenth CREATE task, in a NEW logistics/geo vertical (haversine distance)

A SIXTEENTH held-out CREATE task, in a NEW logistics/geo vertical, graded by the ALREADY-LANDED
`oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `HAVERSINE_DISTANCE_TASK` (`RealSystemTask`,
`cls="logistics"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file module `geo_distance.py` defining one function
`distance_km(lat1, lon1, lat2, lon2)` computing the great-circle haversine distance in kilometers
using Earth radius `R = 6371.0`, returning the result rounded to 2 decimal places.

#### Acceptance Criteria
- [x] `HAVERSINE_DISTANCE_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      haversine contract (filename `geo_distance.py`, the function signature, the exact formula
      -- `math.radians` conversion, `a`/`c` intermediate terms, `R = 6371.0`, the round-to-2-
      decimal-places return contract) with every oracle-checked value derivable from that same
      visible sentence (no hidden key, no leak).
- [x] Three driven checks, every expected value hand-verified via independent recomputation with
      Python's own `math` module (not trusted blindly) before being added to the roster:
      `distance_km(0, 0, 0, 0) == 0.0`; `distance_km(0, 0, 0, 90) == 10007.54` (a quarter of the
      equator's circumference, `R * pi / 2`); `distance_km(52.2296, 21.0122, 52.4064, 16.9252) ==
      278.46` (Warsaw -> Poznan, the ACTUAL recomputed value -- not a naive round-to-nearest-int
      guess of 279). A build that never converts degrees to radians before calling `sin`/`cos`
      (a formula-domain bug) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `geo_distance.py` fixture is accepted by `grade_real_system_task(HAVERSINE_DISTANCE_TASK,
      ...)`; a BROKEN fixture that never converts degrees to radians is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-48/49/50/51
      tasks (length 34 -> 38).

### [REQ-52] Seventeenth CREATE task ("batch-5"), in a NEW fintech-calculator vertical (loan amortization)

A SEVENTEENTH held-out CREATE task ("batch-5"), in a NEW fintech vertical distinct from every prior
fintech task (a structured amortization SCHEDULE, not a ledger and not a single-number calculator),
graded by the ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `LOAN_AMORTIZATION_TASK`
(`RealSystemTask`, `cls="fintech"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file module `loan_amortization.py` defining one
function `schedule(principal, annual_rate, n_months)` computing a standard fixed-payment amortization
schedule entirely in integer cents, with the final month's principal set to exactly the remaining
balance so the schedule always lands on a `0` final balance.

#### Acceptance Criteria
- [x] `LOAN_AMORTIZATION_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      amortization contract (filename `loan_amortization.py`, the function signature, the integer-cents
      contract, the level-payment formula `M = round(principal * r / (1 - (1 + r) ** -n_months))`, the
      per-month interest/principal/balance derivation, and the FINAL-month override that zeroes the
      rounding residue) with every oracle-checked value derivable from that same visible sentence (no
      hidden key, no leak).
- [x] Two driven checks, every cents value hand-verified via an independent scratch Python walk of the
      exact same formula (not trusted blindly) before being added to the roster: `schedule(1200, 0.12,
      1) == [{"payment": 1212, "interest": 12, "principal": 1200, "balance": 0}]`; `schedule(120000,
      0.12, 3)` == the three-row schedule ending in `balance: 0` with principal columns summing to
      `120000`. A build that never special-cases the final month (reuses the level payment for every
      row) is caught: its final balance lands on `-1` cent instead of `0`.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `loan_amortization.py` fixture is accepted by `grade_real_system_task(LOAN_AMORTIZATION_TASK,
      ...)`; a BROKEN fixture that never zeroes the final rounding residue is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`.

### [REQ-53] Eighteenth CREATE task ("batch-5"), in a NEW analytics vertical (running median)

An EIGHTEENTH held-out CREATE task ("batch-5"), in a NEW analytics vertical, graded by the
ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `RUNNING_MEDIAN_TASK`
(`RealSystemTask`, `cls="analytics"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file module `running_median.py` defining one
function `running_medians(stream)` returning the running median after each element of `stream`
(the middle sorted value for an odd-length prefix, the true-division mean of the two middle sorted
values for an even-length prefix).

#### Acceptance Criteria
- [x] `RUNNING_MEDIAN_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the running-median
      contract (filename `running_median.py`, the function signature, the odd-length middle-value rule,
      the even-length true-division-mean rule, the same-length-as-input/no-mutation contract) with
      every oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] Three driven checks, every expected value hand-verified via an independent scratch Python walk
      (a plain sorted-insert simulation) before being added to the roster:
      `running_medians([5, 15, 1, 3]) == [5, 10.0, 5, 4.0]`; `running_medians([2, 4]) == [2, 3.0]`;
      `running_medians([7]) == [7]`. A build that returns the running MEAN instead of the running
      median is caught by the first vector (its 3rd/4th entries diverge: `7.0`/`6.0` vs. `5`/`4.0`).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `running_median.py` fixture is accepted by `grade_real_system_task(RUNNING_MEDIAN_TASK, ...)`; a
      BROKEN fixture that returns the running mean instead of the running median is rejected; the task
      is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-54] Nineteenth CREATE task ("batch-5"), in a NEW devops/SaaS vertical (incident escalation)

A NINETEENTH held-out CREATE task ("batch-5"), in a NEW devops/SaaS incident-management vertical,
graded by the ALREADY-LANDED `oracle_kind="state_machine"` dispatch REQ-13 lands (no new oracle code:
reuses `_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine` verbatim).
`INCIDENT_ESCALATION_TASK` (`RealSystemTask`, `cls="devops"`, `oracle_kind="state_machine"`) is added
to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file `Incident` class in
`incident_escalation.py` modeling an on-call incident's `"open"`/`"acknowledged"`/`"investigating"`/
`"resolved"`/`"closed"` lifecycle, with a `reopen()` action legal from EITHER `"resolved"` OR
`"closed"` (mirroring `JOB_QUEUE_LIFECYCLE_TASK`'s own two-source-state action shape on a distinct
vertical).

#### Acceptance Criteria
- [x] `INCIDENT_ESCALATION_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      five-state, five-action lifecycle contract (filename `incident_escalation.py`, the class name,
      the exact legal source state(s) per action -- including `reopen()`'s two legal sources -- the
      `ValueError`-on-illegal-transition-with-unchanged-state contract, and the `state` property) with
      every oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] THREE illegal transitions are driven and rejected, hand-verified via a scratch walk of the exact
      same transition table before being added to the roster: `resolve()` from `"open"` (skip-ahead),
      `close()` from `"open"` (skip-ahead), and `acknowledge()` from `"closed"` (already terminal) --
      proving the guard holds both before any legal op and after the incident has already reached its
      terminal state. The driven legal path lands on `expect_final == "closed"`.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. None of `acknowledge`/`investigate`/`resolve`/
      `close`/`reopen`/`incident`/`escalation` ever fingerprints a leaf keyword
      (`harness.adt_oracle._KEYWORDS`/`_METHOD_TOKENS` lists none of them) -- verified directly via
      `leaf_for_spec(...) is None`, not just a literal substring scan.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `Incident` fixture
      is accepted by `grade_real_system_task(INCIDENT_ESCALATION_TASK, ...)`; a BROKEN fixture that
      allows an illegal transition (e.g. `resolve()` from any state) is rejected; the task is a member
      of `REAL_SYSTEMS_TASKS`.

### [REQ-55] Twentieth CREATE task ("batch-5"), in a NEW logistics vertical (warehouse stock reservation)

A TWENTIETH held-out CREATE task ("batch-5"), in a NEW logistics/warehouse vertical, graded by the
ALREADY-LANDED `oracle_kind="conservation"` dispatch REQ-15 lands (no new oracle code: reuses
`_grade_conservation` -> `harness.conservation_oracle.grade_conservation` verbatim).
`WAREHOUSE_STOCK_RESERVATION_TASK` (`RealSystemTask`, `cls="logistics"`, `oracle_kind="conservation"`)
is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file
`StockReservation` class in `warehouse_stock_reservation.py` modeling `reserve(n)` (on_hand->reserved),
`unreserve(n)` (reserved->on_hand), and `ship(n)` (reserved->shipped), over a mirror-pair bookkeeping
of `on_hand`/`reserved`/`shipped` that always sums to `total_units`. Deliberately phrased with
"reservation"/"reserve"/"ship" throughout (never "hold"/"queue"/"cache"/"expire"/"stack"/"buffer"/
"ring") so no leaf keyword is ever fingerprinted.

#### Acceptance Criteria
- [x] `WAREHOUSE_STOCK_RESERVATION_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      three-quantity reserve/unreserve/ship contract (filename `warehouse_stock_reservation.py`, the
      class name, the constructor shape, the three reader methods, the exact deltas each action causes,
      the `ValueError`-on-over-reserve/over-ship-with-unchanged-quantities contract) with every
      oracle-checked value derivable from that same visible sentence (no hidden key, no leak).
- [x] TWO illegal ops are driven and rejected, hand-verified via a scratch walk of the exact same
      on_hand/reserved/shipped delta bookkeeping before being added to the roster: reserving MORE units
      than are currently on_hand, and shipping MORE units than are currently reserved (mid-sequence,
      after a partial ship has already moved the balance) -- proving the guard holds both at the very
      start and after legal ops have moved the balance. The full driven sequence lands on
      `expect_final == {"on_hand": 50, "reserved": 0, "shipped": 50}` (summing to the initial
      `total_units` of `100`).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. Verified directly via `leaf_for_spec(...) is None`,
      not just a literal substring scan.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT `StockReservation`
      fixture is accepted by `grade_real_system_task(WAREHOUSE_STOCK_RESERVATION_TASK, ...)`; a BROKEN
      fixture that allows an over-reserve (never checks `on_hand` before moving units to `reserved`) is
      rejected; the task is a member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the
      four REQ-52/53/54/55 tasks (length 38 -> 42).

### [REQ-56] Twenty-first CREATE task ("batch-6"), in a NEW devtools vertical (Roman-numeral codec)

A TWENTY-FIRST held-out CREATE task ("batch-6"), in a NEW devtools vertical, graded by the
ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `ROMAN_NUMERAL_CODEC_TASK`
(`RealSystemTask`, `cls="devtools"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file module `roman_numeral_codec.py` defining
`to_roman(n)` (1..3999 -> uppercase Roman numeral, SUBTRACTIVE notation pinned exactly, e.g. `"IV"`
never `"IIII"`) and `from_roman(s)` (the inverse), round-tripping.

#### Acceptance Criteria
- [x] `ROMAN_NUMERAL_CODEC_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the codec
      contract (filename `roman_numeral_codec.py`, both function signatures, the exact subtractive-
      notation rule for every four-and-nine place value) with every oracle-checked value derivable
      from that same visible sentence (no hidden key, no leak).
- [x] Seven driven checks, every expected value hand-verified via an independent scratch Python walk
      of the classical value/symbol table (not trusted blindly) before being added to the roster:
      `to_roman(4) == "IV"`; `to_roman(9) == "IX"`; `to_roman(58) == "LVIII"`; `to_roman(1994) ==
      "MCMXCIV"`; `to_roman(3999) == "MMMCMXCIX"`; `from_roman("MCMXCIV") == 1994`; a chained
      round-trip check (`from_roman` applied to the prior `to_roman_444` call's own result via a
      `__jaros_ref__`) equals `444`. A build using ADDITIVE-ONLY notation (no subtractive pairs, e.g.
      `to_roman(4) == "IIII"`) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `roman_numeral_codec.py` fixture is accepted by
      `grade_real_system_task(ROMAN_NUMERAL_CODEC_TASK, ...)`; a BROKEN fixture using additive-only
      notation is rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-57] Twenty-second CREATE task ("batch-6"), in a NEW fintech vertical (banker's rounding)

A TWENTY-SECOND held-out CREATE task ("batch-6"), in a NEW fintech vertical distinct from every
prior fintech task (a rounding PRIMITIVE, not a ledger/calculator/schedule), graded by the
ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `BANKERS_ROUNDING_TASK`
(`RealSystemTask`, `cls="fintech"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file module `bankers_rounding.py` defining one
function `round_half_even(x, ndigits=0)` implementing round-half-to-EVEN (banker's rounding), with
the exact convention (which of the two halfway candidates wins) spelled out in the sentence itself.

#### Acceptance Criteria
- [x] `BANKERS_ROUNDING_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully PINS the
      round-half-to-even convention in plain language (a value exactly halfway between two candidates
      rounds to whichever candidate has an EVEN final digit, never always-up or always-down), the
      `decimal.Decimal(str(x))` construction rule (never `decimal.Decimal(x)` directly, to avoid
      binary float representation error), and the int-vs-float return contract by `ndigits`.
- [x] Six driven checks, every expected value independently recomputed with
      `decimal.Decimal(str(x)).quantize(..., rounding=decimal.ROUND_HALF_EVEN)` (not trusted blindly),
      and every literal chosen to be EXACTLY representable in IEEE-754 binary (2.5, 3.5, 0.5, 1.5,
      0.125, 0.375 -- never an ambiguous literal like 2.675) so the class is unambiguous:
      `round_half_even(2.5) == 2`; `round_half_even(3.5) == 4`; `round_half_even(0.5) == 0`;
      `round_half_even(1.5) == 2`; `round_half_even(0.125, 2) == 0.12`; `round_half_even(0.375, 2) ==
      0.38`. A build using round-HALF-UP is caught (diverges on the 2.5/0.5/0.125 vectors).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `bankers_rounding.py` fixture is accepted by `grade_real_system_task(BANKERS_ROUNDING_TASK,
      ...)`; a BROKEN fixture using round-half-up is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-58] Twenty-third CREATE task ("batch-6"), in a NEW data-pipeline vertical (run-length codec)

A TWENTY-THIRD held-out CREATE task ("batch-6"), in a NEW data-pipeline/devtools vertical, graded
by the ALREADY-LANDED `oracle_kind="import"` dispatch REQ-3 lands (no new oracle code: reuses
`_grade_import` -> `harness.import_driver.drive_import` verbatim). `RUN_LENGTH_CODEC_TASK`
(`RealSystemTask`, `cls="data"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a
contract-exact sentence for a stdlib-only, single-file module `run_length_codec.py` defining
`encode(s)` (a `str` -> a list of `[character, count]` maximal-run pairs) and `decode(pairs)` (the
inverse), round-tripping.

#### Acceptance Criteria
- [x] `RUN_LENGTH_CODEC_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the codec
      contract (filename `run_length_codec.py`, both function signatures, the exact `[character,
      count]` pair shape, the MAXIMAL-run rule including that the FINAL run must never be dropped)
      with every oracle-checked value derivable from that same visible sentence (no hidden key, no
      leak).
- [x] Five driven checks, every expected value hand-verified via an independent scratch maximal-run
      walk (not trusted blindly) before being added to the roster: `encode("aaabbc") == [["a", 3],
      ["b", 2], ["c", 1]]`; `encode("") == []`; `encode("aaaa") == [["a", 4]]`; `decode([["a", 3],
      ["b", 2], ["c", 1]]) == "aaabbc"`; a chained round-trip check (`decode` applied to the prior
      `encode_mixed` call's own result via a `__jaros_ref__`) also equals `"aaabbc"`. A build that
      forgets to flush the FINAL run after its scan loop ends (dropping the trailing run) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `run_length_codec.py` fixture is accepted by `grade_real_system_task(RUN_LENGTH_CODEC_TASK,
      ...)`; a BROKEN fixture that drops the final run is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-59] Twenty-fourth CREATE task ("batch-6"), in a NEW fintech-billing vertical (penny allocation)

A TWENTY-FOURTH held-out CREATE task ("batch-6"), in a NEW fintech-billing vertical distinct from
every prior fintech task (a cent-exact proportional-SPLIT primitive, not a
ledger/calculator/schedule/rounding function), graded by the ALREADY-LANDED `oracle_kind="import"`
dispatch REQ-3 lands (no new oracle code: reuses `_grade_import` ->
`harness.import_driver.drive_import` verbatim). `PENNY_ALLOCATION_TASK` (`RealSystemTask`,
`cls="fintech"`, `oracle_kind="import"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence
for a stdlib-only, single-file module `penny_allocation.py` defining one function
`allocate(total_cents, weights)` splitting an integer cent amount proportionally by integer floor
division, with the leftover-remainder rule PINNED exactly: add 1 cent to each of the FIRST
`remainder` parts in index order (never the last parts, never a largest-fractional-remainder sort).

#### Acceptance Criteria
- [x] `PENNY_ALLOCATION_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      proportional-split contract (filename `penny_allocation.py`, the function signature, the
      integer-floor-division base-share formula `(total_cents * weights[i]) // sum(weights)`, and the
      EXACT remainder-distribution rule -- 1 cent to each of the FIRST `remainder` parts in index
      order) with every oracle-checked value derivable from that same visible sentence (no hidden key,
      no leak).
- [x] Four driven checks, every expected value independently recomputed via the exact pinned algorithm
      (not trusted blindly) before being added to the roster: `allocate(100, [1, 1, 1]) == [34, 33,
      33]`; `allocate(100, [1, 1]) == [50, 50]`; `allocate(1000, [7, 3]) == [700, 300]`; `allocate(5,
      [1, 1, 1]) == [2, 2, 1]`. A build that computes the base floor shares but never redistributes the
      leftover remainder (losing cents, e.g. `allocate(100, [1, 1, 1])` summing to only `99`) is
      caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `penny_allocation.py` fixture is accepted by `grade_real_system_task(PENNY_ALLOCATION_TASK,
      ...)`; a BROKEN fixture that never redistributes the remainder is rejected; the task is a member
      of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-56/57/58/59 tasks
      (length 42 -> 46).

### [REQ-60] Twenty-fifth CREATE task ("batch-7"), the batch's state_machine member, in a NEW embedded/devops vertical (elevator dispatch)

A TWENTY-FIFTH held-out CREATE task ("batch-7", picked for ORACLE-KIND DIVERSITY -- the roster had
grown heavy on `oracle_kind="import"` reusable-library tasks -- this is the batch's `state_machine`
member), in a NEW embedded/devops vertical, graded by the ALREADY-LANDED
`oracle_kind="state_machine"` dispatch REQ-13 lands (no new oracle code: reuses
`_grade_state_machine` -> `harness.state_machine_oracle.grade_state_machine` verbatim).
`ELEVATOR_DISPATCH_TASK` (`RealSystemTask`, `cls="embedded"`, `oracle_kind="state_machine"`) is
added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file module
`elevator_dispatch.py` defining `ElevatorController` -- a single elevator car's
idle/moving_up/moving_down/doors_open dispatch lifecycle, with an explicit manual `open()` action
legal only while parked, distinct from the automatic `arrive()`-triggered door-open after travel.

#### Acceptance Criteria
- [x] `ELEVATOR_DISPATCH_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      lifecycle contract (filename `elevator_dispatch.py`, the class name, the `state` property, all
      five action methods and their exact one legal source state each) with every oracle-checked
      value derivable from that same visible sentence (no hidden key, no leak).
- [x] A ten-step driven script, hand-walked against `spec['transitions']` before being added to the
      roster, exercising all three REQUIRED illegal cases (`open()` from a moving state, `call_up()`
      from `"doors_open"`, `arrive()` from `"idle"`) plus a fourth (`open()` from the other moving
      state), interleaved with the full legal up-trip and down-trip paths, landing on
      `expect_final="idle"`. A build that lets `open()` fire while the car is `"moving_up"` or
      `"moving_down"` (opening doors mid-travel) is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No banned leaf keyword (lru/priority-queue/
      ttl-store/fifo/ring-buffer fingerprints) appears in the sentence.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `elevator_dispatch.py` fixture is accepted by `grade_real_system_task(ELEVATOR_DISPATCH_TASK,
      ...)`; a BROKEN fixture whose `open()` never checks the current state (opens doors mid-travel)
      is rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-61] Twenty-sixth CREATE task ("batch-7"), the batch's conservation member, in a NEW hospitality/logistics vertical (hotel room inventory)

A TWENTY-SIXTH held-out CREATE task ("batch-7"), the batch's `conservation` member, in a NEW
hospitality/logistics vertical, graded by the ALREADY-LANDED `oracle_kind="conservation"` dispatch
REQ-15 lands (no new oracle code: reuses `_grade_conservation` ->
`harness.conservation_oracle.grade_conservation` verbatim). `HOTEL_ROOM_INVENTORY_TASK`
(`RealSystemTask`, `cls="hospitality"`, `oracle_kind="conservation"`) is added to
`REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only, single-file module
`hotel_room_inventory.py` defining `RoomInventory` -- a hotel property's
available/reserved/occupied room bookkeeping through a reserve/check-in/check-out/cancel workflow.
The sentence is deliberately phrased with "reserve"/"reserved"/"occupied"/"cancel" throughout
(never "hold"/"queue"/"cache"/"expire"/"stack"/"buffer"/"ring") so no leaf keyword
(`harness.adt_oracle._KEYWORDS`/`_METHOD_TOKENS`) is ever fingerprinted.

#### Acceptance Criteria
- [x] `HOTEL_ROOM_INVENTORY_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      conservation contract (filename `hotel_room_inventory.py`, the class name, the constructor,
      the three reader methods, the `available()+reserved()+occupied()==total_rooms` invariant, and
      all four action methods' exact legal-vs-illegal conditions) with every oracle-checked value
      derivable from that same visible sentence (no hidden key, no leak).
- [x] A six-op driven script, hand-verified via a scratch walk of the exact same mirror-pair
      bookkeeping before being added to the roster: illegal over-reserve (150 of 100 available) FIRST,
      then a legal `reserve(40)`, then illegal `check_in(50)` (only 40 reserved), then legal
      `check_in(30)`, `check_out(10)`, and `cancel(5)`, landing on
      `expect_final={"available": 75, "reserved": 5, "occupied": 20}` (sums to `total_rooms=100`
      throughout). A build that lets `reserve()` succeed beyond current `available` is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. No banned leaf keyword appears in the sentence,
      confirmed both by a literal substring scan and `leaf_for_spec(...) is None`.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `hotel_room_inventory.py` fixture is accepted by
      `grade_real_system_task(HOTEL_ROOM_INVENTORY_TASK, ...)`; a BROKEN fixture whose `reserve()`
      never checks `available` (allows an over-reserve) is rejected; the task is a member of
      `REAL_SYSTEMS_TASKS`.

### [REQ-62] Twenty-seventh CREATE task ("batch-7"), the batch's double_entry member, in a NEW fintech/HR vertical (payroll run)

A TWENTY-SEVENTH held-out CREATE task ("batch-7"), the batch's `double_entry` member, in a NEW
fintech/HR (payroll) vertical, graded by the ALREADY-LANDED `oracle_kind="double_entry"` dispatch
REQ-17 lands (no new oracle code: reuses `_grade_double_entry` ->
`harness.double_entry_oracle.grade_double_entry` verbatim). `PAYROLL_RUN_TASK` (`RealSystemTask`,
`cls="payroll"`, `oracle_kind="double_entry"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact
sentence for a stdlib-only, single-file module `payroll_ledger.py` defining `PayrollLedger` --
a double-entry ledger over `wage_expense`/`tax_payable`/`cash` posting payroll runs (gross wages
debited, withheld tax and net pay credited) plus a later tax remittance (tax_payable debited, cash
credited).

#### Acceptance Criteria
- [x] `PAYROLL_RUN_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the double-entry
      contract (filename `payroll_ledger.py`, the class name, the three account reader methods, the
      `post(legs)` signature and debit-ADDS/credit-SUBTRACTS convention, the balanced-vs-unbalanced
      accept/reject contract) with every oracle-checked value derivable from that same visible
      sentence (no hidden key, no leak).
- [x] A four-posting driven script, hand-verified via an independent debit-positive/credit-negative
      shadow-math walk before being added to the roster: an unbalanced entry FIRST (debits 500000,
      credits 490000 -- off by 10000 cents, must be rejected), then two balanced payroll runs
      ($5000.00 and $6000.00 gross) and one balanced tax remittance (270000 cents, the full amount
      accrued across both runs), landing on
      `expect_final={"wage_expense": 1100000, "tax_payable": 0, "cash": -1100000}`. A build that
      lets an unbalanced posting succeed is caught.
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `payroll_ledger.py` fixture is accepted by `grade_real_system_task(PAYROLL_RUN_TASK, ...)`; a
      BROKEN fixture whose `post()` never checks debits==credits (accepts an unbalanced posting) is
      rejected; the task is a member of `REAL_SYSTEMS_TASKS`.

### [REQ-63] Twenty-eighth CREATE task ("batch-7"), the batch's clock member, in a NEW saas/infra vertical (API rate limiter)

A TWENTY-EIGHTH held-out CREATE task ("batch-7"), the batch's `clock` member, in a NEW saas/infra
vertical, graded by the ALREADY-LANDED `oracle_kind="clock"` dispatch REQ-28 lands (no new oracle
code: reuses `_grade_clock` -> `harness.clock_oracle.grade_clock` verbatim). This completes
batch-7's ORACLE-KIND DIVERSITY goal -- one task per non-import oracle kind
(state_machine/conservation/double_entry/clock), across four distinct verticals, all reusing an
already-landed oracle. `TOKEN_BUCKET_RATE_LIMITER_TASK` (`RealSystemTask`, `cls="infra"`,
`oracle_kind="clock"`) is added to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
stdlib-only, single-file module `rate_limiter.py` defining `TokenBucket` -- a token-bucket API rate
limiter whose bucket refills continuously with injected elapsed time (never merely at fixed
checkpoints), distinct from the two prior clock tasks (both auth-vertical validity/lockout windows).

#### Acceptance Criteria
- [x] `TOKEN_BUCKET_RATE_LIMITER_TASK` is added to `REAL_SYSTEMS_TASKS`: the sentence fully pins the
      injected-clock contract (filename `rate_limiter.py`, the class name, the `now_fn` clock-param
      contract, the `capacity`/`refill_rate` constructor arguments, the exact refill-then-consume
      order of operations in `allow()`, and the capacity cap) with every oracle-checked value
      derivable from that same visible sentence (no hidden key, no leak).
- [x] A fifteen-step driven timeline (capacity=5, refill_rate=1 token/sec), hand-walked before being
      added to the roster: drain all 5 tokens at t=0 (5x `True`), the 6th `allow()` at t=0 fails
      (`False`); advance to t=2 (+2 tokens refilled) -> 2 more succeed, the 3rd at t=2 fails; advance
      to t=100 (98 simulated seconds' worth of refill, but capped at `capacity=5`, never exceeding
      it) -> exactly 5 more succeed (proving the cap held, not 98), the 6th at t=100 fails. A build
      that secretly calls the real wall clock instead of the injected `now_fn` is caught the same way
      REQ-28/34's own tasks are (the huge simulated jump from t=2 to t=100 executes in real
      milliseconds, so a real-clock-driven build cannot correctly report the refill).
- [x] Leaves-OFF enforced identically to every other task in this module (static `leaf_for_spec` +
      post-build `build_path` check, already automatic via the existing `_run_one_task` runner); a
      leaf-produced green is treated as a failure. The sentence says "contain"/"contains" (never
      "hold"/"holds") and avoids every other banned leaf-fingerprinting token.
- [x] Offline-testable (no real model/Jetson, hand-written fixtures only): a CORRECT
      `rate_limiter.py` fixture is accepted by
      `grade_real_system_task(TOKEN_BUCKET_RATE_LIMITER_TASK, ...)`; a BROKEN fixture that reads the
      real wall clock (`time.time()`) instead of the injected `now_fn` is rejected; the task is a
      member of `REAL_SYSTEMS_TASKS`; `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-60/61/62/63
      tasks (length 46 -> 50), covering all four non-import oracle kinds exactly once.
