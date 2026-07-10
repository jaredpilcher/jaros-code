# Design — Real-systems capability suite

`harness/real_systems_suite.py` defines a small set of `RealSystemTask`s (real systems from a sentence),
each pinned to ONE of the landed independent oracles, and a runner that builds each task via
`build_system` with the leaf path OFF and grades ONLY by that task's black-box oracle.

```text
   real_systems_suite.py
     RealSystemTask{ name, cls, sentence, oracle_kind, oracle_spec }
     run_real_systems_suite(tasks, llm) -- per-task pass@1, leaves-OFF asserted
        |
        +-- oracle_kind='fs'   -> harness/fs_oracle.py (seed tree -> run -> independent byte-compare)
        +-- oracle_kind='import' -> harness/import_driver.py (import built module, injected clock)
        +-- oracle_kind='cli-exact' -> exact-stdout/rc check variants (harness/system_suite.py)
```

Guardrails (Tenet 3), enforced in the runner: assert no leaf fingerprint fires for these specs
(`leaf_for_spec` disabled / classifier asserted False); grade only by the task's own oracle output
(never the model's self-acceptance, never a reference implementation); every expected value derives from
the visible sentence; pass@1, frozen held-out. A green earned by a template is a Tenet-3 violation.

## The canonical two-half scoreboard (REQ-7/REQ-8)

EXT-060 is now THE canonical real-systems scoreboard, not just the CREATE half above. A MODIFY half
composes `harness.system_builder.modify_system` with the SAME independent-oracle dispatcher the CREATE
half already uses (`grade_real_system_task` — no new oracle code, no divergent grading path for the two
halves), and a single unified runner reports ONE combined pass@1:

```text
                         sentence
                            |
              +-------------+--------------+
              |                             |
        CREATE half                    MODIFY half
   build_system(spec, root)   modify_system(start_system, mod_sentence, root)
   -> RealSystemTask                  -> RealSystemModifyTask
   (harness.real_systems_suite)       (harness.real_systems_suite)
              |                             |
              +-------------+--------------+
                            |
              grade_real_system_task(task, root)   <-- SAME dispatcher, both halves
                            |
        +-------------------+-------------------+
        |                   |                   |
   oracle_kind="fs"   oracle_kind="import"  oracle_kind="cli-exact"
   harness.fs_oracle  harness.import_driver harness.system_suite's
   (seed -> run ->    (sandboxed import +   exact_stdout check
    independent        driven API calls,     variant
    byte-compare)       sentinel-reported)
        |                   |                   |
        +-------------------+-------------------+
                            |
              run_canonical_scoreboard(llm=...)
        {"create": {...}, "modify": {...},
         "combined": {"n", "passed", "pass_rate"}}
                            |
              ONE headline: combined pass@1, tracked over time
```

Killable execution (REQ-8): the same subprocess-per-build-with-timeout-and-kill pattern already proven
by `.jaros-data/realsys_build_one.py` + `.jaros-data/realsys_killable.py` for the CREATE half is reused
(not reinvented) so a pathological CREATE build or MODIFY draw can never wedge the whole canonical run
— each task's build/modify+grade happens in its own subprocess, bounded by a per-task wall-clock kill.

## The first SaaS rung (REQ-9/REQ-10): `oracle_kind="service"`

The first held-out task shaped like a REAL backend service (not a CLI/library): a stdlib REST API
persisting to SQLite. Grading composes two ALREADY-LANDED independent oracles — never a new
process-launch/teardown mechanism, never trusting the service's own HTTP responses for durability:

```text
        REST_SQLITE_CRUD_TASK.sentence            REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence
                    |                                            |
              build_system(...)                         modify_system(start_system, ...)
                    |                                            |
                    +--------------------+-----------------------+
                                         |
                          grade_real_system_task(task, root)
                             oracle_kind="service"
                                         |
                                  _grade_service(spec, root)
                                         |
                    +--------------------+-----------------------+
                    |                                             |
     (a) serve_and_check_stdlib(root, entry,           (b) AFTER teardown: independently
         http_checks)  -- REAL localhost HTTP,              re-open the SQLite file
         REAL subprocess server, ephemeral port             (harness.datastore_oracle helpers /
         (harness/server_oracle.py, unchanged                inline stdlib sqlite3) and assert
         launch/poll/teardown machinery; `http_check`        the persisted row-count -- catches
         dict gains one new optional key, `json_body`,       a service that only kept state
         so a POST/PUT check can send a real JSON             in-memory (HTTP looks right, disk
         request body -- everything else byte-identical)      state does not)
                    |                                             |
                    +--------------------+-----------------------+
                                         |
                        (accepted, note) -- never raises,
                        same shape every other oracle_kind returns
```

The `json_body` extension to `harness/server_oracle.py`'s `http_check` contract is the ONE new piece of
execution-plane machinery this pair of requirements needs: `serve_and_check_stdlib`'s prior contract
(`method`/`path`/`status`/`json_contains`/`body_contains`) had no way to send a REQUEST body at all, so
a REST CRUD API's `POST`/`PUT` endpoints (which the sentence explicitly requires to accept `{"name":
...}`) could not be exercised honestly without it. The extension is additive and backward-compatible —
every existing `http_check` (across `server_oracle`'s own tests and every earlier EXT-060 task) that
omits `json_body` sends the exact same request as before.

**Demoted (regression checks / feeders, NOT the tracked number):** `harness/system_suite.py`'s toy-CLI
creation suite, `harness/modification_suite.py`, and `harness/daily_driver.py`. They keep running as
fast local regression signals and as a source of new task shapes to graduate into EXT-060's fixed,
growing roster — but the number that gets quoted, trended, and steered from is EXT-060's combined
pass@1, and only that.
