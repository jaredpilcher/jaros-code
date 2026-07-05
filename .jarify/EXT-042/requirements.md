---
id: EXT-042
title: JCODE.md — project instruction memory hierarchy
status: covered
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
  - file: harness/project_memory.py
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

### [REQ-5] Route `/init` and `/remember` host-project writes through a real Jaros Decision (Tenet 1)

Owner-directed 2026-07-04 Tenet-1 compliance fix: `init_jcode_md`'s `JCODE.md` write (and
`harness/project_memory.py`'s `.jcode/memory.md` write, wired from `/remember`) call raw
`Path.write_text` against the user's HOST project — a host side effect that bypasses the Jaros
two-plane path (Decision -> gate `validate_decision` -> executor -> hash-chain log). Both already
call the EXT-037 `path_jail` helper directly, so they are "half-safe" but not a Decision. Route
both through `jaros.core.create_decision(type="code.write_file", ...)` applied via a
root-anchored `harness.coding_loop.Runtime` (mirroring the EXT-037 REQ-5 `_git_tool` root-anchored-
Runtime pattern already used for `git.*` Decisions from the CLI), so the write gets the gate +
EXT-037 root-jail + hash-chain log in the ONE real Jaros-native choke point every other write
Decision passes through.

#### Acceptance Criteria
- [x] `init_jcode_md(root=".", runtime=None)` accepts an optional `runtime` (any object exposing `.apply(decision)`, e.g. a `harness.coding_loop.Runtime`); when given, the JCODE.md write is performed as a `code.write_file` Decision (`payload={"path": ..., "content": ..., "root": ...}`) applied through it, instead of a raw `Path.write_text`.
- [x] `runtime=None` (the default) preserves the EXISTING direct-write behavior byte-for-byte, so every pre-existing caller/test of `init_jcode_md` that does not pass a `runtime` is unaffected.
- [x] `harness/project_memory.py`'s `append_memory(cwd, note, runtime=None)` gets the same optional `runtime` parameter and the same Decision-routing behavior for its `.jcode/memory.md` write, with `runtime=None` preserving the existing direct-write behavior.
- [x] `harness/cli.py`'s `cmd_init` and `cmd_remember` both construct a root-anchored `Runtime` (mirroring `_git_tool`'s construction: `root=os.path.abspath(".")`, plus this CLI instance's `hooks_config`/`mode`/`permission_rules`/`ask_callback`) and pass it as `runtime=` to `init_jcode_md`/`append_memory`, so real `/init` and `/remember` usage is fully routed through the Decision -> gate -> executor -> hash-chain-log path.
- [x] A gate rejection (e.g. the EXT-037 root-jail refusing an escaping path) surfaces as an honest error string from `cmd_init`/`cmd_remember` — it is never allowed to raise/crash the REPL.
- [x] Other identified HOST-project raw writers (`harness/multi_file.py` used by `/fixrepo`/`/undo`, `harness/refactor.py` used by `/rename`/`/move`, `harness/system_builder.py` used by `/buildsystem`/`/modifysystem`, `harness/spec_loop.py` used by `/agent`) are explicitly ACKNOWLEDGED as the same class of gap but OUT OF SCOPE for this requirement — each is deeply entangled with shared eval/sandbox code paths and is large enough (system_builder.py alone is 2000+ lines with ~15 write call sites) to need its own dedicated follow-up task rather than a forced, risky retrofit here. The internal `.jaros/*.jsonl` per-repo stores (`harness/repo_memory.py`, `harness/task_store.py`, `harness/experiment_store.py`) are ALSO acknowledged but left as-is — structurally they mirror the Decision/Transition log's plain-Python precedent (internal durable machine-authored logs, not user-editable content), not a rewritable "content" write like `code.write_file`.
