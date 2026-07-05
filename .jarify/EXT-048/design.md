# EXT-048 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #17 names Claude Code's permission-rules + modes
surface: a settings file mapping `{tool-pattern, action}` to `allow`/`ask`/`deny`, plus a session
mode cycle (`plan` -> propose only, `default` -> today's behavior, `acceptEdits` -> auto-approve
edits). jaros-code already has the right hard gates (EXT-001/REQ-7 shell denylist, EXT-037
path-jail, git-secrets guard) enforced at `harness.coding_loop.Runtime.apply` -- the ONE gate ->
executor -> decision-log choke point every tool call already passes through, extended once already
by EXT-047's hooks -- but there is no user-facing rules layer and no mode concept at all.

The fix must not create a second, competing safety mechanism, and must NEVER let user policy widen
what the hard gates already refuse: a permission rule is consulted strictly AFTER
`validate_decision()` has already accepted the Decision. `plan` mode's "propose only" guarantee
must be even stronger than a permission rule -- it withholds the decision from ever reaching the
gate or hooks at all, so it can never accidentally run a side effect via a mis-configured rule.

## Mechanism

```
  PERMISSIONS CONFIG (user-authored data, inert JSON -- never executed directly)
  +---------------------------------------------------------------------------------+
  | <repo>/.jcode/permissions.json   (PROJECT tier -- consulted FIRST)               |
  | ~/.jcode/permissions.json        (USER tier -- optional, mirrors EXT-042/046/047)|
  |                                                                                   |
  |   {"rules": [                                                                    |
  |     {"tool": "shell.exec", "arg": "pytest*", "action": "allow"},                 |
  |     {"tool": "code.write_file", "arg": "*.md", "action": "ask"},                 |
  |     {"tool": "git.commit", "action": "deny"}                                    |
  |   ]}                                                                             |
  +--------------------------------------+------------------------------------------+
                                           | discovered once per CLI instance (mirrors the
                                           | EXT-042/046/047 caching precedent)
                                           v
  REGISTRY (harness/permissions.py -- NEW module, pure deterministic file I/O + glob match)
  +-----------------------------------------------------------------------------------+
  | PermissionRule(tool, arg, action, source)                                         |
  |                                                                                     |
  | load_permission_rules(root=".") -> [PermissionRule, ...]   (project rules FIRST,   |
  |                                                              then user rules --    |
  |                                                              FIRST-MATCH-WINS, so   |
  |                                                              project overrides the  |
  |                                                              user default; document |
  |                                                              this explicitly)       |
  |                                                                                     |
  | decide(rules, tool_name, arg=None) -> "allow" | "ask" | "deny"                     |
  |   * first rule whose tool/arg globs match wins outright                            |
  |   * no matching rule -> "allow" (today's behavior: no EXTRA restriction beyond the |
  |     hard gates, which is what makes "no permissions.json anywhere" a no-op)        |
  |                                                                                     |
  | resolve_decision_arg(decision) -> str | None   (pulls path/command/target/message  |
  |                                                  out of the payload for arg-glob    |
  |                                                  matching)                          |
  |                                                                                     |
  | MODES = ("plan", "default", "acceptEdits")                                        |
  | PLAN_MODE_WITHHELD_TYPES  -- write/shell Decision types withheld under `plan`      |
  | ACCEPT_EDITS_AUTO_TYPES   -- write Decision types `acceptEdits` auto-approves      |
  |                              on an `ask` result (never shell.exec -- narrower)     |
  +--------------------------------------+--------------------------------------------+
                                           | consulted from the SAME seam EXT-047 uses:
                                           v
  CLERK SEAM (harness/coding_loop.py::Runtime.apply -- EXISTING, additively extended)
  +-------------------------------------------------------------------------------------+
  | apply(decision):                                                                     |
  |   [root-jail stamp -- EXT-037, unchanged]                                            |
  |   if self._mode == "plan" and decision.type in PLAN_MODE_WITHHELD_TYPES:             |
  |     return {"planned": True, ...}   <- NO hook firing, NO gate, NO executor at all   |
  |   [PreToolUse hooks -- EXT-047, unchanged]                                            |
  |   gated = validate_decision(decision)          <- THE HARD GATE, runs UNCONDITIONALLY |
  |   if not gated.ok: raise RuntimeError(...)     <- a user `allow` rule NEVER reaches   |
  |                                                    this far if the hard gate refused  |
  |   if self._permission_rules:                                                          |
  |     action = decide(self._permission_rules, decision.type, resolve_decision_arg(d))   |
  |     if action == "deny": raise RuntimeError(...)   <- genuine refusal                 |
  |     if action == "ask":                                                                |
  |       if mode == "acceptEdits" and type in ACCEPT_EDITS_AUTO_TYPES: pass (allow)       |
  |       elif self._ask_callback: approved = ask_callback(type, arg); deny if declined    |
  |       else: raise RuntimeError(...)   <- headless/no prompt -> safe-default DENY,      |
  |                                            never hang                                 |
  |   outcome = executor.apply(decision, ...)      <- unchanged                            |
  |   [PostToolUse hooks -- EXT-047, unchanged]                                            |
  +-------------------------------------------------------------------------------------+
                                           ^
                                           | mode + rules + an optional interactive ask_callback
                                           | supplied by the CLI lifecycle:
  LIFECYCLE (harness/cli.py::JcodeCli)
  +-----------------------------------------------------------------------------------+
  | __init__(..., interactive=False):                                                 |
  |   self.permission_rules = load_permission_rules(".")                              |
  |   self.mode = DEFAULT_MODE                                                        |
  |   self.rt = Runtime(..., mode=self.mode, permission_rules=self.permission_rules,   |
  |                      ask_callback=(self._ask_permission if interactive else None)) |
  |                                                                                     |
  | cmd_mode(arg): cycles/sets self.mode, calls self.rt.set_mode(self.mode)            |
  | cmd_permissions(_arg): lists configured rules (or an honest empty message)         |
  | _ask_permission(tool, arg): input()-based y/n prompt (REPL only, never blocking a   |
  |                              headless run since ask_callback is None there)        |
  +-----------------------------------------------------------------------------------+
```

- **No second reasoning mechanism.** Deciding which rule applies, and whether plan mode withholds
  a Decision, is a pure dictionary/glob lookup (`decide`, `_matches`-style glob via `fnmatch`) --
  never a model judgement. The model is never consulted about permissions or modes.
- **The hard gate is never bypassed -- this is the whole point of the spec.** `validate_decision()`
  runs BEFORE any permission-rule lookup and its rejection is unconditional; the permission-rule
  block is placed strictly AFTER the existing `if not gated.ok: raise` statement in `apply()`, so
  there is no code path in which a rule is even consulted for a Decision the hard gate refused.
- **`plan` mode is stronger than a permission rule.** It intercepts BEFORE hooks fire and before
  the gate runs at all for the specific Decision types it withholds (`code.write_file`,
  `code.apply_patch`, `code.search_replace`, `shell.exec`) -- a true "propose only," not merely
  "ask and default to no." Read-only types (`fs.read`, `fs.grep`, ...) are unaffected by `plan`
  mode, so an agent can still gather information while proposing a plan.
- **`ask` never hangs.** In a headless/one-shot run (`ask_callback=None`), an `ask` action
  degrades to a safe-default `deny` -- documented explicitly, never a silent allow and never a
  blocking `input()` call with no terminal attached.
- **Discovery is cached once per `JcodeCli` instance**, exactly mirroring `self.hooks_config`/
  `self.skills`/`self.jcode_md` (EXT-047/046/042).
- **Never raises.** `load_permission_rules` degrades tier-by-tier and entry-by-entry (a
  missing/unreadable file, invalid JSON, or one malformed rule entry contributes nothing rather
  than aborting); every function here is defensive to the same standard as `harness/hooks.py`.

## Two-plane / honesty

`harness/permissions.py` is pure deterministic execution-plane code (Tenet 1): JSON parsing, glob
matching, and a first-match lookup -- no LLM call anywhere in the module, and no new Decision TYPE
is introduced. Per Tenet 3, `harness/product_parity.py` row #17 is flipped to `"works"` only
because the rules loader, the safety invariant (hard-gate-first, proven by an explicit test), the
mode cycle (`/mode`), and the ask-never-hangs fallback are genuinely delivered and test-covered;
`current_state` honestly names what remains deferred (a `bypassPermissions`/"YOLO" mode Claude Code
also offers -- deliberately NOT built, since it would contradict the hard-gate-first invariant this
spec exists to prove; a settings-hierarchy precedence UI beyond project-then-user first-match).

## Backward compatibility (no regression)

- `Runtime.__init__`'s new `mode`, `permission_rules`, and `ask_callback` parameters default to
  `"default"`, `None`, and `None` respectively -- every existing call site (`_git_tool`, every
  pre-EXT-048 test, `JcodeCli.__init__` itself before this spec) that doesn't pass them behaves
  byte-identically: the new `plan`-mode branch is only reachable when `self._mode == "plan"`
  (never true by default), and the new permission-rule block is only reachable
  `if self._permission_rules:` (never true when `None`/`[]`).
- `JcodeCli.__init__`'s new `interactive` parameter defaults to `False` -- every existing
  construction call site (every test, and the headless one-shot path) stays exactly as before;
  only `repl()` explicitly opts in.
- A repo with no `.jcode/permissions.json` anywhere yields `JcodeCli.permission_rules == []` --
  `Runtime(permission_rules=[])` behaves exactly as `permission_rules=None` (both are falsy).

## Out of scope (this task)

A `bypassPermissions`/"YOLO" mode (Claude Code has one; it would let a rule or mode skip the hard
gate, which directly contradicts this spec's safety invariant -- not built, on purpose); a settings
UI/precedence visualization beyond `/permissions`' flat listing; permission-rule authoring/
scaffolding tooling; narrating `ask`/`deny` decisions in the EXT-045 terminal stream beyond the
existing `error` event a denial already emits. These remain honestly named in `docs/GAP-MAP.md`
row #17's "Next lever" as the residual gap, per Tenet 3.
