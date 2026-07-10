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
