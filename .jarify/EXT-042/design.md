# EXT-042 — Design

## Problem

Claude Code auto-loads a per-project `CLAUDE.md` (plus a user-level memory file) into every
session's context, and offers `/init` to generate one from repo comprehension. jaros-code has two
adjacent-but-separate pieces today — `.jcode/memory.md` (`harness/project_memory.py`, `/remember`,
never auto-injected into the orchestrator) and `JAROS.md` (`harness/project_md.py`, EXT-036
REQ-17, already auto-injected as a `PROJECT INSTRUCTIONS:` preamble) — but nothing named `JCODE.md`
(the convention GAP-MAP row #14 explicitly names as the next lever), no **user-level** tier, and no
`/init` generator. This spec adds exactly those three things, additively, without touching
EXT-036's `JAROS.md` wiring or EXT-009's `.jcode/memory.md` wiring.

## Mechanism

```
 discovery + load (deterministic, no model call)
 ┌─────────────────────────────────────────────────────────────┐
 │ harness/jcode_md.py                                          │
 │                                                               │
 │  load_project_jcode_md(root)  -> <root>/JCODE.md   (bounded)  │
 │  load_user_jcode_md()         -> ~/.jcode/JCODE.md (bounded)  │
 │  load_jcode_md(root)          -> combines both into ONE       │
 │                                    labeled block, or "" if    │
 │                                    neither file exists        │
 └─────────────────────────────────────────────────────────────┘
                         │  self.jcode_md cached once at
                         │  JcodeCli.__init__ (mirrors the
                         │  EXT-036 REQ-17 project_md cache)
                         ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ harness/cli.py :: _augment_with_history(..., jcode_md=...)    │
 │                                                                │
 │  "PROJECT INSTRUCTIONS (JCODE.md):\n<project text>\n\n        │
 │   USER INSTRUCTIONS (JCODE.md):\n<user text>"                 │
 │  prepended ahead of the existing JAROS.md / memory / history   │
 │  blocks -> reaches the orchestrator's decide({"request":...}) │
 │  and the NL-fix instruction text on EVERY plain-language turn │
 └─────────────────────────────────────────────────────────────┘

 /init generator (repo comprehension -> starter file, deterministic write)
 ┌─────────────────────────────────────────────────────────────┐
 │ harness/jcode_md.py :: init_jcode_md(root)                    │
 │                                                                │
 │   harness/repo_map.py :: build_repo_map(root)  (structure)     │
 │              │                                                │
 │              ▼                                                │
 │   starter Markdown (overview / structure / how-to-run)         │
 │              │                                                │
 │              ▼                                                │
 │   root-jailed write (EXT-037 _pathjail.path_jail pattern)      │
 │   -- WRITE ONLY IF <root>/JCODE.md is ABSENT (never clobbers)  │
 └─────────────────────────────────────────────────────────────┘
                         ▲
                         │ cmd_init() in harness/cli.py, dispatched
                         │ like every other cmd_* handler; listed in /help
```

- **`harness/jcode_md.py`** is the sole new module: pure deterministic file I/O (Tenet 1 — the
  *loading* is execution-plane; nothing here calls the LLM). Two discovery levels mirror Claude
  Code's project/user hierarchy: project (`<root>/JCODE.md`) and user (`~/.jcode/JCODE.md`, using
  `Path.home()`). Each is bounded to a small character budget (small-model context, mirroring
  `harness/project_md.py`'s `MAX_CHARS` precedent) and never raises — an absent or unreadable file
  degrades to `""`, exactly like `load_project_md`.
- **`load_jcode_md(root)`** combines the two into ONE string with clearly-labeled sections so the
  injected block is unambiguous about which instructions come from the project vs the user; when
  both are absent it returns `""` (byte-identical no-op downstream).
- **Injection seam**: `_augment_with_history` in `harness/cli.py` already assembles the
  orchestrator/NL-fix context from a fixed part list (JAROS.md project_md -> memory -> history ->
  request). This spec adds one more optional parameter, `jcode_md`, prepended as its own labeled
  part when non-empty. Both call sites (`handle()`'s orchestrator branch and `_nl_fix`) pass
  `self.jcode_md`, cached once at `JcodeCli.__init__` exactly like `self.project_md` (EXT-036
  precedent) — loaded once per CLI instance, not per keystroke. This is additive: when `jcode_md`
  is `""` (the default, and the case for every repo without a `JCODE.md`), the function's output is
  unchanged from today, so no existing test or behavior regresses.
- **`init_jcode_md(root)`** builds a starter `JCODE.md` from repo comprehension: it calls
  `harness/repo_map.py`'s `build_repo_map(root)` for a ranked structural overview (falling back to
  a minimal generic template if the repo map raises or returns nothing — never let comprehension
  failure block the write), and assembles a small Markdown starter (project overview placeholder,
  file/module structure, a how-to-run section derived from any detected entrypoint). It writes
  through the same root-jailed pattern `harness/system_builder.py` already uses (the `_pathjail`
  helper under `.jaros-data/tools/`), so a malicious/absolute path can never escape `root`. It is
  **write-only-if-absent**: if `<root>/JCODE.md` already exists, `init_jcode_md` is a no-op that
  returns a message saying so, never overwriting existing project instructions.
- **`/init` CLI command**: `cmd_init` on `JcodeCli`, dispatched via the existing dynamic
  `cmd_<name>` routing (no new registration table, same pattern as `/status`/`/parity`), plus one
  line added to the module docstring's command list so `/help` lists it.

## Two-plane / honesty

Everything in `harness/jcode_md.py` is deterministic execution-plane code (Tenet 1): file
discovery, bounding, string assembly, and the jailed write are pure I/O with no model call. Repo
comprehension for `/init` reuses the existing deterministic `build_repo_map` (also model-free); the
task description's "MAY use gemma for repo comprehension" nice-to-have is deliberately NOT
exercised in this implementation — the deterministic repo map already produces a useful starter,
and keeping `/init` fully deterministic means it never raises, never times out on an unreachable
Jetson, and is trivially unit-testable without a live model, which is the honest, minimal-scope
choice (Tenet 3 — no unverified LLM-authored claims about the repo baked into the starter file
without a human review pass).

## Backward compatibility (no regression)

This spec does not modify `harness/project_md.py` (`JAROS.md`, EXT-036 REQ-17) or
`harness/project_memory.py` (`.jcode/memory.md`, EXT-009 REQ-3) — both keep their existing wiring
and tests untouched. `JCODE.md` is a new, additive tier alongside them; a repo using only
`JAROS.md` today continues to work exactly as before, and a repo with neither file sees no change
in orchestrator context at all.

## REQ-5: routing `/init` + `/remember` writes through a real Jaros Decision (Tenet 1)

```
 BEFORE (half-safe): raw write, manual EXT-037 path_jail, no gate/log
 ┌───────────────────────────────────────────────────────────────┐
 │ init_jcode_md(root)              append_memory(cwd, note)      │
 │   path_jail(root, "JCODE.md")      (no jail at all)             │
 │   Path(resolved).write_text(...)   Path(mem_path).write_text(...) │
 └───────────────────────────────────────────────────────────────┘

 AFTER: an optional `runtime` threads the SAME two-plane path every other
 write Decision already uses (mirrors EXT-037 REQ-5's `_git_tool`)
 ┌───────────────────────────────────────────────────────────────┐
 │ cmd_init / cmd_remember (harness/cli.py)                        │
 │   builds a root-anchored Runtime:                               │
 │     Runtime(root=abspath("."), hooks_config=self.hooks_config,  │
 │             mode=self.mode, permission_rules=self.permission_   │
 │             rules, ask_callback=...)      <- mirrors _git_tool  │
 │                        │                                        │
 │                        ▼                                        │
 │ init_jcode_md(root, runtime=rt) / append_memory(cwd, note, rt)   │
 │   create_decision(type="code.write_file",                       │
 │                    payload={path, content, root})                │
 │   rt.apply(decision)                                             │
 │        │                                                         │
 │        ▼                                                         │
 │ Runtime.apply: validate_decision (gate) -> WriteFileTool.execute │
 │   (EXT-037 root-jail re-checked at the gate) -> hash-chain log   │
 └───────────────────────────────────────────────────────────────┘
   `runtime=None` (the default) keeps the OLD direct-write fallback --
   byte-identical for every pre-existing caller/test that never passes one.
```

- `init_jcode_md`/`append_memory` gain an optional `runtime` parameter (any `.apply(decision)`-
  shaped object). Passing one is strictly additive: the function's OWN "already exists" /
  "never overwrite" / "never raises" checks run exactly as before; only the final write step
  changes from a raw `Path.write_text` to a `code.write_file` Decision applied through `runtime`.
  `runtime=None` is a complete no-op — the pre-existing direct-write path, so no existing test of
  either function needs to change.
- `harness/cli.py`'s `cmd_init`/`cmd_remember` build a root-anchored `Runtime` per call, mirroring
  the EXT-037 REQ-5 `_git_tool` helper exactly (`root=os.path.abspath(".")`, plus this CLI
  instance's `hooks_config`/`mode`/`permission_rules`/`ask_callback`) — so a real `/init` or
  `/remember` run now gets PreToolUse/PostToolUse hooks, permission-rule enforcement, plan-mode
  propose-only behavior, and the hash-chain log, exactly like `git.*` Decisions already do.
- A gate rejection (`RuntimeError` from `Runtime.apply`) is caught at the `init_jcode_md`/
  `append_memory` call site and degraded to an honest message string — the two-plane discipline
  never turns into an uncaught crash in the REPL.
- **Acknowledged, out of scope for this requirement** (same class, larger blast radius, needs its
  own dedicated follow-up task): `harness/multi_file.py` (`/fixrepo`, `/undo`'s restore),
  `harness/refactor.py` (`/rename`, `/move`), `harness/system_builder.py` (`/buildsystem`,
  `/modifysystem` — 2000+ lines, ~15 write call sites), and `harness/spec_loop.py` (`/agent`).
  Each of these functions is shared between real HOST-project use and throwaway eval-sandbox use
  by the SAME call path, so splitting the two safely needs a dedicated task, not a forced edit
  here. `harness/repo_memory.py`'s `.jaros/memory.jsonl`, `harness/task_store.py`'s
  `.jaros/tasks.jsonl`, and `harness/experiment_store.py`'s `.jaros/experiments.jsonl` are also
  acknowledged but intentionally left alone — each is structurally an internal durable per-repo
  log/store (append-only-in-spirit, machine-authored JSONL under `.jaros/`, never hand-edited by
  the user), the same precedent as the Decision/Transition log, not rewritable user content like
  `JCODE.md`/`memory.md`.

## Out of scope (this task)

`@path` import expansion inside `JCODE.md` (Claude Code's `@import` syntax) is a nice-to-have
explicitly deferred — it would add parsing/cycle-detection scope not needed to close GAP-MAP row
#14's core gap (auto-load + user level + `/init`). Model-assisted (gemma) repo comprehension for a
richer `/init` starter is also deferred (see Two-plane/honesty above) — a future spec can layer an
optional gemma-authored overview section on top of this deterministic scaffold, gated by its own
eval. Migrating existing `JAROS.md` content into `JCODE.md automatically is out of scope.
