---
id: EXT-037
title: Host Development Toolbelt — the product DOES development on the host, safely
status: partial
priority: high
implementation:
  - .jaros-data/tools/_pathjail.py
  - .jaros-data/tools/write_file_tool.py
  - .jaros-data/tools/apply_patch_tool.py
  - .jaros-data/tools/search_replace_tool.py
  - tests/test_ext037_pathjail.py
---

**Owner directive (2026-07-03):** for Claude-Code parity the prompt→system CLI product (PRIME-001, EXT-036)
must not just EMIT code but actually DO development on the host — run commands, manage files safely, set up
environments, use git — the way Claude Code does. This spec is the **execution-plane toolbelt** that makes that
real, inside PRIME-001's two-plane discipline (model emits inert `Decision`s; every host effect is a deterministic
Jaros tool with `validate()` + `execute()`, hash-chain logged) and the Foundry **safety envelope** (read freely;
write/update confined to the project root; no external egress; no destructive ops outside root; no secrets).

Foundational primitives already exist as Jaros tools (`.jaros-data/tools/`: `fs_read`, `fs_list`, `fs_find`,
`fs_grep`, `write_file`, `apply_patch`, `search_replace`, `shell_exec`, `_codesafety.py`). The gap is (a) HARDENING
them (root-jail on writes, gates on exec) and (b) the MISSING capabilities (environments, git). This spec covers
both, decomposed below. Measured end-to-end by a held-out toolbelt eval (each op has a deterministic pass/fail).

### [REQ-1] Root-jailed filesystem writes — create/write/update confined to the project root  (PARTIAL — mechanism, gate, AND enforcement landed on the two real write paths; interactive-CLI path honestly still unwired)

Reads may range broadly, but every CREATE/WRITE/UPDATE effect (`write_file`, `apply_patch`, `search_replace`, and
any future writer) MUST be confined to the project root folder. A deterministic path-jail resolves the target to an
absolute real path and REJECTS (in `validate()`, before any effect) anything escaping root — `..` traversal,
absolute paths outside root, and symlink escape (resolve symlinks, then check containment). The owner's exact
intent: "very limited and safeguarded write and update operations such as being limited to only the folder that
it's in, the root folder of the project."

**HONEST STATUS (Tenet 3, updated by TASK-2):** the path-jail helper + the `validate()`-gate in all three writers
were BUILT and TESTED first (TASK-1), then TASK-2 threaded an actual `root` into the two real write paths so the
jail now genuinely FIRES in production:
- **The sentence→system product surface** (`harness.system_builder.build_system`/`modify_system`, EXT-036) writes
  module files DIRECTLY (bypassing the Decision/tool layer), so it got its own `path_jail`-backed
  `_jailed_write` guard at every model-controlled-name write site (plan ASSEMBLE, acceptance-repair apply/revert,
  modify assemble/regenerate/revert) — a model-authored module name that escapes the given `root` (e.g.
  `"../../evil.py"`) is refused, no file written outside root.
- **The Jaros-native Decision-dispatch choke point** (`harness.coding_loop.Runtime`) gained an opt-in `root`
  (default `None`, fully backward compatible) that stamps onto every `code.write_file`/`code.apply_patch`/
  `code.search_replace` Decision just before `validate_decision`. This is wired LIVE by the `/agent` loop's `edit`
  step (`harness.agent_loop.execute_step`, EXT-009), where `cwd` is already the loop's authoritative project root.
- **Honestly still UNWIRED:** the general interactive CLI's `Runtime` (`harness.cli.JcodeCli.rt`, backing
  `/patch`, `/fix`, etc.) does NOT get a default `root=cwd` — its existing commands legitimately target paths
  outside the process cwd today (proven by `tests/test_ext004_cli.py::test_files_and_patch_wire_those_tools`,
  which patches a `tmp_path` file via a bare `Runtime()`), so forcing cwd-as-root there would be a regression, not
  a fix. Any other `Runtime()` caller that does not pass `root` (SWE-bench/eval solve loops, `commit_replay`,
  `spec_loop`, `intent_loop`, `solve_routed`, `mutation_repair_loop`/`fix_loop`) is likewise unchanged/unjailed —
  the seam exists (`Runtime(root=...)`) for any of those to adopt when their own "project root" concept is
  established, but none has been threaded here.

#### Acceptance Criteria
- [x] A single deterministic `path_jail(root, target) -> resolved_path | reject` helper (real-path + containment),
  reused by every write/update tool
- [x] `write_file`, `apply_patch`, `search_replace` reject (validate-fail, no effect) any path outside root **when a
  `root` is supplied** — `..` escape, outside-absolute, and symlink-to-outside — proven by tests
- [x] Legitimate in-root writes still succeed unchanged (no regression to the sentence→system build/modify path)
- [x] Rejection is honest + logged (a rejected Decision is recorded, not silently dropped)
- [x] **ENFORCEMENT (TASK-2 / REQ-5): the sentence→system build/modify path and the `/agent` loop's `edit` step
  (via `Runtime(root=...)`) thread an actual root so the jail fires in production for those two paths** — the
  general interactive CLI (`JcodeCli.rt`) and the SWE-bench/eval solve loops remain honestly UNWIRED (see status
  note above); a future task may thread `root` into those once each has an unambiguous root concept to supply

### [REQ-2] Gated host CLI execution — run commands as a deterministic, safeguarded tool  (uncovered)

`shell_exec` (run a host command, capture output as an observation the model can read) hardened with deterministic
gates: a timeout with process-TREE kill (no orphans, per the SWE-bench lesson), NO external network egress by
default, NO destructive operations (rm -rf outside root, etc.), working directory confined to root by default.
Output (stdout/stderr/exit) returns as an inert observation; the model never executes directly.

#### Acceptance Criteria
- [ ] `shell_exec` enforces a timeout + process-tree kill; a hanging/slow command is killed cleanly, no orphan
- [ ] A denylist/gate blocks destructive + egress commands by default (validate-fail), with an explicit
  per-command owner-gated override path (never a default)
- [ ] cwd defaults to the project root; output captured + returned as a structured observation; exit code honest
- [ ] Proven by offline tests (fast in-root commands succeed; a blocked/hanging command is handled without harm)

### [REQ-3] Environment tools — Python + virtualenv + dependencies  (uncovered)

The product must set up a runnable, dependency-complete environment: detect/ensure Python, create + manage a
virtual environment (venv) in the project root, install + pin dependencies (pip) into that venv. Each a
deterministic gated tool; writes (the venv, a requirements file) live in root.

#### Acceptance Criteria
- [ ] Tools to: detect Python, create a project-root venv, install a dependency into it, record/pin deps
- [ ] No global-system mutation without an explicit gate; the venv + reqs are root-scoped
- [ ] Proven by an offline/gated test (create a venv in a temp root, install a trivial dep, verify)

### [REQ-4] Git tools — version the work like Claude Code  (uncovered)

Init a git repository in the project root, stage + commit, view and update commit history when needed, branch,
and read status/log/diff — as native Jaros tools. Guardrails: no force-push / history-rewrite without an explicit
gate; never stage/commit secrets (`.env`, keys) or ignored runtime/log paths (mirror jaros-code's own commit
discipline).

#### Acceptance Criteria
- [ ] Tools to: `git init`, add, commit, log/status/diff, branch, and an explicit-gated history-update path
- [ ] Secret/ignored paths are never committed (a deterministic guard); commits are scoped to the root repo
- [ ] Proven by an offline test (init a temp repo, commit a file, read the log, confirm a secret path is refused)

### [REQ-5] Toolbelt is Jaros-native + Foundry-safe end to end  (uncovered)

Every tool above lands AS Jaros (inert `Decision` → `validate()` gate → `execute()` → hash-chain log → replay),
under the Foundry safety envelope. The orchestrator wields the toolbelt to actually build + modify + set up + run
+ version a real project from a prompt (the PRIME-001 product), not just emit source.

#### Acceptance Criteria
- [ ] All toolbelt effects are deterministic Jaros tools with `validate()`/`execute()`, logged + replayable
- [ ] The safety envelope holds (read-free, write root-jailed, no egress, no destructive-outside-root, no secrets)
- [ ] An end-to-end path: prompt → build a system → set up its env → run it → git-commit it, all in-root, gated
