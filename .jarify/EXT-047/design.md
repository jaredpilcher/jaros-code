# EXT-047 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #16 names Claude Code's lifecycle-hooks surface:
configure a shell command that fires automatically on `PreToolUse`, `PostToolUse`, `SessionStart`,
or `Stop`. Today jaros-code has exactly the right SEAM for this — `harness.coding_loop.Runtime.
apply` is the ONE real gate → executor → decision-log choke point every tool call already passes
through (EXT-045's streaming `on_event` hook proved this seam is reusable for cross-cutting
concerns) — but there is no user-facing way to configure a hook there at all.

The fix must not invent a second execution mechanism or a way around the existing safety gates: a
hook is just a shell command, and every shell command in this harness already has a gated path
(`.jaros-data/tools/shell_exec_tool.py`'s `validate()`/`execute()`, reached via `Runtime.apply` with
a `shell.exec` Decision — denylist + timeout + process-tree-kill). Hooks must run through that SAME
path, not a raw `subprocess.run`.

## Mechanism

```
  HOOKS CONFIG (user-authored data, inert JSON -- never executed directly)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ <repo>/.jcode/hooks.json      (PROJECT tier)                                        │
  │ ~/.jcode/hooks.json           (USER tier -- optional, mirrors EXT-042/EXT-046)       │
  │                                                                                       │
  │   {                                                                                  │
  │     "PreToolUse":  [{"command": "ruff check .", "matcher": "code.write_file"}],      │
  │     "PostToolUse": [{"command": "echo done"}],                                       │
  │     "SessionStart":[{"command": "echo hello"}],                                      │
  │     "Stop":        [{"command": "echo bye"}]                                        │
  │   }                                                                                  │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ discovered once per CLI instance (mirrors the
                                          │ EXT-042/EXT-046 caching precedent)
                                          ▼
  REGISTRY (harness/hooks.py -- NEW module, pure deterministic file I/O, no model calls)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ HookDef(command, matcher, source)        HookOutcome(event, command, matcher,       │
  │                                                        exit_code, stdout, stderr,     │
  │                                                        blocked)                      │
  │                                                                                       │
  │ load_hooks(root=".") -> {event: [HookDef, ...]}   (project+user tiers, ADDITIVE --    │
  │                                                     both fire, unlike EXT-046 skills' │
  │                                                     project-wins-on-collision rule)   │
  │                                                                                       │
  │ fire_event(event, cfg, tool_name=None, cwd=None, run_command=None)                    │
  │   -> [HookOutcome, ...]                                                              │
  │   * PreToolUse/PostToolUse: only hooks whose `matcher` glob-matches `tool_name` fire   │
  │   * SessionStart/Stop: no tool to scope against -- every configured hook fires        │
  │   * a PreToolUse hook exiting non-zero is flagged `blocked=True`                      │
  │                                                                                       │
  │ _default_run_command(command, cwd) -- the REAL runner:                              │
  │   builds a FRESH, hooks-DISABLED Runtime and applies a `shell.exec` Decision through  │
  │   it -- the SAME gate (denylist) + executor (timeout, tree-kill) every other tool     │
  │   call uses. Fresh + hooks-disabled -> firing a hook can NEVER recursively re-fire    │
  │   hooks (no infinite loop even if a hook's own command would itself match a           │
  │   PreToolUse matcher).                                                                │
  │                                                                                       │
  │ blocked(outcomes) / blocking_reason(outcomes)                                        │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ consulted from TWO existing seams:
                     ┌────────────────────┴────────────────────┐
                     ▼                                          ▼
  CLERK SEAM (harness/coding_loop.py::Runtime.apply --   LIFECYCLE (harness/cli.py::JcodeCli)
  EXISTING, additively extended)                          ┌────────────────────────────────┐
  ┌──────────────────────────────────────────────┐        │ __init__:                       │
  │ apply(decision):                              │        │   self.hooks_config = load_hooks│
  │   [root-jail stamp -- EXT-037, unchanged]     │        │     (".")                       │
  │   if hooks_config:                            │        │   self.rt = Runtime(             │
  │     pre = fire_event("PreToolUse", cfg,       │        │       hooks_config=hooks_config) │
  │                       tool_name=decision.type)│        │   fire_event("SessionStart", cfg)│
  │     if blocked(pre): raise RuntimeError(...)  │◄───────┤     (once, here)                │
  │       <- tool call NEVER reaches validate()/  │        │                                 │
  │          execute() -- a genuine refusal       │        │ on_stop():                       │
  │   _emit("call")                               │        │   fire_event("Stop", cfg)        │
  │   gate = validate_decision(decision)          │        │     (once, idempotent)           │
  │   outcome = executor.apply(decision, ...)     │        │   called from repl()'s /quit/EOF/│
  │   _emit("result")                             │        │   interrupt AND from             │
  │   if hooks_config:                            │        │   _run_one_shot() after its       │
  │     fire_event("PostToolUse", cfg,            │        │   single turn                    │
  │                 tool_name=decision.type)      │        │                                 │
  │   return outcome.output                       │        │ cmd_hooks(): lists configured    │
  └──────────────────────────────────────────────┘        │   hooks (or an honest empty msg) │
                                                            └────────────────────────────────┘
```

- **No second reasoning mechanism.** Deciding WHICH hook fires for WHICH event/tool is a pure
  dictionary lookup + glob match (`_matches`) — never a model judgement. The model is never
  consulted about whether a hook fires, and never authors a hook (the user does, by editing the
  JSON file).
- **The gate is never bypassed.** A hook's shell command reaches the host exactly the way any
  other `shell.exec` Decision does — through `validate()`'s denylist (no network egress/
  destructive ops without an explicit `allow_unsafe`) and `execute()`'s timeout + process-tree-kill.
  There is no code path in this spec that runs a hook command via a raw, ungated `subprocess` call.
- **Anti-recursion by construction, not by a special-case flag.** `_default_run_command` always
  builds a Runtime with `hooks_config=None` — the ONLY Runtime instance that ever carries a real
  `hooks_config` is the one the CALLER (e.g. `JcodeCli.rt`) constructs for its OWN tool calls. A
  hook firing through `_default_run_command`'s inner Runtime therefore structurally cannot
  re-trigger `PreToolUse`/`PostToolUse` firing for itself, no matter how the outer config is
  written.
- **Block-on-nonzero is a genuine refusal, not a warning.** `Runtime.apply` raises `RuntimeError`
  BEFORE `validate_decision()` is ever called when a `PreToolUse` hook blocks — the write/command/
  test-run the caller was about to perform never happens, exactly like a gate rejection today.
- **Discovery is cached once per `JcodeCli` instance**, exactly mirroring `self.skills`/
  `self.jcode_md` (EXT-046/EXT-042).
- **Never raises.** `load_hooks` degrades tier-by-tier and entry-by-entry (a missing/unreadable
  file, invalid JSON, or one malformed hook entry contributes nothing rather than aborting); every
  hook-firing path is defensive to the same standard as `harness/skills.py`/`harness/jcode_md.py`.

## Two-plane / honesty

`harness/hooks.py` is pure deterministic execution-plane code (Tenet 1): JSON parsing, glob
matching, and dispatching a shell command through the EXISTING gated `shell.exec` Decision path —
no LLM call anywhere in the module, and no new Decision TYPE is introduced (a hook's command is
just another `shell.exec` Decision). Per Tenet 3, `harness/product_parity.py` row #16 is flipped to
`"works"` only because the four lifecycle events, config loading, block-on-nonzero, and gated
execution are genuinely delivered and test-covered; the row's `current_state` honestly names what
remains deferred (richer stream narration of successful — non-blocking — hook activity; an
ask/allow/deny permission UX around hooks, which overlaps row #17 and is out of this spec's scope).

## Backward compatibility (no regression)

- `Runtime.__init__`'s new `hooks_config` parameter defaults to `None` — every existing call site
  (`_git_tool`, every pre-EXT-047 test, `JcodeCli.__init__` itself before this spec) that doesn't
  pass it behaves byte-identically: `apply()`'s two new `if self._hooks_config:` blocks are
  skipped entirely, and `harness.hooks` is never even imported.
- A repo with no `.jcode/hooks.json` anywhere yields `JcodeCli.hooks_config == {}` —
  `SessionStart`/`Stop` firing becomes a no-op, and `Runtime(hooks_config={})` behaves exactly as
  `hooks_config=None` (both are falsy).
- `on_stop()` is idempotent (`self._stop_fired` guard) so calling it more than once (e.g. an
  interrupted REPL loop) can never double-fire `Stop` hooks.

## Out of scope (this task)

A permission-rules-style ask/allow/deny UX layered on top of hooks (that is row #17's territory);
surfacing successful (non-blocking) hook activity in the EXT-045 terminal stream beyond the
`error` event a block already emits; a hook-authoring/scaffolding command; nested/glob-based event
names beyond the four Claude-Code-style events named here. These remain honestly named in
`docs/GAP-MAP.md` row #16's "Next lever" as the residual gap, per Tenet 3.
