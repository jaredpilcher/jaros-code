# Intent

Claude Code treats a conversation as a durable, addressable thing: `claude -c`/`--continue`
picks up the most recent conversation exactly where it left off, `claude -r <id|name>` resumes
any named/older conversation, and `--fork-session` branches a conversation so exploring an
alternative doesn't mutate the original. `docs/GAP-MAP.md`'s Product-surface parity row #12
names this gap explicitly: jaros-code has a conversational `Session` (EXT-036 REQ-12 —
turns persisted to `.jaros-data/sessions/<id>.json`, `/new`, `/resume <id>`, `/sessions`) but no
`-c`/`-r <id|name>`/`--fork` command-line surface, no session NAME (only the raw id), and no
"most-recently-active session" lookup — so `jcode` cannot yet be picked up cold the way `claude`
can.

This spec closes that gap by extending the EXISTING session store (not duplicating it):
`harness/session.py`'s `Session`/`save_session`/`load_session`/`list_sessions` from EXT-036
already are the durable transcript; EXT-044 adds an optional display `name`, `created`/
`last_active` timestamps, and a small `.jaros-data/sessions/index.json` so a session can be
found by NAME as well as by id, and "the most-recently-active session" is a cheap lookup
instead of a directory mtime scan. On top of that store, `harness/cli.py` gains `-c`/
`--continue` (resume the most recent session), `-r <id|name>` (resume a specific one, by id or
name, with an honest error on an unknown reference — never a crash), and `--fork [<id|name>]`
(copy a session's transcript into a brand-new session id, leaving the original untouched). The
resumed session's prior turns are already loaded into the orchestrator/planner context via the
EXT-036 REQ-12/15 `condense()`/`recent()` machinery — this spec wires the NEW entry points
(`-c`/`-r`/`--fork`) into that existing, already-proven context-load path rather than building a
second one.

This converges PRIME-001 in two ways. First, it directly advances the "in ALL ways" whole-product
parity bar the Prime Directive names — sessions continue/resume/fork/name is called out by name
in the Product-Parity Checklist (EXT-041) as row #12, alongside headless/piping (EXT-043,
closed) and instruction memory (EXT-042, closed); that instrument must move honestly once this
ships. Second, it reinforces Tenet 1 (two-plane discipline) and the harness's long-horizon
continuity story: a session, its name, and its transcript are all deterministic execution-plane
state — no new model call, no new agent — and continuity across sessions is exactly the kind of
long-horizon substrate PRIME-001's commitment to whole-product parity keeps naming as still
missing. It must remain strictly additive (Tenet 3): a caller that uses none of `-c`/`-r`/
`--fork` sees byte-identical output, exit codes, and REPL behavior to today.
