# Implementation Tasks

### [TASK-1] Durable session store extension + `-c`/`-r`/`--fork` CLI entry points

Extend `harness/session.py`'s existing durable session store (name, timestamps, an
`index.json`, resolve-by-id-or-name, most-recent lookup, fork-with-copy) and wire `-c`/
`--continue`, `-r <id|name>`, and `--fork [<id|name>]` into `harness/cli.py`'s existing
headless argument parser (EXT-043) and REPL, without changing the orchestrator/agents.

#### Steps
1. In `harness/session.py`, extend `Session.__init__`/`to_dict`/`from_dict` with optional
   `name: str | None`, `created: float`, `last_active: float` (defaulting to "now" when not
   given), and update `append()` to bump `last_active`. Add `INDEX_FILENAME = "index.json"`,
   `_index_path()`, `_load_index()`/`_save_index()` (never raise; a missing/corrupt index
   degrades to `{}`), and update `save_session()` to also write an index entry
   (`{name, created, last_active}`) for the session's id. Update `list_sessions()` to skip the
   index file itself and to surface `name`/`last_active` per row.
2. Add `resolve_session_ref(ref) -> str | None` (exact-id-file-exists, else name lookup via the
   index, most-recently-active match wins on a name collision), `most_recent_session_id() -> str
   | None` (max `last_active` over the index, with a file-mtime fallback via `list_sessions` for
   a pre-EXT-044 sessions dir), `fork_session(ref) -> Session | None` (resolve → `load_session` →
   construct a NEW `Session` with a copied turns list and a fresh id → `save_session` the new one
   → return it; the source is only ever read), and `set_session_name(session, name) -> None`
   (assign + persist). All never raise.
3. In `harness/cli.py`, add `_parse_session_flags(rest: list[str])`: a linear scan of the tokens
   `_parse_headless_args` (EXT-043, unmodified) left in `rest`, recognizing `-c`/`--continue` (no
   value), `-r <id|name>` (a value), `--fork` (an OPTIONAL following value — consumed only when
   it resolves to a real session via `resolve_session_ref`, else `--fork` takes no value and the
   next token stays in `rest`), and `--name <name>` (a value). Returns `(continue_flag,
   resume_ref, fork_ref, name_to_set, rest)`.
4. Add `_resolve_session_target(continue_flag, resume_ref, fork_ref, legacy_resume_id)`: priority
   order `--fork` (source = `fork_ref or resume_ref or legacy_resume_id or
   most_recent_session_id()`; call `fork_session`; error if source is falsy or fork fails) → `-c`
   (`most_recent_session_id()`; error if none) → `-r` (`resolve_session_ref(resume_ref)`; error if
   unresolved) → fall through to `legacy_resume_id` UNCHANGED (may be `None`, or the literal
   pre-EXT-044 `--resume <id>` value — no existence check, preserving its exact prior semantics).
   Returns `(session_id, error_message)`; never raises (wrap in `try/except`, turn any exception
   into an error string).
5. Wire it into `main()`: after `_parse_headless_args` + `_parse_session_flags`, call
   `_resolve_session_target(...)`; on an error, print it (red text or a `json.dumps` error object
   per `output_format`, mirroring `_run_one_shot`'s existing error shape) and `return 1`
   IMMEDIATELY — before either `repl()` or `_run_one_shot()` is reached, so an unresolvable
   reference never constructs `JcodeCli`. On success, use the resolved id exactly where
   `session_id` was used before. Keep `repl(session_id=...)`'s call SHAPE unchanged (one keyword
   argument only — do not add `name_to_set` there). Add a 5th, defaulted `name_to_set: str | None
   = None` parameter to `_run_one_shot`, applying it via `set_session_name` right after
   constructing `JcodeCli` (before calling `.handle()`). Update `main()`'s docstring with the new
   invocation forms.
6. Add a `/name <name>` REPL command (`JcodeCli.cmd_name`, reflection-dispatched like
   `cmd_new`/`cmd_resume`) that renames the CURRENT session via `set_session_name`, and a `/fork
   [<id|name>]` REPL command (`cmd_fork`) that forks a session via `fork_session` and switches the
   REPL's active `self.session` to the new fork (mirrors `cmd_resume`'s shape). Update the
   `/help` command list docstring with `-c`/`-r`/`--fork`, `/name`, and `/fork`.
7. Write `tests/test_ext044_sessions.py` (deterministic, no live gemma — mirrors
   `tests/test_ext043_headless.py`'s `JcodeCli` stubbing and `tests/test_ext036_cli_session.py`'s
   stub-orchestrator pattern, isolating `harness.session.SESSIONS_DIR` to a tmp dir): store-level
   create→persist→list→resolve-by-name→most-recent→fork-with-independent-copy tests directly
   against `harness.session`; CLI-level `-c`/`-r <id>`/`-r <name>`/`--fork` routing tests via
   `main()` with a stubbed `JcodeCli` (asserting the resolved `session_id` reaching the stub, and
   the honest non-zero exit + no-`JcodeCli`-construction on an unknown ref); a real (unstubbed)
   `JcodeCli` + stub-orchestrator test proving a resumed session's prior turns appear in the
   assembled `handle()` context; a byte-identical no-flags regression test; and a
   never-raises-on-corrupt-index test.
8. Update `harness/product_parity.py` row #12 (`id=12`) honestly: flip `state` to `"works"` only
   if `-c`/`-r <id|name>`/`--fork`/naming/context-load are ALL genuinely delivered and
   test-covered by this task (else `"partial"` with an honest `current_state` naming what's
   missing); update `current_state`/`next_lever` accordingly. Mirror the same honest update into
   `docs/GAP-MAP.md` row #12's `State`/`Current honest state`/`Next lever` columns, and update
   `tests/test_ext041_product_parity.py`'s honesty-pin (`works == [...]`) and the
   `n_works`/aggregate-bound assertions to match — the same mirroring EXT-042/EXT-043 each did on
   landing.

#### Implements
- [REQ-1] Durable session store: name + timestamps + index
- [REQ-2] `-c` / `--continue` resumes the most recent session
- [REQ-3] `-r <id|name>` resumes a specific session by id or name
- [REQ-4] `--fork [<id|name>]` branches a session
- [REQ-5] Resumed context is loaded; fresh runs stay byte-identical
