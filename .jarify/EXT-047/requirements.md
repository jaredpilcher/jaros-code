---
id: EXT-047
title: User-configurable lifecycle hooks
status: covered
priority: medium
---

# EXT-047 — User-configurable lifecycle hooks

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #16 — a user drops a
`.jcode/hooks.json` config mapping `PreToolUse`/`PostToolUse`/`SessionStart`/`Stop` to shell
commands, and the clerk fires them at the existing `validate()`/`execute()` seam. A `PreToolUse`
hook exiting non-zero blocks the tool call it gates. Hooks run through the SAME gated
`shell.exec` path every other tool call uses — never a bypass of the security gates.

### [REQ-1] Hook config — discover `.jcode/hooks.json` (project + user tiers)

A deterministic loader discovers a JSON hooks config at the PROJECT level
(`<repo>/.jcode/hooks.json`) and the USER level (`~/.jcode/hooks.json`, mirroring the EXT-042/
EXT-046 two-tier convention), each mapping an event name (`PreToolUse`, `PostToolUse`,
`SessionStart`, `Stop`) to a list of `{"command": str, "matcher": str (optional)}` entries.

#### Acceptance Criteria
- [x] `harness.hooks.load_hooks(root=".")` returns a `dict[str, list[HookDef]]` keyed by event,
      combining BOTH tiers additively (project entries first, then user entries — no
      name-collision override, since multiple hooks may legitimately fire for one event).
- [x] `HookDef` carries `command`, `matcher` (`None` when absent — matches every tool), and
      `source` (the config file path, for diagnostics).
- [x] A missing `.jcode/hooks.json` (either tier) yields an empty contribution from that tier —
      never raises, never treated as an error.
- [x] Malformed JSON, a non-dict top level, an unrecognized event key, or a malformed individual
      hook entry (missing/blank `command`, non-dict item) is SKIPPED — never raised — so one bad
      entry can never break discovery of the others.
- [x] No `.jcode/hooks.json` anywhere (either tier) yields `load_hooks() == {}` — a graceful
      no-op, zero behavior change for every downstream caller.

### [REQ-2] Fire at the seam — PreToolUse/PostToolUse via `Runtime.apply`, block-on-nonzero

`harness.coding_loop.Runtime` (the ONE gate → executor → decision-log choke point every tool call
already passes through) gains an optional `hooks_config` — when non-empty, `PreToolUse` hooks fire
BEFORE `validate_decision()` (scoped to the Decision's `type` via each hook's optional `matcher`
glob) and `PostToolUse` hooks fire AFTER a successful `execute()`. A `PreToolUse` hook that exits
non-zero BLOCKS the call — the clerk refuses it, exactly like a gate rejection. Every hook's shell
command runs through the SAME gated `shell.exec` Decision path (denylist + timeout +
process-tree-kill) via a FRESH, hooks-disabled `Runtime`, so firing a hook can never recursively
re-trigger hook firing.

#### Acceptance Criteria
- [x] `harness.hooks.fire_event(event, hooks_config, tool_name=..., cwd=..., run_command=...)`
      fires every hook configured for `event` whose `matcher` (if any) glob-matches `tool_name`
      (PreToolUse/PostToolUse only — SessionStart/Stop always fire, having no tool to scope
      against); `run_command` defaults to the real gated `shell.exec` path and is injectable for
      tests.
- [x] `Runtime.apply(decision)`: with a non-empty `hooks_config`, `PreToolUse` hooks matching
      `decision.type` fire before `validate_decision()`; if any exits non-zero, `apply()` raises
      `RuntimeError` and the tool call NEVER executes (no partial effect).
- [x] `PostToolUse` hooks fire after a successful `execute()`; they are observational only — a
      non-zero exit is recorded but never raises/blocks (the tool call already happened).
- [x] `Runtime(...)` with no `hooks_config` (the default) is a complete no-op — behaves
      byte-identically to every pre-EXT-047 caller (`_git_tool`, every existing test/production
      call site).
- [x] A hook's shell command runs via `harness.hooks._default_run_command`, which constructs a
      FRESH `Runtime` carrying no `hooks_config` — proven to route through the real gated
      `shell.exec` Decision (subject to its denylist/timeout/tree-kill) and to never recurse into
      firing hooks for itself.

### [REQ-3] SessionStart / Stop lifecycle

`SessionStart` hooks fire once, at `JcodeCli` construction (session begin). `Stop` hooks fire
once, at session end — the REPL's `/quit`/EOF/interrupt paths, or after a headless one-shot turn
completes.

#### Acceptance Criteria
- [x] `JcodeCli.__init__` fires configured `SessionStart` hooks exactly once, recorded on
      `self._session_start_outcomes`.
- [x] `JcodeCli.on_stop()` fires configured `Stop` hooks exactly once per instance (idempotent —
      calling it again is a no-op) and is called from `repl()`'s `/quit`/EOF/interrupt return
      points and from `_run_one_shot()` after its single turn.
- [x] With no hooks configured, `SessionStart`/`Stop` firing is a complete no-op (no import of the
      hook-execution path is even attempted).

### [REQ-4] `/hooks` list command + `/help`

`/hooks` lists every configured hook (event, matcher if any, command) so a user can see what is
active without reading the JSON file; an empty config reports that honestly. `/help` documents
`/hooks` and the `.jcode/hooks.json` convention.

#### Acceptance Criteria
- [x] `JcodeCli.cmd_hooks(_arg)` renders one line per configured hook across all four events, or
      an honest "(no hooks configured ...)" message when `hooks_config` is empty.
- [x] `/help`'s command list documents `/hooks` and the `.jcode/hooks.json` convention.

### [REQ-5] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=16` (User-configurable hooks) is flipped to `"works"` ONLY
because the four lifecycle events, config loading, block-on-nonzero, and gated execution are
genuinely delivered and test-covered; `current_state` honestly names what is delivered and what
remains deferred (richer stream narration of hook activity beyond a blocking PreToolUse's `error`
event; an ask/allow/deny permission UX around hooks, overlapping row #17).
`docs/GAP-MAP.md` row #16 and `tests/test_ext041_product_parity.py`'s honesty-pin are updated to
match, mirroring how EXT-042/EXT-043/EXT-044/EXT-045/EXT-046 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=16` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [x] `docs/GAP-MAP.md` row #16's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and the `n_works`/aggregate-
      bound assertions include row #16.
