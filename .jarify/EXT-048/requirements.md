---
id: EXT-048
title: Permission rules + modes UX
status: covered
priority: medium
---

# EXT-048 — Permission rules + modes UX

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #17 — a user drops a
`.jcode/permissions.json` config mapping a tool-pattern to `allow`/`ask`/`deny`, and a REPL mode
cycle (`plan` -> `default` -> `acceptEdits`) governs whether writes/shell actually execute. Both
are consulted at the existing `harness.coding_loop.Runtime.apply` gate seam (the same one EXT-047's
hooks use). The built-in HARD gates (egress/destructive-ops denylist, secrets, path-jail) are
ALWAYS enforced first and unconditionally — a user `allow` rule can never widen what they refuse.

### [REQ-1] Permission rules config — discover `.jcode/permissions.json` (project + user tiers)

A deterministic loader discovers a JSON permissions config at the PROJECT level
(`<repo>/.jcode/permissions.json`) and the USER level (`~/.jcode/permissions.json`, mirroring the
EXT-042/EXT-046/EXT-047 two-tier convention), each holding a list of rules of the form
`{"tool": <glob, optional>, "arg": <glob, optional>, "action": "allow"|"ask"|"deny"}`.

#### Acceptance Criteria
- [x] `harness.permissions.load_permission_rules(root=".")` returns a `list[PermissionRule]`
      combining BOTH tiers: PROJECT rules first, then USER rules (first-match-wins in `decide`,
      so project rules take precedence over user defaults — documented explicitly).
- [x] `PermissionRule` carries `tool` (`None` when absent — matches every tool), `arg` (`None`
      when absent — matches every arg), `action` (one of `allow`/`ask`/`deny`), and `source` (the
      config file path, for diagnostics).
- [x] A missing `.jcode/permissions.json` (either tier) yields an empty contribution from that
      tier — never raises, never treated as an error.
- [x] Malformed JSON, a non-dict/non-list top level, or a malformed individual rule entry (missing/
      invalid `action`, non-dict item) is SKIPPED — never raised — so one bad entry can never
      break discovery of the others.
- [x] No `.jcode/permissions.json` anywhere (either tier) yields `load_permission_rules() == []` —
      a graceful no-op, zero behavior change for every downstream caller.

### [REQ-2] `decide()` + the hard-gate-first safety invariant

`harness.permissions.decide(rules, tool_name, arg=None)` resolves the first matching rule's
action (first-match-wins glob on `tool`/`arg`), defaulting to `"allow"` when nothing matches. This
function is consulted from `harness.coding_loop.Runtime.apply` STRICTLY AFTER the existing hard
gate (`validate_decision()`) has already accepted the Decision — never before, and never in a way
that can override a hard-gate rejection.

#### Acceptance Criteria
- [x] `decide([], "shell.exec")` (and any `tool_name` with no matching rule) returns `"allow"` —
      the no-rules-configured case is a no-op, matching today's behavior.
- [x] `decide(rules, tool_name, arg)` returns the FIRST rule (in list order) whose `tool` glob (if
      any) matches `tool_name` AND whose `arg` glob (if any) matches `arg` — later rules are never
      consulted once a match is found.
- [x] `Runtime.apply(decision)`: the permission-rule check (when `self._permission_rules` is
      non-empty) is placed AFTER the existing `if not gated.ok: raise RuntimeError(...)` gate
      rejection — a Decision the hard gate refuses NEVER reaches the permission-rule lookup, so an
      `allow` rule for that tool/arg has no effect on the refusal. An explicit test proves this: a
      `permissions.json` that `allow`s a denylisted/destructive `shell.exec` command is STILL
      refused by the hard gate, with the gate's own rejection reason, not a permission message.
- [x] A `"deny"` action raises `RuntimeError` before `executor.apply()` runs (a genuine refusal, no
      partial effect).
- [x] `Runtime(...)` with no `permission_rules` (the default, `None`) is a complete no-op —
      behaves byte-identically to every pre-EXT-048 caller (`_git_tool`, every existing test/
      production call site) — `harness.permissions` is never even consulted.

### [REQ-3] `ask` resolution — interactive prompt or a safe headless fallback, never hang

An `"ask"` action either prompts interactively (when the caller supplied an `ask_callback`,
wired only from the interactive REPL) or degrades to a safe-default `deny` when no callback is
available (a headless/one-shot run) — it must never block indefinitely on `input()` with no
terminal attached.

#### Acceptance Criteria
- [x] `Runtime.apply(decision)` with an `"ask"`-resolving rule and an injected `ask_callback` that
      returns `True` allows the Decision to proceed to `executor.apply()`; returning `False` raises
      `RuntimeError` (declined).
- [x] The same `"ask"`-resolving rule with `ask_callback=None` (the headless default) raises
      `RuntimeError` (safe-default deny) WITHOUT ever calling `input()` or blocking.
- [x] `harness.cli.JcodeCli.__init__` gains an `interactive: bool = False` parameter (default
      unchanged for every existing caller); only `repl()` passes `interactive=True`, wiring
      `self._ask_permission` (an `input()`-based y/n prompt) as the `Runtime`'s `ask_callback`.
      The headless one-shot path never passes `interactive=True`.

### [REQ-4] Modes — `plan` / `default` / `acceptEdits`, `/mode` command

A REPL mode cycle governs side effects at the SAME `Runtime.apply` seam: `plan` withholds every
write/shell Decision (`code.write_file`, `code.apply_patch`, `code.search_replace`, `shell.exec`)
before the gate or hooks ever see it, returning a `{"planned": True, ...}` description instead;
`default` is today's behavior (byte-identical, the default); `acceptEdits` auto-approves an
`"ask"`-resolving write Decision (never `shell.exec`) that has ALREADY passed the hard gate. A
`/mode [plan|default|acceptEdits]` REPL command sets or cycles the mode; `/permissions` lists
configured rules; both are documented in `/help`.

#### Acceptance Criteria
- [x] `Runtime.apply(decision)` with `self._mode == "plan"` and `decision.type` in the withheld set
      returns `{"planned": True, "type": ..., "payload": ...}` without invoking `validate_decision`,
      `executor.apply`, or any PreToolUse/PostToolUse hook — proven by asserting no filesystem
      write occurs and by an injected hook/gate spy never firing.
  * NOTE: `plan` mode does NOT withhold read-only Decision types (`fs.read`, `fs.grep`, ...) —
      those execute normally so information-gathering still works while proposing a plan.
- [x] `Runtime.apply(decision)` with `self._mode == "acceptEdits"` and an `"ask"`-resolving rule on
      a write-type Decision proceeds to `executor.apply()` WITHOUT an `ask_callback` — but the SAME
      mode with an `"ask"`-resolving rule on `shell.exec` still requires a callback or falls back
      to the safe deny (acceptEdits only auto-approves the narrower write set, not shell).
- [x] `Runtime(...)` with `mode="default"` (the default) is byte-identical to pre-EXT-048 behavior.
- [x] `JcodeCli.cmd_mode(arg)`: no argument cycles `plan -> default -> acceptEdits -> plan`; a
      valid mode name sets it directly; an invalid name returns an honest usage error. Either way
      it updates the live `Runtime` (`self.rt.set_mode(...)`) so the change takes effect
      immediately, without reconstructing the CLI.
- [x] `JcodeCli.cmd_permissions(_arg)` lists every configured rule (or an honest empty message).
- [x] `/help`'s command list documents `/mode` and `/permissions`, and the `.jcode/permissions.json`
      convention.

### [REQ-5] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=17` (Permission rules + modes UX) is flipped to `"works"` ONLY
because the rules loader, the hard-gate-first safety invariant, the ask-never-hangs fallback, and
the mode cycle are genuinely delivered and test-covered; `current_state` honestly names what is
delivered and what remains deferred (a `bypassPermissions`/"YOLO" mode, deliberately not built
since it would contradict the safety invariant; a richer settings-hierarchy precedence UI).
`docs/GAP-MAP.md` row #17 and `tests/test_ext041_product_parity.py`'s honesty-pin are updated to
match, mirroring how EXT-042/043/044/045/046/047 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=17` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [x] `docs/GAP-MAP.md` row #17's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and the `n_works`/aggregate-
      bound assertions include row #17.
