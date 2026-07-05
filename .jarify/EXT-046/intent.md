# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #15 names a gap Claude Code closes but jcode does
not: **custom commands / skills**. In Claude Code, a developer drops a markdown file into
`.claude/skills/<name>.md` and it becomes a first-class `/name` command — a repeatable workflow
(a code-review checklist, a release process, a house convention) authored ONCE as data, not code.
Today every jcode command is built-in Python (`cmd_*` methods in `harness/cli.py`) — there is no
way for a user of this repo, or any repo jcode runs in, to add their OWN command without editing
the harness itself.

This spec closes that gap the same way EXT-042 (`JCODE.md`) closed the instruction-memory gap:
a small, deterministic, execution-plane module that discovers user-authored markdown files at a
conventional path (`.jcode/skills/<name>.md`) and registers each as a `/name` slash command. The
file's body is not code — it is an inert **plan template** (optionally containing `$ARGUMENTS`/
`$1`/`$2`… placeholders, mirroring Claude Code's own argument substitution) that, once the user's
arguments are substituted in, is handed to the SAME orchestrator/routing path `handle()` already
uses for any plain-language request. No new reasoning mechanism is invented, and no skill file is
ever executed as code.

This converges PRIME-001 on two tenets at once. **Tenet 1 (two-plane discipline):** the `.md` file
is pure inert data; a deterministic router (`harness/skills.py` + `JcodeCli.dispatch`) decides
whether a `/name` typed by the user resolves to a built-in command or a discovered skill — that
decision, and the argument substitution that follows it, never touches the model. Only the
resulting text is ever reasoned over, by the existing orchestrator, exactly as any other request
would be. **Tenet 5 (Claude-Code-like UX):** this is direct product-surface parity — a developer
can author a new `/command` for THIS repo without waiting on a jaros-code code change, which is
precisely what row #15 asks for. Per Tenet 3 (honesty), the Product-Parity Checklist (EXT-041) is
only flipped for row #15 once the registry, dispatch, and `/skills` discovery command are
genuinely built and test-covered — the honest residual (no autocomplete/argument-hint validation,
no "model-invocable when relevant" auto-suggestion beyond direct `/name` dispatch) is named, not
hidden.
