---
id: EXT-042
title: JCODE.md — project instruction memory hierarchy
status: partial
priority: high
implementation:
  - file: harness/jcode_md.py
    ranges:
      - - 1
        - 999
  - file: harness/cli.py
    ranges:
      - - 1
        - 999
---

# EXT-042 — JCODE.md — project instruction memory hierarchy

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #14 — the Claude Code
`CLAUDE.md`-equivalent. jaros-code has `.jcode/memory.md` + `/remember` + an episodic store, but no
auto-loaded per-repo instruction file, no user level, and no `/init` generator. This spec adds a
`JCODE.md` convention (project root + user level `~/.jcode/JCODE.md`), auto-loaded into the
orchestrator/planner context every session, plus an `/init` command that writes a starter file from
repo comprehension.

### [REQ-1] JCODE.md discovery + load (project + user levels)

Build `harness/jcode_md.py` with deterministic, never-raising loaders: `load_project_jcode_md(root)`
discovers `<root>/JCODE.md`; `load_user_jcode_md()` discovers `~/.jcode/JCODE.md` (user home
directory); both are bounded to a small character budget (small-model context) and return `""` on
any absent/unreadable file. `load_jcode_md(root)` combines both into one clearly-labeled string
(returns `""` when neither exists).

#### Acceptance Criteria
- [x] `load_project_jcode_md(root)` reads `<root>/JCODE.md` when present, returns `""` when absent, and never raises (including on an unreadable/nonexistent directory).
- [x] `load_user_jcode_md()` reads `~/.jcode/JCODE.md` (via `Path.home()`), returns `""` when absent, and never raises.
- [x] Both loaders bound their returned text to a fixed character budget, mirroring `harness/project_md.py`'s `MAX_CHARS` precedent.
- [x] `load_jcode_md(root)` returns a combined string containing both project and user content, clearly labeled per source, and returns `""` when neither file exists.

### [REQ-2] Inject JCODE.md into the orchestrator/planner context

Wire the loaded `JCODE.md` content into the context the orchestrator/planner sees every turn: cache
it once at `JcodeCli.__init__` (mirroring the existing `self.project_md` / EXT-036 REQ-17 pattern)
and prepend a clearly-labeled `"PROJECT INSTRUCTIONS (JCODE.md)"` block via
`harness/cli.py::_augment_with_history`, ahead of the existing JAROS.md/memory/history blocks. Must
be strictly additive — a repo with no `JCODE.md` produces byte-identical output to today.

#### Acceptance Criteria
- [x] `JcodeCli.__init__` loads and caches `self.jcode_md` once per CLI instance (not per keystroke/turn).
- [x] `_augment_with_history` accepts the loaded JCODE.md content and, when non-empty, prepends a block labeled `"PROJECT INSTRUCTIONS (JCODE.md)"` that precedes the existing JAROS.md/memory/history/request parts.
- [x] The orchestrator's `decide({"request": ...})` call and the NL-fix instruction text (`_nl_fix`) both receive the JCODE.md preamble on a plain-language turn.
- [x] Absent `JCODE.md` (project and user) leaves the assembled request/instruction text byte-identical to today's behavior (no `"PROJECT INSTRUCTIONS (JCODE.md)"` label present) — verified by a regression test.
- [x] This spec does not modify `harness/project_md.py` (`JAROS.md`, EXT-036 REQ-17) or `harness/project_memory.py` (`.jcode/memory.md`, EXT-009 REQ-3) — their existing wiring and tests remain untouched.

### [REQ-3] `/init` starter-file generator

Build `init_jcode_md(root)` in `harness/jcode_md.py`: generates a starter `JCODE.md` from repo
comprehension (reusing `harness/repo_map.py::build_repo_map` for structure; falling back to a
minimal generic template if the repo map is empty/unavailable), and writes it through a root-jailed
path (reusing the EXT-037 `path_jail` pattern) so a malicious/absolute target can never escape
`root`. Must never overwrite an existing `JCODE.md` — write-only-if-absent.

#### Acceptance Criteria
- [x] `init_jcode_md(root)` writes a non-empty `<root>/JCODE.md` containing a project overview section, a structure section (derived from `build_repo_map` when it returns content), and a how-to-run section.
- [x] `init_jcode_md(root)` does NOT overwrite an existing `<root>/JCODE.md` — it returns a message noting the file already exists and leaves its content untouched.
- [x] The write path is root-jailed (mirrors `harness/system_builder.py`'s `_jailed_write`/`path_jail` pattern) — it never writes outside `root`.
- [x] `init_jcode_md` never raises, including when `build_repo_map` raises or the target directory is unusual.

### [REQ-4] `/init` CLI command

Wire `/init` into `harness/cli.py` as a `cmd_init` method, dispatched via the existing dynamic
`cmd_<name>` routing (mirrors `cmd_status`/`cmd_parity`), and add a `/init` line to the module
docstring's command list so `/help` lists it.

#### Acceptance Criteria
- [x] `cmd_init` calls `harness.jcode_md.init_jcode_md(".")` and returns a human-readable result (path written, or "already exists" message).
- [x] `/init` is listed in the `harness/cli.py` module docstring's command list (so `/help` shows it).
- [x] `/init` dispatches through the existing dynamic command routing with no new registration table.
