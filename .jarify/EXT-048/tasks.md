# Implementation Tasks

### [TASK-1] Permission rules + modes, wired into the Runtime seam and CLI lifecycle

Add a new `harness/permissions.py` module that discovers a user's `.jcode/permissions.json`
(project) and `~/.jcode/permissions.json` (user) config, mapping rules to `allow`/`ask`/`deny`;
wire the hard-gate-first safety invariant and a `plan`/`default`/`acceptEdits` mode cycle into
`harness.coding_loop.Runtime.apply` (the same gate -> executor -> decision-log choke point EXT-047's
hooks use); wire a `/mode` and `/permissions` REPL command into `harness.cli.JcodeCli`.

#### Steps
1. Create `harness/permissions.py`: `@dataclass(frozen=True) PermissionRule(tool, arg, action,
   source)`. A private `_parse_rule_item`/`_parse_permissions_file` pair (tolerant JSON parse,
   accepts either a top-level list or a `{"rules": [...]}` dict, skips malformed entries, never
   raises) and `load_project_permissions(root=".")`/`load_user_permissions()`/
   `load_permission_rules(root=".")` (project tier first, then user tier, concatenated — order
   matters for first-match-wins in `decide`).
2. In `harness/permissions.py`: `_rule_matches(rule, tool_name, arg)` (glob via `fnmatch` on both
   `tool` and `arg`, `None`/absent matches everything); `decide(rules, tool_name, arg=None) ->
   "allow"|"ask"|"deny"` (first matching rule wins, no match -> `"allow"`);
   `resolve_decision_arg(decision)` (pulls `path`/`command`/`target`/`message` out of the payload
   for arg-glob matching). Define `MODES = ("plan", "default", "acceptEdits")`,
   `DEFAULT_MODE = "default"`, `PLAN_MODE_WITHHELD_TYPES` (`code.write_file`, `code.apply_patch`,
   `code.search_replace`, `shell.exec`), and `ACCEPT_EDITS_AUTO_TYPES` (the write subset, excluding
   `shell.exec`).
3. In `harness/coding_loop.py`: add optional `mode: str = "default"`, `permission_rules:
   "list | None" = None`, `ask_callback: "callable | None" = None` parameters to `Runtime.__init__`
   (stored as `self._mode`/`self._permission_rules`/`self._ask_callback`) and a `set_mode(self,
   mode)` method. In `apply()`, immediately after the root-jail stamp: if `self._mode == "plan"`
   and `decision.type` is in `PLAN_MODE_WITHHELD_TYPES`, emit a `"planned"` event and return
   `{"planned": True, "type": decision.type, "payload": decision.payload}` WITHOUT firing hooks,
   the gate, or the executor. After the existing `if not gated.ok: raise` block (hard gate ran
   first, unconditionally) and before `executor.apply()`: if `self._permission_rules` is
   non-empty, resolve `decide(...)`; `"deny"` raises `RuntimeError`; `"ask"` auto-approves when
   `self._mode == "acceptEdits"` and the type is in `ACCEPT_EDITS_AUTO_TYPES`, otherwise calls
   `self._ask_callback(type, arg)` if present (declining raises) or raises a safe-default-deny
   `RuntimeError` when no callback is available (never calls `input()` directly in `Runtime`).
4. In `harness/cli.py`: `JcodeCli.__init__` gains an `interactive: bool = False` parameter, loads
   `self.permission_rules = load_permission_rules(".")` (defensive `try/except` -> `[]`) and
   `self.mode = DEFAULT_MODE` BEFORE constructing `self.rt`, passing
   `mode=self.mode, permission_rules=self.permission_rules, ask_callback=(self._ask_permission if
   interactive else None)` into `Runtime(...)`. Add `_ask_permission(self, tool_name, arg)` (an
   `input()`-based y/n prompt, any exception -> `False`). Add `cmd_mode(self, arg)` (no arg cycles
   `plan -> default -> acceptEdits -> plan`; a valid name sets it directly; an invalid name returns
   a usage error; either way calls `self.rt.set_mode(self.mode)`) and `cmd_permissions(self, _arg)`
   (lists configured rules, or an honest empty message). Also pass
   `mode=getattr(self, "mode", "default"), permission_rules=getattr(self, "permission_rules",
   None), ask_callback=(self._ask_permission if getattr(self, "_interactive", False) else None)`
   into `_git_tool`'s separately-constructed `Runtime` for consistency. `repl()` constructs
   `JcodeCli(session_id=session_id, stream=_stream, interactive=True)`; the headless one-shot path
   is unchanged (default `interactive=False`). Document `/mode` and `/permissions` in the module
   docstring's command list.
5. Update `harness/product_parity.py` row `id=17` (Permission rules + modes UX): flip `state` to
   `"works"`; `current_state` names what is genuinely delivered (two-tier rules config, first-
   match `decide()`, the hard-gate-first safety invariant, ask-never-hangs headless fallback, the
   `plan`/`default`/`acceptEdits` mode cycle, `/mode`, `/permissions`) and what remains deferred (a
   `bypassPermissions`/"YOLO" mode, deliberately not built since it would contradict the safety
   invariant; a richer settings-hierarchy precedence UI); `next_lever` names only that residual
   gap. Mirror the same honest update into `docs/GAP-MAP.md` row #17's `State`/`Current honest
   state`/`Next lever` columns.
6. Update `tests/test_ext041_product_parity.py`: add `17` to the `works == [...]` pin (kept
   sorted), and update `test_score_default_rows_reflects_honest_current_baseline`'s
   `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to match the new
   works-count.
7. Write `tests/test_ext048_permissions.py` (deterministic, no live gemma): `load_permission_rules`
   project+user-tier combination and ordering, malformed-config/entry skipping, no-file-anywhere
   no-op; `decide()` first-match-wins, no-match -> `"allow"`, tool/arg glob scoping; `Runtime.apply`
   end-to-end with REAL deterministic Decisions (`fs.read`/`code.write_file`/`shell.exec`) proving:
   the SAFETY INVARIANT (a permissions.json that `allow`s a denylisted `shell.exec` command is
   STILL refused by the hard gate, with the gate's own rejection reason); `"deny"` genuinely blocks
   before `executor.apply()`; `"ask"` with an injected `ask_callback` (approve/decline) and with
   `ask_callback=None` (safe-default deny, never calling `input()`); `plan` mode withholding a
   write/shell Decision (no filesystem write occurs) while leaving `fs.read` unaffected;
   `acceptEdits` auto-approving an `"ask"`-resolving write Decision but NOT a `shell.exec` one;
   `Runtime` with no `permission_rules`/default `mode` behaving byte-identically to pre-EXT-048;
   `JcodeCli.cmd_mode`/`cmd_permissions`/`/help` documentation.

#### Implements
- [REQ-1] Permission rules config — discover `.jcode/permissions.json` (project + user tiers)
- [REQ-2] `decide()` + the hard-gate-first safety invariant
- [REQ-3] `ask` resolution — interactive prompt or a safe headless fallback, never hang
- [REQ-4] Modes — `plan` / `default` / `acceptEdits`, `/mode` command
- [REQ-5] Honest Product-Parity Checklist update
