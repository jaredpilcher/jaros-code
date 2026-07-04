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

## Out of scope (this task)

`@path` import expansion inside `JCODE.md` (Claude Code's `@import` syntax) is a nice-to-have
explicitly deferred — it would add parsing/cycle-detection scope not needed to close GAP-MAP row
#14's core gap (auto-load + user level + `/init`). Model-assisted (gemma) repo comprehension for a
richer `/init` starter is also deferred (see Two-plane/honesty above) — a future spec can layer an
optional gemma-authored overview section on top of this deterministic scaffold, gated by its own
eval. Migrating existing `JAROS.md` content into `JCODE.md automatically is out of scope.
