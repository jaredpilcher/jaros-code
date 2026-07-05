---
id: EXT-046
title: Custom skills / commands (user drop-ins)
status: uncovered
priority: medium
---

# EXT-046 — Custom skills / commands (user drop-ins)

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #15 — a developer drops
a markdown file and it becomes a first-class `/command`, no code change to jaros-code required.
`.jcode/skills/<name>.md` registers `/name`; the file body is an inert plan template the existing
orchestrator/router executes — no new reasoning mechanism, no code execution from the file.

### [REQ-1] Skill registry — discover `.jcode/skills/*.md`

A deterministic registry discovers markdown skill files at the PROJECT level
(`<repo>/.jcode/skills/*.md`) and, optionally, the USER level (`~/.jcode/skills/*.md`, mirroring
the EXT-042 `JCODE.md` two-tier convention). Each `<name>.md` registers a candidate `/name`
command. A file may open with YAML-ish frontmatter (`---` delimited) carrying an optional
`description:` and `argument-hint:`; everything after the frontmatter (or the whole file, if there
is none) is the plan-template body.

#### Acceptance Criteria
- [x] `harness.skills.discover_skills(root=".")` returns a `dict[str, SkillDef]` keyed by skill
      name, scanning `<root>/.jcode/skills/*.md` (project tier) then `~/.jcode/skills/*.md` (user
      tier); a project-tier skill of the same name takes precedence over a user-tier one.
- [x] `SkillDef` carries `name`, `description` (from frontmatter, or "" when absent),
      `argument_hint` (from frontmatter, or "" when absent), `body` (the template text after
      frontmatter is stripped), and `source` (the path it was loaded from).
- [x] A file with no frontmatter is accepted — its ENTIRE content is the body, `description`/
      `argument_hint` are "".
- [x] A missing `.jcode/skills/` directory (either tier) yields an empty contribution from that
      tier — never raises, never treated as an error.
- [x] A malformed file (unreadable, bad encoding, empty body) is SKIPPED — logged/noted, not
      raised — so one bad file can never break discovery of the others.
- [x] A filename that is not a valid Python-identifier-like command name (so it could never
      cleanly become `/name`) is skipped rather than registered.

### [REQ-2] Dispatch — a skill runs as a substituted plan template through the existing router

When the CLI dispatches a `/name` that does NOT match a built-in `cmd_*` handler but DOES match a
discovered skill, it substitutes the user's typed argument text into the skill's template
(`$ARGUMENTS` for the whole argument string, `$1`/`$2`/… for individual whitespace-split tokens,
Claude-Code-style) and feeds the resulting text into the SAME plain-language routing `handle()`
already uses for a non-slash request (the deterministic multistep/fast-path/orchestrator chain) —
not a second reasoning mechanism. A built-in command of the same name ALWAYS wins; a skill can
never shadow or override one.

#### Acceptance Criteria
- [x] `harness.skills.render_template(body, arg_text)` replaces `$ARGUMENTS` with the full
      argument string and `$1`/`$2`/… with the corresponding whitespace-split token (or "" when
      that position wasn't supplied); a template with no placeholders is returned unchanged
      (aside from the substitution having nothing to do); never raises on empty/`None` input.
- [x] `JcodeCli.dispatch(line)`: when `head[1:]` matches neither an alias nor a `cmd_*` method,
      but DOES match a name in the loaded skill registry, the rendered template is routed through
      the same plain-language path `handle()` uses (not re-entered as a literal `/slash` line,
      so a template body that itself starts with `/` is never misread as a second command).
- [x] A skill file named identically to a built-in command (e.g. `status.md`) is NEVER dispatched
      — the built-in `cmd_status` always wins; the skill is simply unreachable by that name (a
      test proves this explicitly).
- [x] Skill dispatch is fully additive: a `JcodeCli` in a repo with no `.jcode/skills/` directory
      behaves byte-identically to before this spec (registry is `{}`, `dispatch()` falls through
      to "unknown command" exactly as today).

### [REQ-3] `/skills` discovery command + `/help`

`/skills` lists every discovered skill (name + description, one per line) so a user can see what
is available without reading the filesystem; an empty registry reports that honestly rather than
an empty/blank response. `/help` documents `/skills` alongside the other commands.

#### Acceptance Criteria
- [x] `JcodeCli.cmd_skills(_arg)` renders one line per discovered skill: `/<name>` plus its
      description (or a placeholder note when the description is empty), sorted by name.
- [x] An empty registry (no `.jcode/skills/` anywhere) renders an honest "(no custom skills
      found ...)" message, not a blank string or a crash.
- [x] `/help`'s command list documents `/skills` and the `.jcode/skills/<name>.md` convention.

### [REQ-4] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=15` (Custom commands / skills) is flipped to `"works"` ONLY
because the registry, dispatch, and `/skills` command are genuinely delivered and test-covered;
its `current_state` honestly names what is delivered and what remains deferred (argument-hint
validation/autocomplete, a "model-invocable when relevant" auto-suggestion beyond direct `/name`
dispatch, and any richer skill-authoring tooling). `docs/GAP-MAP.md` row #15 and
`tests/test_ext041_product_parity.py`'s honesty-pin are updated to match, mirroring how
EXT-042/EXT-043/EXT-044/EXT-045 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=15` `state` is `"works"`, with `current_state` naming
      exactly what is delivered and what remains deferred, and `next_lever` naming only the
      residual gap.
- [x] `docs/GAP-MAP.md` row #15's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and the `n_works`/aggregate-
      bound assertions include row #15.
