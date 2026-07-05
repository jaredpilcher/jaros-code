---
id: EXT-044
title: Durable conversation sessions (continue / resume / fork / name)
status: covered
priority: high
---

# EXT-044 — Durable conversation sessions

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #12 — Claude Code's
`-c`/`-r <id|name>`/`--fork-session` session-continuity surface. jaros-code already has a
durable conversational session store (EXT-036 REQ-12: `harness/session.py`, `/new`, `/resume
<id>`, `/sessions`); this spec extends that SAME store with a session name and an index (for
name lookup + "most recent"), and adds `-c`/`--continue`, `-r <id|name>`, and `--fork
[<id|name>]` as command-line entry points into it — no change to orchestrator reasoning, and no
second session store.

### [REQ-1] Durable session store: name + timestamps + index

`harness/session.py`'s `Session` gains an optional `name`, and `created`/`last_active`
timestamps; `save_session` persists a small `.jaros-data/sessions/index.json` mapping each
session id to `{name, created, last_active}` alongside the existing per-session transcript
file, so a session can be found by NAME as well as by id, and "the most-recently-active session"
is a cheap lookup. All of it is best-effort/never-raising, matching the existing store's
never-crash contract.

#### Acceptance Criteria
- [x] A `Session` constructed with no `name`/`created`/`last_active` behaves exactly as before this spec (`name` is `None`, timestamps default to "now").
- [x] `save_session` persists both the per-session transcript file (unchanged) AND an updated `index.json` entry for that session's id, name, and timestamps.
- [x] A session file persisted BEFORE this spec (no `name`/`created`/`last_active` keys) still loads via `Session.from_dict` without raising, with `name=None` and sane default timestamps.
- [x] A missing or corrupt `index.json` never raises from any store function — lookups against it degrade to an honest "not found"/empty result.

### [REQ-2] `-c` / `--continue` resumes the most recent session

`python -m harness.cli -c` (or `--continue`) resumes the session with the greatest `last_active`
timestamp across all persisted sessions — the conversation continues as if it had never
stopped. When no session has ever been persisted, this is a genuine, reported failure (non-zero
exit / clear message), never a silent fresh-session fallback that hides the miss.

#### Acceptance Criteria
- [x] With two or more persisted sessions, `-c`/`--continue` resolves to the id with the most recent `last_active`.
- [x] With zero persisted sessions, `-c`/`--continue` reports a clear error and exits non-zero — `JcodeCli` is never constructed with a bogus id.
- [x] `-c`/`--continue` composes with a trailing one-shot request (`jcode -c "keep going"`) exactly like the existing `--resume <id>` flag does.

### [REQ-3] `-r <id|name>` resumes a specific session by id or name

`python -m harness.cli -r <ref>` resumes the session referenced by `<ref>`, trying it first as
an exact session id, then as a session NAME (assigned via `--name`/`/name`). An unresolvable
reference is a clear, reported failure (non-zero exit / clear message) — `JcodeCli` is never
constructed for an unresolvable reference, and the process never crashes with a raw traceback.

#### Acceptance Criteria
- [x] `-r <id>` where `<id>` is a real persisted session's id resumes that exact session.
- [x] `-r <name>` where `<name>` matches a session's assigned name resumes that session (by resolving the name to its id first).
- [x] `-r <unknown>` (matches neither an id nor a name) exits non-zero with a clear message, without constructing `JcodeCli`.
- [x] The pre-existing `--resume <id>` flag (EXT-036/043) is UNCHANGED: an unknown id still creates a fresh session under that literal id rather than erroring — `-r`'s stricter honest-error behavior is additive, not a replacement.

### [REQ-4] `--fork [<id|name>]` branches a session

`python -m harness.cli --fork [<ref>]` creates a brand-new session whose transcript is a COPY of
the referenced session's transcript (`<ref>` an id or name; when omitted, the most-recently-
active session, or whichever session `-r`/`--resume` also names on the same invocation). The
run then continues in the NEW forked session — the source session's persisted transcript is
left completely unchanged (a later `-r <source>` still resumes the pre-fork state). An
unresolvable fork source is a clear, reported failure, never a crash.

#### Acceptance Criteria
- [x] `--fork <ref>` creates a NEW session id whose transcript equals the referenced session's transcript at the time of the fork.
- [x] After a fork, the ORIGINAL (source) session's persisted transcript file is byte-unchanged — appending to the fork never mutates the source.
- [x] `--fork` with no `<ref>` and no other session flag on the same invocation forks the most-recently-active session.
- [x] `--fork <unknown-ref>` exits non-zero with a clear message, without creating a fork or constructing `JcodeCli`.

### [REQ-5] Resumed context is loaded; fresh runs stay byte-identical

Whichever session `-c`/`-r`/`--fork`/`--resume` resolves to, its prior turns are loaded into the
orchestrator/planner context on the very next turn — via the EXISTING EXT-036 REQ-12/15
`condense()`/`recent()` context-injection path (no second/duplicate context mechanism). A fresh
invocation that uses NONE of these flags is byte-identical (output, exit codes, and REPL
behavior) to the pre-EXT-044 CLI.

#### Acceptance Criteria
- [x] After resuming a session (via `-c`, `-r`, or `--fork`) that has prior turns, the next `handle()` call's orchestrator-routing context includes those prior turns (via the existing `condense()`/`recent()` slice) — the plumbing is exercised end-to-end, not merely asserted by inspection.
- [x] A plain invocation with no session flags at all produces output byte-identical to the pre-EXT-044 CLI (same request text, same routing, same exit code) — the regression guard from EXT-043 continues to pass unmodified.
- [x] `main()`'s call to `repl(session_id=...)` keeps its exact pre-EXT-044 call shape (one keyword argument) so existing stubs of `repl()` are unaffected.
