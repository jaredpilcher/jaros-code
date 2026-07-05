# EXT-051 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #22 names Claude Code's long-session context
management surfaces: `@path` references that pull a file straight into the conversation, and
`/compact` to shrink a long-running session's context. jcode already has the deeper mechanism a
compactor needs — `harness/session.py`'s `condense()` (EXT-036 REQ-15) auto-folds a session's
oldest turns into a running summary via ONE narrow model call (`_summarize_turns()`) once the
transcript passes a budget, returning `[summary] + recent turns` as a bounded VIEW fed to the
orchestrator. What's missing is (a) any way to reference a file by name inside a plain request, and
(b) a MANUAL, user-invoked command that actually shrinks (mutates + persists) the session transcript
itself, rather than only a transient per-turn view.

Neither addition should invent a new reasoning/side-effect mechanism: `@`-expansion is pure string
composition over content read through the EXISTING gated `fs.read`/`fs.list` tools (`/read`/`/ls`'s
`self._tool(...)` seam); `/compact` reuses `_summarize_turns()` verbatim rather than writing a
second summarizer.

## Mechanism

```text
  PLAIN REQUEST (typed, or a skill-substituted template -- both share _route_plain)
  +-------------------------------------------------------------------------------------+
  | "explain @harness/cli.py"        "review @src/ and fix the bug"                       |
  +-----------------------------------------------------+---------------------------------+
                                                          |
                                                          v
  @-REF EXPANSION (harness/atrefs.py -- NEW module, pure deterministic string composition,
                    no model call anywhere in this module)
  +-------------------------------------------------------------------------------------+
  | find_at_refs(text) -> ["harness/cli.py"]           (regex token scan, whitespace-     |
  |                                                      anchored, order-preserving,      |
  |                                                      de-duplicated)                  |
  |                                                                                         |
  | expand_at_refs(text, read_file, list_dir, ...)                                         |
  |   for each ref:                                                                        |
  |     ref ends with "/"  -> list_dir(ref) -> bounded entry listing (NOT recursive)       |
  |     else                -> read_file(ref) -> bounded content (cap + truncation note)   |
  |     any miss/exception  -> an honest "(not found)"/"(error: ...)" annotated block --    |
  |                            the original @token is left in the request text, unchanged  |
  |   appends one labeled block per ref after the original text; NO refs -> text unchanged  |
  |   (byte-identical no-op)                                                               |
  +-----------------------------------------------------+---------------------------------+
                                                          | read_file/list_dir are CALLER-
                                                          | supplied callables --
                                                          v
  READ ADAPTERS (harness/cli.py -- JcodeCli, wraps the EXISTING gated tool seam)
  +-------------------------------------------------------------------------------------+
  | _at_ref_read(path)  -> self._tool("fs.read", {"path": path})   <- SAME seam /read     |
  | _at_ref_list(path)  -> self._tool("fs.list", {"path": path})   <- SAME seam /ls uses  |
  |   never a raw open()/os.listdir() -- every host file read goes through the gated      |
  |   Runtime.apply(fs.read/fs.list) Decision, exactly like every other read in this CLI   |
  +-----------------------------------------------------+---------------------------------+
                                                          | expanded text
                                                          v
  ROUTER (harness/cli.py::JcodeCli._route_plain -- EXISTING seam, additively extended)
  +-------------------------------------------------------------------------------------+
  | _route_plain(line):                                                                  |
  |   if _is_multistep(line): ...           (unchanged -- runs on the RAW line)          |
  |   delegated = _match_subagent_delegation(line); ...   (unchanged -- RAW line)         |
  |   intent = _route_intent(line); ...     (unchanged -- RAW line; deterministic         |
  |                                           refactor/nav phrasings are keyword-shaped,   |
  |                                           not file-content-shaped, so they stay on     |
  |                                           the raw line to avoid a file's own prose      |
  |                                           spuriously matching a fast-path regex)       |
  |   expanded = expand_at_refs(line, self._at_ref_read, self._at_ref_list)   <- NEW       |
  |   augmented = _augment_with_history(expanded, history, project_md, memory, jcode_md)   |
  |   [d] = orchestrator.decide({"request": augmented, "history": history})    (unchanged) |
  +-------------------------------------------------------------------------------------+
```

```text
  /compact (a manual, DURABLE shrink -- distinct from condense()'s transient per-turn VIEW)
  +-------------------------------------------------------------------------------------+
  | harness/session.py (EXISTING module, additively extended)                             |
  |                                                                                         |
  |   condense(session, ...) -> VIEW only         (EXT-036 REQ-15, UNCHANGED)              |
  |     len(turns) <= MAX_TURNS -> session.recent(...) (a read, never mutates session)      |
  |     else -> [summary] + recent  (session.turns itself is left untouched)               |
  |                                                                                         |
  |   compact_session(session, llm=None, keep=CONDENSE_KEEP) -> dict      <- NEW           |
  |     len(turns) <= keep  -> {"compacted": False, ...}   (honest no-op, nothing folded)   |
  |     else:                                                                                |
  |       oldest = session.turns[: len(turns) - keep]                                      |
  |       summary_text = _summarize_turns(oldest, llm)    <- THE SAME narrow-model-call     |
  |                                                            mechanism condense() already  |
  |                                                            built -- NOT a second         |
  |                                                            summarizer                   |
  |       session.turns = [{"role": "summary", "text": summary_text}] + recent_turns        |
  |       save_session(session)                            <- persisted, unlike condense()  |
  |       returns {"compacted": True, before/after turn+char counts, "message": ...}         |
  +-----------------------------------------------------+---------------------------------+
                                                          |
                                                          v
  harness/cli.py::JcodeCli.cmd_compact(arg)  <- NEW, calls compact_session(self.session, self.llm)
                                                  and reports the before/after message
```

- **No second reasoning mechanism, no new Decision type, no new side-effect path.** `@`-expansion
  is pure string composition; the only model call in either deliverable is `_summarize_turns()`,
  which already existed (EXT-036 REQ-15) and is called, not re-implemented, by `compact_session()`.
- **Never a raw host read.** `_at_ref_read`/`_at_ref_list` wrap `self._tool("fs.read"/"fs.list", ...)`
  — the exact seam `/read`/`/ls` already route through (`Runtime.apply`, gated, hash-chain logged).
- **Bounded, honest, never crashes.** A referenced file's content is capped with a truncation note
  when it overflows the cap; `@dir/` lists entries (bounded count, not a recursive dump); a missing
  or unreadable path degrades to an annotated "(not found)"/"(error: ...)" block rather than raising
  — the original `@token` stays in the request text so the request still reads naturally.
  `expand_at_refs` returns `text` UNCHANGED when it contains no `@` references at all — a request
  with no refs is byte-identical to before this spec.
- **Wired into the ONE `_route_plain` chain** both a typed plain request (`handle()`) and a
  skill-substituted template (`_run_skill`, EXT-046) already share — `@path` therefore works
  identically for both entry points with a single wiring point, exactly mirroring how EXT-050's
  subagent-delegation fast path was added to the same chain.
- **`/compact` mutates + persists**, unlike `condense()`'s read-only transient view — this is the
  deliberate distinction: `condense()` exists to keep every ROUTED turn's context bounded without
  ever touching the durable transcript; `/compact` is the user's explicit, durable "shrink this
  session now" action. Both share the identical folding mechanism (`_summarize_turns()`) so there is
  exactly one place summarization logic lives.
- **An already-short session is an honest no-op.** `compact_session()` never wastes a model call
  summarizing zero/near-zero "older" turns; it returns `compacted: False` with a plain message.

## Two-plane / honesty

`harness/atrefs.py` is pure execution-plane string composition (Tenet 1) — no LLM call anywhere in
the module; the caller-supplied `read_file`/`list_dir` callables let `harness/cli.py` wire the
EXISTING gated tool seam without `atrefs.py` itself doing any I/O or gating. `compact_session()`'s
only model-facing call is the pre-existing `_summarize_turns()` — this spec adds no new model-facing
surface. Per Tenet 3, `harness/product_parity.py` row #22 is flipped to `"works"` only because both
surfaces are genuinely delivered, wired through the existing routing chain, and test-covered; the
row's `current_state` honestly names what remains deferred: no context-usage METER/display (how
much of the budget is used, right now); no auto-compact-on-threshold trigger (today `/compact` is
manual-only, `condense()`'s auto-fold stays a transient view); `@path` expansion inside `JCODE.md`
itself (already named as deferred on row #14, EXT-042, and not re-solved here).

## Backward compatibility (no regression)

- A plain request with no `@` token anywhere is byte-identical to before this spec —
  `expand_at_refs` returns its input unchanged when `find_at_refs` finds nothing.
- `condense()`'s behavior, signature, and return shape are entirely unchanged; `compact_session()`
  is a new, additive function that calls the same `_summarize_turns()` helper `condense()` already
  used internally.
- `/compact` is a new slash command; no existing command name collides with it.

## Out of scope (this task)

A context-usage meter/percentage display; an automatic compact-on-threshold trigger (today's
auto-condensation stays a transient per-turn view, not a persisted mutation); `@path` expansion
inside `JCODE.md`/skill template files themselves (distinct from expansion inside a live request);
recursive/glob `@` references (`@src/**/*.py`); an `@`-token argument-completion UX. These remain
honestly named in `docs/GAP-MAP.md` row #22's "Next lever" as the residual gap, per Tenet 3.
