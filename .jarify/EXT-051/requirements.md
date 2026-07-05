---
id: EXT-051
title: Context management for long sessions (@path references + /compact)
status: draft
priority: medium
---

# EXT-051 — Context management for long sessions

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #22 — a plain-language
request containing `@<path>` deterministically inlines that file's (or directory's) content into
the request before it reaches the orchestrator/planner, and `/compact` deterministically shrinks
the current session's transcript by reusing the EXISTING EXT-036 REQ-12/REQ-15
`condense()`/`_summarize_turns()` mechanism (not a second summarizer). Both are pure
deterministic execution-plane operations, wired into the SAME plain-language routing chain
(`_route_plain`) every typed request and skill-substituted template already share.

### [REQ-1] `@path` / `@dir/` file references inlined into plain requests

A new module `harness/atrefs.py` deterministically finds `@<path>` tokens in a plain-language
request and inlines the referenced content — a file's content (bounded, with a truncation note
when it overflows the cap) or, for a path ending in `/`, a bounded directory listing (not a
recursive dump). Reads are performed through caller-supplied `read_file`/`list_dir` callables, so
`harness/cli.py` can wire them to the EXISTING gated `fs.read`/`fs.list` tools (the same
`self._tool(...)` seam `/read`/`/ls` already use) — never a raw `open()`/`os.listdir()`. This is
wired into `JcodeCli._route_plain` — the SAME chain a typed plain request (`handle()`) and a
skill-substituted template (`_run_skill`, EXT-046) already share — so `@`-refs work identically
for both entry points via one wiring point.

#### Acceptance Criteria
- [ ] `harness.atrefs.find_at_refs(text)` returns the distinct `@`-prefixed path tokens in `text`,
      in first-seen order, anchored so it never matches an `@` embedded mid-word (e.g. an email
      address); an empty/`None` input returns `[]`, never raises.
- [ ] `harness.atrefs.expand_at_refs(text, read_file, list_dir)` appends one labeled block per
      distinct `@`-ref found, AFTER the original `text` (the `@token` itself is left in place,
      unrewritten); `text` with NO `@`-refs at all is returned byte-identical (a complete no-op).
- [ ] A ref resolving to a real file inlines its content, bounded by a byte/char cap; content
      that overflows the cap is truncated with an explicit truncation note in the block.
- [ ] A ref ending in `/` is treated as a directory reference: `list_dir` is called instead of
      `read_file`, and the resulting block is a BOUNDED listing of entries (a fixed cap on entry
      count), never a recursive dump of the directory's contents.
- [ ] A ref that `read_file`/`list_dir` reports as missing/unreadable (returns `None`, or raises)
      degrades to an honest `(not found)`-style annotated block — `expand_at_refs` itself never
      raises regardless of what the callables do.
- [ ] `harness.cli.JcodeCli._route_plain` expands `@`-refs (via callables wired to the existing
      `fs.read`/`fs.list` `self._tool(...)` seam) into the text that reaches the
      orchestrator/planner's `decide()` call, proven via a stubbed orchestrator receiving the
      referenced file's content in its `request` context — for BOTH a directly typed plain
      request and a skill-substituted rendered template routed through `_run_skill`.
- [ ] A plain request with no `@` token anywhere is byte-identical in its routing behavior to
      before this spec (no wasted tool calls, no altered orchestrator context).

### [REQ-2] `/compact` — deterministic session-transcript compaction

`harness/session.py` gains `compact_session(session, llm=None, keep=CONDENSE_KEEP) -> dict`,
which REUSES the EXISTING `_summarize_turns()` narrow-model-call mechanism `condense()` (EXT-036
REQ-15) already built — not a second summarization mechanism — to fold every turn OLDER than the
most recent `keep` into a single `{"role": "summary", ...}` entry, replacing `session.turns` and
persisting the result via the existing `save_session()`. Unlike `condense()` (a transient, read-
only VIEW for per-turn routing context), `compact_session()` durably mutates the session. Wired
into `harness/cli.py` as `cmd_compact`, reachable via `/compact`, documented in `/help`.

#### Acceptance Criteria
- [ ] `compact_session(session, llm=None, keep=CONDENSE_KEEP)` on a session with MORE than `keep`
      turns: folds every turn before the most recent `keep` into one summary turn via the SAME
      `_summarize_turns()` helper `condense()` already uses (proven by an injected/stubbed `llm`
      whose output appears in the resulting summary text), replaces `session.turns` with
      `[summary] + recent_turns`, persists via `save_session`, and returns a result dict reporting
      `compacted=True` plus before/after turn count and character count.
- [ ] `compact_session(session, ...)` on a session with `keep` turns or fewer is an honest no-op:
      returns `compacted=False` with an explanatory message, `session.turns` is left unchanged,
      and `_summarize_turns` (or the underlying `llm`) is never invoked.
- [ ] `compact_session` never raises — a save failure or any other internal exception degrades to
      a `compacted=False` result rather than crashing the caller.
- [ ] `JcodeCli.cmd_compact(arg)` calls `compact_session(self.session, llm=self.llm)` and returns
      its human-readable before/after message; `/compact` is documented in `cmd_help`'s output and
      the module docstring's command list.
- [ ] `condense()`'s existing behavior, signature, and return shape are entirely unchanged by this
      requirement — `compact_session` is purely additive.

### [REQ-3] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=22` (Context management for long sessions) is flipped to
`"works"` ONLY because `@path`/`@dir/` expansion and `/compact` are genuinely delivered and
test-covered; its `current_state` honestly names what is delivered and what remains deferred (no
context-usage meter/display; no auto-compact-on-threshold trigger — today's auto-condensation
stays a transient view via `condense()`; `@path` expansion inside `JCODE.md` itself, already named
deferred on row #14). `docs/GAP-MAP.md` row #22 and `tests/test_ext041_product_parity.py`'s
honesty-pin are updated to match, mirroring how EXT-042/043/.../050 each did on landing.

#### Acceptance Criteria
- [ ] `harness/product_parity.py`'s row `id=22` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [ ] `docs/GAP-MAP.md` row #22's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [ ] `tests/test_ext041_product_parity.py`'s `works == [...]` pin (kept sorted) and the
      `n_total`/`n_works` (and derived `n_partial + n_missing`) assertions include row #22.
