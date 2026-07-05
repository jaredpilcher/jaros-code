# EXT-044 — Design

## Problem

`harness/session.py` (EXT-036 REQ-12/15) already IS a durable conversation session: an ordered
transcript of `{role, text, ts}` turns persisted to `.jaros-data/sessions/<id>.json`, with
`/new`, `/resume <id>`, `/sessions`, and a bounded/condensed context slice (`recent()`/
`condense()`) already wired into `JcodeCli.handle()`'s orchestrator routing. GAP-MAP row #12
names three concrete missing pieces on top of that store: (1) a session NAME (today only the
raw hex id addresses a session), (2) a "most-recently-active session" lookup for `-c`/
`--continue` (today would mean scanning file mtimes each time), and (3) a `--fork` that copies a
transcript into a new session id without disturbing the original, plus the command-line flags
(`-c`, `-r <id|name>`, `--fork [<id|name>]`) that expose all of it. None of this touches the
orchestrator, any agent, or any tool — it is deterministic store + argument-routing work, exactly
like EXT-043's headless layer.

## Mechanism

```
  DURABLE SESSION STORE (harness/session.py — EXT-036 store, extended by EXT-044)
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │ .jaros-data/sessions/<id>.json   {id, name, created, last_active, turns[]}       │
  │ .jaros-data/sessions/index.json  {id: {name, created, last_active}}  (EXT-044)   │
  │                                                                                    │
  │  save_session(s)        writes both the transcript file AND the index entry       │
  │  load_session(id)        unchanged (EXT-036) -- reads the transcript file by id    │
  │  resolve_session_ref(r)  id-file-exists? -> r  :  else name lookup in the index    │
  │  most_recent_session_id() max(last_active) over the index (mtime fallback)        │
  │  fork_session(ref)       resolve -> load -> NEW Session(turns=copy) -> save;       │
  │                          the SOURCE file is only ever read, never rewritten        │
  └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                              │
  CLI ARGUMENT ROUTING (harness/cli.py -- extends the EXT-043 headless parser)         │
  ┌─────────────────────────────────────────▼─────────────────────────────────────────┐
  │ argv → _parse_headless_args(args)  (EXT-043, unchanged 4-tuple: session_id from    │
  │         the OLD `--resume <id>` flag, output_format, max_turns, rest)              │
  │      → _parse_session_flags(rest)   NEW: scans the remaining tokens for            │
  │         -c/--continue, -r <id|name>, --fork [<id|name>], --name <name>             │
  │      → _resolve_session_target(continue_flag, resume_ref, fork_ref, legacy_id)     │
  │           --fork given      -> fork_session(source) -> new id            (or err)  │
  │           -c given          -> most_recent_session_id()                  (or err)  │
  │           -r given          -> resolve_session_ref(ref)                  (or err)  │
  │           --resume <id>     -> id AS-IS, unchanged pre-EXT-044 behavior (no error   │
  │                                 on a miss -- JcodeCli creates a fresh session under │
  │                                 that id, exactly as before this spec)              │
  │           none of the above -> None  (fresh session -- byte-identical to today)    │
  └─────────────────────────────────────────┬─────────────────────────────────────────┘
                                              │ resolved session id (or an honest error,
                                              │ printed + exit 1, in BOTH text/json formats)
                                              ▼
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │ JcodeCli(session_id=resolved_id)  -- UNCHANGED constructor (EXT-036): load_session │
  │   finds the resolved id's transcript; `--name` (one-shot only) renames it after   │
  │   construction via set_session_name()                                             │
  │                                                                                     │
  │ handle(request) -- UNCHANGED (EXT-036 REQ-12/15): condense(self.session) feeds the │
  │   bounded [summary?] + recent-turns slice into the orchestrator/planner context --  │
  │   this IS "prior turns loaded into context"; EXT-044 adds no second context path    │
  └─────────────────────────────────────────────────────────────────────────────────┘
```

- **No new context-loading mechanism.** EXT-036 REQ-12/15 already load a bounded slice of
  `session.turns` into every plain-language `handle()` call (`recent()`/`condense()`). Once
  `-c`/`-r`/`--fork` resolve to a concrete session id and `JcodeCli(session_id=...)` loads that
  session's transcript, the EXISTING wiring does the rest — this spec's job stops at "resolve the
  right id, honestly."
- **`_parse_session_flags(rest)`** is a NEW function operating only on the tokens
  `_parse_headless_args` (EXT-043, unmodified in shape) left in `rest` — so the two parsers
  compose without either needing to know about the other's flags. It recognizes `-c`/
  `--continue` (no value), `-r <id|name>` (a value), `--fork` (an OPTIONAL value: the following
  token is consumed as the fork target only when it resolves to a real, existing session via
  `resolve_session_ref` — otherwise `--fork` takes no value and that token is left in `rest` as
  ordinary request text, avoiding ambiguity with a plain-language request), and `--name <name>`
  (a value, one-shot only — see below). Unrecognized tokens are left, in original order, in the
  final `rest`.
- **`_resolve_session_target(...)`** turns the parsed flags into ONE resolved session id or an
  honest error string, in priority order `--fork` > `-c` > `-r` > legacy `--resume <id>` > fresh.
  The legacy `--resume <id>` path is deliberately left OUT of the new strict-resolve/error
  behavior — it keeps its pre-EXT-044 semantics exactly (an unknown id creates a fresh session
  under that id, not an error) so existing callers/tests see zero behavior change. `-r` is the
  NEW, stricter alias that also accepts a NAME and treats an unresolvable reference as a genuine,
  reported failure — this is the intentional difference between the old and new flags.
- **`--fork`'s copy is a real, independent session.** `fork_session()` only ever reads the
  source file (`load_session`) and writes a NEW file under a fresh uuid id — the source
  transcript on disk is untouched, so a later `-r <original>` still resumes the pre-fork state.
- **`--name <name>`** is supported for the one-shot/headless invocation only (an optional 5th
  parameter on `_run_one_shot`, defaulted so existing calls are unaffected) and via a new `/name
  <name>` REPL command (mirrors `/new`/`/resume`'s reflection-dispatch pattern — `dispatch()`
  looks up `cmd_name` automatically, no registration table to touch). It is NOT threaded through
  `main()`'s call to `repl()`, which keeps `repl(session_id=...)`'s call SHAPE byte-identical to
  before this spec (a real backward-compat constraint: `main()`'s only argument to `repl()` stays
  `session_id`).
- **Fresh runs are unaffected.** When none of `-c`/`-r`/`--fork`/`--name` are present,
  `_parse_session_flags` returns all falsy/`None` values and `_resolve_session_target` falls
  straight through to `legacy_resume_id` (itself `None` unless the OLD `--resume` flag was used)
  with no session-store I/O at all — the exact pre-EXT-044 code path, byte-identical output.

## Two-plane / honesty

Every function this spec adds (`_index_path`/`_load_index`/`_save_index`, `resolve_session_ref`,
`most_recent_session_id`, `fork_session`, `set_session_name`, `_parse_session_flags`,
`_resolve_session_target`) is pure deterministic execution-plane code (Tenet 1): file/JSON I/O,
a linear argv scan, and a small priority-ordered `if`/`elif` chain. None of it calls the LLM or
changes what the orchestrator/agents decide — it only changes WHICH session's transcript is
loaded as prior context for the same decision-making path.

## Backward compatibility (no regression)

- No flags at all: `_parse_session_flags` returns `(False, None, None, None, rest)` where `rest`
  is unchanged from `_parse_headless_args`'s output; `_resolve_session_target` returns
  `(legacy_resume_id, None)` with zero session-store I/O — identical to pre-EXT-044 `main()`.
- The OLD `--resume <id>` flag (EXT-036/043) keeps its exact prior semantics: passed straight
  through as `session_id`, no existence check, no error on a miss (creates a fresh session under
  that id, as documented in `JcodeCli.__init__`).
- `main()`'s call to `repl(session_id=...)` is unchanged in shape (still exactly one keyword
  argument) — the EXT-043 tests that monkeypatch `cli_mod.repl` with a `def fake_repl(session_id
  =None)` stub keep working unmodified.
- `_run_one_shot`'s new `name_to_set` parameter has a default (`None`), so the EXT-043 test that
  calls `_run_one_shot("a request", None, "text", None)` with 4 positional arguments is
  unaffected.
- `Session`'s new `name`/`created`/`last_active` fields all default sanely, so a session file
  persisted before this spec (no such keys) still loads via `from_dict` with `name=None` and
  fresh timestamps — no migration step required.

## Out of scope (this task)

Renaming/deleting a session via a dedicated `/sessions --delete` surface; enforcing globally
unique session names (a name collision resolves to the most-recently-active match — recorded
here, not silently assumed); a `--fork-session` flag spelled exactly like Claude Code's (this
spec ships `--fork` as the jcode-native spelling; a `--fork-session` alias can be added later at
zero design cost if 1:1 flag-name parity is wanted). Threading `--name` through the interactive
REPL's `main()` → `repl()` call is also out of scope, in favor of the already-available `/name`
command, to avoid changing `repl()`'s call shape (a real backward-compat constraint, see above).
