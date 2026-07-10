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
