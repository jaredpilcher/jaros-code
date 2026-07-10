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
