# EXT-046 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #15 names Claude Code's user-extensible command
surface: drop a markdown file into `.claude/skills/<name>.md` and it becomes a `/name` command,
with argument substitution and (in Claude Code) model-invocable suggestion. Today every jcode
command is a hand-authored `cmd_*` Python method in `harness/cli.py` — a user of this repo has no
way to add a repeatable workflow as a first-class command without a code change to jaros-code
itself.

The fix must not invent a second reasoning/execution mechanism: `harness/cli.py`'s `handle()`
already has ONE plain-language routing path (deterministic multistep detection → deterministic
intent fast-path → the `orchestrator_agent`) that turns free text into an action. A skill's
markdown body, once its placeholders are substituted, is just another piece of free text — it
should be handed to that SAME path, exactly like `EXT-042`'s `JCODE.md` is pure inert data loaded
by a small, never-raising module and folded into context, never a new code path of its own.

## Mechanism

```
  SKILLS DIR (user-authored data, inert -- never executed as code)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ <repo>/.jcode/skills/<name>.md      (PROJECT tier -- wins on a name collision)      │
  │ ~/.jcode/skills/<name>.md           (USER tier -- optional, mirrors EXT-042)        │
  │                                                                                       │
  │   ---                                (optional frontmatter, `---`-delimited)         │
  │   description: <one line>                                                            │
  │   argument-hint: <shown in /skills / usage strings>                                  │
  │   ---                                                                                 │
  │   <plan template body -- may contain $ARGUMENTS, $1, $2, ...>                        │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ discovered once per CLI instance (mirrors the
                                          │ EXT-042 JCODE.md / EXT-036 project_md cache pattern)
                                          ▼
  REGISTRY (harness/skills.py -- NEW module, pure deterministic file I/O, no model calls)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ @dataclass(frozen=True) SkillDef(name, description, argument_hint, body, source)    │
  │                                                                                       │
  │ _parse_skill_file(path) -> SkillDef | None      (frontmatter split + validation;      │
  │                                                   None on anything malformed)         │
  │ discover_skills(root=".") -> dict[str, SkillDef]                                      │
  │   scans <root>/.jcode/skills/*.md (project) then ~/.jcode/skills/*.md (user);         │
  │   project-tier entries OVERWRITE same-named user-tier entries (project wins);         │
  │   never raises -- a missing dir on either tier contributes {} from that tier          │
  │                                                                                       │
  │ render_template(body, arg_text) -> str                                               │
  │   "$ARGUMENTS" -> arg_text (whole string); "$1"/"$2"/... -> the Nth whitespace-split  │
  │   token of arg_text (else ""); a template with no placeholders passes through as-is   │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ registry dict, cached on JcodeCli at construction
                                          ▼
  ROUTER (harness/cli.py -- JcodeCli, EXISTING seam, additively extended)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ JcodeCli.__init__: self.skills = discover_skills(".")   (mirrors self.jcode_md /     │
  │                                                          self.project_md caching)    │
  │                                                                                       │
  │ dispatch(line):                                                                      │
  │   head, arg = split(line)                                                           │
  │   handler = getattr(self, "cmd_" + head[1:], None)                                  │
  │   if handler is not None: return handler(arg)      <- BUILT-IN ALWAYS WINS (UNCHANGED)│
  │   skill = self.skills.get(head[1:])                                                 │
  │   if skill is not None:                              <- NEW, additive fallback       │
  │       text = render_template(skill.body, arg)                                       │
  │       return self._run_skill(text)      -> routes through the SAME plain-language    │
  │                                             chain handle() uses (multistep/fast-path/ │
  │                                             orchestrator) -- not re-entered as a       │
  │                                             literal slash line                        │
  │   return "unknown command ..."                        <- UNCHANGED fallback          │
  │                                                                                       │
  │ cmd_skills(_arg): lists self.skills sorted by name (name + description)             │
  └───────────────────────────────────────────────────────────────────────────────────┘
                                          │ substituted template text, treated as ONE more
                                          │ plain-language request
                                          ▼
  ORCHESTRATOR (harness/orchestrator_agent.py + handle()'s existing routing -- UNCHANGED)
```

- **No second reasoning mechanism.** `_run_skill` does not call the model itself, add a new
  agent, or introduce a new Decision type — it re-enters the exact same deterministic
  multistep-detection → intent-fast-path → orchestrator chain `handle()` already runs for a plain
  request. The skill's contribution is entirely upstream of that: WHICH text gets routed, decided
  by a pure dictionary lookup over inert markdown data.
- **Built-ins always win.** The registry is consulted only as a fallback AFTER `getattr(self,
  "cmd_" + name, None)` comes back `None` — a same-named skill file is simply unreachable by that
  name, by construction (no explicit shadow-detection code needed; it falls out of dispatch
  order).
- **Discovery is cached once per `JcodeCli` instance**, exactly mirroring how `self.project_md`
  (EXT-036 REQ-17) and `self.jcode_md` (EXT-042 REQ-2) are loaded once at construction rather than
  re-read on every keystroke.
- **Never raises.** `discover_skills` degrades tier-by-tier (a missing/unreadable directory on
  either tier contributes nothing, not an error) and file-by-file (one malformed `.md` is skipped,
  never aborting the whole scan) — the same defensive posture as `harness/jcode_md.py`'s
  `_bounded_read`.

## Two-plane / honesty

`harness/skills.py` is pure deterministic execution-plane code (Tenet 1): file discovery,
frontmatter parsing, and string substitution — no LLM call anywhere in the module. The ROUTING
DECISION (built-in vs. skill vs. unknown) is likewise deterministic — a dictionary lookup, not a
model judgement. Only the FINAL substituted text is ever reasoned over, and it is reasoned over by
the pre-existing orchestrator exactly as any other plain request would be — this spec adds no new
model-facing surface. Per Tenet 3, `harness/product_parity.py` row #15 is flipped to `"works"`
only because the registry + dispatch + `/skills` are genuinely delivered and test-covered; the
row's `current_state` honestly names what remains deferred (argument-hint validation/
autocomplete, a "model-invocable when relevant" auto-suggestion beyond direct `/name` dispatch,
and richer skill-authoring tooling) rather than inflating the whole feature bundle.

## Backward compatibility (no regression)

- A repo with no `.jcode/skills/` directory (either tier) yields `self.skills == {}` — `dispatch`
  falls straight through to today's "unknown command" message exactly as before this spec; a
  plain invocation is otherwise byte-identical.
- A skill file sharing a name with any existing `cmd_*` built-in is simply never reachable by that
  name — there is no behavior change for any existing command.
- `JcodeCli.__init__`'s new `self.skills = discover_skills(".")` line is additive state, mirroring
  the `self.jcode_md`/`self.project_md` precedent — it does not change any existing constructor
  parameter or return shape.
- `dispatch(line)`'s signature and its BUILT-IN-command return path are entirely unchanged; the
  skill fallback is inserted strictly AFTER the existing `handler is None` check, so every
  existing dispatch branch (alias resolution, built-in lookup, unknown-command message) keeps its
  exact prior behavior when no skill happens to match.

## Out of scope (this task)

Argument-hint validation or shell-style tab-completion; a "model-invocable when relevant" mode
where the orchestrator itself decides to invoke a skill without the user typing `/name` (Claude
Code's fuzzier "skills the model reaches for automatically"); an authoring/scaffolding command
(e.g. a hypothetical `/skills new <name>`); nested/namespaced skill directories. These remain
honestly named in `docs/GAP-MAP.md` row #15's "Next lever" as the residual gap, per Tenet 3.
