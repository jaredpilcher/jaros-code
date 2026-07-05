---
id: EXT-050
title: User-authorable subagents
status: covered
priority: medium
---

# EXT-050 — User-authorable subagents

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #19 — a developer drops a
markdown file describing a scoped agent (a system prompt + a tool allowlist + an optional model)
and the CLI can delegate a task to it, no code change to jaros-code required.
`.jcode/agents/<name>.md` registers subagent `<name>`; the file body is an inert system-prompt
prefix folded into the SAME gated Runtime + plain-language routing chain every other agent turn
already uses — no new reasoning mechanism, no new side-effect path. A subagent's `tools:` allowlist
can only NARROW what the hard gates already permit, at the `Runtime.apply` gate seam — never widen
past them.

### [REQ-1] Subagent registry — discover `.jcode/agents/*.md`

A deterministic registry discovers markdown subagent files at the PROJECT level
(`<repo>/.jcode/agents/*.md`) and, optionally, the USER level (`~/.jcode/agents/*.md`, mirroring
the EXT-042/046/047/048 two-tier convention). Each `<name>.md` registers a candidate subagent
`<name>`. A file may open with `---`-delimited frontmatter carrying an optional `description:`,
`tools:` (a CSV allowlist of tool/Decision type names), and `model:`; everything after the
frontmatter (or the whole file, if there is none) is the subagent's system-prompt body.

#### Acceptance Criteria
- [x] `harness.subagents.discover_subagents(root=".")` returns a `dict[str, SubagentDef]` keyed by
      subagent name, scanning `<root>/.jcode/agents/*.md` (project tier) then
      `~/.jcode/agents/*.md` (user tier); a project-tier subagent of the same name takes
      precedence over a user-tier one.
- [x] `SubagentDef` carries `name`, `description` (from frontmatter, or "" when absent), `tools`
      (a tuple of tool/Decision type names parsed from the CSV `tools:` frontmatter value, or an
      empty tuple when absent — an empty tuple means "no extra narrowing beyond the hard gates"),
      `model` (from frontmatter, or `None` when absent), `body` (the system-prompt text after
      frontmatter is stripped), and `source` (the path it was loaded from).
- [x] A file with no frontmatter is accepted — its ENTIRE content is the body, `description` is
      "", `tools` is an empty tuple, `model` is `None`.
- [x] A missing `.jcode/agents/` directory (either tier) yields an empty contribution from that
      tier — never raises, never treated as an error.
- [x] A malformed file (unreadable, bad encoding, empty body) is SKIPPED — not raised — so one bad
      file can never break discovery of the others.
- [x] A filename that is not a valid Python-identifier-like name (so it could never cleanly become
      a delegation target) is skipped rather than registered.

### [REQ-2] Delegation — a subagent's body frames a task through the existing router

`harness.subagents.render_subagent_prompt(subagent, task)` composes the subagent's `body` (a
system-prompt prefix) with the delegated `task` text into ONE plain-language request — pure string
composition, no model call, never raises on `None`/empty input. `harness.cli.JcodeCli` gains a
`_run_subagent(name, task)` method that looks up a registered subagent, composes the prompt, and
routes it through the SAME plain-language chain `_route_plain` already runs for a typed non-slash
request (deterministic multistep detection → deterministic intent fast-path → orchestrator) — not
a second reasoning mechanism. A new `/subagent <name> :: <task>` command and a deterministic,
no-model-call "delegate to `<name>` subagent: `<task>`" / "use the `<name>` subagent to `<task>`"
phrasing (only firing when `<name>` is an ACTUALLY REGISTERED subagent, so ordinary prose is never
misrouted) both invoke it.

#### Acceptance Criteria
- [x] `harness.subagents.render_subagent_prompt(subagent, task)` returns the subagent's `body`
      followed by the delegated `task` text (both present); degrades gracefully to whichever of
      the two is non-empty when the other is empty/`None`; never raises on `None` input.
- [x] `JcodeCli._run_subagent(name, task)`: an unregistered `name` returns an honest error message
      (naming `/agents` as where to discover what's registered) without raising.
- [x] `JcodeCli._run_subagent(name, task)` for a REGISTERED subagent routes the composed prompt
      through `_route_plain` — proven by an injected/stubbed orchestrator receiving the composed
      text (containing the subagent's body content, not just the raw task) rather than the raw
      task alone.
- [x] `JcodeCli.cmd_subagent(arg)` parses `"<name> :: <task>"` (mirroring the `::`-separated
      argument convention `/fix`/`/experiment` already use); a missing name or task returns a
      usage message rather than raising.
- [x] A plain (non-slash) request matching "delegate to `<name>` subagent: `<task>`" or "use the
      `<name>` subagent to `<task>`" is routed to `_run_subagent(name, task)` when `<name>` is a
      registered subagent, and falls through to today's existing routing (multistep/intent
      fast-path/orchestrator, entirely unchanged) when `<name>` does NOT match any registered
      subagent — an unrelated plain request naming no subagent is never misrouted.
- [x] Delegation is fully additive: a `JcodeCli` in a repo with no `.jcode/agents/` directory
      behaves byte-identically to before this spec (registry is `{}`, the delegation phrasing
      never matches, `_route_plain`'s prior chain runs unchanged).

### [REQ-3] Tool-allowlist safety invariant — narrows, never widens, past the hard gates

A registered subagent's `tools:` allowlist is enforced at `harness.coding_loop.Runtime.apply` —
the SAME gate → executor → decision-log seam EXT-047's hooks and EXT-048's permission rules already
use — via a new `tool_allowlist` constructor parameter. When non-empty, a Decision whose `type` is
NOT in the allowlist is refused. This check is consulted STRICTLY AFTER the existing hard gate
(`validate_decision()`) has already accepted the Decision — it can only NARROW what the hard gate
already permits, never override a hard-gate rejection.

#### Acceptance Criteria
- [x] `Runtime(...)` with `tool_allowlist=None` (the default) is a complete no-op — behaves
      byte-identically to every pre-EXT-050 caller; `harness.subagents`'s allowlist concept is
      never even consulted.
- [x] `Runtime.apply(decision)` with a non-empty `tool_allowlist` that does NOT contain
      `decision.type` raises `RuntimeError` BEFORE `executor.apply()` runs (a genuine refusal, no
      partial effect) — even when the Decision would otherwise pass the hard gate cleanly (proves
      the allowlist narrows a decision the hard gate WOULD have allowed).
- [x] `Runtime.apply(decision)` with a `tool_allowlist` that DOES `allow` a denylisted/destructive
      `shell.exec` command (e.g. one matching the EXT-001/REQ-7 safety denylist) is STILL refused
      by the hard gate, with the gate's own rejection reason — proving the allowlist can never
      widen past the hard gate (an explicit test, mirroring EXT-048's identical hard-gate-first
      proof for permission rules).
- [x] `JcodeCli._subagent_runtime(tool_allowlist)` constructs a scoped `Runtime` carrying the SAME
      `hooks_config`/`mode`/`permission_rules`/`ask_callback`/`checkpoint_ring` wiring as the CLI's
      primary `self.rt`, plus the given `tool_allowlist`; `_run_subagent` swaps `self.rt` to this
      scoped Runtime for the duration of the delegated turn only, restoring the CLI's primary
      `self.rt` in a `finally` block regardless of outcome.
- [x] An optional `model:` frontmatter value, when present, causes `_run_subagent` to construct the
      LLM client via `build_llm(model=subagent.model)` for the duration of the delegated turn,
      restoring the CLI's primary `self.llm` in a `finally` block afterward; `build_llm`'s new
      `model` parameter defaults to `None` (byte-identical to every existing caller).

### [REQ-4] `/agents` lists discovered subagents + `/help`

`JcodeCli.cmd_agents` (the existing built-in-agent-fleet listing) is EXTENDED, additively, to also
list every user-authored subagent discovered by `discover_subagents` (name + description), with an
honest message when none are found; the existing built-in-fleet line is unchanged. `/help`
documents `/subagent` and the `.jcode/agents/<name>.md` convention.

#### Acceptance Criteria
- [x] `JcodeCli.cmd_agents("")` still includes the existing built-in Python agent-fleet listing
      (unchanged) AND, additionally, lists every discovered subagent's name + description when
      `self.subagents` is non-empty.
- [x] `JcodeCli.cmd_agents("")` reports an honest "(no user-authored subagents found...)"-style
      note when `self.subagents` is empty, rather than a blank/silent gap.
- [x] `/help`'s command list documents `/subagent <name> :: <task>` and the
      `.jcode/agents/<name>.md` convention (frontmatter keys `description`/`tools`/`model`).

### [REQ-5] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=19` (Subagent authoring surface) is flipped to `"works"` ONLY
because the registry, delegation, the tool-allowlist safety invariant, and `/agents`'s subagent
listing are genuinely delivered and test-covered; its `current_state` honestly names what is
delivered and what remains deferred (narrowing the tool allowlist into `/agent`'s/`/fix`'s own
internally-constructed Runtimes; a "model-invocable when relevant" auto-suggestion beyond an
explicit `/subagent`/"delegate to X" phrasing; genuinely rewiring to a different SERVED model per
subagent, which is EXT-021's job). `docs/GAP-MAP.md` row #19 and
`tests/test_ext041_product_parity.py`'s honesty-pin are updated to match, mirroring how
EXT-042/043/044/045/046/047/048/049 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=19` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [x] `docs/GAP-MAP.md` row #19's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and the `n_works`/aggregate-
      bound assertions include row #19.
