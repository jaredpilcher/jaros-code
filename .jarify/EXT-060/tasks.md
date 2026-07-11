# Implementation Tasks

### [TASK-1] Suite scaffold + CSV→JSON ETL task wired to fs_oracle (REQ-1, REQ-2)

#### Steps
1. Create `harness/real_systems_suite.py` with a `RealSystemTask` dataclass (name, cls, sentence,
   oracle_kind, oracle_spec) and `run_real_systems_suite(tasks, llm)` that builds each via `build_system`,
   asserts the leaf path is OFF for the spec (no `leaf_for_spec` fingerprint), grades by the task's oracle,
   returns per-class pass@1.
2. Add the CSV→JSON group-by ETL `RealSystemTask` (contract-exact sentence) and wire its grading to
   `harness/fs_oracle.py` (seed a CSV tree, run the built entrypoint, byte-compare the output JSON file)
   plus an exact-stdout check variant where useful.
3. Add `tests/test_ext060_real_systems_suite.py` (OFFLINE, no Jetson): prove the fs_oracle grading catches
   a WRONG built stub (wrong grouping) and passes a CORRECT stub, and that the leaves-OFF assertion holds.
4. Update `.jarify/EXT-060/index.json` (REQ-1/REQ-2 ranges); flip `status` toward `partial`.

#### Implements
- [REQ-1] Suite scaffold + leaves-OFF pass@1 runner
- [REQ-2] CSV→JSON group-by ETL task graded by fs_oracle

### [TASK-2] Retry/backoff library task wired to import_driver (REQ-3)

#### Steps
1. In `harness/real_systems_suite.py`, add a `RETRY_BACKOFF_LIB_TASK` `RealSystemTask` (oracle_kind
   'import') with a contract-exact sentence for a single-file `retry.py` exporting `retry(times,
   exceptions=Exception)`; add `'import'` dispatch in `grade_real_system_task`/`_grade_*` that wires
   `harness/import_driver.py` (`drive_import`): import the built module, apply the decorator to a
   fail-then-succeed callable with an injected sleep, assert retry-count + eventual success + no real sleep.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks) + leak-free.
3. Extend `tests/test_ext060_real_systems_suite.py` (OFFLINE, no Jetson): hand-authored CORRECT retry.py
   stub passes the import_driver grading; a WRONG one (wrong count / gives up early) fails; leaves-OFF holds.
4. Run `python -m pytest tests/test_ext060_real_systems_suite.py tests/test_ext059_import_driver.py -q`;
   confirm green. Update `.jarify/EXT-060/index.json` (REQ-3 ranges) + check REQ-3 boxes.

#### Implements
- [REQ-3] Retry/backoff decorator library task graded by import_driver

### [TASK-3] INI-section config-query CLI task wired to the existing cli-exact oracle (REQ-4)

#### Steps
1. In `harness/real_systems_suite.py`, add `INI_SECTION_QUERY_TASK` (a `RealSystemTask`, `oracle_kind
   ="cli-exact"`) with a contract-exact sentence for a single-file `main.py` that reads an INI-format
   config file from standard input and takes exactly two command-line arguments (a section name, then
   a key name), prints the value of that key inside that section followed by a single trailing
   newline and nothing else, or prints nothing and exits nonzero if the section or key is absent.
   Wire it via the EXISTING cli-exact grading path (`_grade_cli_exact` / `_run_check_variant`'s
   `exact_stdout` check) -- no new oracle code.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as the other tasks --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (the oracle-chosen argv/stdin/
   expected_stdout values are all derivable from the visible sentence contract).
3. Add `tests/test_ext060_ini_query.py` (OFFLINE, no Jetson): a hand-authored CORRECT `main.py` stub
   passes the cli-exact grading; a WRONG one (wrong value or extra output) fails.
4. Run `python -m pytest tests/test_ext060_ini_query.py tests/test_ext060*.py -q`; confirm green.
   Update `.jarify/EXT-060/index.json` (REQ-4 ranges) + check REQ-4 boxes in requirements.md.

#### Implements
- [REQ-4] INI-section config-query CLI task graded by the existing cli-exact oracle

### [TASK-4] Memoize/cache decorator library task wired to the existing import_driver oracle (REQ-5)

#### Steps
1. In `harness/real_systems_suite.py`, add `MEMOIZE_LIB_TASK` (a `RealSystemTask`, `oracle_kind
   ="import"`) with a contract-exact sentence for a single-file `memoize.py` module exporting
   exactly one public function `memoize(maxsize=128)` that returns a decorator; the decorated
   callable caches its return value keyed by the tuple of positional arguments it is called with
   (a repeated call with the SAME arguments returns the cached value without re-invoking the
   wrapped callable; a call with NEW arguments does invoke it). Wire it via the ALREADY-LANDED
   `"import"` oracle dispatch (`_grade_import` -> `harness/import_driver.py`'s `drive_import`) --
   no new oracle code. The oracle's `api_calls` chain calls `memoize()` with NO arguments (relying
   entirely on the `maxsize=128` default) to also exercise the EXT-036 REQ-45 signature-contract-
   default repair on this second library class.
2. Add it to `REAL_SYSTEMS_TASKS` (append after the existing INI task, outside any existing
   REQ-tagged block). Keep leaves-OFF enforced (same two checks as the other tasks -- static
   `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value is
   derivable from the visible sentence contract).
3. Add `tests/test_ext060_memoize.py` (OFFLINE, no Jetson/model): a hand-authored CORRECT
   `memoize.py` stub passes the import_driver grading; a WRONG stub (never caches -- always calls
   through) is caught; leaves-OFF holds (`leaf_for_spec` returns `None` for the sentence); the
   task is a member of `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_memoize.py tests/test_ext060*.py -q`; confirm green.
   Update `.jarify/EXT-060/index.json` (REQ-5 ranges) + check REQ-5 boxes in requirements.md.

#### Implements
- [REQ-5] Memoize/cache decorator library task graded by the existing import_driver oracle

### [TASK-5] File-organizer-by-extension CLI task wired to the existing fs oracle (REQ-6)

#### Steps
1. In `harness/real_systems_suite.py`, add `FILE_ORGANIZER_TASK` (a `RealSystemTask`, `oracle_kind
   ="fs"`) with a contract-exact sentence for a single-file `main.py` program that takes one
   command-line argument (a directory path) and, for every regular file directly inside that
   directory (never recursing into subdirectories), moves it into a subdirectory of that same
   directory named after the file's lowercased extension without the leading dot (preserving the
   file's own name/case), or into a subdirectory named `noext` when the file has no extension; it
   prints nothing on success and exits 0. Wire it via the ALREADY-LANDED `"fs"` oracle dispatch
   (`_grade_fs` -> `harness/fs_oracle.py`'s `seed_tree` + `run_and_inspect`) -- no new oracle code.
   Seed a subdirectory containing files with a lowercase extension, an uppercase extension, another
   extension, and no extension; `argv` passes that seeded subdirectory's path; `checks` assert each
   file landed at its expected per-extension (or `noext`) path with unchanged bytes AND that the
   original path is now absent.
2. Add it to `REAL_SYSTEMS_TASKS` (append after the existing memoize task, outside any existing
   REQ-tagged block). Keep leaves-OFF enforced (same two checks as the other tasks -- static
   `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen path is
   derivable from the visible sentence contract).
3. Add `tests/test_ext060_file_organizer.py` (OFFLINE, no Jetson/model): a hand-authored CORRECT
   `main.py` stub passes the fs-oracle grading; a WRONG stub (e.g. does not lowercase the
   extension directory, or recurses into subdirectories, or leaves the originals in place) is
   caught; leaves-OFF holds (`leaf_for_spec` returns `None` for the sentence); the task is a
   member of `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_file_organizer.py tests/test_ext060*.py -q`; confirm
   green. Update `.jarify/EXT-060/index.json` (REQ-6 ranges) + check REQ-6 boxes in
   requirements.md.

#### Implements
- [REQ-6] File-organizer-by-extension CLI task graded by the existing fs oracle

### [TASK-6] MODIFY half wired to modify_system + the existing independent oracles (REQ-7)

#### Steps
1. In `harness/real_systems_suite.py`, add a `RealSystemModifyTask` dataclass (name, cls,
   start_system: dict, mod_sentence: str, oracle_kind: str, oracle_spec: dict) and a
   `run_real_systems_modify_suite(tasks=None, *, llm=None, python_exe=None) -> dict` runner
   that, per task in an isolated temp root: (a) statically asserts `leaf_for_spec(task.
   mod_sentence) is None` (leaves-OFF, scored a failure without calling the model if it
   fires); (b) calls `harness.system_builder.modify_system(dict(task.start_system), task.
   mod_sentence, root, llm=llm)`; (c) when `applied` is True, grades the resulting tree via
   the EXISTING `grade_real_system_task(task, root, python_exe=python_exe)` dispatcher
   (duck-typed -- no new oracle code, no `RealSystemTask` wrapping needed); (d) never raises,
   returns the same `{"results": [...], "aggregate": {...}}` shape as
   `run_real_systems_suite` (reuse the existing `_rates`/`_aggregate` helpers).
2. Add `RETRY_BASE_DELAY_MODIFY_TASK` (oracle_kind `"import"`): `start_system` = a
   hand-authored correct baseline `retry.py` (matching the original REQ-3 contract:
   `retry(times, exceptions=Exception)`), `mod_sentence` asks for an added optional
   `base_delay=0.1` keyword parameter used as the sleep duration between attempts,
   `oracle_spec` reuses the SAME check kinds as `RETRY_BACKOFF_LIB_TASK`'s oracle_spec
   (`returns_equals`/`call_count`/`expected_sleep_calls`) but with an `api_call` that
   explicitly passes `base_delay` (e.g. `{"times": 3, "base_delay": 0.05}`) to `retry(...)`
   so an unmodified/incorrect module (that doesn't accept the new kwarg) is caught via the
   resulting call-chain exception cascade.
3. Add `INI_DEFAULT_FLAG_MODIFY_TASK` (oracle_kind `"cli-exact"`): `start_system` = a
   hand-authored correct baseline `main.py` (matching the original REQ-4 INI-section-query
   contract), `mod_sentence` asks for an added optional `--default VALUE` fallback (invoked
   as `python main.py <section> <key> --default VALUE`) that prints VALUE + newline and
   exits 0 when the section/key is absent (existing 2-arg behavior unchanged when
   `--default` is not supplied), `oracle_spec` picks an absent key with `--default` supplied
   and pins the exact expected stdout.
4. Add both tasks to a new `REAL_SYSTEMS_MODIFY_TASKS` list (module-level, alongside the
   existing `REAL_SYSTEMS_TASKS`).
5. Add `tests/test_ext060_modify_suite.py` (OFFLINE, no Jetson/model): for EACH of the 2
   modify tasks, hand-write a CORRECT post-modification module and assert
   `grade_real_system_task` accepts it against a temp root seeded with that module;
   hand-write a WRONG one (doesn't implement the change) and assert it's rejected; assert
   `leaf_for_spec(task.mod_sentence) is None` for both tasks (leaves-OFF holds); assert both
   tasks are members of `REAL_SYSTEMS_MODIFY_TASKS`. Also add ONE test that drives
   `run_real_systems_modify_suite` end-to-end with a stub llm (same
   `.complete(LlmRequest)->.text` canned-response convention as
   `tests/test_ext036_modify.py`'s `_CannedModifyLlm`, routed by the "MODIFICATION
   TARGET"/"APPLY MODIFICATION"/"SYNTAX ERROR"/"ACCEPTANCE CHECKS" prompt-substring
   convention) that returns the CORRECT post-modification module content, and assert the
   suite reports `accepted=True` for that task.
6. Run `python -m pytest tests/test_ext060_modify_suite.py tests/test_ext060*.py -q`;
   confirm green. Update `.jarify/EXT-060/index.json` (REQ-7 ranges, via
   `jarify-manage-links`) + the REQ-7 acceptance boxes are already checked in
   requirements.md (jarify-manage-specs pass already did this).

#### Implements
- [REQ-7] MODIFY half: RealSystemModifyTask + run_real_systems_modify_suite, leaves-OFF, independent-oracle-graded

### [TASK-7] Unified canonical scoreboard runner (REQ-8)

#### Steps
1. In `harness/real_systems_suite.py`, add `run_canonical_scoreboard(*, llm=None,
   create_tasks=None, modify_tasks=None, python_exe=None) -> dict` that calls
   `run_real_systems_suite(create_tasks, llm=llm, python_exe=python_exe)` and
   `run_real_systems_modify_suite(modify_tasks, llm=llm, python_exe=python_exe)`, and
   returns `{"create": <create suite result>, "modify": <modify suite result>, "combined":
   {"n": int, "passed": int, "pass_rate": float}}` where combined n/passed/pass_rate are
   computed from both halves' results lists (division-by-zero guarded -- pass_rate 0.0 when
   n==0). Never raises.
2. Add a killable canonical runner script `.jaros-data/realsys_canonical.py` that reuses
   (imports, does not duplicate) `.jaros-data/realsys_build_one.py`'s per-task subprocess
   pattern for BOTH the CREATE tasks (`REAL_SYSTEMS_TASKS`) and the new MODIFY tasks
   (`REAL_SYSTEMS_MODIFY_TASKS`) -- add a sibling `.jaros-data/realsys_modify_one.py`
   (mirrors `realsys_build_one.py` but drives `run_real_systems_modify_suite` for one named
   modify task) for the modify side's per-task subprocess isolation -- with the same
   per-task wall-clock kill (`taskkill /F /T`) as `.jaros-data/realsys_killable.py`, and
   prints the single headline "CANONICAL real-systems: create X/A, modify Y/B, total
   (X+Y)/(A+B)" at the end.
3. Add `tests/test_ext060_canonical_scoreboard.py` (OFFLINE, no Jetson/model): monkeypatching
   `run_real_systems_suite`/`run_real_systems_modify_suite` with fake per-task results proves
   `run_canonical_scoreboard`'s aggregation arithmetic is correct (combined
   n/passed/pass_rate match the two halves' totals) including the empty-halves
   division-by-zero-guarded case.
4. Run `python -m pytest tests/test_ext060_canonical_scoreboard.py tests/test_ext060*.py -q`;
   confirm green. Update `.jarify/EXT-060/index.json` (REQ-8 ranges, via
   `jarify-manage-links`).

#### Implements
- [REQ-8] Unified canonical scoreboard runner

### [TASK-8] `oracle_kind="service"` + first REST/SQLite CRUD CREATE+MODIFY tasks (REQ-9, REQ-10)

#### Steps
1. In `harness/server_oracle.py`'s `_do_request`, add support for an optional `json_body` key on the
   `http_check` dict: when present, `json.dumps` it to bytes and pass it as the request `data=` with a
   `Content-Type: application/json` header on the `urllib.request.Request(...)` call; when absent,
   build the request exactly as before (`data=None`, no extra headers) so every existing caller of
   `serve_and_check_stdlib`/`_check_one` is byte-identical. Update the module's docstrings to mention
   the new key.
2. In `harness/real_systems_suite.py`, import `serve_and_check_stdlib` from `harness.server_oracle`,
   `detect_sqlite_datastore`/`count_all_rows` from `harness.datastore_oracle`, and stdlib `sqlite3`.
   Add `_grade_service(oracle_spec, root, python_exe)` that (a) calls `serve_and_check_stdlib(root,
   oracle_spec.get("entry", "main.py"), oracle_spec.get("http_checks") or [], startup_timeout=...,
   request_timeout=...)`, requiring `ok=True`; (b) when `oracle_spec.get("db")` is present, AFTER
   `serve_and_check_stdlib` has returned (server already torn down), opens a FRESH `sqlite3` connection
   to the declared/detected `.db` file and asserts the row count (schema-agnostic via `count_all_rows`,
   or against a named `table` when given) meets `min_rows`; never raises, mirrors every other `_grade_*`
   helper's `(accepted, note)` return shape. Wire `oracle_kind == "service"` into
   `grade_real_system_task`'s dispatch.
3. Add `REST_SQLITE_CRUD_TASK` (`RealSystemTask`, `oracle_kind="service"`) to `REAL_SYSTEMS_TASKS`: the
   contract-exact stdlib REST/SQLite CRUD sentence (filename `main.py`, `PORT` env var, `data.db`
   SQLite file created if missing, `items` resource with autoincrement integer `id` + string `name`,
   `POST`/`GET`/`GET <id>`/`DELETE <id>` semantics + status codes, persists across restarts).
   `oracle_spec.http_checks` drives two `POST`s (so an item survives the later `DELETE`, keeping the
   independent db assertion honestly satisfiable), a `GET` list, a `GET` single item, a `DELETE`, and a
   post-delete `GET` 404; `oracle_spec.db` asserts `>=1` row in `data.db` after the full sequence.
4. Add `REST_SQLITE_ADD_UPDATE_MODIFY` (`RealSystemModifyTask`, `oracle_kind="service"`) to
   `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored correct baseline CRUD `main.py`
   (matching TASK-8 step 3's original contract, no `PUT`); `mod_sentence` asks for an added `PUT
   /items/<id>` endpoint (JSON body `{"name": ...}`, 200 + updated item JSON, 404 when absent).
   `oracle_spec.http_checks` seed two items, exercise the new `PUT` (including a `PUT` on a
   subsequently-deleted id, asserting 404), and regress the existing `POST`/`GET`/`DELETE`/404
   behavior; `oracle_spec.db` asserts the surviving item's row.
5. Add `tests/test_ext060_service_oracle.py` (OFFLINE, no model/Jetson — hand-written fixture services
   only): (a) a CORRECT stdlib items service fixture passes `grade_real_system_task` for
   `REST_SQLITE_CRUD_TASK`-shaped input, including the independent db assertion; (b) WRONG fixtures
   (doesn't persist to sqlite / wrong status code / missing `DELETE`) are rejected; (c) the service
   oracle never raises on a crashing/never-binding fixture; (d) a correct post-modify fixture (baseline
   + `PUT`) is accepted by `REST_SQLITE_ADD_UPDATE_MODIFY`'s checks and the unmodified baseline is
   rejected; (e) both tasks are members of their respective lists and `leaf_for_spec` returns `None`
   for both sentences. Also add `tests/test_ext036_server_oracle_stdlib.py`-style regression coverage
   (or extend that file minimally) proving an `http_check` WITHOUT `json_body` still behaves exactly as
   before the extension.
6. Run `python -m pytest tests/test_ext060_service_oracle.py tests/test_ext060_real_systems_suite.py
   tests/test_ext036_server_oracle_stdlib.py -q`; confirm green (offline only — do not run the full
   suite). Update `.jarify/EXT-060/index.json` (REQ-9/REQ-10 ranges, via `jarify-manage-links`) and flip
   the REQ-9/REQ-10 acceptance boxes + `status` toward `covered` if both requirements are fully met.

#### Implements
- [REQ-9] `oracle_kind="service"` + first REST/SQLite CRUD service CREATE task (the first SaaS rung)
- [REQ-10] First REST/SQLite CRUD MODIFY task (add a `PUT` endpoint)

### [TASK-9] `oracle_kind="agent"` + first plain-Python AGENT-SYSTEM CREATE+MODIFY tasks (REQ-11, REQ-12)

#### Steps
1. In `harness/real_systems_suite.py`, import `drive_agent`/`check_agent` from
   `harness.agent_oracle`. Add `_grade_agent(oracle_spec, root, python_exe)` that maps
   `oracle_spec` (`{"entry", "script", "tools", "goal", "expect_tool_calls",
   "expect_final_contains", "expect_terminated"}` plus optional `max_steps`/`timeout`
   passthrough) to `drive_agent(root, oracle_spec["entry"], script=..., tools=..., goal=...,
   python_exe=python_exe, ...)` then `check_agent(result, expect_tool_calls=...,
   expect_final_contains=..., expect_terminated=...)`, returning `(accepted, note)`; never
   raises. Wire `oracle_kind == "agent"` into `grade_real_system_task`'s dispatch.
2. Add `PLAIN_AGENT_TASK` (`RealSystemTask`, `cls="agent"`, `oracle_kind="agent"`) to
   `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only single-file plain-Python
   agent `main.py` implementing the `agent_oracle` protocol (`OPENAI_BASE_URL` chat-completions
   POST, `sys.argv[1]` goal, `JAROS_TOOL_URL/<tool>` tool-call POST feeding the returned
   `"observation"` back into the loop, `__JAROS_AGENT_FINAL__<content>__END__` sentinel + exit
   0). `oracle_spec`: a `script` of 2 tool_call turns then a final turn, `tools` returning
   canned observations, a `goal`, `expect_tool_calls` = those 2 in order, `expect_final_contains`
   = a substring of the final.
3. Add `AGENT_ADD_STEP_GUARD_MODIFY` (`RealSystemModifyTask`, `cls="agent-modify"`,
   `oracle_kind="agent"`) to `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` = a hand-authored
   CORRECT baseline agent (matching `PLAIN_AGENT_TASK`'s contract, no step guard); `mod_sentence`
   asks for an added maximum-N-tool-calls-without-a-final-answer guard that prints the final
   marker with a gave-up message and exits 0; `oracle_spec`'s `script` is all tool_call turns (no
   final turn) scripted past N so an UNGUARDED baseline never terminates (`accepted=False`) and a
   GUARDED agent terminates cleanly (`accepted=True`).
4. Add `tests/test_ext060_agent_task.py` (OFFLINE, no model/Jetson, hand-written agent fixtures
   only): (a) a CORRECT plain-Python agent fixture ->
   `grade_real_system_task(PLAIN_AGENT_TASK, root, python_exe=...)` accepted True; (b) a BROKEN
   fixture (ignores the tool observation / never terminates / wrong tool) -> accepted False; (c)
   leaves-OFF (`leaf_for_spec(PLAIN_AGENT_TASK.sentence) is None`) + `PLAIN_AGENT_TASK` is a
   member of `REAL_SYSTEMS_TASKS`; (d) the MODIFY task's oracle accepts a hand-written guarded
   agent fixture and rejects a hand-written unguarded one, and `AGENT_ADD_STEP_GUARD_MODIFY` is a
   member of `REAL_SYSTEMS_MODIFY_TASKS` with `leaf_for_spec(mod_sentence) is None`.
5. Run `python -m pytest tests/test_ext060_agent_task.py tests/test_ext060_real_systems_suite.py
   -q`; confirm green (offline only -- do not run the full suite). Update
   `.jarify/EXT-060/index.json` (REQ-11/REQ-12 ranges, via `jarify-manage-links`) and flip the
   REQ-11/REQ-12 acceptance boxes + `status` toward `covered` if both requirements are fully met.

#### Implements
- [REQ-11] `oracle_kind="agent"` + first plain-Python AGENT-SYSTEM CREATE task
- [REQ-12] First AGENT-SYSTEM MODIFY task: add a maximum-steps guard

### [TASK-10] `oracle_kind="state_machine"` + first LIFECYCLE CREATE+MODIFY tasks (REQ-13, REQ-14)

#### Steps
1. In `harness/real_systems_suite.py`, import `grade_state_machine` from
   `harness.state_machine_oracle`. Add `_grade_state_machine(oracle_spec, root, python_exe)` that
   maps `oracle_spec` (`{"module": str, "entity": str, "spec": {...state-machine spec shape...}}`)
   to `grade_state_machine(root, module=oracle_spec["module"], entity=oracle_spec["entity"],
   spec=oracle_spec["spec"], python_exe=python_exe)`, returning `(accepted, note)`; never raises.
   Wire `oracle_kind == "state_machine"` into `grade_real_system_task`'s dispatch.
2. Add `ORDER_LIFECYCLE_TASK` (`RealSystemTask`, `cls="lifecycle"`, `oracle_kind="state_machine"`)
   to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only single-file `Order` class in
   `order.py` (states `created`/`paid`/`shipped`/`delivered`/`cancelled`,
   `pay()`/`ship()`/`deliver()`/`cancel()`, a real `state` property, `ValueError` raised on any
   illegal transition with state left unchanged). `oracle_spec.spec` drives: `ship` from `created`
   (reject), `pay` (accept -> `paid`), `ship` (accept -> `shipped`), `deliver` (accept ->
   `delivered`), `cancel` from `delivered` (reject); `expect_final="delivered"`.
3. Add `ORDER_ADD_REFUND_MODIFY` (`RealSystemModifyTask`, `cls="lifecycle-modify"`,
   `oracle_kind="state_machine"`) to `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored
   CORRECT baseline `Order` matching step 2's contract exactly (no `refund()`); `mod_sentence` asks
   for an added `refund()` transition legal ONLY from `delivered` (moving to a new `refunded`
   state) and illegal (raising `ValueError`, state unchanged) from every other state.
   `oracle_spec.spec`'s `states`/`transitions` are extended with `refunded` + the `delivered:refund`
   transition; the drive script walks the full legal path to `delivered`, then exercises the legal
   `refund` (accept -> `refunded`), plus regresses an illegal `refund` attempted from an earlier
   state (e.g. `paid`) in a SEPARATE drive entry, and regresses the original illegal
   `ship`-before-`pay` check.
4. Add `tests/test_ext060_lifecycle_inventory.py` (OFFLINE, no model/Jetson, hand-written fixtures
   only): (a) a CORRECT `Order` fixture is accepted by
   `grade_real_system_task(ORDER_LIFECYCLE_TASK, ...)`; (b) a BROKEN fixture (an illegal transition
   allowed, e.g. unguarded `ship()`) is rejected; (c) leaves-OFF
   (`leaf_for_spec(ORDER_LIFECYCLE_TASK.sentence) is None`) + the task is a member of
   `REAL_SYSTEMS_TASKS`; (d) the MODIFY task's oracle accepts a hand-written CORRECT
   guarded-`refund()` fixture and rejects both the unmodified baseline (no `refund()`) and an
   UNGUARDED `refund()` fixture (legal from any state); `ORDER_ADD_REFUND_MODIFY` is a member of
   `REAL_SYSTEMS_MODIFY_TASKS` with `leaf_for_spec(mod_sentence) is None`.
5. Run `python -m pytest tests/test_ext060_lifecycle_inventory.py
   tests/test_ext060_real_systems_suite.py -q`; confirm green (offline only -- do not run the full
   suite). Update `.jarify/EXT-060/index.json` (REQ-13/REQ-14 ranges, via `jarify-manage-links`) and
   flip the REQ-13/REQ-14 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-13] `oracle_kind="state_machine"` + first LIFECYCLE CREATE task (order state machine)
- [REQ-14] First LIFECYCLE MODIFY task: add a `refund()` transition

### [TASK-11] `oracle_kind="conservation"` + first INVENTORY CREATE+MODIFY tasks (REQ-15, REQ-16)

#### Steps
1. In `harness/real_systems_suite.py`, import `grade_conservation` from
   `harness.conservation_oracle`. Add `_grade_conservation(oracle_spec, root, python_exe)` that maps
   `oracle_spec` (`{"module": str, "entity": str, "spec": {...conservation spec shape...}}`) to
   `grade_conservation(root, module=oracle_spec["module"], entity=oracle_spec["entity"],
   spec=oracle_spec["spec"], python_exe=python_exe)`, returning `(accepted, note)`; never raises.
   Wire `oracle_kind == "conservation"` into `grade_real_system_task`'s dispatch.
2. Add `INVENTORY_TASK` (`RealSystemTask`, `cls="inventory"`, `oracle_kind="conservation"`) to
   `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a stdlib-only single-file `Inventory` class in
   `inventory.py` (constructor takes an initial per-SKU stock count, `reserve(qty)`/`release(qty)`
   methods, zero-argument `available()`/`reserved()` readers, `reserve(qty)` raising `ValueError`
   with quantities left unchanged when `qty` exceeds what is available, units conserved).
   `oracle_spec.spec` drives an illegal oversell `reserve` (reject), then a legal `reserve` and a
   legal `release` each with declared per-quantity `deltas`, ending on a concrete `expect_final`.
3. Add `INVENTORY_ADD_BACKORDER_MODIFY` (`RealSystemModifyTask`, `cls="inventory-modify"`,
   `oracle_kind="conservation"`) to `REAL_SYSTEMS_MODIFY_TASKS`: `start_system` is a hand-authored
   CORRECT baseline `Inventory` matching step 2's contract exactly (no `backorder()`);
   `mod_sentence` asks for an added `backorder(qty)` method that records demand beyond available
   WITHOUT ever mutating `available`/`reserved`, exposing the recorded demand via a new
   zero-argument reader (e.g. `backordered()`). `oracle_spec.spec["quantities"]` is extended with
   that new backorder-demand quantity; a `backorder()` op's `deltas` entry touches ONLY the new
   quantity (never `available`/`reserved`), so the conservation oracle's own per-op
   reader-vs-shadow check independently proves the addition leaves `available`/`reserved`
   conservation undisturbed while still recording backorder growth.
4. Extend `tests/test_ext060_lifecycle_inventory.py` (same file TASK-10 creates, OFFLINE, no
   model/Jetson): (a) a CORRECT `Inventory` fixture is accepted by
   `grade_real_system_task(INVENTORY_TASK, ...)`; (b) a BROKEN fixture (allows an oversell, e.g.
   unguarded `reserve()`) is rejected; (c) leaves-OFF
   (`leaf_for_spec(INVENTORY_TASK.sentence) is None`) + the task is a member of
   `REAL_SYSTEMS_TASKS`; (d) the MODIFY task's oracle accepts a hand-written CORRECT `backorder()`
   fixture and rejects both the unmodified baseline (no `backorder()`) and a fixture whose
   `backorder()` incorrectly mutates `available`/`reserved`; `INVENTORY_ADD_BACKORDER_MODIFY` is a
   member of `REAL_SYSTEMS_MODIFY_TASKS` with `leaf_for_spec(mod_sentence) is None`.
5. Run `python -m pytest tests/test_ext060_lifecycle_inventory.py
   tests/test_ext060_real_systems_suite.py -q`; confirm green (offline only -- do not run the full
   suite). Update `.jarify/EXT-060/index.json` (REQ-15/REQ-16 ranges, via `jarify-manage-links`) and
   flip the REQ-15/REQ-16 acceptance boxes + `status` toward `covered` if REQ-13 through REQ-16 are
   all fully met.

#### Implements
- [REQ-15] `oracle_kind="conservation"` + first INVENTORY CREATE task (no-oversell reservation)
- [REQ-16] First INVENTORY MODIFY task: add a non-oversell-safe `backorder()`

### [TASK-12] `oracle_kind="double_entry"` + first FINTECH-LEDGER CREATE task (REQ-17)

#### Steps
1. In `harness/real_systems_suite.py`, import `grade_double_entry` from
   `harness.double_entry_oracle`. Add `_grade_double_entry(oracle_spec, root, python_exe)` that
   maps `oracle_spec` (`{"module": str, "entity": str, "spec": {...double-entry spec shape...}}`)
   to `grade_double_entry(root, module=oracle_spec["module"], entity=oracle_spec["entity"],
   spec=oracle_spec["spec"], python_exe=python_exe)`, returning `(accepted, note)`; never raises.
   Wire `oracle_kind == "double_entry"` into `grade_real_system_task`'s dispatch.
2. Add `DOUBLE_ENTRY_LEDGER_TASK` (`RealSystemTask`, `cls="ledger"`,
   `oracle_kind="double_entry"`) to `REAL_SYSTEMS_TASKS`: a contract-exact sentence for a
   stdlib-only single-file `Ledger` class in `ledger.py` over three named accounts (`cash`,
   `revenue`, `expense`), zero-argument `cash()`/`revenue()`/`expense()` readers, and a
   `post(legs)` method applying a balanced list of debit/credit legs (debit adds, credit
   subtracts) to each account's exact-integer-cents balance, raising `ValueError` with every
   balance left unchanged when the legs are unbalanced. `oracle_spec.spec` drives an illegal
   unbalanced posting (reject) first, then three legal balanced postings touching all three
   accounts, ending on a concrete `expect_final`.
3. Add `tests/test_ext060_double_entry_task.py` (OFFLINE, no model/Jetson, hand-written fixtures
   only): (a) a CORRECT `Ledger` fixture is accepted by
   `grade_real_system_task(DOUBLE_ENTRY_LEDGER_TASK, ...)`; (b) a BROKEN fixture (posts an
   unbalanced entry with no guard) is rejected; (c) leaves-OFF
   (`leaf_for_spec(DOUBLE_ENTRY_LEDGER_TASK.sentence) is None`) + the task is a member of
   `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_double_entry_task.py tests/test_ext060_real_systems_suite.py
   tests/test_ext060_lifecycle_inventory.py -q`; confirm green (offline only -- do not run the
   full suite). Update `.jarify/EXT-060/index.json` (REQ-17 ranges, via `jarify-manage-links`) and
   flip the REQ-17 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-17] `oracle_kind="double_entry"` + first FINTECH-LEDGER CREATE task (double-entry balance)

### [TASK-13] Second LIFECYCLE CREATE task, in a NEW SaaS-billing vertical (subscription state machine) (REQ-18)

#### Steps
1. In `harness/real_systems_suite.py`, add `SUBSCRIPTION_LIFECYCLE_TASK` (`RealSystemTask`,
   `cls="subscription"`, `oracle_kind="state_machine"`) with a contract-exact sentence for a
   stdlib-only single-file `Subscription` class in `subscription.py` (states `trialing`/`active`/
   `past_due`/`canceled`/`expired`, action methods `activate()`/`payment_failed()`/`recover()`/
   `cancel()`/`lapse()`, a real `state` property, `ValueError` raised on any illegal transition
   with state left unchanged). Reuse the ALREADY-LANDED `_grade_state_machine` dispatch (REQ-13) --
   no new oracle code. `oracle_spec.spec` drives: `cancel` from `trialing` (reject), `activate`
   (accept -> `active`), `payment_failed` (accept -> `past_due`), `recover` (accept -> `active`),
   `cancel` (accept -> `canceled`), `lapse` from `canceled` (reject); `expect_final="canceled"`.
   Name the trial-lapse action `lapse()`, NOT `expire()`/`expiry` -- those tokens trip
   `harness.adt_oracle`'s `ttl-store` keyword fingerprint (`leaf_for_spec` would falsely classify
   this unrelated lifecycle sentence as the verified `ttl-store` leaf, breaking leaves-OFF).
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as every other task --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value
   is derivable from the visible sentence contract).
3. Add `tests/test_ext060_saas_fintech_tasks.py` (OFFLINE, no model/Jetson, hand-written fixtures
   only): a CORRECT `Subscription` fixture is accepted by
   `grade_real_system_task(SUBSCRIPTION_LIFECYCLE_TASK, ...)`; a BROKEN fixture (an illegal
   transition allowed, e.g. unguarded `cancel()`) is rejected; leaves-OFF holds
   (`leaf_for_spec(SUBSCRIPTION_LIFECYCLE_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_saas_fintech_tasks.py tests/test_ext060_lifecycle_inventory.py
   -q`; confirm green (offline only -- do not run the full suite). Update `.jarify/EXT-060/index.json`
   (REQ-18 ranges, via `jarify-manage-links`) and flip the REQ-18 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-18] Second LIFECYCLE CREATE task, in a NEW SaaS-billing vertical (subscription state machine)

### [TASK-14] Second CONSERVATION CREATE task, in a fintech vertical (wallet, no-overdraw balance) (REQ-19)

#### Steps
1. In `harness/real_systems_suite.py`, add `WALLET_NO_OVERDRAW_TASK` (`RealSystemTask`,
   `cls="wallet"`, `oracle_kind="conservation"`) with a contract-exact sentence for a stdlib-only
   single-file `Wallet` class in `wallet.py` (constructor takes an initial integer-cents balance,
   `credit(cents)`/`debit(cents)` methods, zero-argument `balance_cents()`/`ledger_cents()` readers,
   `debit(cents)` raising `ValueError` with quantities left unchanged when `cents` exceeds the
   current `balance_cents`, cents conserved between `balance_cents` and the internal `ledger_cents`
   mirror counter). Reuse the ALREADY-LANDED `_grade_conservation` dispatch (REQ-15) -- no new
   oracle code. `oracle_spec.spec` drives an illegal overdraw `debit` (reject), then a legal
   `credit` and a legal `debit` each with declared per-quantity `deltas`, then a SECOND illegal
   overdraw `debit` mid-sequence (proving the guard holds after legal ops have moved the balance
   too), ending on a concrete `expect_final`.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as every other task --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value
   is derivable from the visible sentence contract).
3. Extend `tests/test_ext060_saas_fintech_tasks.py` (same file TASK-13 creates, OFFLINE, no
   model/Jetson): a CORRECT `Wallet` fixture is accepted by
   `grade_real_system_task(WALLET_NO_OVERDRAW_TASK, ...)`; a BROKEN fixture (allows an overdraw,
   e.g. unguarded `debit()`) is rejected; leaves-OFF holds
   (`leaf_for_spec(WALLET_NO_OVERDRAW_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`; assert `REAL_SYSTEMS_TASKS` grew by exactly the two REQ-18/REQ-19 tasks
   (length 10 -> 12).
4. Run `python -m pytest tests/test_ext060_saas_fintech_tasks.py tests/test_ext060_lifecycle_inventory.py
   -q`; confirm green (offline only -- do not run the full suite). Update `.jarify/EXT-060/index.json`
   (REQ-19 ranges, via `jarify-manage-links`) and flip the REQ-19 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-19] Second CONSERVATION CREATE task, in a fintech vertical (wallet, no-overdraw balance)

### [TASK-15] Third LIFECYCLE CREATE task, in a support/helpdesk vertical (ticket workflow state machine) (REQ-20)

#### Steps
1. In `harness/real_systems_suite.py`, add `TICKET_WORKFLOW_TASK` (`RealSystemTask`,
   `cls="ticket"`, `oracle_kind="state_machine"`) with a contract-exact sentence for a
   stdlib-only single-file `Ticket` class in `ticket.py` (states `open`/`assigned`/
   `pending_customer`/`resolved`/`closed`, action methods `assign()`/`await_customer()`/
   `respond()`/`resolve()`/`close()`/`reopen()`, a real `state` property, `ValueError` raised on
   any illegal transition with state left unchanged). Reuse the ALREADY-LANDED
   `_grade_state_machine` dispatch (REQ-13) -- no new oracle code. `oracle_spec.spec` drives:
   `resolve` from `open` (reject), `assign` (accept -> `assigned`), `reopen` from `assigned`
   (reject -- a SECOND distinct illegal transition), `await_customer` (accept ->
   `pending_customer`), `respond` (accept -> `assigned`), `resolve` (accept -> `resolved`),
   `close` (accept -> `closed`), `reopen` (accept -> `open`); `expect_final="open"`. Confirm via
   `harness.graph_dsl.leaf_for_spec` that no leaf fingerprint fires for the sentence (avoid
   queue/cache/ttl/expire/stack/ring/buffer/memoize tokens).
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as every other task --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value
   is derivable from the visible sentence contract).
3. Add `tests/test_ext060_ticket_booking_invoice.py` (OFFLINE, no model/Jetson, hand-written
   fixtures only): a CORRECT `Ticket` fixture is accepted by
   `grade_real_system_task(TICKET_WORKFLOW_TASK, ...)`; a BROKEN fixture (illegal transitions
   allowed, e.g. unguarded `resolve()`/`reopen()`) is rejected; leaves-OFF holds
   (`leaf_for_spec(TICKET_WORKFLOW_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_ticket_booking_invoice.py tests/test_ext060_lifecycle_inventory.py
   -q`; confirm green (offline only -- do not run the full suite). Update `.jarify/EXT-060/index.json`
   (REQ-20 ranges, via `jarify-manage-links`) and flip the REQ-20 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-20] Third LIFECYCLE CREATE task, in a support/helpdesk vertical (ticket workflow state machine)

### [TASK-16] Third CONSERVATION CREATE task, in an events/venue-booking vertical (seat booking, no double-book) (REQ-21)

#### Steps
1. In `harness/real_systems_suite.py`, add `SEAT_BOOKING_TASK` (`RealSystemTask`, `cls="booking"`,
   `oracle_kind="conservation"`) with a contract-exact sentence for a stdlib-only single-file
   `SeatBooking` class in `booking.py` (constructor takes a fixed total-seats capacity,
   `reserve(n)`/`release(n)` methods, zero-argument `available_seats()`/`reserved_seats()`
   readers, `reserve(n)` raising `ValueError` with quantities left unchanged when `n` exceeds
   what is available, seats conserved). Reuse the ALREADY-LANDED `_grade_conservation` dispatch
   (REQ-15) -- no new oracle code. `oracle_spec.spec` drives an illegal overbooking `reserve` at
   the start (reject), a legal `reserve` and a legal `release` each with declared per-quantity
   `deltas`, a SECOND illegal overbooking `reserve` mid-sequence after the partial release
   (reject -- proving the guard holds after legal ops have moved the balance too), then a final
   legal `reserve`, ending on a concrete `expect_final`.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as every other task --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value
   is derivable from the visible sentence contract).
3. Extend `tests/test_ext060_ticket_booking_invoice.py` (same file TASK-15 creates, OFFLINE, no
   model/Jetson): a CORRECT `SeatBooking` fixture is accepted by
   `grade_real_system_task(SEAT_BOOKING_TASK, ...)`; a BROKEN fixture (allows an overbook, e.g.
   unguarded `reserve()`) is rejected; leaves-OFF holds
   (`leaf_for_spec(SEAT_BOOKING_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
4. Run `python -m pytest tests/test_ext060_ticket_booking_invoice.py tests/test_ext060_lifecycle_inventory.py
   -q`; confirm green (offline only -- do not run the full suite). Update `.jarify/EXT-060/index.json`
   (REQ-21 ranges, via `jarify-manage-links`) and flip the REQ-21 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-21] Third CONSERVATION CREATE task, in an events/venue-booking vertical (seat booking, no double-book)

### [TASK-17] Second FINTECH-LEDGER CREATE task, in an accounts-receivable/invoicing vertical (REQ-22)

#### Steps
1. In `harness/real_systems_suite.py`, add `INVOICE_AR_TASK` (`RealSystemTask`, `cls="invoice"`,
   `oracle_kind="double_entry"`) with a contract-exact sentence for a stdlib-only single-file
   `Invoicing` class in `invoicing.py` (three named accounts `accounts_receivable`/`revenue`/
   `cash`, zero-argument readers, a `post(legs)` method applying balanced debit/credit legs --
   issuing an invoice debits `accounts_receivable`/credits `revenue`; receiving payment debits
   `cash`/credits `accounts_receivable` -- raising `ValueError` with every balance left unchanged
   when the legs are unbalanced). Reuse the ALREADY-LANDED `_grade_double_entry` dispatch
   (REQ-17) -- no new oracle code. `oracle_spec.spec` drives an illegal unbalanced posting
   (reject) first, then two balanced invoice postings ($500.00 and $300.00) and one balanced
   payment posting ($500.00), ending on a concrete `expect_final`
   (`accounts_receivable=30000, revenue=-80000, cash=50000` cents, debit-positive/credit-negative
   convention). Validate the spec via `harness.double_entry_oracle.validate_spec` and an
   end-to-end `grade_double_entry` dry run against both a correct and a broken fixture before
   adding the task to the roster.
2. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (same two checks as every other task --
   static `leaf_for_spec` + post-build `build_path` check) + leak-free (every oracle-chosen value
   is derivable from the visible sentence contract).
3. Extend `tests/test_ext060_ticket_booking_invoice.py` (same file TASK-15/16 create, OFFLINE, no
   model/Jetson): a CORRECT `Invoicing` fixture is accepted by
   `grade_real_system_task(INVOICE_AR_TASK, ...)`; a BROKEN fixture (posts an unbalanced entry
   with no guard) is rejected; leaves-OFF holds (`leaf_for_spec(INVOICE_AR_TASK.sentence) is
   None`); the task is a member of `REAL_SYSTEMS_TASKS`; assert `REAL_SYSTEMS_TASKS` grew by
   exactly the three REQ-20/21/22 tasks (length 12 -> 15).
4. Run `python -m pytest tests/test_ext060_ticket_booking_invoice.py tests/test_ext060*.py -q`;
   confirm green (offline only -- do not run the full suite). Update `.jarify/EXT-060/index.json`
   (REQ-22 ranges, via `jarify-manage-links`) and flip the REQ-22 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-22] Second FINTECH-LEDGER CREATE task, in an accounts-receivable/invoicing vertical

### [TASK-18] Thread `spec_hint` from the real-systems MODIFY driver into `modify_system` (REQ-23)

#### Steps
1. In `harness/real_systems_suite.py`, add an optional `base_sentence: str = ""` field to
   `RealSystemModifyTask` (fully backward compatible). Populate it for all 6 existing modify
   tasks with the matching CREATE task's sentence: `RETRY_BASE_DELAY_MODIFY_TASK` <-
   `_RETRY_BACKOFF_SENTENCE` (`RETRY_BACKOFF_LIB_TASK`'s), `INI_DEFAULT_FLAG_MODIFY_TASK` <-
   `_INI_SECTION_QUERY_SENTENCE` (`INI_SECTION_QUERY_TASK`'s), `REST_SQLITE_ADD_UPDATE_MODIFY` <-
   `_REST_SQLITE_CRUD_SENTENCE` (`REST_SQLITE_CRUD_TASK`'s), `AGENT_ADD_STEP_GUARD_MODIFY` <-
   `_PLAIN_AGENT_SENTENCE` (`PLAIN_AGENT_TASK`'s), `ORDER_ADD_REFUND_MODIFY` <-
   `_ORDER_LIFECYCLE_SENTENCE` (`ORDER_LIFECYCLE_TASK`'s), `INVENTORY_ADD_BACKORDER_MODIFY` <-
   `_INVENTORY_SENTENCE` (`INVENTORY_TASK`'s).
2. In `_run_one_modify_task`, pass `spec_hint=(task.base_sentence or None)` to the
   `modify_system(...)` call (REQ-52's already-landed kwarg) -- `base_sentence` defaults to `""`
   (falsy), so `spec_hint` stays `None` for any task that never sets it.
3. Verify (offline, pure functions, no build): `REST_SQLITE_ADD_UPDATE_MODIFY.base_sentence + " "
   + REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence` makes
   `harness.http_service_scaffold.spec_demands_stdlib_http_service` return `True` (and the bare
   `mod_sentence` alone returns `False`, proving the gap); `AGENT_ADD_STEP_GUARD_MODIFY.
   base_sentence + " " + AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence` makes
   `harness.agent_scaffold.spec_demands_tool_calling_agent` return `True`.
4. Add `tests/test_ext060_spec_hint.py` (offline, no Jetson/`build_llm`): (a) every modify task in
   `REAL_SYSTEMS_MODIFY_TASKS` has a non-empty `base_sentence` drawn from
   `REAL_SYSTEMS_TASKS`'s own sentences; (b) the two protocol-modify detector checks from step 3;
   (c) the driver passes `spec_hint` through to `modify_system` -- verified by monkeypatching
   `harness.real_systems_suite.modify_system` with a stub that captures its kwargs and calling
   `_run_one_modify_task` directly (both a task with a `base_sentence` and one without, asserting
   `spec_hint is None` in the latter case); (d) `REAL_SYSTEMS_TASKS`/`REAL_SYSTEMS_MODIFY_TASKS`
   are unchanged in size (15 create + 6 modify) -- this task only threads an existing field
   through, it never adds/removes a roster task.
5. Run `python -m pytest tests/test_ext060_spec_hint.py tests/test_ext060*.py -q`; confirm green
   (offline only). Update `.jarify/EXT-060/index.json` (REQ-23 ranges, via `jarify-manage-links`)
   and flip the REQ-23 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-23] Thread `spec_hint` from the real-systems MODIFY driver into `modify_system`

### [TASK-19] Fourth LIFECYCLE CREATE task, in an SLA-tiered helpdesk vertical (REQ-24)

#### Steps
1. In `harness/real_systems_suite.py`, add `HELPDESK_SLA_TASK` (`RealSystemTask`,
   `cls="helpdesk"`, `oracle_kind="state_machine"`) with a contract-exact sentence for a
   stdlib-only single-file `HelpdeskTicket` class in `helpdesk.py` (states
   `new`/`triaged`/`escalated`/`waiting_customer`/`resolved`/`closed`, action methods
   `triage()`/`escalate()`/`resolve()`/`wait_on_customer()`/`resume()`/`close()`/`reopen()`,
   with `escalate()` legal ONLY from `triaged` -- the SLA-tier-escalation behavior that
   distinguishes it from `TICKET_WORKFLOW_TASK`'s plain support ticket). Reuse the
   ALREADY-LANDED `_grade_state_machine` dispatch (REQ-13) -- no new oracle code. Avoid every
   leaf-fingerprinting token (queue/cache/ttl/expire/stack/ring/buffer/memoize) in the sentence.
2. `oracle_spec.spec` drives an illegal `escalate()` from `"new"` FIRST (reject), then the legal
   `triage()`, then an illegal `close()` from `"triaged"` (reject, a SECOND distinct illegal
   transition), then the full legal SLA-escalation path (`escalate` -> `wait_on_customer` ->
   `resume` -> `resolve` -> `close` -> `reopen`) back to `expect_final="new"`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` +
   post-build `build_path` check) + leak-free (every oracle-chosen value is derivable from the
   visible sentence contract).
4. Add `tests/test_ext060_atlas_wave1_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `HelpdeskTicket` fixture is accepted by `grade_real_system_task(HELPDESK_SLA_TASK, ...)`; a
   BROKEN fixture (unguarded `escalate()`, legal from any state) is rejected; leaves-OFF holds
   (`leaf_for_spec(HELPDESK_SLA_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave1_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-24 ranges, via
   `jarify-manage-links`) and flip the REQ-24 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-24] Fourth LIFECYCLE CREATE task, in an SLA-tiered helpdesk vertical (helpdesk ticket, distinct from the plain-ticket class)

### [TASK-20] Second cli-exact CREATE task, in an elections/voting vertical (REQ-25)

#### Steps
1. In `harness/real_systems_suite.py`, add `IRV_TALLY_TASK` (`RealSystemTask`,
   `cls="elections"`, `oracle_kind="cli-exact"`) with a contract-exact sentence for a
   stdlib-only `main.py` CLI reading ranked-choice ballots from stdin (one comma-separated
   ranked candidate list per line) and printing an instant-runoff tally: per-round
   `Round <N>: <name>=<count>, ...` lines (candidates in alphabetical order), an
   `Eliminated: <name>` line when no candidate has a strict majority that round, and a final
   `Winner: <name>` line once one does. Reuse the ALREADY-LANDED `_grade_cli_exact` dispatch
   (REQ-4) -- no new oracle code.
2. Craft the seeded ballot fixture (21 ballots: 10 `A,B`, 6 `B,C`, 5 `C,B`) so the round-1
   plurality leader (`A`, 10 votes) LOSES after `C` is eliminated and its votes transfer to `B`
   (`B` wins with 11/21), and set `oracle_spec["expected_stdout"]` to the full exact
   elimination-order printout (`Round 1: A=10, B=6, C=5`, `Eliminated: C`,
   `Round 2: A=10, B=11`, `Winner: B`).
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free (every oracle-chosen
   value is derivable from the visible sentence contract).
4. Extend `tests/test_ext060_atlas_wave1_tasks.py` (same file TASK-19 creates, OFFLINE, no
   model/Jetson): a CORRECT IRV `main.py` stub is accepted by
   `grade_real_system_task(IRV_TALLY_TASK, ...)`; a BROKEN stub that implements plain plurality
   (declares the round-1 leader the winner outright) is rejected; leaves-OFF holds
   (`leaf_for_spec(IRV_TALLY_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave1_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-25 ranges, via
   `jarify-manage-links`) and flip the REQ-25 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-25] Second cli-exact CREATE task, in an elections/voting vertical (ranked-choice instant-runoff tally)

### [TASK-21] Third import-oracle CREATE task, in a payroll/tax vertical (REQ-26)

#### Steps
1. In `harness/real_systems_suite.py`, add `TAX_WITHHOLDING_TASK` (`RealSystemTask`,
   `cls="payroll"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `compute_withholding_cents(income_cents, brackets)` function in `withholding.py`
   -- `brackets` is a caller-supplied list of `[upper_bound_cents, rate_percent]` pairs (last
   entry's `upper_bound_cents` is `None`, open-ended), and each bracket's contribution is
   `(portion_cents * rate_percent) // 100` (integer floor division, pinned explicitly so there
   is no rounding ambiguity). No jurisdiction/bracket table is hardcoded anywhere in the module.
   Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Pick a bracket table (`[[100000, 10], [400000, 20], [None, 30]]`) and four `api_calls`/
   `checks` covering zero income, an income exactly at a bracket boundary, a mid-bracket income,
   and a top-bracket-overflow income -- hand-verify every expected value against the pinned
   floor-division rule (e.g. via a scratch Python script) before adding the task to the roster.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_atlas_wave1_tasks.py` (same file TASK-19/20 create, OFFLINE, no
   model/Jetson): a CORRECT `compute_withholding_cents` fixture is accepted by
   `grade_real_system_task(TAX_WITHHOLDING_TASK, ...)`; a BROKEN fixture with an off-by-one
   bracket boundary (excludes the ceiling cent from its own bracket) is rejected; leaves-OFF
   holds (`leaf_for_spec(TAX_WITHHOLDING_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave1_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-26 ranges, via
   `jarify-manage-links`) and flip the REQ-26 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-26] Third import-oracle CREATE task, in a payroll/tax vertical (progressive bracket withholding)

### [TASK-22] Fourth import-oracle CREATE task, in a legal/court-filing vertical (REQ-27)

#### Steps
1. In `harness/real_systems_suite.py`, add `COURT_DEADLINE_TASK` (`RealSystemTask`,
   `cls="legal"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `compute_deadline(trigger_date, day_count, counting_rule, holidays)` function in
   `deadline.py` -- explicit ISO `trigger_date`, integer `day_count`, `"calendar"`/`"court"`
   `counting_rule`, a fixed Saturday/Sunday weekend rule, and a caller-supplied `holidays` list
   (no built-in holiday calendar); the raw landing day rolls forward past any trailing
   weekend/holiday run to the next court day. Fully deterministic (no reliance on "today", no
   clock oracle seam needed). Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no
   new oracle code.
2. Pick four `api_calls`/`checks`: a baseline calendar computation with no rolling, a
   calendar-day landing on a Saturday rolling to the following Monday, a court-day count
   skipping both weekends and an explicit interior holiday, and a calendar-day landing that
   falls exactly on an explicit (non-weekend) holiday and must still roll forward --
   independently hand-verify every expected date with `datetime.date` arithmetic (e.g. via a
   scratch Python script) before adding the task to the roster.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_atlas_wave1_tasks.py` (same file TASK-19/20/21 create, OFFLINE, no
   model/Jetson): a CORRECT `compute_deadline` fixture is accepted by
   `grade_real_system_task(COURT_DEADLINE_TASK, ...)`; a BROKEN fixture that forgets to honor
   `holidays` (only honors weekends) is rejected; leaves-OFF holds
   (`leaf_for_spec(COURT_DEADLINE_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`; assert `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-24/25/26/27
   tasks (length 15 -> 19).
5. Run `python -m pytest tests/test_ext060_atlas_wave1_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; also confirm the two pre-existing hardcoded roster-size
   assertions in `tests/test_ext060_ticket_booking_invoice.py` and
   `tests/test_ext060_spec_hint.py` are updated to the new total of 19). Update
   `.jarify/EXT-060/index.json` (REQ-27 ranges, via `jarify-manage-links`) and flip the REQ-27
   acceptance boxes in `requirements.md`.

#### Implements
- [REQ-27] Fourth import-oracle CREATE task, in a legal/court-filing vertical (deadline date math)

### [TASK-23] `oracle_kind="clock"` + first TIME-DEPENDENT CREATE task (account lockout/backoff) (REQ-28)

#### Steps
1. In `harness/real_systems_suite.py`, add a `from harness.clock_oracle import grade_clock`
   import, a new `_grade_clock(oracle_spec, root, python_exe)` helper mirroring
   `_grade_conservation` exactly (validates `module`/`entity` keys, calls
   `harness.clock_oracle.grade_clock(root, module=..., entity=..., spec=oracle_spec.get("spec"),
   python_exe=python_exe)`), and a new `oracle_kind == "clock"` branch in
   `grade_real_system_task` dispatching to it -- no new driving mechanism.
2. Add `LOCKOUT_BACKOFF_TASK` (`RealSystemTask`, `cls="auth"`, `oracle_kind="clock"`) with a
   contract-exact sentence for a stdlib-only single-file `LoginAttemptTracker` class (plus a
   `LockedOut` exception) in `lockout.py`, constructed with a keyword-named zero-argument clock
   callable `now_fn` it must consult for EVERY time decision (never the real wall clock): three
   consecutive failed attempts within a 300-second window locks the account for 600 seconds
   (further attempts raise `LockedOut` while locked); a successful attempt resets the failure
   streak; the lock clears once `now_fn()` reaches the recorded lock-clear time. Say "clears,"
   never "expires"; avoid every leaf-fingerprinting token (cache/ttl/queue/stack/ring/buffer/
   memoize).
3. Hand-walk (e.g. via a scratch Python script) a timeline that exercises the FLAGSHIP honesty
   case: failures at `t=0/10/20` trigger a lock clearing at `t=620`; `t=30` (still locked) must
   raise `LockedOut`; `t=650` (a 620-SIMULATED-second jump from `t=30`, executed in real
   milliseconds) must succeed (unlocked) -- a real-wall-clock-driven build cannot tell those two
   calls apart. Call `harness.clock_oracle.validate_spec` on the resulting spec and confirm
   `(True, "ok")` before adding the task to the roster.
4. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free.
5. Add `tests/test_ext060_clock_agent_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `LoginAttemptTracker` fixture is accepted by `grade_real_system_task(LOCKOUT_BACKOFF_TASK,
   ...)`; a BROKEN fixture that secretly uses `time.time()` instead of `now_fn` is rejected; a
   SECOND, independently BROKEN fixture with no lock guard at all is also rejected;
   `harness.clock_oracle.validate_spec(LOCKOUT_BACKOFF_TASK.oracle_spec["spec"])` reports
   `(True, "ok")`; leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`.
6. Run `python -m pytest tests/test_ext060_clock_agent_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-28 ranges, via
   `jarify-manage-links`) and flip the REQ-28 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-28] `oracle_kind="clock"` + first TIME-DEPENDENT CREATE task (account lockout/backoff)

### [TASK-24] First agent/LLM-infrastructure CREATE task, an LLM-output parsing library (REQ-29)

#### Steps
1. In `harness/real_systems_suite.py`, add `OUTPUT_PARSER_TASK` (`RealSystemTask`,
   `cls="agent-infra"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `output_parser.py` module exporting `parse_json_block(text)` (finds and parses the
   first ` ```json ` fenced block, tolerating prose around it, raising `ValueError` when none is
   present), `parse_key_values(text)` (parses "Key: value" lines into a dict, splitting on the
   FIRST colon only, skipping non-matching lines), and `strip_fences(text)` (removes every fenced
   -code-block marker line, returning the remaining content). Reuse the ALREADY-LANDED
   `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Pick four `api_calls`/`checks`: a fenced block WITH a language tag whose JSON content contains
   NESTED objects/arrays (proving line-based, not balanced-brace, extraction), the no-fenced
   -block `ValueError` case, `parse_key_values` on a mix of matching/non-matching lines (including
   a value that itself contains a colon), and `strip_fences` on text with a differently-tagged
   fence -- hand-verify every expected value against a scratch reference implementation before
   adding the task to the roster.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_clock_agent_tasks.py` (same file TASK-23 creates, OFFLINE, no
   model/Jetson): a CORRECT `output_parser.py` fixture is accepted by
   `grade_real_system_task(OUTPUT_PARSER_TASK, ...)`; a BROKEN fixture that returns the wrong
   nesting for `parse_json_block` (re-wraps nested values) is rejected; leaves-OFF holds; the
   task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_clock_agent_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-29 ranges, via
   `jarify-manage-links`) and flip the REQ-29 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-29] First agent/LLM-infrastructure CREATE task, an LLM-output parsing library

### [TASK-25] Second agent/LLM-infrastructure CREATE task, a schema-validation-retry loop (REQ-30)

#### Steps
1. In `harness/real_systems_suite.py`, add `VALIDATION_RETRY_TASK` (`RealSystemTask`,
   `cls="agent-infra"`, `oracle_kind="agent"`) with a contract-exact sentence for a stdlib-only
   single-file plain-Python agent `main.py` implementing a Pydantic-AI-shaped validation-retry
   loop, mirroring `PLAIN_AGENT_TASK`'s env-var/chat-completions/tool-call protocol: it asks the
   stub model for structured output via tool/function calling (the model "calls" a
   `submit_output` function whose arguments ARE the candidate payload), validates the parsed
   arguments LOCALLY against a required-keys schema (`name`+`email`), and on validation failure
   appends the error to the message list and sends ONE retry before finalizing. Reuse the
   ALREADY-LANDED `_grade_agent` dispatch (REQ-11) -- no new oracle code.
2. Script `oracle_spec["script"]` with exactly TWO turns (`tool_call_turn("submit_output", ...)`
   with an INVALID payload missing `email`, then a VALID, corrected one), and
   `oracle_spec["expect_tool_calls"]` as the matching ORDERED, args-exact 2-entry list -- proving
   via the EXISTING `check_agent` call-count/args check (no new oracle code) that exactly one
   retry occurred and that the retry's payload is schema-corrected.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_clock_agent_tasks.py` (same file TASK-23/24 create, OFFLINE, no
   model/Jetson): a CORRECT validation-retry agent fixture is accepted by
   `grade_real_system_task(VALIDATION_RETRY_TASK, ...)` and independently confirmed (via a direct
   `harness.agent_oracle.drive_agent` call) to make exactly 2 model round-trips; a BROKEN fixture
   that never retries on an invalid first attempt is rejected; leaves-OFF holds; the task is a
   member of `REAL_SYSTEMS_TASKS`; assert `REAL_SYSTEMS_TASKS` grew by exactly the three
   REQ-28/29/30 tasks (length 19 -> 22).
5. Run `python -m pytest tests/test_ext060_clock_agent_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; also confirm the three pre-existing hardcoded roster-size
   assertions in `tests/test_ext060_atlas_wave1_tasks.py`, `tests/test_ext060_ticket_booking_
   invoice.py`, and `tests/test_ext060_spec_hint.py` are updated to the new total of 22). Update
   `.jarify/EXT-060/index.json` (REQ-30 ranges, via `jarify-manage-links`) and flip the REQ-30
   acceptance boxes in `requirements.md`.

#### Implements
- [REQ-30] Second agent/LLM-infrastructure CREATE task, a schema-validation-retry loop

### [TASK-26] Third import-oracle CREATE task, in a backup/ops vertical (GFS retention pruning) (REQ-31)

#### Steps
1. In `harness/real_systems_suite.py`, add `GFS_RETENTION_TASK` (`RealSystemTask`,
   `cls="backup"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `compute_keep_dates(snapshots, keep_daily, keep_weekly, keep_monthly)` function in
   `gfs_retention.py` implementing a Grandfather-Father-Son retention policy: the union of a
   DAILY tier (the `keep_daily` most-recent dates kept outright), a WEEKLY tier (the newest
   snapshot in each of the `keep_weekly` most-recent distinct ISO calendar weeks), and a MONTHLY
   tier (the newest snapshot in each of the `keep_monthly` most-recent distinct calendar months),
   deduplicated, sorted ascending. Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) --
   no new oracle code.
2. Craft a 15-date fixture (shuffled input order) spanning three calendar months with several
   dates sharing the same ISO week or calendar month; hand-verify the exact expected keep-set for
   a concrete policy (via a scratch Python script computing the same grouping rule) before adding
   the task to the roster. Add a second `api_calls`/`checks` entry exercising the
   fewer-snapshots-than-the-policy-asks edge case (every tier requested larger than the available
   count -- expect every date kept, no error, no padding).
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free (every oracle-chosen value is derivable from the visible
   sentence contract).
4. Add `tests/test_ext060_atlas_wave2_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `compute_keep_dates` fixture is accepted by `grade_real_system_task(GFS_RETENTION_TASK, ...)`;
   a BROKEN fixture that ignores the policy and keeps every snapshot is rejected; leaves-OFF
   holds (`leaf_for_spec(GFS_RETENTION_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave2_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-31 ranges, via
   `jarify-manage-links`) and flip the REQ-31 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-31] Third import-oracle CREATE task, in a backup/ops vertical (Grandfather-Father-Son retention pruning)

### [TASK-27] Fourth import-oracle CREATE task, in a devtools/CI vertical (CI job-matrix expansion) (REQ-32)

#### Steps
1. In `harness/real_systems_suite.py`, add `CI_MATRIX_TASK` (`RealSystemTask`, `cls="devtools"`,
   `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only single-file
   `expand_matrix(matrix, exclude=None, include=None)` function in `ci_matrix.py` that expands a
   CI job matrix into its full cross product (axes iterated in ascending alphabetical order, the
   alphabetically-last axis cycling fastest), removing any combo matching ALL of AT LEAST ONE
   `exclude` entry's axis:value pairs (a subset-of-axes match), then appending every `include`
   entry verbatim. Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle
   code.
2. Hand-verify (via a scratch `itertools.product` computation) a 2x3 matrix with one full-axis
   `exclude` entry plus one `include` entry, and a second matrix whose `exclude` entry names only
   a subset of its axes (proving subset-match removes every matching combo); add both as
   `api_calls`/`checks` entries, plus a third exercising the bare `=None` defaults (no
   `exclude`/`include` supplied at all).
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_atlas_wave2_tasks.py` (same file TASK-26 creates, OFFLINE, no
   model/Jetson): a CORRECT `expand_matrix` fixture is accepted by
   `grade_real_system_task(CI_MATRIX_TASK, ...)`; a BROKEN fixture that computes the correct
   cross product but never applies `exclude` is rejected; leaves-OFF holds
   (`leaf_for_spec(CI_MATRIX_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave2_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-32 ranges, via
   `jarify-manage-links`) and flip the REQ-32 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-32] Fourth import-oracle CREATE task, in a devtools/CI vertical (CI job-matrix expansion)

### [TASK-28] Second `oracle_kind="service"` CREATE task, in a web vertical (URL shortener) (REQ-33)

#### Steps
1. In `harness/real_systems_suite.py`, add `URL_SHORTENER_TASK` (`RealSystemTask`, `cls="web"`,
   `oracle_kind="service"`) with a contract-exact sentence for a stdlib REST/SQLite URL-shortener
   `main.py` (`http.server` + `sqlite3` + `json`, `PORT` env var, `data.db` SQLite file): `POST
   /links` creates a shortened link, responding 201 with `{"code": ..., "url": ...}` (the code is
   the link's SQLite autoincrement id in decimal-string form); `GET /links/<code>` returns the
   stored mapping or 404; `GET /r/<code>` redirects (301 + `Location` header set to the original
   url) for a known code, or 404 for an unknown one. Reuse the ALREADY-LANDED `_grade_service`
   dispatch (REQ-9) -- no new oracle code.
2. Read `harness/server_oracle.py`'s `_do_request` first: its plain `urllib.request.urlopen`
   client transparently FOLLOWS a real 3xx response (no way to observe `status == 301`) and its
   `http_check` dict has no response-header assertion at all -- so do NOT exercise `GET
   /r/<code>` for a KNOWN code (it would make the check client dereference the arbitrary
   submitted url, an unverifiable/hermeticity-hazardous request); only exercise it for an
   UNKNOWN code (a plain 404, never followed). Verify the redirect TARGET instead via the `GET
   /links/<code>` 200 `json_contains` check. Use `.invalid`-TLD urls in the fixture http_checks
   (RFC 2606-reserved, guaranteed non-resolving) as defense-in-depth.
3. `oracle_spec.http_checks` drives two `POST`s, a `GET /links/<code>` mapping check, a `GET
   /links/<unknown>` 404, and a `GET /r/<unknown>` 404; `oracle_spec.db` asserts both created
   rows persisted in `data.db` (`min_rows: 2`, both items left undeleted so this is honestly
   satisfiable).
4. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Extend `tests/test_ext060_atlas_wave2_tasks.py` (same file TASK-26/27 create, OFFLINE, no
   model/Jetson): a CORRECT stdlib URL-shortener fixture is accepted by
   `grade_real_system_task(URL_SHORTENER_TASK, ...)`, including the independent db assertion; a
   BROKEN fixture whose `GET /links/<code>` lookup is dead (always 404s) is rejected; leaves-OFF
   holds (`leaf_for_spec(URL_SHORTENER_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
6. Run `python -m pytest tests/test_ext060_atlas_wave2_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-33 ranges, via
   `jarify-manage-links`) and flip the REQ-33 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-33] Second `oracle_kind="service"` CREATE task, in a web vertical (stdlib REST/SQLite URL shortener)

### [TASK-29] Second `oracle_kind="clock"` CREATE task, in an auth vertical (access-token validity window) (REQ-34)

#### Steps
1. In `harness/real_systems_suite.py`, add `TOKEN_VALIDITY_TASK` (`RealSystemTask`,
   `cls="auth"`, `oracle_kind="clock"`) with a contract-exact sentence for a stdlib-only
   single-file `TokenIssuer` class in `tokens.py`, constructed with a keyword-named zero-argument
   clock callable `now_fn` it must consult for EVERY time decision: `issue(name)` returns a
   token id (pinned, for testability, to be exactly `name` itself) valid for exactly 900 seconds
   per `now_fn`; `check(token)` returns `True` strictly within that window and `False` at or
   after it, and once `False` for a token, every later `check` for that same token also stays
   `False`. Reuse the ALREADY-LANDED `_grade_clock` dispatch (REQ-28) -- no new oracle code. Say
   "valid for 900 seconds"/"elapsed", never "expires" (avoids the verified `ttl-store` leaf's
   keyword fingerprint, mirroring REQ-28's own note).
2. Hand-walk (e.g. via a scratch Python script) a timeline: issue at `t=0`; `check` at `t=899`
   (still valid, `True`); `check` at `t=900` (the exact boundary, `False`); `check` at `t=3600`
   (a large jump, still `False`, proving the SAME token stays invalid rather than re-validating).
   Call `harness.clock_oracle.validate_spec` on the resulting spec and confirm `(True, "ok")`
   before adding the task to the roster.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free.
4. Extend `tests/test_ext060_atlas_wave2_tasks.py` (same file TASK-26/27/28 create, OFFLINE, no
   model/Jetson): a CORRECT `TokenIssuer` fixture is accepted by
   `grade_real_system_task(TOKEN_VALIDITY_TASK, ...)`; a BROKEN fixture that never invalidates a
   token is rejected; `harness.clock_oracle.validate_spec(TOKEN_VALIDITY_TASK.oracle_spec["spec"])`
   reports `(True, "ok")`; leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`; assert
   `REAL_SYSTEMS_TASKS` grew by exactly the four REQ-31/32/33/34 tasks (length 22 -> 26).
5. Run `python -m pytest tests/test_ext060_atlas_wave2_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; also confirm the four pre-existing hardcoded roster-size
   assertions in `tests/test_ext060_atlas_wave1_tasks.py`, `tests/test_ext060_clock_agent_
   tasks.py`, `tests/test_ext060_ticket_booking_invoice.py`, and `tests/test_ext060_spec_hint.py`
   are updated to the new total of 26). Update `.jarify/EXT-060/index.json` (REQ-34 ranges, via
   `jarify-manage-links`) and flip the REQ-34 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-34] Second `oracle_kind="clock"` CREATE task, in an auth vertical (access-token validity window)

### [TASK-30] Fifth LIFECYCLE MODIFY task: add an `on_hold` state to the helpdesk ticket (REQ-35)

#### Steps
1. In `harness/real_systems_suite.py`, add a hand-authored CORRECT baseline `_HELPDESK_SLA_
   BASELINE_PY` matching REQ-24's `HELPDESK_SLA_TASK` contract exactly (no `hold()`/`release()`).
2. Add `HELPDESK_ADD_STATE_MODIFY` (`RealSystemModifyTask`, `cls="helpdesk-modify"`,
   `oracle_kind="state_machine"`, `start_system={"helpdesk.py": _HELPDESK_SLA_BASELINE_PY}`,
   `base_sentence=_HELPDESK_SLA_SENTENCE`) with a `mod_sentence` asking for a new `on_hold` state
   reachable via `hold()` from EITHER `triaged` OR `escalated`, with `release()` returning it to
   `triaged` -- legal ONLY from those source states, illegal (raising `ValueError`, state
   unchanged) everywhere else. Reuse the ALREADY-LANDED `_grade_state_machine` dispatch
   (REQ-13) -- no new oracle code.
3. Extend the `oracle_spec.spec` transitions table with the three new entries
   (`triaged:hold`/`escalated:hold` -> `on_hold`, `on_hold:release` -> `triaged`) and hand-walk a
   `drive` script that mixes an illegal hold-from-`new` (regression of the leaves-OFF-honesty
   habit REQ-13/24 already established), the ORIGINAL legal SLA path, a regression of the
   ORIGINAL illegal close-from-`triaged` rejection, and the NEW hold/release pair exercised from
   BOTH its legal source states.
4. Add it to `REAL_SYSTEMS_MODIFY_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Create `tests/test_ext060_modify_wave2.py` (OFFLINE, no model/Jetson) with its first section:
   the `start_system` baseline ALONE is accepted by `grade_real_system_task(HELPDESK_SLA_TASK,
   ...)`; a hand-authored CORRECT post-modification fixture (baseline + guarded
   `hold()`/`release()`) is accepted by `grade_real_system_task(HELPDESK_ADD_STATE_MODIFY, ...)`;
   the UNMODIFIED baseline is rejected; a fixture that adds `hold()`/`release()` correctly but
   ALSO regresses the original illegal close-from-`triaged` rejection is also rejected;
   leaves-OFF holds (`leaf_for_spec(HELPDESK_ADD_STATE_MODIFY.mod_sentence) is None`); the task is
   a member of `REAL_SYSTEMS_MODIFY_TASKS`.
6. Run `python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-35 ranges, via
   `jarify-manage-links`) and flip the REQ-35 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-35] Fifth LIFECYCLE MODIFY task: add an `on_hold` state to the SLA-tiered helpdesk ticket

### [TASK-31] Second `oracle_kind="import"` MODIFY task: add an optional `cap_cents` to tax withholding (REQ-36)

#### Steps
1. In `harness/real_systems_suite.py`, add a hand-authored CORRECT baseline `_TAX_WITHHOLDING_
   BASELINE_PY` matching REQ-26's `TAX_WITHHOLDING_TASK` contract exactly (no `cap_cents`).
2. Add `TAX_ADD_CAP_MODIFY` (`RealSystemModifyTask`, `cls="payroll-modify"`,
   `oracle_kind="import"`, `start_system={"withholding.py": _TAX_WITHHOLDING_BASELINE_PY}`,
   `base_sentence=_TAX_WITHHOLDING_SENTENCE`) with a `mod_sentence` asking for an ADDITIONAL
   optional `cap_cents` keyword (default `None`) that, when supplied as an integer, caps the
   computed withholding at `cap_cents` -- never raising it, and leaving the uncapped behavior
   completely unchanged when omitted or `None`. Reuse the ALREADY-LANDED `_grade_import` dispatch
   (REQ-3) -- no new oracle code.
3. `oracle_spec.api_calls` REUSES REQ-26's own four exact hand-verified regression values (`zero`/
   `boundary`/`mid`/`top`, invoked with no `cap_cents`) plus two NEW calls at the `mid` income
   proving the cap both BINDS (a cap below the natural 35007-cent amount) and is a no-op (a cap
   above it).
4. Add it to `REAL_SYSTEMS_MODIFY_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Extend `tests/test_ext060_modify_wave2.py` (same file TASK-30 creates, OFFLINE, no
   model/Jetson): the `start_system` baseline ALONE is accepted by
   `grade_real_system_task(TAX_WITHHOLDING_TASK, ...)`; a hand-authored CORRECT
   post-modification fixture (baseline + `cap_cents=None` cap) is accepted by
   `grade_real_system_task(TAX_ADD_CAP_MODIFY, ...)`; the UNMODIFIED baseline is rejected
   (`TypeError` on the cap calls); a fixture that adds `cap_cents` with a WRONG nonzero default
   (regressing the original uncapped behavior) is also rejected; leaves-OFF holds; the task is a
   member of `REAL_SYSTEMS_MODIFY_TASKS`.
6. Run `python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-36 ranges, via
   `jarify-manage-links`) and flip the REQ-36 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-36] Second `oracle_kind="import"` MODIFY task: add an optional `cap_cents` to progressive tax withholding

### [TASK-32] Second `oracle_kind="cli-exact"` MODIFY task: add an alphabetical-tie-elimination rule to IRV tally (REQ-37)

#### Steps
1. In `harness/real_systems_suite.py`, add a hand-authored CORRECT baseline `_IRV_TALLY_
   BASELINE_PY` implementing REQ-25's ORIGINAL instant-runoff contract exactly, breaking a tie
   for fewest votes (a case REQ-25's own ballots never exercise) by eliminating the
   alphabetically EARLIEST tied candidate -- a plausible but WRONG guess, deliberately distinct
   from the new rule this task adds.
2. Add `IRV_ADD_TIE_RULE_MODIFY` (`RealSystemModifyTask`, `cls="elections-modify"`,
   `oracle_kind="cli-exact"`, `start_system={"main.py": _IRV_TALLY_BASELINE_PY}`,
   `base_sentence=_IRV_TALLY_SENTENCE`) with a `mod_sentence` pinning the new rule: on a tie for
   fewest first-choice votes, eliminate the candidate LATER alphabetically instead; the no-tie
   case is unchanged. Reuse the ALREADY-LANDED `_grade_cli_exact` dispatch (REQ-25) -- no new
   oracle code.
3. Hand-craft a 22-ballot fixture (10 ballots ranking `A` alone; 6 ranking `B,C`; 6 ranking `C,B`)
   where round 1 produces a genuine tie for fewest between `B`/`C` (6 each) AND the tie-break
   choice CHANGES the eventual winner (eliminating `C`, the correct rule, transfers its votes to
   `B`, who then wins; eliminating `B` instead would transfer to `C` and hand `C` the win) --
   hand-recompute the exact multi-round expected stdout and independently re-verify it against a
   scratch script implementing the rule before adding it to `oracle_spec`.
4. Add it to `REAL_SYSTEMS_MODIFY_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Extend `tests/test_ext060_modify_wave2.py` (same file TASK-30/31 create, OFFLINE, no
   model/Jetson): the `start_system` baseline ALONE is accepted by
   `grade_real_system_task(IRV_TALLY_TASK, ...)`; a hand-authored CORRECT post-modification
   fixture is accepted by `grade_real_system_task(IRV_ADD_TIE_RULE_MODIFY, ...)`; the UNMODIFIED
   baseline is rejected (wrong tie-break, wrong winner); a fixture that implements the new rule
   correctly but regresses the original `Round <N>: ...` separator format is also rejected;
   leaves-OFF holds; the task is a member of `REAL_SYSTEMS_MODIFY_TASKS`.
6. Run `python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-37 ranges, via
   `jarify-manage-links`) and flip the REQ-37 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-37] Second `oracle_kind="cli-exact"` MODIFY task: add an alphabetical-tie-elimination rule to IRV tally

### [TASK-33] Second `oracle_kind="service"` MODIFY task: add `DELETE /links/<code>` to the URL shortener (REQ-38)

#### Steps
1. In `harness/real_systems_suite.py`, add a hand-authored CORRECT baseline
   `_URL_SHORTENER_BASELINE_PY` matching REQ-33's `URL_SHORTENER_TASK` contract exactly (no
   `DELETE`).
2. Add `SHORTENER_ADD_DELETE_MODIFY` (`RealSystemModifyTask`, `cls="web-modify"`,
   `oracle_kind="service"`, `start_system={"main.py": _URL_SHORTENER_BASELINE_PY}`,
   `base_sentence=_URL_SHORTENER_SENTENCE`) with a `mod_sentence` asking for a
   `DELETE /links/<code>` endpoint: 204 + genuine removal for a known code (a subsequent `GET`
   for that code must 404), 404 with no effect for an unknown/already-deleted code. Follow
   REQ-33's own SAFETY design (no redirect-following, `.invalid`-TLD fixture urls). Reuse the
   ALREADY-LANDED `_grade_service` dispatch (REQ-9) -- no new oracle code.
3. `oracle_spec.http_checks` REGRESSES REQ-33's original `POST`/`GET`/unknown-`GET /r/<code>`
   checks unchanged, then exercises the new `DELETE` for a real link (204, then a follow-up `GET`
   proving it is genuinely gone) and for an already-deleted code (404, no effect).
   `oracle_spec.db` uses the SURVIVING (never-deleted) second link so the independent
   post-teardown row assertion (`min_rows: 1`) stays honestly satisfiable.
4. Add it to `REAL_SYSTEMS_MODIFY_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Extend `tests/test_ext060_modify_wave2.py` (same file TASK-30/31/32 create, OFFLINE, no
   model/Jetson): the `start_system` baseline ALONE is accepted by
   `grade_real_system_task(URL_SHORTENER_TASK, ...)`; a hand-authored CORRECT post-modification
   fixture (baseline + a real `do_DELETE`) is accepted by
   `grade_real_system_task(SHORTENER_ADD_DELETE_MODIFY, ...)`; the UNMODIFIED baseline is
   rejected (`BaseHTTPRequestHandler` 501s with no `do_DELETE`); a fixture whose `DELETE` wipes
   EVERY row (no `WHERE id = ?` clause, regressing persistence) is also rejected; leaves-OFF
   holds; the task is a member of `REAL_SYSTEMS_MODIFY_TASKS`.
6. Run `python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-38 ranges, via
   `jarify-manage-links`) and flip the REQ-38 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-38] Second `oracle_kind="service"` MODIFY task: add `DELETE /links/<code>` to the URL shortener

### [TASK-34] Second `oracle_kind="clock"` MODIFY task: add `admin_unlock()` to the account lockout policy (REQ-39)

#### Steps
1. In `harness/real_systems_suite.py`, add a hand-authored CORRECT baseline
   `_LOCKOUT_BACKOFF_BASELINE_PY` matching REQ-28's `LOCKOUT_BACKOFF_TASK` contract exactly (no
   `admin_unlock()`).
2. Add `LOCKOUT_ADMIN_UNLOCK_MODIFY` (`RealSystemModifyTask`, `cls="auth-modify"`,
   `oracle_kind="clock"`, `start_system={"lockout.py": _LOCKOUT_BACKOFF_BASELINE_PY}`,
   `base_sentence=_LOCKOUT_BACKOFF_SENTENCE`) with a `mod_sentence` asking for a new
   `admin_unlock()` zero-argument method that clears an active lock IMMEDIATELY (`is_locked()`
   false right after, the next `record_attempt` processed as unlocked), a no-op when not
   currently locked. Reuse the ALREADY-LANDED `_grade_clock` dispatch (REQ-28) -- no new oracle
   code.
3. Hand-walk a timeline that REGRESSES REQ-28's own t=0/10/20 (lock-triggering) and t=30
   (still-locked, `LockedOut`) steps, then calls `admin_unlock()` at t=40 and a `record_attempt`
   at t=50 -- only 10 simulated seconds later, WAY before the natural t=620 clear -- so a no-op
   or unwired `admin_unlock()` is caught (t=50 would still raise `LockedOut` under the OLD
   lock-clear time).
4. Add it to `REAL_SYSTEMS_MODIFY_TASKS`. Keep leaves-OFF enforced + leak-free.
5. Extend `tests/test_ext060_modify_wave2.py` (same file TASK-30/31/32/33 create, OFFLINE, no
   model/Jetson): the `start_system` baseline ALONE is accepted by
   `grade_real_system_task(LOCKOUT_BACKOFF_TASK, ...)`; a hand-authored CORRECT
   post-modification fixture is accepted by
   `grade_real_system_task(LOCKOUT_ADMIN_UNLOCK_MODIFY, ...)`; the UNMODIFIED baseline is rejected
   (`AttributeError` on `admin_unlock`); a fixture that adds a genuinely-working `admin_unlock()`
   but regresses the original 3-failure lock threshold (weakened to 4) is also rejected;
   leaves-OFF holds; the task is a member of `REAL_SYSTEMS_MODIFY_TASKS`. Add a final roster-wide
   test asserting `REAL_SYSTEMS_MODIFY_TASKS` grew by exactly these five REQ-35/36/37/38/39 tasks
   (length 6 -> 11) while `REAL_SYSTEMS_TASKS` stays at 26.
6. Bump the one pre-existing hardcoded MODIFY roster-size assertion in
   `tests/test_ext060_spec_hint.py` (`len(REAL_SYSTEMS_MODIFY_TASKS) == 6` -> `== 11`, plus the
   five new task names added to its membership set).
7. Run `python -m pytest tests/test_ext060_modify_wave2.py tests/test_ext060*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-39 ranges, via
   `jarify-manage-links`) and flip the REQ-39 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-39] Second `oracle_kind="clock"` MODIFY task: add `admin_unlock()` to the account lockout policy

### [TASK-35] Fifth import-oracle CREATE task, in a NEW reliability vertical (Stripe-style recovery-point request executor) (REQ-40)

#### Steps
1. In `harness/real_systems_suite.py`, add `RECOVERY_POINT_TASK` (`RealSystemTask`,
   `cls="reliability"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `replay_execution(steps, recovery_point)` function in `recovery_point.py`: `steps`
   is a list of `{"name": str, "kind": "idempotent"|"non_idempotent"}` dicts in execution order;
   for `i < recovery_point`, re-run (record) idempotent steps, SKIP non-idempotent ones; for
   `i >= recovery_point`, run every step unconditionally regardless of `kind`; return the `name`s
   actually run, in original order. Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) --
   no new oracle code.
2. Hand-verify (via a scratch walk of the exact same rule) three fixtures before adding the task
   to the roster: `recovery_point=0` (all steps run); a 5-step list with `recovery_point=3` (skips
   one non-idempotent prefix step, reruns an idempotent prefix step, runs both trailing steps);
   `recovery_point == len(steps) - 1` (only the trailing step runs unconditionally). Add all three
   as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free; confirm the sentence contains none of the banned leaf keywords
   (`expire`/`expiry`/`expiration`/`cache`/`ttl`/`queue`/`stack`/`ring buffer`/`circular
   buffer`/`memoize`).
4. Add `tests/test_ext060_atlas_wave7_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `replay_execution` fixture is accepted by `grade_real_system_task(RECOVERY_POINT_TASK, ...)`; a
   BROKEN fixture that reruns every step before the checkpoint regardless of idempotency (unsafely
   re-running a non-idempotent step) is rejected; leaves-OFF holds
   (`leaf_for_spec(RECOVERY_POINT_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave7_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-40 ranges, via
   `jarify-manage-links`) and flip the REQ-40 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-40] Fifth import-oracle CREATE task, in a NEW reliability vertical (Stripe-style recovery-point request executor)

### [TASK-36] Sixth import-oracle CREATE task, in a NEW authz vertical (Discord-style layered permission-overwrite resolution) (REQ-41)

#### Steps
1. In `harness/real_systems_suite.py`, add `PERMISSION_OVERWRITE_TASK` (`RealSystemTask`,
   `cls="authz"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `resolve_permissions(everyone_allow, everyone_deny, role_overwrites, member_allow,
   member_deny)` function in `permission_overwrite.py`: starting from `0`, apply the `@everyone`
   layer (clear its deny bits, then set its allow bits), then the combined role layer (union every
   role's deny bits and separately union every role's allow bits, clear-then-set), then the member
   layer (clear-then-set); return the final bitmask. Reuse the ALREADY-LANDED `_grade_import`
   dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via scratch bit math) three fixtures before adding the task to the roster: a
   member-allow bit overriding a role-deny on the SAME bit; a role-allow bit overriding an
   `@everyone`-deny on the SAME bit; a permission bit no layer ever grants staying clear in the
   result (with an empty `role_overwrites` list). Add all three as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_wave7_tasks.py` (same file TASK-35 creates, OFFLINE, no
   model/Jetson): a CORRECT `resolve_permissions` fixture is accepted by
   `grade_real_system_task(PERMISSION_OVERWRITE_TASK, ...)`; a BROKEN fixture that applies the
   member layer BEFORE the role layer (the wrong precedence order) is rejected; leaves-OFF holds
   (`leaf_for_spec(PERMISSION_OVERWRITE_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave7_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-41 ranges, via
   `jarify-manage-links`) and flip the REQ-41 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-41] Sixth import-oracle CREATE task, in a NEW authz vertical (Discord-style layered permission-overwrite resolution)

### [TASK-37] Seventh import-oracle CREATE task, in the payroll vertical (FLSA blended-rate overtime calculator) (REQ-42)

#### Steps
1. In `harness/real_systems_suite.py`, add `BLENDED_OVERTIME_TASK` (`RealSystemTask`,
   `cls="payroll"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file `compute_blended_overtime_pay(entries)` function in `blended_overtime.py`:
   `entries` is a list of `[rate_cents, hours]` pairs; `total_straight_pay_cents` = sum of
   `rate_cents * hours`; when `total_hours <= 40`, owed = `total_straight_pay_cents`; when
   `total_hours > 40`, `blended_regular_rate = total_straight_pay_cents / total_hours`,
   `overtime_hours = total_hours - 40`, premium = `0.5 * blended_regular_rate * overtime_hours`,
   owed = `total_straight_pay_cents + premium`; round the final owed amount to the nearest cent
   using round-half-up and return it as an integer. Reuse the ALREADY-LANDED `_grade_import`
   dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via scratch arithmetic) four fixtures before adding the task to the roster:
   under-40-hours (no overtime, e.g. `[[2000, 30]]` -> `60000`); over-40-hours at a single rate
   (e.g. `[[1500, 45]]` -> `71250`); over-40-hours at TWO rates -- the genuinely blended case
   (e.g. `[[1000, 20], [2000, 25]]` -> `73889`, exercising the non-trivial blended-rate division);
   exactly 40 hours (the boundary, still no overtime, e.g. `[[1200, 40]]` -> `48000`). Add all
   four as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_wave7_tasks.py` (same file TASK-35/36 create, OFFLINE, no
   model/Jetson): a CORRECT `compute_blended_overtime_pay` fixture is accepted by
   `grade_real_system_task(BLENDED_OVERTIME_TASK, ...)`; a BROKEN fixture that computes the
   overtime premium from only the first entry's rate instead of the true blended rate is rejected
   (caught specifically by the two-rate check, since the single-rate check cannot distinguish this
   bug); leaves-OFF holds (`leaf_for_spec(BLENDED_OVERTIME_TASK.sentence) is None`); the task is a
   member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_atlas_wave7_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-42 ranges, via
   `jarify-manage-links`) and flip the REQ-42 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-42] Seventh import-oracle CREATE task, in the payroll vertical (FLSA blended-rate overtime calculator)

### [TASK-38] Eighth import-oracle CREATE task, in a NEW comms vertical (Twilio-style SMS segmentation calculator) (REQ-43)

#### Steps
1. In `harness/real_systems_suite.py`, add `SMS_SEGMENT_TASK` (`RealSystemTask`, `cls="comms"`,
   `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only single-file
   `segment_sms(message)` function in `sms_segments.py`: a SIMPLIFIED GSM-7-encodability rule
   (visible ASCII `0x20`-`0x7E` plus `\n`, stated explicitly as a simplification) selects the
   160-char single-segment / 153-char-per-segment thresholds; any other character forces UCS-2
   (70 single / 67 per segment); segment count = ceiling division of the character count by the
   per-segment threshold once it exceeds the single-segment threshold; the empty string is defined
   GSM-7, 1 segment; return `(encoding, segment_count, n)`. Reuse the ALREADY-LANDED
   `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via scratch ceiling-division arithmetic) five fixtures before adding the task to
   the roster: exactly 160 GSM-7 chars (1 segment); 161 GSM-7 chars (2 segments, `ceil(161/153)`);
   a message forced to UCS-2 by one non-ASCII (BMP-only, to avoid Python/UTF-16 surrogate-pair
   counting differences) character at exactly 70 chars (1 segment) and 71 chars (2 segments,
   `ceil(71/67)`); the empty string (GSM-7, 1 segment, 0 chars). Add all five as
   `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_wave7_tasks.py` (same file TASK-35/36/37 create, OFFLINE, no
   model/Jetson): a CORRECT `segment_sms` fixture is accepted by
   `grade_real_system_task(SMS_SEGMENT_TASK, ...)`; a BROKEN fixture that always applies the
   GSM-7 160/153 thresholds even for a UCS-2-encoded message is rejected (caught by the 71-char
   UCS-2 check regressing to 1 segment instead of 2); leaves-OFF holds
   (`leaf_for_spec(SMS_SEGMENT_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`. Add a final roster-wide test asserting `REAL_SYSTEMS_TASKS` grew by
   exactly these four REQ-40/41/42/43 tasks (length 26 -> 30).
5. Bump the six pre-existing hardcoded CREATE roster-size assertions
   (`len(REAL_SYSTEMS_TASKS) == 26` -> `== 30`) in `tests/test_ext060_atlas_wave1_tasks.py`,
   `tests/test_ext060_atlas_wave2_tasks.py`, `tests/test_ext060_clock_agent_tasks.py`,
   `tests/test_ext060_modify_wave2.py`, `tests/test_ext060_spec_hint.py`, and
   `tests/test_ext060_ticket_booking_invoice.py`.
6. Run `python -m pytest tests/test_ext060_atlas_wave7_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; 30-item CREATE roster). Update `.jarify/EXT-060/index.json`
   (REQ-43 ranges, via `jarify-manage-links`) and flip the REQ-43 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-43] Eighth import-oracle CREATE task, in a NEW comms vertical (Twilio-style SMS segmentation calculator)

### [TASK-39] Ninth CREATE task, in a NEW background-job-processing vertical (background-job lifecycle) (REQ-44)

#### Steps
1. In `harness/real_systems_suite.py`, add `JOB_QUEUE_LIFECYCLE_TASK` (`RealSystemTask`,
   `cls="jobs"`, `oracle_kind="state_machine"`) with a contract-exact sentence for a stdlib-only
   single-file `Job` class in `job.py`: states `"queued"`/`"running"`/`"succeeded"`/`"failed"`/
   `"retrying"`/`"dead"`; `start()` legal from `"queued"` OR `"retrying"` (moves to `"running"`);
   `succeed()` legal from `"running"` (moves to `"succeeded"`); `fail()` legal from `"running"`
   (moves to `"failed"`); `retry()` legal from `"failed"` (moves to `"retrying"`); `kill()` legal
   from `"queued"`/`"running"`/`"failed"`/`"retrying"` (moves to `"dead"`). Phrase the sentence as
   a "background-job processor" throughout (never "job queue"/"task queue") -- the required
   literal state name `"queued"` stays safe against the leaf classifier regardless (confirmed via
   `harness.adt_oracle._KEYWORDS`/`_METHOD_TOKENS`, which never lists the bare token `"queue"`).
   Reuse the ALREADY-LANDED `_grade_state_machine` dispatch (REQ-13) -- no new oracle code.
2. Hand-verify (via a scratch walk of the exact same transition table) a drive script before
   adding the task to the roster: illegal `succeed()` from `"queued"` (reject), then a full legal
   path through ONE retry cycle (`start` -> `fail` -> `retry` -> `start` -> `succeed`, exercising
   `start()` from BOTH `"queued"` and `"retrying"`), then a SECOND illegal transition -- `retry()`
   from `"succeeded"` (reject). `expect_final` is `"succeeded"`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free; confirm the sentence contains none of the banned leaf keywords
   (`expire`/`expiry`/`expiration`/`cache`/`ttl`/`stack`/`ring buffer`/`circular buffer`/
   `memoize`/`fifo`/`priority queue`) and that `leaf_for_spec(JOB_QUEUE_LIFECYCLE_TASK.sentence)`
   is genuinely `None` (not just a literal substring scan) despite the required `"queued"` state
   name.
4. Add `tests/test_ext060_atlas_batch4_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `Job` fixture is accepted by `grade_real_system_task(JOB_QUEUE_LIFECYCLE_TASK, ...)`; a BROKEN
   fixture that allows an illegal transition (e.g. `succeed()` unconditionally, from any state) is
   rejected; leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`; its `oracle_spec`
   validates via `harness.state_machine_oracle.validate_spec`.
5. Run `python -m pytest tests/test_ext060_atlas_batch4_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-44 ranges, via
   `jarify-manage-links`) and flip the REQ-44 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-44] Ninth CREATE task, in a NEW background-job-processing vertical (background-job lifecycle)

### [TASK-40] Tenth CREATE task, in the ticketing vertical (event seat hold/confirm/release) (REQ-45)

#### Steps
1. In `harness/real_systems_suite.py`, add `SEAT_HOLD_TASK` (`RealSystemTask`, `cls="ticketing"`,
   `oracle_kind="conservation"`) with a contract-exact sentence for a stdlib-only single-file
   `SeatHold` class in `seat_hold.py`: `SeatHold(total_seats)` starts `available=total_seats`,
   `held=0`, `sold=0`; `hold(n)` moves `n` from `available` to `held` (reject if `n > available`,
   raise `ValueError`, leave every quantity unchanged); `confirm(n)` moves `n` from `held` to
   `sold` (reject if `n > held`); `release(n)` moves `n` from `held` back to `available`.
   `available() + held() + sold()` always equals `total_seats`. Reuse the ALREADY-LANDED
   `_grade_conservation` dispatch (REQ-15) -- no new oracle code.
2. Hand-verify (via a scratch delta walk) a drive script before adding the task to the roster:
   illegal over-hold FIRST (150 of 100 available -- reject), then a legal hold (60) and a legal
   partial confirm (40 of the 60 held), then a SECOND illegal op -- confirming 30 when only 20
   remain held (reject, proving the guard holds mid-sequence too), then a legal release (10) and
   a legal final confirm (10), landing on `expect_final = {"available": 50, "held": 0, "sold":
   50}`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_batch4_tasks.py` (same file TASK-39 creates, OFFLINE, no
   model/Jetson): a CORRECT `SeatHold` fixture is accepted by
   `grade_real_system_task(SEAT_HOLD_TASK, ...)`; a BROKEN fixture that never checks `available`
   before `hold()` (allows an over-hold) is rejected; leaves-OFF holds
   (`leaf_for_spec(SEAT_HOLD_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`; its `oracle_spec` validates via
   `harness.conservation_oracle.validate_spec`.
5. Run `python -m pytest tests/test_ext060_atlas_batch4_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-45 ranges, via
   `jarify-manage-links`) and flip the REQ-45 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-45] Tenth CREATE task, in the ticketing vertical (event seat hold/confirm/release)

### [TASK-41] Eleventh CREATE task, in the fintech vertical (AR partial-payment application ledger) (REQ-46)

#### Steps
1. In `harness/real_systems_suite.py`, add `INVOICE_AR_AGING_TASK` (`RealSystemTask`,
   `cls="fintech"`, `oracle_kind="double_entry"`) with a contract-exact sentence for a
   stdlib-only single-file `ARPaymentLedger` class in `ar_payment_application.py`, over the SAME
   `accounts_receivable`/`revenue`/`cash` three-account shape and debit-ADDS/credit-SUBTRACTS
   sign convention `INVOICE_AR_TASK` (REQ-22) already uses: `post(legs)` applies a BALANCED entry
   (sum of `debit` legs == sum of `credit` legs) and returns normally, or raises `ValueError` and
   leaves every balance unchanged for an UNBALANCED entry. Reuse the ALREADY-LANDED
   `_grade_double_entry` dispatch (REQ-17) -- no new oracle code.
2. Hand-verify (via `harness.double_entry_oracle.validate_spec` and a scratch debit/credit sum
   walk) a drive script before adding the task to the roster: an UNBALANCED posting FIRST (debit
   accounts_receivable 100000 / credit revenue 90000 -- reject), then one balanced $1000.00
   invoice posting (debit accounts_receivable / credit revenue), then TWO balanced partial-
   payment postings ($400.00 then $600.00, each debit cash / credit accounts_receivable) that
   together exactly clear the invoice -- landing on `expect_final = {"accounts_receivable": 0,
   "revenue": -100000, "cash": 100000}`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_batch4_tasks.py` (same file TASK-39/40 create, OFFLINE, no
   model/Jetson): a CORRECT `ARPaymentLedger` fixture is accepted by
   `grade_real_system_task(INVOICE_AR_AGING_TASK, ...)`; a BROKEN fixture that never checks
   debits equal credits (accepts an unbalanced posting) is rejected; leaves-OFF holds
   (`leaf_for_spec(INVOICE_AR_AGING_TASK.sentence) is None`); the task is a member of
   `REAL_SYSTEMS_TASKS`; its `oracle_spec` validates via
   `harness.double_entry_oracle.validate_spec`.
5. Run `python -m pytest tests/test_ext060_atlas_batch4_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-46 ranges, via
   `jarify-manage-links`) and flip the REQ-46 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-46] Eleventh CREATE task, in the fintech vertical (AR partial-payment application ledger)

### [TASK-42] Twelfth CREATE task, in a NEW validation-library vertical (Luhn/ISBN-13/EAN-13 check digits) (REQ-47)

#### Steps
1. In `harness/real_systems_suite.py`, add `CHECK_DIGIT_TASK` (`RealSystemTask`,
   `cls="validation"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `check_digits.py` defining `luhn_valid(number)` (standard Luhn checksum:
   double every second digit from the right, subtract 9 when the doubled value exceeds 9, sum
   every digit, valid when the total is divisible by 10), `isbn13_valid(s)`, and `ean13_valid(s)`
   (both applying the IDENTICAL EAN-13 weighted checksum -- alternating weights 1/3 across all 13
   positions left-to-right including the check digit, valid when the weighted sum is divisible by
   10) -- each returning a `bool`, and returning `False` (never raising) for a non-digit or
   wrong-length argument. Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new
   oracle code.
2. Hand-verify (via scratch checksum arithmetic against REAL published test vectors) six fixtures
   before adding the task to the roster: Luhn `4539148803436467` (valid, checksum total 80) /
   `1234567890123456` (invalid, checksum total 64); ISBN-13 `9780306406157` (valid, weighted sum
   100) / `9780306406158` (invalid, weighted sum 101); EAN-13 `4006381333931` (valid, weighted sum
   90) / `4006381333932` (invalid, weighted sum 91). Add all six as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence.
4. Extend `tests/test_ext060_atlas_batch4_tasks.py` (same file TASK-39/40/41 create, OFFLINE, no
   model/Jetson): a CORRECT `check_digits.py` fixture is accepted by
   `grade_real_system_task(CHECK_DIGIT_TASK, ...)`; a BROKEN fixture whose `luhn_valid` only
   checks digit format (never doubles/sums, so it wrongly accepts the invalid Luhn number) is
   rejected; leaves-OFF holds (`leaf_for_spec(CHECK_DIGIT_TASK.sentence) is None`); the task is a
   member of `REAL_SYSTEMS_TASKS`. Add a final roster-wide test asserting `REAL_SYSTEMS_TASKS`
   grew by exactly these four REQ-44/45/46/47 tasks (length 30 -> 34).
5. Bump the seven pre-existing hardcoded CREATE roster-size assertions
   (`len(REAL_SYSTEMS_TASKS) == 30` -> `== 34`) in `tests/test_ext060_atlas_wave1_tasks.py`,
   `tests/test_ext060_atlas_wave2_tasks.py`, `tests/test_ext060_clock_agent_tasks.py`,
   `tests/test_ext060_modify_wave2.py`, `tests/test_ext060_spec_hint.py`,
   `tests/test_ext060_ticket_booking_invoice.py`, and
   `tests/test_ext060_atlas_wave7_tasks.py`.
6. Run `python -m pytest tests/test_ext060_atlas_batch4_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; 34-item CREATE roster). Update `.jarify/EXT-060/index.json`
   (REQ-47 ranges, via `jarify-manage-links`) and flip the REQ-47 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-47] Twelfth CREATE task, in a NEW validation-library vertical (Luhn/ISBN-13/EAN-13 check digits)

### [TASK-43] Thirteenth CREATE task, in a NEW fintech-calculator vertical (Net Present Value) (REQ-48)

#### Steps
1. In `harness/real_systems_suite.py`, add `NPV_CALCULATOR_TASK` (`RealSystemTask`,
   `cls="fintech"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `npv.py` defining one function `npv(rate, cashflows)`: `cashflows[t]` is
   discounted by `(1 + rate) ** t` (so `t=0` is NEVER discounted), returns the sum ROUNDED to
   exactly 2 decimal places via Python's `round(value, 2)`. Reuse the ALREADY-LANDED
   `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via independent recomputation, not trusted blindly) three vectors before adding
   the task to the roster: `npv(0.1, [-1000, 500, 500, 500])` -> `243.42599549211099` -> rounds to
   `243.43`; `npv(0.0, [-100, 50, 50])` -> `0.0`; `npv(0.05, [100])` -> `100.0` (a single `t=0`
   inflow is never discounted). Add all three as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free; confirm no banned leaf keyword appears in the sentence and
   `leaf_for_spec(NPV_CALCULATOR_TASK.sentence) is None`.
4. Add `tests/test_ext060_wave8_import_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `npv.py` fixture is accepted by `grade_real_system_task(NPV_CALCULATOR_TASK, ...)`; a BROKEN
   fixture that discounts the `t=0` cashflow too (uses exponent `t+1` for every entry, an
   off-by-one bug) is rejected; leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_wave8_import_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-48 ranges, via
   `jarify-manage-links`) and flip the REQ-48 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-48] Thirteenth CREATE task, in a NEW fintech-calculator vertical (Net Present Value)

### [TASK-44] Fourteenth CREATE task, in a NEW scheduling/devtools vertical (closed-interval merge) (REQ-49)

#### Steps
1. In `harness/real_systems_suite.py`, add `INTERVAL_MERGE_TASK` (`RealSystemTask`,
   `cls="scheduling"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `interval_merge.py` defining one function `merge(intervals)`: a list of
   closed `[start, end]` integer intervals, NOT necessarily sorted, merged into a sorted,
   non-overlapping list where any two intervals that overlap OR merely TOUCH (`start <= end` of
   the previous merged interval) are combined. Reuse the ALREADY-LANDED `_grade_import` dispatch
   (REQ-3) -- no new oracle code.
2. Hand-verify (via a scratch walk) four vectors before adding the task to the roster:
   `merge([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]`; `merge([[1,4],[4,5]]) ==
   [[1,5]]` (the touching-interval case that a strict `<` overlap test would miss);
   `merge([]) == []`; `merge([[5,5]]) == [[5,5]]`. Add all four as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(INTERVAL_MERGE_TASK.sentence) is None`.
4. Extend `tests/test_ext060_wave8_import_tasks.py` (same file TASK-43 creates, OFFLINE, no
   model/Jetson): a CORRECT `interval_merge.py` fixture is accepted by
   `grade_real_system_task(INTERVAL_MERGE_TASK, ...)`; a BROKEN fixture using a strict `<`
   overlap test (fails to merge touching intervals) is rejected; leaves-OFF holds; the task is a
   member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_wave8_import_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-49 ranges, via
   `jarify-manage-links`) and flip the REQ-49 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-49] Fourteenth CREATE task, in a NEW scheduling/devtools vertical (closed-interval merge)

### [TASK-45] Fifteenth CREATE task, in a NEW devtools vertical (RFC 4648 Base32 codec) (REQ-50)

#### Steps
1. In `harness/real_systems_suite.py`, add `BASE32_CODEC_TASK` (`RealSystemTask`,
   `cls="devtools"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `base32_codec.py` defining `encode(data)` (a `list[int]` of byte values 0-
   255 -> an RFC 4648 Base32 `str` WITH standard `=` padding) and `decode(s)` (a padded Base32
   `str` -> a `list[int]` of byte values), using JSON-safe `list[int]` byte representations
   throughout (never a raw `bytes` object, which cannot cross the import-driver's JSON-argument
   boundary). Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (against Python's own `base64.b32encode`/`base64.b32decode`, the RFC 4648
   reference implementation) before adding the task to the roster: `encode([]) == ""`;
   `encode([102]) == "MY======"`; `encode([102,111,111]) == "MZXW6==="`;
   `encode([102,111,111,98,97,114]) == "MZXW6YTBOI======"`; `decode("MY======") == [102]`;
   `decode("MZXW6YTBOI======") == [102,111,111,98,97,114]`. Add a chained round-trip check
   (`decode` applied to the prior `encode_foobar` call's own result via a `{"__jaros_ref__":
   "encode_foobar"}` argument) also equaling `[102,111,111,98,97,114]`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(BASE32_CODEC_TASK.sentence) is None`.
4. Extend `tests/test_ext060_wave8_import_tasks.py` (same file TASK-43/44 create, OFFLINE, no
   model/Jetson): a CORRECT `base32_codec.py` fixture is accepted by
   `grade_real_system_task(BASE32_CODEC_TASK, ...)`; a BROKEN fixture that strips the required
   `=` padding is rejected; leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_wave8_import_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only). Update `.jarify/EXT-060/index.json` (REQ-50 ranges, via
   `jarify-manage-links`) and flip the REQ-50 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-50] Fifteenth CREATE task, in a NEW devtools vertical (RFC 4648 Base32 codec)

### [TASK-46] Sixteenth CREATE task, in a NEW logistics/geo vertical (haversine distance) (REQ-51)

#### Steps
1. In `harness/real_systems_suite.py`, add `HAVERSINE_DISTANCE_TASK` (`RealSystemTask`,
   `cls="logistics"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `geo_distance.py` defining one function `distance_km(lat1, lon1, lat2,
   lon2)`: the standard haversine great-circle formula with `R = 6371.0` km, converting every
   coordinate to radians via `math.radians` before any `sin`/`cos` call, returning the result
   ROUNDED to exactly 2 decimal places via `round(value, 2)`. Reuse the ALREADY-LANDED
   `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via independent recomputation with Python's own `math` module, not trusted
   blindly) three vectors before adding the task to the roster: `distance_km(0, 0, 0, 0) == 0.0`;
   `distance_km(0, 0, 0, 90)` -> `10007.543398010288` -> rounds to `10007.54`;
   `distance_km(52.2296, 21.0122, 52.4064, 16.9252)` [Warsaw -> Poznan] -> `278.4550198592262` ->
   rounds to `278.46` (the ACTUAL recomputed value, not a naive round-to-nearest-int guess of
   279). Add all three as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(HAVERSINE_DISTANCE_TASK.sentence) is None`.
4. Extend `tests/test_ext060_wave8_import_tasks.py` (same file TASK-43/44/45 create, OFFLINE, no
   model/Jetson): a CORRECT `geo_distance.py` fixture is accepted by
   `grade_real_system_task(HAVERSINE_DISTANCE_TASK, ...)`; a BROKEN fixture that never converts
   degrees to radians before `sin`/`cos` is rejected; leaves-OFF holds; the task is a member of
   `REAL_SYSTEMS_TASKS`. Add a final roster-wide test asserting `REAL_SYSTEMS_TASKS` grew by
   exactly these four REQ-48/49/50/51 tasks (length 34 -> 38).
5. Bump the eight pre-existing hardcoded CREATE roster-size assertions
   (`len(REAL_SYSTEMS_TASKS) == 34` -> `== 38`) in `tests/test_ext060_atlas_batch4_tasks.py`,
   `tests/test_ext060_atlas_wave1_tasks.py`, `tests/test_ext060_atlas_wave2_tasks.py`,
   `tests/test_ext060_atlas_wave7_tasks.py`, `tests/test_ext060_clock_agent_tasks.py`,
   `tests/test_ext060_modify_wave2.py`, `tests/test_ext060_spec_hint.py`, and
   `tests/test_ext060_ticket_booking_invoice.py`.
6. Run `python -m pytest tests/test_ext060_wave8_import_tasks.py tests/test_ext060*.py -q`;
   confirm green (offline only; 38-item CREATE roster). Update `.jarify/EXT-060/index.json`
   (REQ-51 ranges, via `jarify-manage-links`) and flip the REQ-51 acceptance boxes in
   `requirements.md`.

#### Implements
- [REQ-51] Sixteenth CREATE task, in a NEW logistics/geo vertical (haversine distance)

### [TASK-47] Seventeenth CREATE task ("batch-5"), in a NEW fintech-calculator vertical (loan amortization) (REQ-52)

#### Steps
1. In `harness/real_systems_suite.py`, add `LOAN_AMORTIZATION_TASK` (`RealSystemTask`,
   `cls="fintech"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `loan_amortization.py` defining one function `schedule(principal,
   annual_rate, n_months)`: integer-cents throughout, level monthly payment `M = round(principal *
   r / (1 - (1 + r) ** -n_months))` for every month except the last, with the FINAL month's
   principal set to exactly the remaining balance (so the schedule always ends on `balance: 0`).
   Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via an independent scratch Python walk of the exact formula, not trusted blindly)
   two vectors before adding the task to the roster: `schedule(1200, 0.12, 1)` -> `[{"payment":
   1212, "interest": 12, "principal": 1200, "balance": 0}]`; `schedule(120000, 0.12, 3)` -> a
   three-row schedule with principal columns `39603/39999/40398` (summing to `120000`) and a final
   `balance: 0`. Add both as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free; confirm no banned leaf keyword appears in the sentence and
   `leaf_for_spec(LOAN_AMORTIZATION_TASK.sentence) is None`.
4. Add `tests/test_ext060_batch5_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `loan_amortization.py` fixture is accepted by `grade_real_system_task(LOAN_AMORTIZATION_TASK,
   ...)`; a BROKEN fixture that never special-cases the final month (reuses the level payment for
   every row, so the final balance lands on `-1` cent instead of `0`) is rejected; leaves-OFF
   holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch5_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-52 ranges, via
   `jarify-manage-links`) and flip the REQ-52 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-52] Seventeenth CREATE task ("batch-5"), in a NEW fintech-calculator vertical (loan amortization)

### [TASK-48] Eighteenth CREATE task ("batch-5"), in a NEW analytics vertical (running median) (REQ-53)

#### Steps
1. In `harness/real_systems_suite.py`, add `RUNNING_MEDIAN_TASK` (`RealSystemTask`,
   `cls="analytics"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `running_median.py` defining one function `running_medians(stream)`: for
   each prefix `stream[0:i+1]`, an ODD-length prefix's median is the sorted middle value, an
   EVEN-length prefix's median is the true-division mean of the two sorted middle values. Reuse
   the ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via an independent scratch Python walk, a plain sorted-insert simulation, not
   trusted blindly) three vectors before adding the task to the roster: `running_medians([5, 15,
   1, 3]) == [5, 10.0, 5, 4.0]`; `running_medians([2, 4]) == [2, 3.0]`; `running_medians([7]) ==
   [7]`. Add all three as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(RUNNING_MEDIAN_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch5_tasks.py` (same file TASK-47 creates, OFFLINE, no
   model/Jetson): a CORRECT `running_median.py` fixture is accepted by
   `grade_real_system_task(RUNNING_MEDIAN_TASK, ...)`; a BROKEN fixture that returns the running
   MEAN instead of the running median is rejected (caught by the mixed-length vector's 3rd/4th
   entries diverging); leaves-OFF holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch5_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-53 ranges, via
   `jarify-manage-links`) and flip the REQ-53 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-53] Eighteenth CREATE task ("batch-5"), in a NEW analytics vertical (running median)

### [TASK-49] Nineteenth CREATE task ("batch-5"), in a NEW devops/SaaS vertical (incident escalation) (REQ-54)

#### Steps
1. In `harness/real_systems_suite.py`, add `INCIDENT_ESCALATION_TASK` (`RealSystemTask`,
   `cls="devops"`, `oracle_kind="state_machine"`) with a contract-exact sentence for a stdlib-only
   single-file `Incident` class in `incident_escalation.py`: states `"open"`/`"acknowledged"`/
   `"investigating"`/`"resolved"`/`"closed"`; actions `acknowledge()`/`investigate()`/`resolve()`/
   `close()`/`reopen()`, with `reopen()` legal from EITHER `"resolved"` OR `"closed"` (mirroring
   `JOB_QUEUE_LIFECYCLE_TASK`'s own two-source-state action shape). Reuse the ALREADY-LANDED
   `_grade_state_machine` dispatch (REQ-13) -- no new oracle code.
2. Hand-verify (via a scratch walk of the transition table) the driven script before adding the
   task to the roster: illegal `resolve()`-from-`"open"` and `close()`-from-`"open"` (both
   skip-ahead, must reject) FIRST, then the full legal path `acknowledge -> investigate -> resolve
   -> close` to `"closed"`, then a third illegal `acknowledge()`-from-`"closed"` (must ALSO
   reject, proving the guard holds after the terminal state). `expect_final == "closed"`.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm none of
   `acknowledge`/`investigate`/`resolve`/`close`/`reopen`/`incident`/`escalation` appears in
   `harness.adt_oracle._KEYWORDS`/`_METHOD_TOKENS`, no banned leaf keyword appears in the
   sentence, and `leaf_for_spec(INCIDENT_ESCALATION_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch5_tasks.py` (same file TASK-47/48 create, OFFLINE, no
   model/Jetson): a CORRECT `Incident` fixture is accepted by
   `grade_real_system_task(INCIDENT_ESCALATION_TASK, ...)`; a BROKEN fixture that allows an
   illegal transition (e.g. `resolve()` from any state) is rejected; leaves-OFF holds; the task is
   a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch5_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-54 ranges, via
   `jarify-manage-links`) and flip the REQ-54 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-54] Nineteenth CREATE task ("batch-5"), in a NEW devops/SaaS vertical (incident escalation)

### [TASK-50] Twentieth CREATE task ("batch-5"), in a NEW logistics vertical (warehouse stock reservation) (REQ-55)

#### Steps
1. In `harness/real_systems_suite.py`, add `WAREHOUSE_STOCK_RESERVATION_TASK` (`RealSystemTask`,
   `cls="logistics"`, `oracle_kind="conservation"`) with a contract-exact sentence for a
   stdlib-only single-file `StockReservation` class in `warehouse_stock_reservation.py`:
   quantities `on_hand`/`reserved`/`shipped`; `reserve(n)` (on_hand->reserved, rejects over-
   reserve), `unreserve(n)` (reserved->on_hand), `ship(n)` (reserved->shipped, rejects over-ship).
   Use "reservation"/"reserve"/"ship" throughout (never "hold"/"queue"/"cache"/"expire"/"stack"/
   "buffer"/"ring"). Reuse the ALREADY-LANDED `_grade_conservation` dispatch (REQ-15) -- no new
   oracle code.
2. Hand-verify (via a scratch walk of the delta bookkeeping) the driven script before adding the
   task to the roster: illegal `reserve(150)` (over the initial `on_hand=100`, must reject), then
   legal `reserve(60)` and `ship(40)`, then illegal `ship(30)` (over the remaining `reserved=20`,
   must ALSO reject), then legal `unreserve(20)`, `reserve(10)`, `ship(10)`, landing on
   `expect_final == {"on_hand": 50, "reserved": 0, "shipped": 50}` (summing to the initial
   `total_units` of `100`).
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and
   `leaf_for_spec(WAREHOUSE_STOCK_RESERVATION_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch5_tasks.py` (same file TASK-47/48/49 create, OFFLINE, no
   model/Jetson): a CORRECT `StockReservation` fixture is accepted by
   `grade_real_system_task(WAREHOUSE_STOCK_RESERVATION_TASK, ...)`; a BROKEN fixture that allows
   an over-reserve (never checks `on_hand`) is rejected; leaves-OFF holds; the task is a member of
   `REAL_SYSTEMS_TASKS`. Add a final roster-wide test asserting `REAL_SYSTEMS_TASKS` grew by
   exactly these four REQ-52/53/54/55 tasks (length 38 -> 42).
5. Bump the ten pre-existing hardcoded CREATE roster-size assertions
   (`len(REAL_SYSTEMS_TASKS) == 38` -> `== 42`) in `tests/test_ext060_atlas_batch4_tasks.py`,
   `tests/test_ext060_atlas_wave1_tasks.py`, `tests/test_ext060_atlas_wave2_tasks.py`,
   `tests/test_ext060_atlas_wave7_tasks.py`, `tests/test_ext060_clock_agent_tasks.py`,
   `tests/test_ext060_modify_wave2.py`, `tests/test_ext060_spec_hint.py`,
   `tests/test_ext060_ticket_booking_invoice.py`, and `tests/test_ext060_wave8_import_tasks.py`.
6. Run `python -m pytest tests/test_ext060_*.py -q`; confirm green (offline only; 42-item CREATE
   roster). Update `.jarify/EXT-060/index.json` (REQ-55 ranges, via `jarify-manage-links`) and flip
   the REQ-55 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-55] Twentieth CREATE task ("batch-5"), in a NEW logistics vertical (warehouse stock reservation)

### [TASK-51] Twenty-first CREATE task ("batch-6"), in a NEW devtools vertical (Roman-numeral codec) (REQ-56)

#### Steps
1. In `harness/real_systems_suite.py`, add `ROMAN_NUMERAL_CODEC_TASK` (`RealSystemTask`,
   `cls="devtools"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `roman_numeral_codec.py` defining `to_roman(n)` (1..3999 -> uppercase Roman
   numeral using SUBTRACTIVE notation for every four-and-nine place value, e.g. `"IV"` never
   `"IIII"`) and `from_roman(s)` (the inverse). Reuse the ALREADY-LANDED `_grade_import` dispatch
   (REQ-3) -- no new oracle code.
2. Hand-verify (via an independent scratch Python walk of the classical value/symbol table, not
   trusted blindly) seven vectors before adding the task to the roster: `to_roman(4) == "IV"`;
   `to_roman(9) == "IX"`; `to_roman(58) == "LVIII"`; `to_roman(1994) == "MCMXCIV"`;
   `to_roman(3999) == "MMMCMXCIX"`; `from_roman("MCMXCIV") == 1994`; a chained round-trip
   (`from_roman(to_roman(444)) == 444`, via a `__jaros_ref__`). Add all as `api_calls`/`checks`
   entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced (static `leaf_for_spec` + post-build
   `build_path` check) + leak-free; confirm no banned leaf keyword appears in the sentence and
   `leaf_for_spec(ROMAN_NUMERAL_CODEC_TASK.sentence) is None`.
4. Add `tests/test_ext060_batch6_tasks.py` (new file, OFFLINE, no model/Jetson): a CORRECT
   `roman_numeral_codec.py` fixture is accepted by
   `grade_real_system_task(ROMAN_NUMERAL_CODEC_TASK, ...)`; a BROKEN fixture using ADDITIVE-ONLY
   notation (no subtractive pairs, so `to_roman(4) == "IIII"`) is rejected; leaves-OFF holds; the
   task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch6_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-56 ranges, via
   `jarify-manage-links`) and flip the REQ-56 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-56] Twenty-first CREATE task ("batch-6"), in a NEW devtools vertical (Roman-numeral codec)

### [TASK-52] Twenty-second CREATE task ("batch-6"), in a NEW fintech vertical (banker's rounding) (REQ-57)

#### Steps
1. In `harness/real_systems_suite.py`, add `BANKERS_ROUNDING_TASK` (`RealSystemTask`,
   `cls="fintech"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `bankers_rounding.py` defining one function `round_half_even(x,
   ndigits=0)`: PIN the exact round-half-to-EVEN convention in plain language (a value exactly
   halfway between two candidates rounds to whichever candidate has an EVEN final digit, never
   always-up or always-down), require constructing the `decimal.Decimal` via
   `decimal.Decimal(str(x))` (never `decimal.Decimal(x)` directly, to avoid binary float
   representation error), and pin the int-vs-float return contract by `ndigits`. Reuse the
   ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via `decimal.Decimal(str(x)).quantize(..., rounding=decimal.ROUND_HALF_EVEN)`,
   not trusted blindly) six vectors chosen to be EXACTLY representable in IEEE-754 binary (never
   an ambiguous literal like `2.675`) before adding the task to the roster: `round_half_even(2.5)
   == 2`; `round_half_even(3.5) == 4`; `round_half_even(0.5) == 0`; `round_half_even(1.5) == 2`;
   `round_half_even(0.125, 2) == 0.12`; `round_half_even(0.375, 2) == 0.38`. Add all as
   `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(BANKERS_ROUNDING_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch6_tasks.py` (same file TASK-51 creates, OFFLINE, no
   model/Jetson): a CORRECT `bankers_rounding.py` fixture is accepted by
   `grade_real_system_task(BANKERS_ROUNDING_TASK, ...)`; a BROKEN fixture using round-HALF-UP
   (always away from zero) is rejected (caught by the 2.5/0.5/0.125 vectors diverging); leaves-OFF
   holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch6_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-57 ranges, via
   `jarify-manage-links`) and flip the REQ-57 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-57] Twenty-second CREATE task ("batch-6"), in a NEW fintech vertical (banker's rounding)

### [TASK-53] Twenty-third CREATE task ("batch-6"), in a NEW data-pipeline vertical (run-length codec) (REQ-58)

#### Steps
1. In `harness/real_systems_suite.py`, add `RUN_LENGTH_CODEC_TASK` (`RealSystemTask`,
   `cls="data"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `run_length_codec.py` defining `encode(s)` (a `str` -> a `list` of exactly
   `[character, count]` two-element pairs, one per MAXIMAL run of identical consecutive
   characters, INCLUDING the final run) and `decode(pairs)` (the inverse). Reuse the
   ALREADY-LANDED `_grade_import` dispatch (REQ-3) -- no new oracle code.
2. Hand-verify (via an independent scratch maximal-run walk, not trusted blindly) five vectors
   before adding the task to the roster: `encode("aaabbc") == [["a", 3], ["b", 2], ["c", 1]]`;
   `encode("") == []`; `encode("aaaa") == [["a", 4]]`; `decode([["a", 3], ["b", 2], ["c", 1]]) ==
   "aaabbc"`; a chained round-trip (`decode(encode("aaabbc")) == "aaabbc"`, via a
   `__jaros_ref__`). Add all as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(RUN_LENGTH_CODEC_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch6_tasks.py` (same file TASK-51/52 create, OFFLINE, no
   model/Jetson): a CORRECT `run_length_codec.py` fixture is accepted by
   `grade_real_system_task(RUN_LENGTH_CODEC_TASK, ...)`; a BROKEN fixture that forgets to flush
   the FINAL run after its scan loop ends (dropping the trailing run) is rejected; leaves-OFF
   holds; the task is a member of `REAL_SYSTEMS_TASKS`.
5. Run `python -m pytest tests/test_ext060_batch6_tasks.py tests/test_ext060_*.py -q`; confirm
   green (offline only). Update `.jarify/EXT-060/index.json` (REQ-58 ranges, via
   `jarify-manage-links`) and flip the REQ-58 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-58] Twenty-third CREATE task ("batch-6"), in a NEW data-pipeline vertical (run-length codec)

### [TASK-54] Twenty-fourth CREATE task ("batch-6"), in a NEW fintech-billing vertical (penny allocation) (REQ-59)

#### Steps
1. In `harness/real_systems_suite.py`, add `PENNY_ALLOCATION_TASK` (`RealSystemTask`,
   `cls="fintech"`, `oracle_kind="import"`) with a contract-exact sentence for a stdlib-only
   single-file module `penny_allocation.py` defining one function `allocate(total_cents,
   weights)`: base share `share[i] = (total_cents * weights[i]) // sum(weights)` (integer floor
   division, never float), with the leftover-remainder rule PINNED exactly: add 1 cent to each of
   the FIRST `remainder` parts in index order (never the last parts, never a
   largest-fractional-remainder sort). Reuse the ALREADY-LANDED `_grade_import` dispatch (REQ-3)
   -- no new oracle code.
2. Hand-verify (via the exact pinned algorithm, not trusted blindly) four vectors before adding
   the task to the roster: `allocate(100, [1, 1, 1]) == [34, 33, 33]`; `allocate(100, [1, 1]) ==
   [50, 50]`; `allocate(1000, [7, 3]) == [700, 300]`; `allocate(5, [1, 1, 1]) == [2, 2, 1]`. Add
   all as `api_calls`/`checks` entries.
3. Add it to `REAL_SYSTEMS_TASKS`. Keep leaves-OFF enforced + leak-free; confirm no banned leaf
   keyword appears in the sentence and `leaf_for_spec(PENNY_ALLOCATION_TASK.sentence) is None`.
4. Extend `tests/test_ext060_batch6_tasks.py` (same file TASK-51/52/53 create, OFFLINE, no
   model/Jetson): a CORRECT `penny_allocation.py` fixture is accepted by
   `grade_real_system_task(PENNY_ALLOCATION_TASK, ...)`; a BROKEN fixture that computes the base
   floor shares but never redistributes the remainder (losing cents) is rejected; leaves-OFF
   holds; the task is a member of `REAL_SYSTEMS_TASKS`. Add a final roster-wide test asserting
   `REAL_SYSTEMS_TASKS` grew by exactly these four REQ-56/57/58/59 tasks (length 42 -> 46).
5. Bump the ten pre-existing hardcoded CREATE roster-size assertions
   (`len(REAL_SYSTEMS_TASKS) == 42` -> `== 46`) in `tests/test_ext060_atlas_batch4_tasks.py`,
   `tests/test_ext060_atlas_wave1_tasks.py`, `tests/test_ext060_atlas_wave2_tasks.py`,
   `tests/test_ext060_atlas_wave7_tasks.py`, `tests/test_ext060_batch5_tasks.py`,
   `tests/test_ext060_clock_agent_tasks.py`, `tests/test_ext060_modify_wave2.py`,
   `tests/test_ext060_spec_hint.py`, `tests/test_ext060_ticket_booking_invoice.py`, and
   `tests/test_ext060_wave8_import_tasks.py`.
6. Run `python -m pytest tests/test_ext060_*.py -q`; confirm green (offline only; 46-item CREATE
   roster). Update `.jarify/EXT-060/index.json` (REQ-59 ranges, via `jarify-manage-links`) and flip
   the REQ-59 acceptance boxes in `requirements.md`.

#### Implements
- [REQ-59] Twenty-fourth CREATE task ("batch-6"), in a NEW fintech-billing vertical (penny allocation)
