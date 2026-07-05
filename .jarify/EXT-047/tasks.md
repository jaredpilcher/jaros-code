# Implementation Tasks

### [TASK-1] Lifecycle hooks config + gated firing, wired into the Runtime seam and CLI lifecycle

Add a new `harness/hooks.py` module that discovers a user's `.jcode/hooks.json` (project) and
`~/.jcode/hooks.json` (user) config, mapping `PreToolUse`/`PostToolUse`/`SessionStart`/`Stop` to a
list of `{command, matcher}` entries; wire `PreToolUse`/`PostToolUse` firing into
`harness.coding_loop.Runtime.apply` (the one gate → executor → decision-log choke point every tool
call already passes through) with a block-on-nonzero `PreToolUse` refusal, and wire
`SessionStart`/`Stop` firing into `harness.cli.JcodeCli`'s construction and session-end points.
Every hook's shell command runs through the existing gated `shell.exec` Decision path via a fresh,
hooks-disabled `Runtime` (no recursion possible).

#### Steps
1. Create `harness/hooks.py`: `@dataclass(frozen=True) HookDef(command, matcher, source)` and
   `HookOutcome(event, command, matcher, exit_code, stdout, stderr, blocked)`. A private
   `_parse_hook_item`/`_parse_hooks_file` pair (tolerant JSON parse, skip malformed entries/events,
   never raise) and `load_project_hooks(root=".")`/`load_user_hooks()`/`load_hooks(root=".")`
   (project + user tiers combined ADDITIVELY per event — both fire, no name-collision override).
2. In `harness/hooks.py`: `_matches(matcher, tool_name)` (glob via `fnmatch`, `None`/`"*"` matches
   everything); `_default_run_command(command, cwd)` (builds a FRESH `Runtime` with NO
   `hooks_config`, applies a `shell.exec` Decision through it — the real gated path — and reports
   any gate/executor `RuntimeError` as an honest non-zero exit); `fire_event(event, hooks_config,
   tool_name=None, cwd=None, run_command=None)` (fires every matching configured hook, injectable
   runner for tests, never raises); `blocked(outcomes)`/`blocking_reason(outcomes)`.
3. In `harness/coding_loop.py`: add an optional `hooks_config` parameter to `Runtime.__init__`
   (default `None` — every existing caller stays byte-identical) stored as `self._hooks_config`.
   In `apply()`, BEFORE `validate_decision()`, fire `PreToolUse` hooks matching `decision.type`
   when `self._hooks_config` is non-empty; if any is blocking, `_emit` an error event and raise
   `RuntimeError` (the tool call never reaches the gate). AFTER a successful `execute()`, fire
   `PostToolUse` hooks (observational only, never raises).
4. In `harness/cli.py`: `JcodeCli.__init__` loads `self.hooks_config = load_hooks(".")` (defensive
   `try/except` → `{}`) BEFORE constructing `self.rt`, passes it to `Runtime(hooks_config=...)`,
   and fires `SessionStart` hooks once (`self._session_start_outcomes`). Add `on_stop()` (fires
   `Stop` hooks once, idempotent via a `_stop_fired` guard) called from `repl()`'s `/quit`/EOF/
   interrupt return points and from `_run_one_shot()` after its single turn. Also pass
   `hooks_config=self.hooks_config` into `_git_tool`'s separately-constructed `Runtime` for
   consistency. Add `cmd_hooks(self, _arg)` listing configured hooks (or an honest empty message)
   and document `/hooks` in the module docstring's command list.
5. Update `harness/product_parity.py` row `id=16` (User-configurable hooks): flip `state` to
   `"works"`; `current_state` names what is genuinely delivered (config loading, the four
   lifecycle events, block-on-nonzero, gated execution via the shared `shell.exec` path,
   anti-recursion, `/hooks`) and what remains deferred (richer stream narration of non-blocking
   hook activity; an ask/allow/deny permission UX overlapping row #17); `next_lever` names only
   that residual gap. Mirror the same honest update into `docs/GAP-MAP.md` row #16's `State`/
   `Current honest state`/`Next lever` columns.
6. Update `tests/test_ext041_product_parity.py`: add `16` to the `works == [...]` pin (kept
   sorted), and update `test_score_default_rows_reflects_honest_current_baseline`'s
   `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to match the new
   works-count.
7. Write `tests/test_ext047_hooks.py` (deterministic, no live gemma): `load_hooks`
   project+user-tier combination, malformed-config/entry skipping, matcher scoping; `fire_event`
   with an injected fake runner (order, block-on-nonzero, PostToolUse never blocks, unknown event/
   `None` config/runner-raises degrade to nothing); `Runtime.apply` end-to-end with a REAL
   deterministic Decision (`fs.read`/`code.write_file`) — PreToolUse fires before the tool, and a
   blocking PreToolUse hook genuinely prevents the write (asserted via the filesystem); `Runtime`
   with no `hooks_config` never even imports `harness.hooks` (backward-compat); `JcodeCli`
   `SessionStart`/`Stop` firing (once, idempotent), `/hooks`, `/help`, and a couple of tests
   exercising the REAL (non-mocked) `_default_run_command` to prove hooks run through the gated
   `shell.exec` path (a real exit code, and a denylisted command genuinely refused) rather than a
   raw subprocess call.

#### Implements
- [REQ-1] Hook config — discover `.jcode/hooks.json` (project + user tiers)
- [REQ-2] Fire at the seam — PreToolUse/PostToolUse via `Runtime.apply`, block-on-nonzero
- [REQ-3] SessionStart / Stop lifecycle
- [REQ-4] `/hooks` list command + `/help`
- [REQ-5] Honest Product-Parity Checklist update
