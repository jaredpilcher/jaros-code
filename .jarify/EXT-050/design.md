# EXT-050 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #19 names Claude Code's subagent-authoring surface: a
user-defined agent (prompt + tools + model in a markdown file) that can be delegated a task with
its own narrower context. Today every jcode agent is a hand-authored Python module in
`.jaros-data/agents/` (`build(llm) -> Boundary` with a `.decide(context) -> [Decision]` method) — a
user of this repo has no way to add a scoped agent without a code change to jaros-code itself.

The fix must not invent a second reasoning/execution mechanism, and must NEVER let a subagent's
declared tool allowlist widen what the hard gates already refuse. `harness/cli.py`'s `_route_plain`
already has ONE plain-language routing path (deterministic multistep detection → deterministic
intent fast-path → the `orchestrator_agent`, all landing on Decisions applied through
`self.rt`/`harness.coding_loop.Runtime`) that turns free text into action. A subagent's markdown
body, once combined with a delegated task, is just another piece of free text fed through that SAME
path — exactly like EXT-046's skill templates. The one genuinely NEW mechanism this spec adds is a
narrowing tool-allowlist check at the `Runtime.apply` gate seam (mirroring EXT-048's permission-rule
placement STRICTLY AFTER the hard gate).

## Mechanism

```
  SUBAGENTS DIR (user-authored data, inert -- never executed as code)
  +-------------------------------------------------------------------------------------+
  | <repo>/.jcode/agents/<name>.md      (PROJECT tier -- wins on a name collision)        |
  | ~/.jcode/agents/<name>.md           (USER tier -- optional, mirrors EXT-042/046/047)  |
  |                                                                                         |
  |   ---                                (optional frontmatter, `---`-delimited)           |
  |   description: <one line>                                                              |
  |   tools: fs.read, fs.grep, shell.exec      (CSV allowlist; absent/empty = no EXTRA      |
  |                                              narrowing beyond the hard gates)           |
  |   model: <optional Jetson-fitting model label>                                         |
  |   ---                                                                                   |
  |   <system-prompt body -- folded ahead of the delegated task, never executed as code>    |
  +-----------------------------------------------------+---------------------------------+
                                                          | discovered once per CLI instance
                                                          | (mirrors EXT-042/046/047/048)
                                                          v
  REGISTRY (harness/subagents.py -- NEW module, pure deterministic file I/O, no model calls)
  +-------------------------------------------------------------------------------------+
  | @dataclass(frozen=True) SubagentDef(name, description, tools: tuple[str,...],         |
  |                                     model: str|None, body, source)                    |
  |                                                                                         |
  | _parse_subagent_file(path) -> SubagentDef | None   (frontmatter split + validation;    |
  |                                                       None on anything malformed)       |
  | discover_subagents(root=".") -> dict[str, SubagentDef]                                 |
  |   scans <root>/.jcode/agents/*.md (project) then ~/.jcode/agents/*.md (user);          |
  |   project-tier entries OVERWRITE same-named user-tier entries (project wins);          |
  |   never raises -- a missing dir on either tier contributes {} from that tier           |
  |                                                                                         |
  | render_subagent_prompt(subagent, task) -> str                                          |
  |   pure string composition: subagent.body (system-prompt prefix) + the delegated task   |
  |   -- no model call, no placeholder-substitution mechanism (unlike EXT-046 skills; a     |
  |   subagent's body is a PERSONA/scope, not a $ARGUMENTS plan template)                  |
  +-----------------------------------------------------+---------------------------------+
                                                          | registry dict, cached on JcodeCli
                                                          v
  ROUTER + DELEGATION (harness/cli.py -- JcodeCli, EXISTING seam, additively extended)
  +-------------------------------------------------------------------------------------+
  | JcodeCli.__init__: self.subagents = discover_subagents(".")  (mirrors self.skills /   |
  |                                                                self.hooks_config)     |
  |                                                                                         |
  | _route_plain(line):                                                                   |
  |   if _is_multistep(line): ... (unchanged)                                            |
  |   delegated = _match_subagent_delegation(line)   <- NEW, deterministic, no model call  |
  |     ("delegate to <name> subagent: <task>" / "use the <name> subagent to <task>",      |
  |      only fires when <name> IS a registered subagent -- ordinary prose never misroutes)|
  |   if delegated: name, task = delegated; return self._run_subagent(name, task), ...     |
  |   intent = _route_intent(line); ... (unchanged)                                       |
  |   ... orchestrator ... (unchanged)                                                     |
  |                                                                                         |
  | _run_subagent(name, task):                                                            |
  |   subagent = self.subagents.get(name)  -> honest error if unregistered                |
  |   augmented = render_subagent_prompt(subagent, task)                                  |
  |   scoped_rt = self._subagent_runtime(subagent.tools)   <- SAME hooks/mode/permission/  |
  |                                              ask_callback/checkpoint_ring wiring as    |
  |                                              self.rt, PLUS tool_allowlist=subagent.tools|
  |   self.rt <- scoped_rt (temporarily); self.llm <- build_llm(model=subagent.model) if   |
  |               a model override is given (same LOCAL Jetson endpoint, Tenet 2 --        |
  |               relabels the request only, never a different backend/provider)          |
  |   out, _ = self._route_plain(augmented)     <- the SAME chain, no second mechanism     |
  |   restore self.rt / self.llm in `finally` regardless of outcome                       |
  |   return out                                                                           |
  |                                                                                         |
  | cmd_subagent(arg): "/subagent <name> :: <task>" -- explicit slash-command delegation   |
  | cmd_agents(arg): EXTENDED (additive) -- built-in Python fleet (unchanged) PLUS a new    |
  |                  "user-authored subagents" section listing self.subagents              |
  +-----------------------------------------------------+---------------------------------+
                                                          | a normal Decision-emitting turn,
                                                          | narrowed by tool_allowlist
                                                          v
  GATE SEAM (harness/coding_loop.py::Runtime.apply -- EXISTING, additively extended)
  +-------------------------------------------------------------------------------------+
  | apply(decision):                                                                     |
  |   [root-jail stamp -- EXT-037, unchanged]                                             |
  |   [plan mode -- EXT-048, unchanged]                                                   |
  |   [PreToolUse hooks -- EXT-047, unchanged]                                            |
  |   gated = validate_decision(decision)          <- THE HARD GATE, runs UNCONDITIONALLY |
  |   if not gated.ok: raise RuntimeError(...)     <- a subagent's allowlist NEVER reaches |
  |                                                    this far if the hard gate refused   |
  |   if self._tool_allowlist is not None and decision.type not in self._tool_allowlist:  |
  |     raise RuntimeError(...)    <- NEW (EXT-050): narrows what THIS scoped Runtime may   |
  |                                    do, but ONLY consulted after the hard gate already   |
  |                                    accepted -- an allowlisted-but-hard-gate-refused     |
  |                                    Decision is STILL refused, with the gate's reason    |
  |   [permission rules -- EXT-048, unchanged]                                            |
  |   outcome = executor.apply(decision, ...)      <- unchanged                           |
  |   [PostToolUse hooks -- EXT-047, unchanged]                                            |
  +-------------------------------------------------------------------------------------+
```

- **No second reasoning mechanism.** `_run_subagent` never calls the model itself beyond what
  `_route_plain` already does — it re-enters the exact same deterministic
  multistep-detection → intent-fast-path → orchestrator chain `handle()` and EXT-046's `_run_skill`
  already use. The subagent's contribution is entirely upstream (WHICH system-prompt text frames
  the request) and at the gate seam (a narrower tool allowlist), never a new Decision type.
- **The hard gate is never bypassed — the whole point of the tool-allowlist mechanism.**
  `validate_decision()` runs BEFORE any tool-allowlist check, and the tool-allowlist check itself
  is placed strictly AFTER the existing `if not gated.ok: raise` statement in `apply()` — there is
  no code path in which the allowlist is even consulted for a Decision the hard gate refused. A
  subagent that lists a denylisted/destructive `shell.exec` command in its `tools:` is STILL
  refused, with the gate's own rejection reason (proven by an explicit test).
- **The allowlist only NARROWS.** `tool_allowlist=None` (no `tools:` frontmatter, or delegation
  without a scoped Runtime) is a complete no-op — behaves byte-identically to every pre-EXT-050
  Runtime. When set, it can only ever REJECT a Decision type absent from the list; it can never
  ADD permission for anything the hard gate (or a configured permission rule) would otherwise
  refuse.
- **Delegation swaps `self.rt`/`self.llm` for exactly one turn**, restored in a `finally` block
  regardless of success/failure — a delegated subagent turn can never leave the CLI's primary
  Runtime/LLM permanently narrowed or mis-labeled for subsequent turns.
- **`model:` is a label, not a provider swap (Tenet 2).** `build_llm(model=...)` constructs the
  SAME local `DeterministicLlamaCppClient` against the SAME Jetson endpoint, just with a different
  `model` field in the request payload — never a paid/cloud call, never a different backend.
- **Discovery is cached once per `JcodeCli` instance**, exactly mirroring `self.skills`/
  `self.hooks_config`/`self.permission_rules`.
- **Never raises.** `discover_subagents` degrades tier-by-tier and file-by-file, exactly like
  `harness/skills.py`'s `discover_skills` — a missing/unreadable directory or a malformed file
  contributes nothing rather than aborting the whole scan.

## Two-plane / honesty

`harness/subagents.py` is pure deterministic execution-plane code (Tenet 1): file discovery,
frontmatter parsing, and string composition — no LLM call anywhere in the module. The DELEGATION
decision (which subagent, if any, a plain request names) is likewise deterministic — a regex match
gated on registry membership, not a model judgement. The subagent's OWN turn is reasoned over by
the pre-existing orchestrator/plain-language chain exactly as any other request would be — this
spec adds no new model-facing surface beyond framing. Per Tenet 3, `harness/product_parity.py` row
#19 is flipped to `"works"` only because the registry, delegation, the `/subagent` command, and the
tool-allowlist safety invariant are genuinely delivered and test-covered; the row's `current_state`
honestly names what remains deferred: the deeper multi-step flows reached via `/agent`/`/fix`/
`/fixrepo` construct their OWN internal `Runtime`s (mirroring EXT-049 row #20's identical residual
for the checkpoint ring) and are not yet narrowed by a subagent's tool allowlist when delegation
happens to route into one of them; there is also no "model-invocable when relevant" auto-suggestion
beyond an explicit `/subagent`/"delegate to X" phrasing.

## Backward compatibility (no regression)

- A repo with no `.jcode/agents/` directory (either tier) yields `self.subagents == {}` —
  `_match_subagent_delegation` always returns `None` (nothing registered to match), so
  `_route_plain`'s existing behavior (multistep → intent fast-path → orchestrator) is entirely
  unchanged; a plain invocation is byte-identical to before this spec.
- `Runtime.__init__`'s new `tool_allowlist` parameter defaults to `None` — every existing call site
  (`_git_tool`, every pre-EXT-050 test, `JcodeCli.__init__`'s primary `self.rt`) that doesn't pass
  it behaves byte-identically: the new allowlist branch in `apply()` is only reachable
  `if self._tool_allowlist is not None`, never true by default.
- `build_llm`'s new `model` parameter defaults to `None` — every existing caller keeps today's
  exact model selection.
- `cmd_agents`'s existing built-in-fleet line is unchanged; the new user-subagents section is
  purely additive text appended after it.

## Out of scope (this task)

Narrowing the tool allowlist into `/agent`'s/`/fix`'s/`/fixrepo`'s own internally-constructed
Runtimes (each already root-anchors its own `Runtime()` independent of `self.rt`, mirroring
EXT-049's identical residual for its checkpoint ring); a "model-invocable when relevant"
auto-suggestion mode where the orchestrator reaches for a subagent without an explicit
`/subagent`/"delegate to X" phrasing; genuinely rewiring to a DIFFERENT served model per subagent
(that is EXT-021's multi-model-registry job — `model:` here only relabels the request to the same
local endpoint); subagent-authoring/scaffolding tooling; nested/namespaced subagent directories.
These remain honestly named in `docs/GAP-MAP.md` row #19's "Next lever" as the residual gap, per
Tenet 3.
