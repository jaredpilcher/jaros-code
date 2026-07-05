# Implementation Tasks

### [TASK-1] Custom skill registry + dispatch, wired into the CLI

Add a new `harness/skills.py` module that discovers user-authored markdown skill files at
`.jcode/skills/<name>.md` (project) and `~/.jcode/skills/<name>.md` (user), parses optional
frontmatter + a plan-template body, and renders `$ARGUMENTS`/`$1`/`$2`… substitutions; wire it
into `harness/cli.py` (`JcodeCli.__init__`, `dispatch()`, a new `cmd_skills`, `/help`) so a
discovered skill becomes a real `/name` command that routes its substituted template through the
SAME plain-language chain `handle()` already uses — without ever shadowing a built-in command.

#### Steps
1. Create `harness/skills.py`: `@dataclass(frozen=True) SkillDef(name, description,
   argument_hint, body, source)`. A private `_parse_skill_file(path) -> SkillDef | None` that
   reads the file as UTF-8, splits an optional leading `---`-delimited frontmatter block (parsing
   only the two known keys, `description:`/`argument-hint:`, with a tolerant line-based parser —
   no YAML dependency), treats the remainder (or the whole file when there is no frontmatter) as
   the template body, and returns `None` (skip) on any read failure, empty body, or a filename
   stem that isn't a valid command-name identifier. `discover_skills(root=".") -> dict[str,
   SkillDef]`: glob `<root>/.jcode/skills/*.md` (project tier) into the result dict first, then
   glob `~/.jcode/skills/*.md` (user tier) adding only names NOT already present (project wins on
   a collision); wrap each tier's glob + `Path.home()` resolution in `try/except` so a missing
   directory, an unresolvable home, or any OS error contributes `{}` from that tier rather than
   raising. `render_template(body, arg_text) -> str`: replace `$ARGUMENTS` with `arg_text` (or ""
   when `arg_text` is falsy/`None`) and `$1`/`$2`/… with the corresponding 1-indexed
   whitespace-split token of `arg_text` (or "" past the end); never raises on `None`/empty
   `body`/`arg_text` (degrades to the empty string / an unsubstituted-but-still-returned body).
2. In `harness/cli.py`: in `JcodeCli.__init__`, add `self.skills = discover_skills(".")` wrapped
   in `try/except` so any discovery failure falls back to `{}` rather than blocking construction
   (mirrors the `self.jcode_md`/`self.project_md` caching precedent — loaded once, not
   per-keystroke). Add a private `_run_skill(self, text: str) -> str` that routes `text` through
   the SAME plain-language routing `handle()` runs for a non-slash request (the deterministic
   `_is_multistep` → `_route_intent` → orchestrator chain) by refactoring that chain out of
   `handle()`'s else-branch into a reusable private method (e.g. `_route_plain(self, line,
   *, interactive=False)`) that both `handle()` and `_run_skill` call — no duplicated logic, no
   second reasoning mechanism. In `dispatch(line)`, after the existing `handler = getattr(self,
   "cmd_" + head[1:], None)` check comes back `None`, look up `self.skills.get(head[1:])` as an
   ADDITIVE fallback: when found, render the template (`render_template(skill.body, arg)`) and
   return `self._run_skill(rendered)`; only when THAT also misses does `dispatch` fall through to
   today's "unknown command" message — the built-in lookup and its return path are otherwise
   completely unchanged. Add `cmd_skills(self, _arg: str) -> str` listing `self.skills` sorted by
   name, one line per skill (`/<name>` + its description, or a placeholder note when the
   description is empty), and an honest "(no custom skills found — drop a `.md` file into
   `.jcode/skills/` to add one)" message when the registry is empty. Update the module docstring's
   command list to document `/skills` and the `.jcode/skills/<name>.md` convention.
3. Update `harness/product_parity.py` row `id=15` (Custom commands / skills): flip `state` to
   `"works"`; `current_state` names what is genuinely delivered (the two-tier `.jcode/skills/`
   registry, dispatch through the existing plain-language router with a built-in-always-wins
   guarantee, `$ARGUMENTS`/`$1`/`$2` argument substitution, and the `/skills` discovery command)
   and what remains deferred (argument-hint validation/tab-completion, a "model-invocable when
   relevant" auto-suggestion mode beyond direct `/name` dispatch, and any skill-authoring/
   scaffolding tooling); `next_lever` names only that residual gap. Mirror the same honest update
   into `docs/GAP-MAP.md` row #15's `State`/`Current honest state`/`Next lever` columns.
4. Update `tests/test_ext041_product_parity.py`: add `15` to the `works == [...]` pin (kept
   sorted), and update `test_score_default_rows_reflects_honest_current_baseline`'s
   `n_total`/`n_works` (and the derived `n_partial + n_missing`) assertions to match the new
   works-count.
5. Write `tests/test_ext046_skills.py` (deterministic, no live gemma): using `tmp_path` as a fake
   project root and monkeypatching `Path.home()` for the user tier, cover — a dropped
   `.jcode/skills/foo.md` (with `description:`/`argument-hint:` frontmatter) is discovered and,
   through a `JcodeCli` whose orchestrator/LLM call is stubbed/monkeypatched, `/foo bar baz`
   substitutes `$ARGUMENTS`/`$1`/`$2` into the template and the SUBSTITUTED text reaches the
   mocked plain-language routing path (not the literal, unsubstituted template); a skill file
   named after a real built-in (e.g. `status.md`) is never dispatched — `/status` still returns
   the built-in's output; `/skills` lists discovered skills including frontmatter descriptions,
   and reports the honest empty message when none exist; a malformed/empty `.md` file is skipped
   without raising and without appearing in the registry; a repo with no `.jcode/skills/`
   directory at all yields `self.skills == {}` and unchanged dispatch behavior (backward-compat);
   `discover_skills`/`render_template` never raise on a missing/corrupt directory or `None` input.

#### Implements
- [REQ-1] Skill registry — discover `.jcode/skills/*.md`
- [REQ-2] Dispatch — a skill runs as a substituted plan template through the existing router
- [REQ-3] `/skills` discovery command + `/help`
- [REQ-4] Honest Product-Parity Checklist update
