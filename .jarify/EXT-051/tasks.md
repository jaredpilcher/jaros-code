# Implementation Tasks

### [TASK-1] `@path`/`@dir/` reference expansion + `/compact` session compaction, wired into the CLI

Add a new `harness/atrefs.py` module that deterministically finds `@<path>`/`@<dir>/` tokens in a
plain-language request and inlines the referenced file content (bounded, truncation-noted) or a
bounded directory listing, reading through caller-supplied callables so `harness/cli.py` can wire
them to the EXISTING gated `fs.read`/`fs.list` tools; wire the expansion into
`JcodeCli._route_plain` so it reaches the orchestrator/planner context for both a typed plain
request and a skill-substituted rendered template. Add `compact_session()` to `harness/session.py`,
reusing the existing `_summarize_turns()` mechanism `condense()` already built, to durably fold and
persist a session's older turns; wire it into a new `/compact` command. Flip
`docs/GAP-MAP.md`/`harness/product_parity.py` row #22 to `works` honestly.

#### Steps
1. Create `harness/atrefs.py`: a module-level `_AT_REF_RE` regex that matches `@`-prefixed path
   tokens only when preceded by whitespace/start-of-string (never mid-word, so an email-like
   string is never mistaken for a ref), capturing path-safe characters (letters/digits/`_`/`.`/`/`
   /`\`/`-`), with trailing sentence punctuation (`.`, `,`, `:`, `;`, `)`, `!`, `?`) stripped from
   the captured token (a ref's own trailing `/` is preserved, since it is the directory sentinel).
   `find_at_refs(text) -> list[str]`: returns the distinct captured tokens in first-seen order;
   `None`/empty `text` returns `[]`; never raises. `expand_at_refs(text, read_file, list_dir,
   max_chars=4000, max_dir_entries=40) -> str`: for each ref found by `find_at_refs`, if it ends
   with `/` or `\\` calls `list_dir(ref)` (expected to return `(entries: list[str] | None,
   truncated: bool)` or raise), else calls `read_file(ref)` (expected to return `(content: str |
   None, truncated: bool)` or raise); wraps each call in `try/except` so a raised exception or a
   `None` result degrades to a single labeled `--- @{ref} (not found) ---`-style block rather than
   propagating; a successful file read is capped at `max_chars` (truncated + noted if it
   overflows); a successful directory listing is capped at `max_dir_entries` (truncated + noted if
   it overflows). All blocks are joined and appended AFTER the original `text` (the `@token` itself
   stays in the original text, unrewritten); `text` with no refs (or a `find_at_refs` failure) is
   returned byte-identical. The whole function never raises regardless of what the callables do.
2. In `harness/cli.py`: add `_at_ref_read(self, path: str) -> "tuple[str | None, bool]"` calling
   `self._tool("fs.read", {"path": path})` (mirrors `cmd_read`'s existing seam) inside a
   `try/except`, returning `(None, False)` on any exception or an `{"error": ...}` result, else
   `(out.get("content", ""), bool(out.get("truncated")))`. Add `_at_ref_list(self, path: str) ->
   "tuple[list[str] | None, bool]"` calling `self._tool("fs.list", {"path": path.rstrip("/\\\\")
   or "."})` (mirrors `cmd_ls`'s existing seam), returning `(None, False)` on any exception/error,
   else a list of `"{type}  {name}"` strings built from `out["entries"]` (truncation of the entry
   list itself is left to `expand_at_refs`'s `max_dir_entries` cap, so this adapter returns
   `truncated=False` and the full entry list). In `_route_plain`, immediately before the
   `_augment_with_history(line, ...)` call in the orchestrator branch (the deterministic
   multistep/subagent-delegation/intent-fast-path checks above it keep matching the RAW `line`
   unchanged, so a file's own prose content can never spuriously trigger one of those regexes),
   add `from harness.atrefs import expand_at_refs` and `expanded = expand_at_refs(line,
   self._at_ref_read, self._at_ref_list)`, then pass `expanded` (not `line`) as the first argument
   to `_augment_with_history`. Add `cmd_compact(self, arg: str) -> str`: `from harness.session
   import compact_session; result = compact_session(self.session, llm=self.llm); return
   result.get("message", "")`. Update the module docstring's command list (add a `/compact` line
   documenting the reused condense mechanism, and a note under the existing plain-request section
   documenting `@path`/`@dir/` expansion) — `cmd_help` reads directly from this docstring, so no
   separate edit is needed there.
3. In `harness/session.py`: add `compact_session(session: "Session", llm=None, keep: int =
   CONDENSE_KEEP) -> dict`, placed near `condense()` (REQ-15 section). Computes
   `before_turns = len(session.turns)` and `before_chars` (sum of each turn's `text` length). If
   `before_turns <= keep`: return `{"compacted": False, "before_turns": before_turns,
   "after_turns": before_turns, "before_chars": before_chars, "after_chars": before_chars,
   "message": f"session already short ({before_turns} turn(s)) -- nothing to compact"}` WITHOUT
   calling `_summarize_turns`/`llm`. Otherwise: `recent_turns = [dict(t) for t in
   session.turns[-keep:]]`; `oldest = session.turns[: before_turns - keep]`; `summary_text =
   _summarize_turns(oldest, llm)` (the SAME helper `condense()` already calls — not a new
   summarizer); `session.turns = [{"role": "summary", "text": summary_text, "ts": time.time()}] +
   recent_turns`; `save_session(session)`; compute `after_turns`/`after_chars` and return
   `{"compacted": True, "before_turns", "after_turns", "before_chars", "after_chars", "message": f"
   compacted {before_turns} turns ({before_chars} chars) -> {after_turns} turns ({after_chars}
   chars)"}`. Wrap the whole body in `try/except` returning a safe `compacted: False` fallback
   result (never raises) mirroring the module's existing best-effort conventions.
4. Update `harness/product_parity.py` row `id=22` (Context management for long sessions): flip
   `state` to `"works"`; `current_state` names what is genuinely delivered (deterministic `@path`/
   `@dir/` expansion through the existing gated `fs.read`/`fs.list` tools, wired into the SAME
   `_route_plain` chain a typed request and a skill-substituted template already share, bounded +
   truncation-noted + an honest not-found annotation on a miss; `/compact` reusing the existing
   `_summarize_turns()`/`condense()` mechanism to durably fold + persist a session's older turns,
   with an honest no-op on an already-short session) and what remains deferred (no context-usage
   meter/percentage display; no auto-compact-on-threshold trigger — today's auto-condensation
   stays a transient view via `condense()`; `@path` expansion inside `JCODE.md` itself, already
   named deferred on row #14); `next_lever` names only that residual gap. Mirror the same honest
   update into `docs/GAP-MAP.md` row #22's `State`/`Current honest state`/`Next lever` columns.
5. Update `tests/test_ext041_product_parity.py`: add `22` to the `works == [...]` pin (kept
   sorted), and update `test_score_default_rows_reflects_honest_current_baseline`'s
   `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to match the new
   works-count.
6. Write `tests/test_ext051_context.py` (deterministic, no live gemma, following the
   `tests/test_ext050_subagents.py` fixture/stubbing pattern): `harness.atrefs.find_at_refs`/
   `expand_at_refs` unit tests exercised directly with fake `read_file`/`list_dir` callables — a
   ref inlines fake content (bounded/truncation noted when it overflows a small test `max_chars`),
   a ref whose callable returns `None`/raises degrades to an honest annotated block (never raises),
   a `@dir/` ref calls `list_dir` and bounds the entry count (truncation noted when it overflows a
   small test `max_dir_entries`), text with no `@` ref is returned byte-identical, `None`/empty
   text never raises. A `JcodeCli` (mirroring `_stub_cli` from `test_ext050_subagents.py`) with a
   stubbed orchestrator: a typed plain request containing `@<realfile>` reaches the stub with the
   real file's content inlined in `request` (proving the `_at_ref_read`/`fs.read` wiring); the SAME
   proof routed through a skill's rendered template (`_run_skill`) with a dropped
   `.jcode/skills/<name>.md`, proving expansion applies identically to both entry points; a request
   naming NO `@` ref reaches the stub with `request` unchanged from before this spec (byte-identical
   routing, no extra tool calls — assert `stub.calls[0]["request"]` contains no injected block).
   `harness.session.compact_session` unit tests: a `Session` with more than `keep` turns, given a
   monkeypatched/stubbed `harness.session._summarize_turns` (or an injected fake `llm` whose output
   is asserted to appear in the resulting summary turn), compacts to `keep + 1` turns with
   `compacted=True` and `after_turns < before_turns`/`after_chars < before_chars`, and the result is
   persisted (verified via `harness.session.load_session` re-reading it back, with `SESSIONS_DIR`
   monkeypatched to `tmp_path` mirroring `test_ext050_subagents.py`'s `_isolate_sessions_dir`
   fixture); a `Session` with `keep` or fewer turns returns `compacted=False` with
   `_summarize_turns` verified NEVER called (monkeypatch it to raise if invoked); a broken/failing
   internal step degrades to a safe `compacted=False` result rather than raising. `JcodeCli.
   cmd_compact`/`/compact` dispatch reaches `compact_session` and returns its message (asserted via
   a monkeypatched `harness.session.compact_session` recording its call args and returning a fixed
   result dict).

#### Implements
- [REQ-1] `@path` / `@dir/` file references inlined into plain requests
- [REQ-2] `/compact` — deterministic session-transcript compaction
- [REQ-3] Honest Product-Parity Checklist update
