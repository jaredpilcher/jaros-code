# Implementation Tasks

### [TASK-1] Subagent registry + delegation + tool-allowlist safety invariant, wired into the CLI

Add a new `harness/subagents.py` module that discovers user-authored markdown subagent files at
`.jcode/agents/<name>.md` (project) and `~/.jcode/agents/<name>.md` (user), parses optional
frontmatter (`description`/`tools`/`model`) + a system-prompt body, and composes it with a
delegated task; add a `tool_allowlist` narrowing check to `harness.coding_loop.Runtime.apply` at
the SAME gate seam EXT-047/EXT-048 use, strictly after the hard gate; wire it all into
`harness/cli.py` so a discovered subagent becomes a real delegation target reachable via
`/subagent <name> :: <task>`, a deterministic "delegate to `<name>` subagent: `<task>`" phrasing,
and `/agents`'s listing — without ever widening past the hard gates.

#### Steps
1. Create `harness/subagents.py`: `@dataclass(frozen=True) SubagentDef(name, description,
   tools: tuple[str, ...], model: "str | None", body, source)`. A private
   `_split_frontmatter(text) -> tuple[dict, str]` (tolerant `---`-delimited line-based `key: value`
   parser, no YAML dependency, recognizing `description`/`tools`/`model`) and
   `_parse_tools_field(raw: str) -> tuple[str, ...]` (CSV split, strip, drop empties, order-
   preserving). A private `_parse_subagent_file(path) -> SubagentDef | None` that reads the file as
   UTF-8, splits frontmatter, treats the remainder (or the whole file when there is no
   frontmatter) as the body, and returns `None` (skip) on any read failure, empty body, or a
   filename stem that isn't a valid identifier. `_discover_tier(directory) -> dict[str,
   SubagentDef]` (non-recursive `*.md` glob, wrapped in `try/except` so a missing/unreadable
   directory yields `{}`). `discover_subagents(root=".") -> dict[str, SubagentDef]`: project tier
   first, then user tier adding only names not already present (project wins on a collision);
   never raises (a missing directory, an unresolvable home, or any OS error contributes `{}` from
   that tier). `render_subagent_prompt(subagent, task) -> str`: pure string composition of
   `subagent.body` + the delegated `task` text (both present -> body then a blank line then the
   task; either absent -> the other alone; both absent -> `""`); never raises on `None` input.
2. In `harness/coding_loop.py`: add a `tool_allowlist: "list[str] | None" = None` parameter to
   `Runtime.__init__`, stored as `self._tool_allowlist` (defaulting to `None`, a complete no-op for
   every existing caller). In `Runtime.apply`, immediately after the existing
   `if not gated.ok: raise RuntimeError(...)` hard-gate block (and BEFORE the EXT-048 permission-
   rules block), add: `if self._tool_allowlist is not None and decision.type not in
   self._tool_allowlist: raise RuntimeError(...)` (emitting the same `{"phase": "error", ...}`
   event shape EXT-047/048 already use) — this can only be reached for a Decision the hard gate has
   ALREADY accepted, so it narrows but never widens. Add a `model: "str | None" = None` parameter
   to `build_llm()`, passed through to `DeterministicLlamaCppClient(model=model)` (llamacpp
   backend) or `DeterministicOllamaClient(model=model or MODEL)` (legacy ollama backend); default
   `None` keeps every existing caller's exact current model selection.
3. In `harness/cli.py`: in `JcodeCli.__init__`, add `self.subagents = discover_subagents(".")`
   wrapped in `try/except` falling back to `{}` (mirrors the `self.skills`/`self.hooks_config`
   caching precedent). Add `_subagent_runtime(self, tool_allowlist)` (mirrors `_write_runtime`):
   constructs a `Runtime` with the same `hooks_config`/`mode`/`permission_rules`/`ask_callback`/
   `checkpoint_ring` wiring as `self.rt`, plus `tool_allowlist=tool_allowlist`; returns `None` on
   any construction failure. Add `_run_subagent(self, name, task) -> str`: looks up
   `self.subagents.get(name)` (honest error message naming `/agents` on a miss); composes
   `render_subagent_prompt(subagent, task)`; temporarily swaps `self.rt` to
   `self._subagent_runtime(list(subagent.tools))` (when `subagent.tools` is non-empty and
   construction succeeds) and `self.llm` to `build_llm(model=subagent.model)` (when
   `subagent.model` is set); calls `self._route_plain(augmented)` (the SAME chain
   `_run_skill`/`handle()` already use — no second reasoning mechanism); restores `self.rt`/
   `self.llm` in a `finally` block regardless of outcome; returns the routed text. Add a private
   `_match_subagent_delegation(self, line)` that regex-matches "delegate to `<name>` subagent:
   `<task>`" / "use the `<name>` subagent to `<task>`" (case-insensitive) and returns
   `(name, task)` ONLY when `name` is an actual key in `self.subagents` (else `None`, so unrelated
   prose is never misrouted). In `_route_plain`, after the existing `_is_multistep` check and
   BEFORE `_route_intent`, call `_match_subagent_delegation(line)`; when it matches, return
   `self._run_subagent(name, task)`'s output (banner-prefixed like the intent/orchestrator
   branches) with action label `f"subagent:{name}"`. Add `cmd_subagent(self, arg) -> str`: splits
   `arg` on the first `"::"` (mirroring `/fix`/`/experiment`'s convention) into `name`/`task`; a
   missing name or task returns a usage message; otherwise calls `_run_subagent(name, task)`.
   Extend `cmd_agents` (additive, existing built-in-fleet line unchanged) to append a
   "user-authored subagents" section listing `self.subagents` sorted by name (name + description,
   or a placeholder note when the description is empty), with an honest empty-registry message
   when `self.subagents` is `{}`. Update the module docstring's command list to document
   `/subagent <name> :: <task>` and the `.jcode/agents/<name>.md` convention (frontmatter keys
   `description`/`tools`/`model`).
4. Update `harness/product_parity.py` row `id=19` (Subagent authoring surface): flip `state` to
   `"works"`; `current_state` names what is genuinely delivered (the two-tier `.jcode/agents/`
   registry, delegation through the existing plain-language router via `/subagent`/a deterministic
   "delegate to X subagent" phrasing, the tool-allowlist safety invariant proven hard-gate-first,
   `/agents`'s subagent listing) and what remains deferred (narrowing the allowlist into `/agent`'s/
   `/fix`'s own internally-constructed Runtimes; a model-invocable auto-suggestion beyond an
   explicit phrasing; genuinely rewiring to a different served model per subagent, EXT-021's job);
   `next_lever` names only that residual gap. Mirror the same honest update into
   `docs/GAP-MAP.md` row #19's `State`/`Current honest state`/`Next lever` columns.
5. Update `tests/test_ext041_product_parity.py`: add `19` to the `works == [...]` pin (kept
   sorted), and update `test_score_default_rows_reflects_honest_current_baseline`'s
   `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to match the new
   works-count.
6. Write `tests/test_ext050_subagents.py` (deterministic, no live gemma, following the
   `tests/test_ext046_skills.py` fixture/stubbing pattern): `harness.subagents.discover_subagents`
   two-tier discovery (project wins on collision, missing dir is a no-op, malformed/empty file is
   skipped, never raises on an unresolvable home or a `None` root); `render_subagent_prompt`
   composition + `None`-safety; a `JcodeCli` with a dropped `.jcode/agents/<name>.md` discovers it
   in `self.subagents`; `/subagent <name> :: <task>` and the "delegate to `<name>` subagent:
   `<task>`" plain phrasing both reach a stubbed orchestrator with the SUBSTITUTED/composed prompt
   (containing the subagent's body content); an unregistered name in either path returns an honest
   error, never a crash; `/agents` lists discovered subagents with descriptions and reports the
   honest empty message when none exist, while still including the built-in agent-fleet listing;
   ★ the tool-allowlist SAFETY INVARIANT: (a) `Runtime.apply` with a `tool_allowlist` that excludes
   a Decision type refuses it even though the hard gate would otherwise accept it; (b) `Runtime.apply`
   with a `tool_allowlist` that INCLUDES `shell.exec` still refuses a denylisted/destructive command
   (e.g. matching the EXT-001/REQ-7 pattern), with the hard gate's own rejection reason — proving the
   allowlist can never escalate past the hard gates; a `model:` frontmatter override causes
   `build_llm` to be called with that model during delegation, restored to the CLI's original `llm`
   afterward, verified via a monkeypatched `harness.coding_loop.build_llm`.

#### Implements
- [REQ-1] Subagent registry — discover `.jcode/agents/*.md`
- [REQ-2] Delegation — a subagent's body frames a task through the existing router
- [REQ-3] Tool-allowlist safety invariant — narrows, never widens, past the hard gates
- [REQ-4] `/agents` lists discovered subagents + `/help`
- [REQ-5] Honest Product-Parity Checklist update
