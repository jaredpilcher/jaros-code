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
  - .jaros-data/tools/shell_exec_tool.py
  - .jaros-data/tools/_envtools.py
  - .jaros-data/tools/python_detect_tool.py
  - .jaros-data/tools/venv_create_tool.py
  - .jaros-data/tools/venv_install_tool.py
  - .jaros-data/tools/venv_pin_tool.py
  - .jaros-data/tools/_gittools.py
  - .jaros-data/tools/_gitsecrets.py
  - .jaros-data/tools/git_init_tool.py
  - .jaros-data/tools/git_commit_tool.py
  - .jaros-data/tools/git_status_tool.py
  - .jaros-data/tools/git_log_tool.py
  - .jaros-data/tools/git_diff_tool.py
  - .jaros-data/tools/git_branch_tool.py
  - .jaros-data/tools/git_history_update_tool.py
  - harness/system_finalize.py
  - harness/research_scripts.py
  - tests/test_ext037_pathjail.py
  - tests/test_ext037_gated_exec.py
  - tests/test_ext037_env_tools.py
  - tests/test_ext037_git_tools.py
  - tests/test_ext037_finalize.py
  - tests/test_ext037_research_scripts.py
  - harness/secure_exec.py
  - tests/test_ext037_secure_exec.py
  - harness/server_oracle.py
  - harness/system_suite.py
  - tests/test_ext036_suite.py
  - tests/test_ext036_server_oracle.py
  - harness/code_quality.py
  - tests/test_ext037_code_quality.py
  - harness/refactor.py
  - harness/cli.py
  - tests/test_ext037_refactor_jaros_write.py
  - harness/multi_file.py
  - tests/test_ext037_fixrepo_jaros_write.py
  - harness/system_builder.py
  - tests/test_ext037_buildsystem_jaros_write.py
  - harness/spec_loop.py
  - tests/test_ext037_agent_plan_jaros_write.py
  - harness/intent_loop.py
  - tests/test_ext037_build_jaros_write.py
  - .jaros-data/tools/delete_file_tool.py
  - tests/test_ext037_delete_decision.py
  - harness/stdlib_safety.py
  - tests/test_ext037_stdlib_safety.py
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

### [REQ-2] Gated host CLI execution — run commands as a deterministic, safeguarded tool  (covered)

`shell_exec` (run a host command, capture output as an observation the model can read) hardened with deterministic
gates: a timeout with process-TREE kill (no orphans, per the SWE-bench lesson), NO external network egress by
default, NO destructive operations (rm -rf outside root, etc.), working directory confined to root by default.
Output (stdout/stderr/exit) returns as an inert observation; the model never executes directly.

**HONEST STATUS (Tenet 3, TASK-3):** the timeout + process-tree kill and the destructive/egress denylist gate
already existed in `.jaros-data/tools/shell_exec_tool.py` (built under EXT-001 / REQ-5 / REQ-7, before this spec).
TASK-3 added the two REQ-2-specific pieces that were genuinely missing: (a) an explicit, payload-scoped
`allow_unsafe: true` override so a caller can opt a single command past the denylist gate — never default-on,
any other value (missing/`False`/a truthy string) leaves the gate fully in effect; and (b) a `cwd` default that
anchors to a caller-supplied `root` when no explicit `cwd` is given. It also hardened `execute()` so a bad `cwd`
or unresolvable command returns a structured, honest failure observation instead of raising uncaught.
**Honest limitation:** the denylist is a deterministic regex safety NET, not a full sandbox — it catches the
common destructive/egress command shapes by pattern match; a sufficiently obfuscated command could still evade
it. This is documented in the tool's own code comments, not hidden.

#### Acceptance Criteria
- [x] `shell_exec` enforces a timeout + process-tree kill; a hanging/slow command is killed cleanly, no orphan
- [x] A denylist/gate blocks destructive + egress commands by default (validate-fail), with an explicit
  per-command owner-gated override path (never a default)
- [x] cwd defaults to the project root; output captured + returned as a structured observation; exit code honest
- [x] Proven by offline tests (fast in-root commands succeed; a blocked/hanging command is handled without harm)

### [REQ-3] Environment tools — Python + virtualenv + dependencies  (covered)

The product must set up a runnable, dependency-complete environment: detect/ensure Python, create + manage a
virtual environment (venv) in the project root, install + pin dependencies (pip) into that venv. Each a
deterministic gated tool; writes (the venv, a requirements file) live in root.

**HONEST STATUS (Tenet 3, TASK-4):** four new Jaros tools land this requirement, all sharing the existing
`path_jail`/`path_escape_reason` root-jail choke point (REQ-1) for every write: `env.python_detect` (read-only,
probes the available interpreter(s) + version), `env.venv_create` (creates a real stdlib `venv` inside a
root-jailed path, `with_pip=True` via `ensurepip` — offline, no network), `env.venv_install` (installs into the
venv's OWN python only; `validate()` refuses any global/system-scope pip flag — `--user`/`--target`/`--prefix`/
`--system`/`--global`/`--root`/`--break-system-packages` — and refuses to run at all against a not-yet-created
venv unless the caller passes `dry_run: true`), and `env.venv_pin` (writes a root-jailed requirements file, by
default from the venv's own offline `pip freeze`, or from an explicit `packages` list). A new `_envtools.py`
helper holds the shared cross-platform venv-python path lookup and the global-install-flag denylist.
**Honest limitation:** the offline test suite exercises `env.venv_install` via `dry_run: true` rather than a
real PyPI install (per the no-network test constraint) — it proves the exact venv-scoped `pip install` command
is constructed and that `validate()` blocks a global-scope flag / a missing-venv target; the real (non-dry-run)
install path is unchanged code but is not network-exercised in CI. `env.venv_pin`'s freeze mode IS exercised for
real (offline `pip freeze` against a genuinely created venv), so "record/pin deps" is proven end-to-end.

#### Acceptance Criteria
- [x] Tools to: detect Python, create a project-root venv, install a dependency into it, record/pin deps
- [x] No global-system mutation without an explicit gate; the venv + reqs are root-scoped
- [x] Proven by an offline/gated test (create a venv in a temp root, install a trivial dep, verify) — the
  install step is proven via a `dry_run` command-construction + validate()-gate test (no real PyPI network
  call in the hermetic suite, honestly noted above); venv creation and requirements pinning are proven for real

### [REQ-4] Git tools — version the work like Claude Code  (covered)

Init a git repository in the project root, stage + commit, view and update commit history when needed, branch,
and read status/log/diff — as native Jaros tools. Guardrails: no force-push / history-rewrite without an explicit
gate; never stage/commit secrets (`.env`, keys) or ignored runtime/log paths (mirror jaros-code's own commit
discipline).

**HONEST STATUS (Tenet 3, TASK-5):** seven new Jaros tools land this requirement, all sharing a new `_gittools.py`
choke point (`run_git(cwd, args, timeout_s)`, never raises — a bad `cwd`/missing binary/timeout all come back as a
structured, honest result dict) and a new `_gitsecrets.py` deterministic secret/ignored-path guard: `git.init`
(initializes a repo at `root`), `git.commit` (stages `paths` — or everything when omitted — and commits; every
explicit path is root-jailed via `_pathjail`'s existing `path_escape_reason` choke point, AND `validate()` runs a
read-only `git status --porcelain` to enumerate what would ACTUALLY be staged, whether the caller named files or
asked for "everything", and refuses the whole commit if any candidate matches the secret/ignored-path guard —
`.env`, `*.key`/`*.pem`, `id_rsa`, common credential files, `.log`, `__pycache__`, etc.), `git.status`/`git.log`/
`git.diff` (read-only observations, never jailed per the existing "reads may range broadly" rule), `git.branch`
(create/list/switch, with a name-shape sanity check), and `git.history_update` (the ONE explicitly-gated
history-mutating operation — `amend`/`reset_hard`/`force_push` — REJECTED by `validate()` unless the payload's
`allow_unsafe` key is the literal boolean `True`, mirroring REQ-2's `shell_exec` override exactly: never
default-on, any other value leaves the gate fully in effect).
**Honest limitation:** `force_push`'s gate is proven (rejected by default, and rejected even when gated without a
complete `remote`/`branch`), but no test actually exercises a real network/remote push — there is intentionally no
remote configured anywhere in this offline suite, so the real push codepath is unchanged but not
network-exercised, consistent with the repo's no-network testing constraint.

#### Acceptance Criteria
- [x] Tools to: `git init`, add, commit, log/status/diff, branch, and an explicit-gated history-update path
- [x] Secret/ignored paths are never committed (a deterministic guard); commits are scoped to the root repo
- [x] Proven by an offline test (init a temp repo, commit a file, read the log, confirm a secret path is refused)

### [REQ-5] Toolbelt is Jaros-native + Foundry-safe end to end  (covered)

Every tool above lands AS Jaros (inert `Decision` → `validate()` gate → `execute()` → hash-chain log → replay),
under the Foundry safety envelope. The orchestrator wields the toolbelt to actually build + modify + set up + run
+ version a real project from a prompt (the PRIME-001 product), not just emit source.

**HONEST STATUS (Tenet 3, TASK-6):** `harness/system_finalize.py`'s `finalize_system(root, modules, *, git=True,
venv="auto", ...)` is the FINISHER that wires the toolbelt into the live product: after a shipped `/buildsystem`
build, it git-inits + commits the shipped system (through the secret-guarded `git.init`/`git.commit` tools,
REQ-4) and, only when the system actually DECLARES a dependency (an existing `requirements.txt`, or a detected
non-stdlib top-level import across the built modules), creates a root venv and pins the detected package names
into `requirements.txt` (REQ-3) — a stdlib-only system (the common case) skips the venv entirely, no noise. Every
finalize effect is dispatched as a real `Decision` through `harness.coding_loop.Runtime(root=root)` — the SAME
gate → executor → decision-log choke point every other Runtime-mediated effect in this codebase goes through —
so finalize's effects are genuinely hash-chain logged and replayable, not called ad hoc. `harness/cli.py`'s
`cmd_buildsystem` calls `finalize_system` after every shipped build, gated by `_buildsystem_finalize_config()`
(env-var driven: `JCODE_FINALIZE_SYSTEM` disables the whole step, `JCODE_FINALIZE_GIT` disables only git,
`JCODE_FINALIZE_VENV` overrides `auto`/`always`/`off`) — defaulting to git-commit ON (the Claude-Code-like safe
default), venv `"auto"`, and auto-run unconditionally OFF (`finalize_system` never executes the built system;
that remains an explicit later opt-in). `finalize_system` NEVER raises — a rejected commit, a venv failure, a
missing git binary, or any unexpected exception is caught and reported in the returned `steps`/`note`, never
propagated, so a finalize failure can never break a successful build.
**Honest limitation:** venv-if-deps only CREATES the venv and PINS detected dependency names into
`requirements.txt` — no package is actually installed over the network by this step, consistent with the
toolbelt's own "no external network egress by default" safety envelope; installing declared dependencies for
real is a later opt-in, out of this task's scope. Auto-run of the built system (even behind the gated
`shell_exec`) is likewise explicitly deferred, per the owner's scoping of this task.

#### Acceptance Criteria
- [x] All toolbelt effects are deterministic Jaros tools with `validate()`/`execute()`, logged + replayable —
  proven for the finalize path specifically by routing every effect through `Runtime` (real gate/executor/log)
- [x] The safety envelope holds (read-free, write root-jailed, no egress, no destructive-outside-root, no
  secrets) — finalize commits are refused whenever the secret guard would refuse them (proven: a `.env` in the
  build root is never committed, even via the finalize path), and no network egress is ever attempted (venv
  creation/pin are both offline; no real dependency install runs)
- [x] An end-to-end path: prompt → build a system → set up its env (venv-if-deps) → git-commit it, all in-root,
  gated, wired live into `/buildsystem` — **honest scope note:** "run it" (auto-executing the built system) is
  explicitly NOT part of this path by design (security default); the path proven end-to-end is
  build → env-setup → version, not build → env-setup → run → version

### [REQ-6] Scratch research-script investigation plane — throwaway probes, native two-plane

PRIME-001 intent capability (e): the product must be able to INVESTIGATE, not just build — the exact
Claude-Code "write a probe, run it, read the result" loop. A deterministic execution-plane module
(`harness/research_scripts.py`, not a Jaros custom tool, since it is invoked directly by orchestration
code rather than dispatched as a Decision) writes a caller-supplied throwaway `.py` script into a SCRATCH
location that is always OUTSIDE the target repo, runs it as a gated subprocess (timeout + process-tree
kill, mirroring `shell_exec_tool.py`'s `_kill_tree` so a hanging probe never orphans), and returns its
result as a bounded, honest observation — streamed inline when small, or written to a file in scratch and
parsed in a head/tail slice when the output is too large to read inline. This tool never mutates the
target repo; the script's own effects (importing a module, timing something, hitting a localhost service
or an API) are the SCRIPT's business, not the tool's — the tool only runs it, root-jailed to scratch.

**HONEST STATUS (Tenet 3, TASK-8):** `harness/research_scripts.py` adds `run_research_script(code, *,
scratch_dir=None, timeout=30, args=None, stdout_limit=20000)` and `read_research_output(path, *,
max_bytes=20000)`. Every script file and any file the script itself writes lives only under the scratch
dir (a fresh `tempfile.mkdtemp(prefix="jcode_research_")` when `scratch_dir` is not supplied); the script
path and the `output.txt` overflow file are both resolved through the existing `_pathjail.path_jail`
choke point (REQ-1's mechanism) so nothing can be written outside scratch. The subprocess is invoked as
`[sys.executable, <script>, *args]` with `cwd=<scratch dir>`, the same timeout + tree-kill discipline as
`shell_exec_tool.py` (REQ-2) reused directly (not reimplemented) so a `while True: pass` probe is killed
cleanly with no orphan. `run_research_script` never raises: a bad `code`/`scratch_dir`, a subprocess start
failure, or any other exception comes back as a structured `{"ok": False, ...}` observation instead of
propagating.

#### Acceptance Criteria
- [x] `run_research_script` writes the throwaway script under a scratch dir strictly outside the target
  repo (a fresh `tempfile.mkdtemp` by default, or a caller-supplied `scratch_dir`), root-jailed via the
  existing `_pathjail` choke point
- [x] The script runs as a gated subprocess with a `timeout` and a process-TREE kill on expiry (no orphan
  left running), mirroring `shell_exec_tool.py::_kill_tree`
- [x] Small stdout (`<= stdout_limit`) is returned inline; stdout exceeding `stdout_limit` is written in
  full to `output.txt` in scratch and returned as `{stdout_file, stdout_head, stdout_tail, truncated:
  True, total_bytes}` so a reader can parse an oversized result in bounded chunks
- [x] `read_research_output` returns a bounded head/tail slice of a large output file for a reader agent
- [x] `run_research_script`/`read_research_output` never raise, even on garbage input, a nonexistent
  path, or a hung/crashing script — always an honest structured result
- [x] Proven by an offline test (small-result probe, oversized-output probe, non-zero-exit probe, a
  hang-with-short-timeout probe with no orphan left behind, and confirmation the target repo's working
  tree is untouched)

### [REQ-7] Secure sandboxed execution of generated code + gated egress  (partial)

**Owner-directed, highest priority (2026-07-04) — a live safety gap.** `build_system`'s acceptance step
RUNS model-generated code on the host as a plain subprocess (`python main.py`, `uvicorn main:app`) with
`cwd=<build dir>` but **no `env=` restriction** — the child inherits the FULL host environment, including
secrets (API keys, `LLAMACPP_*`, tokens), runs with full host permissions, has unrestricted network egress,
and is never statically scanned before it runs. Only the existing timeout + tree-kill and root-jailed
*writes* (REQ-1/REQ-2) cover any part of this path. Executing untrusted, model-generated code with host
trust is a Foundry safety-envelope violation; this requirement closes the FOUNDATION of that gap: a
deterministic AST scanner that classifies dangerous operations, a first-class `EgressPolicy` that GATES
(not blankets) network egress, and a scrubbed-environment/resource-capped sandboxed runner.

**OWNER CONSTRAINT — egress is GATED, not BLOCKED.** Web research and dependency installation both need
controlled network access, so the design is DEFAULT-DENY with an explicit ALLOW-LIST a caller supplies for
the hosts it actually needs (e.g. `pypi.org`, `docs.python.org`) — never a blanket network kill. A code
path that uses network APIs is refused ONLY when no `EgressPolicy` permits it; supplying an allow-list
policy that covers the used host(s) is enough to pass the static gate.

**HONEST STATUS (Tenet 3, updated by TASK-10):** TASK-9 landed the standalone `harness/secure_exec.py`
module (`EgressPolicy`, `scan_code`, `run_sandboxed`, `secure_run_generated`) and its offline test suite —
the FOUNDATION. TASK-10 then closed the live gap this requirement named: `harness/system_builder.py`'s
`build_system` now (a) runs a **SECURITY SCAN GATE** (`scan_code(built, egress_policy=EgressPolicy.DENY_ALL)`)
right after assembly and BEFORE either acceptance path (the HTTP/web-service checks or the plain checklist)
ever executes — any SUBPROCESS/SHELL, DYNAMIC-EXEC, DESTRUCTIVE/FS-OUTSIDE-ROOT, or un-permitted
NETWORK/EGRESS operation in the generated modules REFUSES the build (`shipped=True` — the files are still
assembled to disk for inspection — but `done=False`, an honest `"SECURITY: build refused — ..."` note, and
a new `security` field carrying the full `SecurityReport`); and (b) routes the acceptance-check execution
itself (`_run_check`/`_run_check_verbose`, reused by the REQ-5 repair loop and by `modify_system`) through a
new `_run_acceptance_cmd` helper that calls `harness.secure_exec.run_sandboxed` instead of the prior plain
`harness.multi_file._run` subprocess call — the check script (and anything it in turn spawns, e.g. its own
`python main.py` subprocess) now runs with a SCRUBBED environment (no ambient host secrets), POSIX resource
caps, and the same timeout + process-tree-kill discipline, egress DENY_ALL by default. `_result`'s return
dict gained the additive, backward-compatible `security` field (`None` on every non-refused path). Proven
by three new offline fake-llm tests in `tests/test_ext036_system_builder.py`: a build whose generated
module contains `os.system(...)` is refused before its acceptance checklist is ever derived/run; a normal
clean build still ships/passes exactly as before (now via the sandboxed path); and a host secret env var
set in the test process is genuinely INVISIBLE to the sandboxed acceptance subprocess (this exact check
would have FAILED before TASK-10, since the prior plain-subprocess path inherited the full host
environment). **Honest platform limitation (unchanged from TASK-9):** true runtime network blocking needs
an OS-level mechanism (a Linux network namespace or firewall rule) this module does not implement — egress
is gated at the STATIC layer only.

**HONEST SCOPE (TASK-10 wired `build_system`'s OWN acceptance path only):** `harness/server_oracle.py`
(the `uvicorn`-based HTTP acceptance path `build_system` calls when a web service is detected) and
`harness/system_suite.py`'s `_run_cli` (used by the coherence/suite tooling) also execute model-generated
code as a plain, unsandboxed subprocess today — sandboxing those is an EXPLICIT, NAMED follow-up, not
silently deferred (see the updated Acceptance Criteria below). The security SCAN GATE above does cover a
detected web service too (it runs before the HTTP-vs-checklist branch), so a dangerous web-service build is
still refused before `serve_and_check`/`uvicorn` ever starts it — only the SANDBOXING (scrubbed env/resource
caps) of `server_oracle`'s own `uvicorn` subprocess and `system_suite._run_cli` remain outstanding.

**HONEST STATUS (Tenet 3, closed by TASK-11):** both named follow-ups above are now closed.
`harness/system_suite.py`'s `_run_cli` (shared by the creation suite, `modification_suite`, and
`coherence_suite`) now runs the built CLI's entrypoint via `harness.secure_exec.run_sandboxed`
(egress `DENY_ALL`, scrubbed environment, POSIX resource caps) instead of a plain
`subprocess.Popen`, with the exact same `(ok, combined stdout+stderr)` return shape every caller
already depends on. `harness/server_oracle.py`'s `_launch` now builds its `uvicorn`/`flask`
subprocess's environment via `harness.secure_exec._scrubbed_env` (reused, not reimplemented) in
place of `dict(os.environ)`, and (POSIX only) applies the same `RLIMIT_AS`/`RLIMIT_CPU`
resource-cap `preexec_fn` `run_sandboxed` itself builds — `run_sandboxed` is NOT called directly
for the server launch, since it is a blocking helper (`communicate()`s until exit/timeout)
fundamentally incompatible with a long-running server the caller must poll/query/kill across its
own lifecycle; only its scrub/cap building blocks are reused. A module-level
`SERVER_EGRESS_POLICY = EgressPolicy.allow("127.0.0.1", "localhost")` documents that the server is
expected to need only localhost (it binds a listen socket, which is not egress, and the PARENT
oracle process — not sandboxed — makes the HTTP requests to it), consistent with the same
static-only honest limitation `run_sandboxed` already documents elsewhere — it is NOT a new
runtime enforcement mechanism. `run_sandboxed` also gained an optional `stdin: str | None`
parameter (a private `_STDIN_UNSET` sentinel distinguishes "omitted" — unchanged, byte-for-byte
backward-compatible behavior for every pre-existing caller — from an explicit `stdin=<str-or-
None>`, which pipes and feeds it), needed so `_run_cli` could keep feeding each CLI check's
`stdin` exactly as before. Proven by new offline tests: a host secret env var set in the test
process is invisible to both the built-CLI subprocess (`tests/test_ext036_suite.py`) and the real
FastAPI server subprocess (`tests/test_ext036_server_oracle.py`); a hanging built CLI is still
killed cleanly with no orphaned process; every existing `server_oracle` fixture test (real
FastAPI + Flask servers) still passes unchanged, proving the scrub doesn't break serving; and
`run_sandboxed`'s new `stdin` parameter is proven to feed data correctly while still scrubbing
the environment. **Still honestly outstanding (unchanged from TASK-9):** true RUNTIME
network-egress blocking (an OS network namespace or firewall rule) is not implemented anywhere in
this module — every egress gate in this codebase, including `SERVER_EGRESS_POLICY` above, remains
a STATIC/documentation-time gate only.

#### Acceptance Criteria
- [x] `EgressPolicy` (default-deny, `DENY_ALL`, an `allow(*hosts)` allow-list constructor, and
  `is_host_allowed(host)`) is the one mechanism that GATES egress — never a blanket network kill
- [x] `scan_code(sources)` AST-scans (never raises; unparseable code is a violation, not a crash) and
  classifies dangerous operations into NETWORK/EGRESS, SUBPROCESS/SHELL, DYNAMIC-EXEC, and
  DESTRUCTIVE/FS-OUTSIDE-ROOT, returning a structured `SecurityReport{ok, violations, egress_ops, notes}`
- [x] By default SUBPROCESS/SHELL, DYNAMIC-EXEC, and DESTRUCTIVE/FS-OUTSIDE-ROOT are always violations
  (`ok=False`); EGRESS is flagged only as a violation when NO `EgressPolicy` would permit it — an
  `allow_list` policy covering the used host(s) lets a scan with egress still report `ok=True` for that
  category (a configurable `ScanPolicy` lets a caller loosen specific categories deliberately)
- [x] `run_sandboxed(cmd, cwd=..., egress_policy=..., timeout=..., mem_mb=..., extra_env=...)` runs with a
  SCRUBBED environment (a minimal safe allow-list + `extra_env` only — no ambient secrets reach the child,
  proven by a test), `cwd` confined to the caller's build dir, POSIX resource caps
  (`RLIMIT_AS`/`RLIMIT_CPU` via `resource.setrlimit`, guarded/optional on non-POSIX), and the existing
  timeout + process-tree-kill discipline; never raises
- [x] `secure_run_generated(sources, cmd, cwd=..., egress_policy=...)` scans first and REFUSES to run
  (`{ran: False, blocked: True, report}`) on any violation, else delegates to `run_sandboxed` — the gate a
  future `build_system` acceptance call will use
- [x] Proven by an offline test suite: each violation category flagged on a crafted snippet, a clean
  script `ok=True`, the egress allow-list path proven both ways (flagged under `DENY_ALL`, permitted under
  an `allow()` policy covering the used host), the env-scrub proof (a test-set secret is invisible to the
  child, a safe var like `PATH` still present), timeout+kill with no orphan, and `secure_run_generated`
  refusing a violating snippet while running a clean one
- [x] **TASK-10:** `harness/system_builder.py`'s `build_system` runs a SECURITY SCAN GATE
  (`scan_code(built, egress_policy=EgressPolicy.DENY_ALL)`) immediately after assembly, before
  EITHER acceptance path (HTTP or plain checklist) executes anything — a violation REFUSES the
  build (`shipped=True`, `done=False`, an honest `"SECURITY: build refused — ..."` note, a
  populated `security` field), and never runs the offending code
- [x] **TASK-10:** `build_system`'s own acceptance-check execution (`_run_check`/
  `_run_check_verbose`, shared by the REQ-5 repair loop and `modify_system`) now runs through
  `harness.secure_exec.run_sandboxed` (via a new `_run_acceptance_cmd` helper) instead of a plain
  `harness.multi_file._run` subprocess call — SCRUBBED environment (no ambient host secrets),
  POSIX resource caps, DENY_ALL egress by default, same timeout + tree-kill discipline; a clean
  build still ships/passes unchanged, proven by three new offline fake-llm tests (security
  refusal, clean-build regression, and a live env-scrub proof) in
  `tests/test_ext036_system_builder.py`
- [x] **TASK-11:** `harness/server_oracle.py`'s `uvicorn`/`flask` subprocess (the HTTP
  acceptance path for a detected web service) and `harness/system_suite.py`'s `_run_cli` (shared
  by the creation suite, `modification_suite`, and `coherence_suite`) no longer run
  model-generated code as a plain, unsandboxed subprocess: `_run_cli` now runs through
  `harness.secure_exec.run_sandboxed` (scrubbed environment, POSIX resource caps, `DENY_ALL`
  egress), and `server_oracle._launch` builds its subprocess's environment/resource caps via
  `run_sandboxed`'s own internal building blocks (`_scrubbed_env`/`_make_preexec_fn`) since
  `run_sandboxed` itself is a blocking call incompatible with a long-running server process —
  proven by new offline tests including a live env-scrub check against a real FastAPI server
  subprocess and against a built CLI's subprocess, with every existing `server_oracle` fixture
  test (real FastAPI + Flask servers) still passing unchanged
- [ ] **Follow-up (not in this task's scope):** real runtime egress ENFORCEMENT (a Linux network
  namespace or firewall rule on the Jetson/Linux deployment target) — today's gate is static-only

### [REQ-8] Code-quality signal on generated systems — advisory  (covered)

**Owner's open question (2026-07-04):** "are we checking the actual code it's writing for
quality?" — before this requirement, honestly NO. REQ-7's `scan_code` gates DANGEROUS
operations (subprocess/dynamic-exec/destructive-fs/egress) and correctly refuses a build over
a real violation; it says nothing about ordinary code-QUALITY smells (bare excepts, swallowed
exceptions, mutable default args, star imports, overly-long/overly-complex/deeply-nested
functions) that are never dangerous enough to refuse a build over but are worth surfacing to a
caller/reader. This requirement adds that complementary signal as a deterministic, ADVISORY
field on `build_system`'s result — never a second gate.

**HONEST STATUS (Tenet 3, TASK-12):** a new, standalone, PURE-STDLIB (`ast`-only — no
`ruff`/`radon`/`pyflakes`; none are installed and none are added by this task) module
`harness/code_quality.py` adds `assess_quality(sources: dict[str, str]) -> QualityReport`,
deliberately mirroring `harness/secure_exec.py::scan_code`'s house pattern (never raises;
unparseable source is recorded as a note and skipped, not a crash; accepts a single code string
or a `{filename: code}` dict). It computes, per function, McCabe cyclomatic complexity
(`1 + count of If/For/AsyncFor/While/ExceptHandler/With-items/BoolOp-extra-values/IfExp/
comprehension-if/assert/match-case`, never double-counting a nested function/lambda's own
decision points into its outer function's score), line length, and max nesting depth; and
flags conservative structural smells (bare `except:`, `except Exception: pass` swallow,
a mutable list/dict/set literal default argument, a star-import, an overly-long function
(> 80 lines), a high-complexity function (CC > 15), and deep nesting (> 5 levels)) — each a
`{category, detail, lineno, file}` dict. `QualityReport.ok` is ADVISORY: `True` unless a
*critical* smell (`bare_except`/`swallowed_exception` — the two patterns that actively HIDE a
bug/error, as opposed to the merely-stylistic smells) fires; it is never consulted to change
`done` or refuse a build. Unused-import detection is deliberately OMITTED (cannot be done
reliably from a single module's own AST without false-positiving on re-exports/`getattr` use —
better to omit a detector than to false-positive).

`harness/system_builder.py::build_system` computes `quality = dataclasses.asdict(assess_quality
(built))` immediately AFTER the REQ-7 security scan gate has already passed (built modules exist
and are cleared to run), and attaches it as an ADDITIVE `quality` field (via a new `quality=None`
default kwarg on the shared `_result(...)` helper, exactly mirroring the existing `security=None`
kwarg) on every RELEVANT return path that has `built` — both the `done=True` and the `done=False`
acceptance-outcome paths (the web-service-not-HTTP-verified path, the web-service HTTP-verified
path, the no-checklist-derived path, and the final checklist/repair-loop result). **This is
advisory ONLY**: no return path's `shipped`/`done`/`unmet` computation reads or is influenced by
`quality` in any way, and every caller that ignores the field (every pre-existing test/caller)
sees a byte-compatible result dict except for the new `"quality"` key.

#### Acceptance Criteria
- [x] `harness/code_quality.py::assess_quality(sources)` is pure-stdlib (`ast` only, no
  `ruff`/`radon`/`pyflakes`), never raises, and mirrors `secure_exec.py::scan_code`'s AST-walk
  house pattern (single string or `{filename: code}` dict, unparseable source becomes a note)
- [x] Per-function McCabe cyclomatic complexity, function length (lines), and max nesting depth
  are computed correctly (proven by a hand-computed known-CC function) and aggregated into
  `max_complexity`/`worst_function` across the whole scanned system
- [x] Structural smells (bare `except:`, `except Exception: pass` swallow, mutable default arg,
  star-import, overly-long function, high-complexity function, deep nesting) each fire on a
  positive example and stay silent on clean code — conservative detectors, no false-positive
  storms (unused-import detection deliberately omitted rather than risk false positives)
- [x] `QualityReport(ok, max_complexity, worst_function, smells, per_file, notes)` — `ok` is
  ADVISORY (True unless a critical smell fires) and is NEVER used to gate a build
- [x] `build_system` attaches a populated `quality` field (via `_result`'s additive
  `quality=None` default kwarg) on every relevant done=True/done=False return path that has
  `built`, computed once, after the REQ-7 security scan gate has already passed
- [x] **PROVEN ADVISORY, NOT A GATE:** a deliberately-smelly-but-WORKING generated system
  (a bare `except:` around code that never actually raises) still returns `shipped=True`,
  `done=True`, `unmet=[]` — only `quality.ok` is False and a `bare_except` smell is recorded;
  the signal never touches `done`/`unmet`/`shipped`
- [x] Proven by an offline test suite (`tests/test_ext037_code_quality.py`): a hand-computed
  McCabe complexity value, every smell detector firing positive/staying silent on clean code,
  clean code scoring empty smells + `ok=True`, `build_system`'s result carrying a `quality`
  field, the smelly-but-working advisory-not-gating proof above, and `_result`'s omitted
  `quality` kwarg staying byte-compatible for every pre-existing caller

### [REQ-9] Deterministic refactor writes (`/rename`, `/move`) are Jaros-native (Tenet 1)

**Owner directive (2026-07-04) — Tenet-1 compliance sweep, tracker #112, refactor.py slice.**
`harness/refactor.py`'s deterministic `/rename` and `/move` commands write directly to the
user's repo via raw `Path.write_text`, with ZERO Jaros Decisions — bypassing the gate,
the REQ-1 root-jail, and the hash-chain log every other compliant host write goes through.
This requirement closes that gap for `refactor.py` specifically (the model-driven edit path
is already Jaros-native; other deterministic fast-paths — `multi_file.py`, `system_builder.py`,
`spec_loop.py` — are separate, explicitly out-of-scope follow-ups), mirroring the PROVEN idiom
already landed for EXT-042 REQ-5 (`harness/jcode_md.py::init_jcode_md` + `harness/cli.py::
_write_runtime`): an optional `runtime` parameter that, when supplied, performs the write as a
real `code.write_file` Decision applied through `Runtime.apply` (gate + REQ-1 root-jail +
hash-chain log); `runtime=None` (the default) preserves the exact prior direct-write behavior
byte-for-byte, so every existing eval/test caller against a throwaway sandbox directory is
unaffected — those callers' temp-dir paths are not under any repo root and must never be forced
through a root-jail that would reject them.

#### Acceptance Criteria
- [x] `harness/refactor.py`'s `rename_symbol` and `move_symbol` gain an optional `runtime=None`
  parameter; every file write in both functions routes through a shared helper that, when
  `runtime` is given, builds a `code.write_file` Decision (`payload={"path", "content", "root"}`)
  and applies it via `runtime.apply(...)` instead of a raw `Path.write_text`
- [x] `runtime=None` (the default) preserves the exact current raw-write behavior byte-for-byte —
  no existing eval/test caller (`harness/daily_driver.py`, `harness/refactor_eval.py`,
  `tests/test_ext003_refactor.py`, `tests/test_ext003_scoped_rename.py`) is affected
- [x] `harness/cli.py`'s `cmd_rename`/`cmd_move` (the real-host command handlers) pass
  `runtime=self._write_runtime()` — the same root-anchored `Runtime` already used by `/init`,
  `/remember`, `/rewind` — so a real `/rename`/`/move` invocation is gated, root-jailed, and
  hash-chain logged
- [x] A gate rejection (e.g. a path escaping root) degrades to an honest error string returned
  from `rename_symbol`/`move_symbol` — never an uncaught exception — and any partial rename/move
  already applied is reverted via the existing suite-green snapshot/restore mechanism
- [x] `/rename`/`/move`'s existing behavior/output and the suite-green revert-on-red-suite
  contract are unchanged for a caller that supplies a `runtime`
- [x] Proven by `tests/test_ext037_refactor_jaros_write.py`: `/rename` and `/move` route through
  a `code.write_file` Decision when a runtime is supplied (spied via a fake runtime/`DecisionLog`);
  a root-jail rejection through the Decision path is honest (no crash, no partial effect); the
  `runtime=None` raw fallback is byte-identical to the pre-existing behavior; and the full suite
  has no regression

### [REQ-10] Deterministic multi-file-fix writes (`/fixrepo`, and the SHARED `/undo` restore) are Jaros-native (Tenet 1)

**Owner directive (2026-07-04) — Tenet-1 compliance sweep, tracker #112, `multi_file.py` slice
(SLICE 2).** `harness/multi_file.py`'s `/fixrepo` command writes to the user's repo via raw
`Path.write_text` at three sites — inside the shared `_restore` helper, and inside the
delta-debugging `_minimize_edits` pass — with ZERO Jaros Decisions, bypassing the gate, the REQ-1
root-jail, and the hash-chain log every other compliant host write goes through. This requirement
closes that gap for `multi_file.py` specifically, mirroring the PROVEN REQ-9 idiom
(`harness/refactor.py`'s `_jaros_write` + `harness/cli.py`'s `_write_runtime`): an optional
`runtime` parameter that, when supplied, performs each write as a real `code.write_file` Decision
applied through `Runtime.apply` (gate + REQ-1 root-jail + hash-chain log); `runtime=None` (the
default) preserves the exact prior direct-write behavior byte-for-byte, so every existing
eval/test/sandbox caller against a throwaway temp dir is unaffected.

**`_restore` is SHARED beyond `/fixrepo`** — it is imported directly by `harness/cli.py`'s
`cmd_undo` (EXT-009 `/undo`) and by `harness/refactor.py`'s rename/move revert paths (REQ-9,
unchanged by this task, since it never passes `runtime` and stays on the byte-identical
fallback). Threading `runtime`/`root` through `_restore`'s signature therefore closes the gap for
BOTH `/fixrepo`'s internal revert-on-no-progress path and `/undo`'s whole-run restore in one move
— `harness/cli.py`'s `cmd_undo` now also passes `runtime=self._write_runtime()` and a
`root=os.path.abspath(".")`, so a real `/undo` invocation is gated, root-jailed, and hash-chain
logged, exactly like `/fixrepo`.

**Caller audit (host → runtime, sandbox → raw):** `harness/cli.py`'s `cmd_fixrepo` and `cmd_undo`
(both real-host, `cwd`/root is `os.path.abspath(".")`) now pass a root-anchored `runtime`.
Every other caller of `multi_file_fix`/`_restore`/`_minimize_edits` is an eval/sandbox/test
caller against a throwaway temp directory with no meaningful "project root" — `runtime` is
omitted, so they stay on the byte-identical raw-write fallback:
`harness/daily_driver.py`, `harness/multifile_eval.py`, `tests/test_ext003_multifile.py`,
`tests/test_ext010_minimal_diff.py`, `.jaros-data/mf_probe*.py` (scratch probes), and
`harness/agent_loop.py`'s `execute_step` "fix" action (used only by `tests/test_agent_loop.py`
and the `agentic_eval.py` eval harness — never wired into any live CLI command today, unlike its
sibling "edit" action which already routes through `Runtime(root=cwd)` per REQ-1 TASK-2).
**Flagged, explicitly out of this task's scope (not silently deferred):** `harness/cli.py`'s
`cmd_plan` (`/plan`) and `_nl_fix` (the natural-language-routing fallback when no file is named
in a plain request) ALSO call `multi_file_fix(".", ...)` as real-host operations without a
`runtime` today — the same production gap this requirement closes for `/fixrepo`/`/undo`. They
are left unwired here since the task named only `cmd_fixrepo`/`cmd_undo` explicitly; wiring them
is a natural, low-risk follow-up (the exact same `runtime=self._write_runtime()` one-line
addition) for a future slice. `harness/system_builder.py` (`/buildsystem`) and
`harness/spec_loop.py` (`/agent`'s structured flow, which also calls `multi_file_fix`) remain
explicitly out of scope, per the owner's slice boundaries — separate follow-up slices.

#### Acceptance Criteria
- [x] `harness/multi_file.py` gains a private `_jaros_write(path, content, root, runtime=None)`
  helper (mirroring `harness/refactor.py`'s REQ-9 helper): `runtime=None` performs the existing
  raw `Path.write_text(..., encoding="utf-8", newline="\n")`; a supplied `runtime` builds a
  `jaros.core.create_decision(type="code.write_file", payload={"path", "content", "root"})` and
  applies it via `runtime.apply(...)` inside a `try`/`except`, returning `None` on success or an
  honest `f"failed to write {path}: {exc}"` string on any gate rejection/executor failure — never
  raises
- [x] `_restore(snap, *, runtime=None, root=None)` gains the optional keyword-only parameters;
  every file write in its loop routes through `_jaros_write`; returns `None` on full success or
  the first honest error string encountered (never crashes, never stops attempting the remaining
  files)
- [x] `_minimize_edits(cwd, test_cmd, orig, kept_paths, *, runtime=None)` gains the optional
  keyword-only parameter; both probe writes (the temporary revert-to-original, and the
  restore-of-the-necessary-fix) route through `_jaros_write`; a probe write that is refused by the
  gate conservatively leaves that edit KEPT/untouched rather than risk a half-reverted file
- [x] `multi_file_fix(..., *, runtime=None)` gains the optional keyword-only parameter and threads
  it to its own internal `_restore(snap, runtime=runtime, root=cwd)` call (the no-progress revert)
  and to `_minimize_edits(..., runtime=runtime)`
- [x] `harness/cli.py`'s `cmd_fixrepo` passes `runtime=self._write_runtime()` to `multi_file_fix`,
  and `cmd_undo` passes `runtime=self._write_runtime()` plus `root=os.path.abspath(".")` to
  `_restore` — the same root-anchored `Runtime` `/init`/`/rename`/`/move` already use — so both a
  real `/fixrepo` and a real `/undo` invocation are gated, root-jailed, and hash-chain logged
- [x] `runtime=None` (the default) preserves the exact current raw-write behavior byte-for-byte —
  no existing eval/test/sandbox caller (`harness/daily_driver.py`, `harness/multifile_eval.py`,
  `harness/agent_loop.py`, `tests/test_ext003_multifile.py`, `tests/test_ext010_minimal_diff.py`)
  is affected, and `harness/refactor.py`'s own `_restore` calls (REQ-9) are unaffected since they
  never pass `runtime`
- [x] A gate rejection (e.g. a path escaping root) degrades to an honest error string — never an
  uncaught exception — from `_restore`/`cmd_undo`, and never crashes `_minimize_edits`
- [x] Proven by `tests/test_ext037_fixrepo_jaros_write.py`: `_restore` and `_minimize_edits` route
  writes through a `code.write_file` Decision when a runtime is supplied (a fake recording
  runtime, and a real `harness.coding_loop.Runtime` proving the gate + REQ-1 root-jail actually
  fire); a root-jail rejection through the Decision path is honest (no crash, no partial effect,
  the escaping path is never created); the `runtime=None` raw fallback is byte-identical to the
  pre-existing behavior for `_restore`/`_minimize_edits`/`multi_file_fix`; `multi_file_fix`'s own
  internal revert lands through a REAL Decision end to end (spied via `DecisionLog`); `/fixrepo`
  and `/undo` (via `JcodeCli.dispatch`) each genuinely record a `code.write_file` Decision on the
  hash-chain `DecisionLog` for a real host-rooted temp repo, and `/undo`'s escaping-snapshot gate
  rejection is honest and non-destructive (the snapshot is preserved so `/undo` can be retried);
  and the full suite has no regression

### [REQ-11] `system_builder.py`'s `/buildsystem`/`/modifysystem` writes are Jaros-native (Tenet 1)  (covered)

**Owner directive (2026-07-04) — Tenet-1 compliance sweep, tracker #112, `system_builder.py` slice
(SLICE 3).** `harness/system_builder.py`'s `/buildsystem` and `/modifysystem` commands write
model-generated module files to the user's target directory through a SINGLE choke point —
`_jailed_write(root, name, content)` (already applies the REQ-1 `path_jail` root-jail) — but that
helper performs the actual write via raw `Path.write_text`, bypassing the gate and the hash-chain
log every other compliant host write goes through. This requirement closes that gap for
`system_builder.py` specifically, mirroring the PROVEN REQ-9/REQ-10 idiom (`harness/refactor.py`'s
`_jaros_write`, `harness/multi_file.py`'s `_jaros_write`): an optional `runtime` parameter that,
when supplied, performs the write as a real `code.write_file` Decision applied through
`Runtime.apply` (gate + hash-chain log — the local `path_jail` pre-check is KEPT regardless,
preserving the exact current rejection messages/behavior); `runtime=None` (the default) preserves
the exact prior direct-write behavior byte-for-byte, so every existing eval/test/suite caller
against a throwaway sandbox directory is unaffected.

**Single chokepoint, five public entry points.** Every model-controlled-name write in this module
(the plan-derived ASSEMBLE step, the REQ-5 acceptance-repair apply/revert, `modify_system`'s
assemble/regenerate/revert, `build_system_governed`'s RE-GROUND repair writes, and
`build_system_best_of_k`'s final winner assembly) already funnels through `_jailed_write` —
threading the optional `runtime` through that one helper, plus the module-level `_repair_system`
helper it calls from within `build_system`, closes the gap for every public entry point
(`build_system`, `modify_system`, `build_system_escalating`, `build_system_governed`,
`build_system_best_of_k`) in one move.

**Caller audit (host → runtime, eval/suite → raw):** `harness/cli.py`'s `cmd_buildsystem` (which
calls `build_system`/`build_system_escalating` against a real subdirectory of the current working
directory) and `cmd_modifysystem` (which calls `modify_system` against a real, caller-named target
directory) are the only REAL-HOST callers found by an exhaustive grep of every
`build_system`/`modify_system`/`build_system_escalating`/`build_system_governed`/
`build_system_best_of_k` call site in the repo — both now pass `runtime=self._write_runtime()`.
Every other caller targets a throwaway temp directory with no meaningful "project root" and stays
on the byte-identical raw-write fallback: `tests/test_ext036_system_builder.py`,
`tests/test_ext036_acceptance.py`, `tests/test_ext036_modify.py`, `tests/test_ext036_escalate.py`,
`tests/test_ext036_buildsystem_escalate.py`, `tests/test_ext036_system_repair.py`,
`tests/test_ext036_planrepair.py`, `tests/test_ext037_root_enforcement.py`,
`tests/test_ext037_code_quality.py`, `tests/test_ext040_heartbeat.py`, and every creation/
modification-suite and Foundry probe script under `.jaros-data/` (e.g. `run_creation_suite_*.py`,
`run_modification_suite_*.py`, `coherence_*_measure.py`, `bestofk_verify.py`) — all build into
temp/throwaway roots, never a real project directory. `build_system_governed` and
`build_system_best_of_k` are not yet wired into any CLI command at all (an explicit, separate
follow-up per their own TASK-27/TASK-33 scope notes) — this requirement still threads `runtime`
through both so the seam exists the moment either is wired live, with no further code change
needed at that point.

**The two `chk_path.write_text` sites (`_run_check`/`_run_check_verbose`, ~lines 822/862) are
INTERNAL BUILD-SCRATCH state, not product output** — each writes a temporary acceptance-check
script (`_s2s_acceptance_check.py`) immediately before running it and unconditionally `unlink()`s
it in a `finally` block a few lines later; it is never part of the shipped system, never seen by
the user, and never reaches `root` as a delivered module. Left raw, same as `.jaros-data/` runtime
state — routing it through a Decision would log-and-gate a file that exists for microseconds and
is deleted before the caller ever returns.

#### Acceptance Criteria
- [x] `harness/system_builder.py`'s `_jailed_write(root, name, content, runtime=None)` gains the
  optional `runtime` parameter: the existing local `path_jail` pre-check runs unconditionally
  first (unchanged rejection messages/behavior); on success, `runtime=None` performs the existing
  raw `Path.write_text(..., encoding="utf-8", newline="\n")`, while a supplied `runtime` builds a
  `jaros.core.create_decision(type="code.write_file", payload={"path", "content", "root"})` and
  applies it via `runtime.apply(...)` inside a `try`/`except Exception`, returning `None` on
  success or an honest `f"failed to write {name}: {exc}"` string on any gate rejection/executor
  failure — never raises
- [x] `build_system`, `modify_system`, `build_system_escalating`, `build_system_governed`, and
  `build_system_best_of_k` each gain an optional keyword-only `runtime: object | None = None`
  parameter and thread it to every `_jailed_write` call they (or, for `build_system`, the
  `_repair_system` helper it calls) perform; `build_system_escalating`/`build_system_governed`
  thread their own `runtime` straight through to their internal `build_system(..., runtime=runtime)`
  calls (same target `root`); `build_system_best_of_k` threads `runtime` only to its FINAL
  winner-assembly write onto the caller's real `root` — its own per-attempt `build_system(...)`
  calls into isolated, throwaway `tempfile.mkdtemp()` subdirectories stay on `runtime=None`
  (there is no meaningful project root to gate for a directory that is `shutil.rmtree`'d before
  the function returns)
- [x] `runtime=None` (the default) preserves the exact current raw-write behavior byte-for-byte —
  no existing eval/test/suite caller (`tests/test_ext036_system_builder.py`,
  `tests/test_ext036_acceptance.py`, `tests/test_ext036_modify.py`, `tests/test_ext036_escalate.py`,
  `tests/test_ext036_buildsystem_escalate.py`, `tests/test_ext036_system_repair.py`,
  `tests/test_ext036_planrepair.py`, `tests/test_ext037_root_enforcement.py`,
  `tests/test_ext037_code_quality.py`, `tests/test_ext040_heartbeat.py`, any creation/modification-
  suite or Foundry probe script) is affected
- [x] `harness/cli.py`'s `cmd_buildsystem` passes `runtime=self._write_runtime()` to
  `build_system`/`build_system_escalating`, and `cmd_modifysystem` passes
  `runtime=self._write_runtime()` to `modify_system` — the same root-anchored `Runtime`
  `/init`/`/rename`/`/move`/`/fixrepo`/`/undo` already use — so a real `/buildsystem` and
  `/modifysystem` invocation is gated and hash-chain logged. No other CLI change.
- [x] The two `chk_path.write_text` sites in `_run_check`/`_run_check_verbose` are left unrouted
  (internal build-scratch state — a transient acceptance-check script written and unlinked within
  the same call, never shipped) — documented here, not silently skipped
- [x] A gate rejection (e.g. a path escaping root through the Decision path) degrades to an honest
  error string surfaced in the existing `note`/`assembly failed`/`could not assemble` messages —
  never an uncaught exception — and never ships a partially-written module outside the intended
  behavior of the existing `_jailed_write` contract
- [x] Proven by `tests/test_ext037_buildsystem_jaros_write.py`: `_jailed_write` routes through a
  `code.write_file` Decision when a runtime is supplied (spied via a fake runtime/`DecisionLog`);
  a root-jail rejection through the local `path_jail` pre-check is unchanged/honest regardless of
  `runtime`; the `runtime=None` raw fallback is byte-identical to the pre-existing behavior for a
  full `build_system` run (fake-llm, offline); `build_system`/`modify_system` genuinely record a
  `code.write_file` Decision on the hash-chain `DecisionLog` for a real host-rooted temp directory
  when a real `harness.coding_loop.Runtime` is supplied; `build_system_best_of_k`'s per-attempt
  temp-dir builds stay raw while its final winner-assembly write is routed through a supplied
  runtime; and the full suite has no regression

### [REQ-12] `spec_loop.py`'s `/agent`/`/plan`/`_nl_fix` writes are Jaros-native (Tenet 1)  (covered)

**Owner directive (2026-07-04) — Tenet-1 compliance sweep, tracker #112, FINAL SLICE (4).**
`harness/multi_file.py`'s `multi_file_fix` is already runtime-capable (REQ-10) — it just needs a
`runtime` PASSED at the remaining REAL-HOST call sites REQ-10 explicitly flagged and left out of
scope: `harness/cli.py`'s `cmd_plan` (`/plan`'s `fix` step) and `_nl_fix` (the natural-language
no-file-named fallback) both call `multi_file_fix(".", ...)` against the real host `cwd` without a
`runtime`; and `harness/spec_loop.py`'s `spec_driven_loop` (reached by `cmd_agent`/`/agent`) calls
`multi_file_fix(cwd, ...)` the same way. This requirement closes the gap at all three, mirroring
the PROVEN REQ-9/REQ-10/REQ-11 idiom exactly: an optional `runtime` parameter that, when supplied,
performs the write as a `code.write_file` Decision through `Runtime.apply`; `runtime=None` (the
default) preserves every existing eval/test/suite caller's raw-write behavior byte-for-byte.

**`spec_loop.py`'s BUILD flow is ALSO a real-host write path, not eval scaffolding — checked, not
assumed.** `cmd_agent` calls `spec_driven_loop(arg, ".")` against the real host working directory.
When no failing test exists there, `spec_driven_loop` falls through to the BUILD flow
(`_decompose_build` → `_build_class` / `_build_per_function` / `_build_whole_file`), which writes
`solution.py`/per-function modules/the sanitized final module directly onto that same real `cwd`
via raw `Path.write_text` (the `~lines 142, 152, 189, 201, 254, 285, 301, 305` sites). Every other
caller of `spec_driven_loop`/`_decompose_build` (`harness/build_eval.py`, `harness/agentic_eval.py`,
`tests/test_spec_loop.py`) passes a `tempfile.TemporaryDirectory()`/`tmp_path` — a throwaway
benchmark workdir with no meaningful project root. So the VERDICT, checked per site rather than
assumed: these are (b) real-host product writes reachable via `/agent`, not (a) eval/benchmark
scaffolding — they get the same treatment as the FIX flow, routed through `harness/multi_file.py`'s
existing `_jaros_write(path, content, root, runtime)` helper (reused, not duplicated) when a
`runtime` is supplied. The ONE exception: `_build_per_function`'s hybrid-probe call
`_build_whole_file(intent, alt, ...)` builds into an isolated `tempfile.mkdtemp()` subdirectory
(`alt`) that is discarded before the function returns — not the caller's real root — so that
specific internal call stays on `runtime=None`, mirroring `system_builder.py`'s REQ-11
`build_system_best_of_k` per-attempt-tempdir precedent exactly.

**Flagged, explicitly out of this requirement's scope (not silently deferred):**
`_decompose_build`'s single-function fallback (`len(reqs) <= 1`) calls `harness/intent_loop.py`'s
`build_in_dir`, a DIFFERENT module with its own write path, not one of `spec_loop.py`'s raw
`Path.write_text` sites this requirement routes. `build_in_dir` is reached by `/agent` the same
way (a plain single-function request with no existing test file), so it is a real-host write path
too — a natural, low-risk follow-up (the same `runtime`-threading idiom) for a future slice, left
unwired here since this requirement's scope is `spec_loop.py` itself.

#### Acceptance Criteria
- [x] `harness/cli.py`'s `cmd_plan` passes `runtime=self._write_runtime()` to its `fix`-step
  `multi_file_fix` call, and `_nl_fix` passes `runtime=self._write_runtime()` to its no-file-named
  fallback `multi_file_fix` call — the same root-anchored `Runtime` `/fixrepo`/`/undo` already use
- [x] `harness/cli.py`'s `cmd_agent` passes `runtime=self._write_runtime()` to
  `spec_driven_loop(arg, ".")`
- [x] `harness/spec_loop.py`'s `spec_driven_loop(intent, cwd, *, ..., runtime=None)` gains the
  optional keyword-only parameter and threads it to its FIX-flow `multi_file_fix(...,
  runtime=runtime)` call and to its BUILD-flow `_decompose_build(..., runtime=runtime)` call
- [x] `_decompose_build`, `_build_class`, `_build_whole_file`, and `_build_per_function` each gain
  an optional keyword-only `runtime: object | None = None` parameter; every raw `Path.write_text`
  call in each that targets the caller's real `cwd` (the stub write, the final
  `_sanitize_source` write, the per-function stub write, the combined `solution.py` assembly
  write, and the hybrid winner swap-in write) is routed through `harness/multi_file.py`'s
  `_jaros_write(path, content, root=cwd, runtime)` instead of a raw `Path.write_text`
- [x] `_build_per_function`'s internal hybrid-probe `_build_whole_file(intent, alt, ...)` call
  (building into a throwaway `tempfile.mkdtemp()` subdirectory `alt`, discarded before return)
  stays on `runtime=None` — there is no meaningful project root to gate for a directory that is
  never the caller's real `cwd`
- [x] `runtime=None` (the default) preserves the exact current raw-write behavior byte-for-byte —
  no existing eval/test/suite caller (`harness/build_eval.py`, `harness/agentic_eval.py`,
  `tests/test_spec_loop.py`, `tests/test_ext004_planner.py`) is affected
- [x] A gate rejection (e.g. a path escaping root through the Decision path) degrades to an honest
  error string surfaced in the existing `note`/`solved` result — never an uncaught exception
- [x] Proven by `tests/test_ext037_agent_plan_jaros_write.py`: `/plan`'s `fix` step, `/agent`'s FIX
  and BUILD flows, and `_nl_fix`'s no-file-named fallback each route their host writes through a
  `code.write_file` Decision when a runtime is supplied (spied via a fake runtime/`DecisionLog`,
  and a real `harness.coding_loop.Runtime` proving the gate + REQ-1 root-jail actually fire); the
  `runtime=None` raw fallback is byte-identical to the pre-existing behavior for `spec_driven_loop`
  (FIX and BUILD flows) and `_decompose_build`'s three build strategies; the hybrid-probe temp-dir
  build in `_build_per_function` stays raw (no Decision recorded for `alt`-root writes); and the
  full suite has no regression

### [REQ-13] `intent_loop.py`'s `/build` writes are Jaros-native (Tenet 1)  (covered)

**Owner directive (2026-07-04) — Tenet-1 compliance sweep, tracker #112, TRUE FINAL SLICE (5).**
`harness/intent_loop.py`'s `build_in_dir` — the last real-host write path in this sweep — writes
the model-generated code + its self-written tests directly onto the caller's real `cwd` via raw
`Path.write_text` (inside the `run_tests` probe closure, and in the two final writes after
`behavioral_solve` returns), bypassing the gate, the REQ-1 root-jail, and the hash-chain log every
other compliant host write goes through. The real-host caller is `harness/cli.py`'s `cmd_build`
(`/build <func> <intent>`, turning an intent into a working function in the CURRENT directory) —
the one product command still writing raw before this requirement. This closes that gap, mirroring
the PROVEN REQ-9/REQ-10/REQ-11/REQ-12 idiom exactly: an optional `runtime` parameter that, when
supplied, performs each write as a real `code.write_file` Decision applied through `Runtime.apply`
(gate + REQ-1 root-jail + hash-chain log); `runtime=None` (the default) preserves the exact prior
direct-write behavior byte-for-byte, so every existing eval/test/sandbox caller against a
throwaway temp dir is unaffected.

**Reused, not duplicated:** `build_in_dir` imports `harness/multi_file.py`'s existing
`_jaros_write(path, content, root, runtime)` helper (REQ-10) rather than writing a fourth copy of
the same idiom.

**Caller audit (host → runtime, eval/oracle → raw), checked per site, not assumed:**
- `harness/cli.py`'s `cmd_build` (real-host, `cwd="."`) now passes `runtime=self._write_runtime()`
  — the same root-anchored `Runtime` `/rename`/`/move`/`/fixrepo`/`/undo`/`/buildsystem`/`/agent`
  already use.
- `harness/spec_loop.py`'s `_decompose_build` single-function fallback (line ~201) — flagged as an
  explicit, real-host follow-up by REQ-12 rather than silently deferred — now threads its own
  already-existing `runtime` parameter straight through to `build_in_dir(..., runtime=runtime)`,
  closing that named gap in the same move (no new parameter needed there; REQ-12 already added
  it).
- `harness/agent_loop.py`'s `execute_step` `"build"` action (line ~112) also calls `build_in_dir`
  without a `runtime` — RE-CONFIRMED (not assumed) eval-only, exactly as REQ-10 found for the
  sibling `"fix"` action: an exhaustive grep shows `harness.agent_loop.agent_loop`/`execute_step`
  is reached only by `harness/agentic_eval.py` and `tests/test_agent_loop.py`/
  `tests/test_ext037_root_enforcement.py` — never by any live CLI command. `harness/cli.py`'s
  `cmd_agent` (`/agent`) calls `harness.spec_loop.spec_driven_loop` instead, a completely different
  function. Left unwired here, honestly, not silently — no host-write gap exists at this site.
- `harness/intent_loop.py`'s own `build_from_intent` (the daily-driver/Foundry oracle-scoring
  spine, EXT-008) and the `_run_oracle` helper it calls are OUT OF SCOPE by design: both always
  build into a `tempfile.TemporaryDirectory()` they create themselves — never a caller-supplied
  project root — so they are internal scratch/eval concerns (like `system_builder.py`'s
  acceptance-check scratch and `spec_loop.py`'s hybrid-probe temp dir), not real-host writes.
  Neither function gained a `runtime` parameter; confirmed by their unchanged signatures.
  `harness/daily_driver.py`, `harness/foundry.py`, `scripts/probe_intent.py`,
  `tests/test_ext005_daily_driver.py`, `tests/test_ext008_intent.py`, and every other
  `build_from_intent`/`_run_oracle` caller is an eval/exploration script, never a live CLI command
  — confirmed by grep, none of them are reached from `harness/cli.py`.

**This COMPLETES the Tenet-1 host-write sweep (tracker #112):** every product command that
performs a real-host write — `/rename`/`/move` (REQ-9), `/fixrepo`/`/undo` (REQ-10),
`/buildsystem`/`/modifysystem` (REQ-11), `/agent`/`/plan`/`_nl_fix` (REQ-12), and now `/build`
(REQ-13) — is Jaros-native: gated, EXT-037 root-jailed, and hash-chain logged.

#### Acceptance Criteria
- [x] `harness/intent_loop.py`'s `build_in_dir(cwd, intent, target, func=None, signature=None, *,
  max_iters=3, verbose=False, runtime=None)` gains the optional keyword-only `runtime` parameter;
  every write it performs onto `cwd` (the `run_tests` probe's code + test writes, and the two
  final writes after `behavioral_solve` returns) is routed through `harness/multi_file.py`'s
  existing `_jaros_write(path, content, root=cwd, runtime)` helper instead of a raw
  `Path.write_text`
- [x] `runtime=None` (the default) preserves the exact current raw-write behavior byte-for-byte —
  no existing eval/test/sandbox caller (`harness/build_eval.py`, `harness/agentic_eval.py`,
  `harness/daily_driver.py`, `harness/foundry.py`, `tests/test_ext008_intent.py`) is affected
- [x] `harness/cli.py`'s `cmd_build` passes `runtime=self._write_runtime()` to `build_in_dir` — the
  same root-anchored `Runtime` every other Tenet-1-compliant product command already uses
- [x] `harness/spec_loop.py`'s `_decompose_build` single-function fallback passes its own
  already-existing `runtime` parameter through to `build_in_dir(..., runtime=runtime)`, closing the
  gap REQ-12 explicitly flagged and left out of scope
- [x] `harness/agent_loop.py`'s `execute_step` `"build"` action is RE-CONFIRMED eval-only (reached
  only by `harness/agentic_eval.py` and tests, never a live CLI command) and is left unwired,
  documented honestly rather than silently
- [x] `harness/intent_loop.py`'s `build_from_intent`/`_run_oracle` (the hidden-oracle eval spine,
  always building into a self-created `tempfile.TemporaryDirectory()`) are confirmed OUT OF SCOPE
  and unchanged — no `runtime` parameter added, no signature change
- [x] A gate rejection (e.g. a path escaping root) degrades to an honest failed result
  (`self_pass=False`, the rejection reason in `note`, `files: []`) — never an uncaught exception —
  from `build_in_dir`
- [x] Proven by `tests/test_ext037_build_jaros_write.py`: `build_in_dir` routes its code + test
  writes through a `code.write_file` Decision when a runtime is supplied (a fake recording
  runtime, and a real `harness.coding_loop.Runtime` proving the gate + REQ-1 root-jail actually
  fire); a root-jail rejection through the Decision path is honest (no crash, no partial effect);
  the `runtime=None` raw fallback is byte-identical to the pre-existing behavior; `/build` (via
  `JcodeCli.dispatch`) genuinely records a `code.write_file` Decision on the hash-chain
  `DecisionLog` for a real host-rooted temp directory; `_run_oracle`/`build_from_intent` are
  confirmed unchanged by signature inspection; `harness/agent_loop.py`'s eval-only `build` action
  is confirmed unchanged by source inspection; and the full suite has no regression

### [REQ-14] Gate host-repo file DELETIONS through a `code.delete_file` Decision (Tenet 1)  (covered)

**Owner directive (2026-07-08) — Tenet-1 compliance fix, same family as REQ-11.** The leaf-repair
"adopt" path in `harness/system_builder.py` (EXT-058's leaf-adoption cleanup, ~line 2809/2842)
deletes stale free-form module files via `_jailed_delete`, which ALWAYS raw-unlinks
(`Path.unlink()`) regardless of whether a `runtime` is present — bypassing the Jaros Decision
gate + hash-chain that every other product-surface host FS effect goes through. REQ-11 already
closed this gap for WRITES (`_jailed_write`); this requirement closes the matching gap for
DELETES, mirroring the exact same idiom: an optional `runtime` parameter that, when supplied,
performs the delete as a real `code.delete_file` Decision applied through `Runtime.apply` (gate +
hash-chain log); `runtime=None` (the default) preserves the exact prior raw-unlink behavior
byte-for-byte, so every existing eval/test/suite caller against a throwaway sandbox directory is
unaffected.

Unlike `code.write_file`, no `code.delete_file` Jaros tool previously existed — `Runtime.apply`
dispatches generically to whatever tool is registered under `.jaros-data/tools/` for a Decision's
`type`, so this requirement also adds that tool (mirroring `write_file_tool.py`'s structure
exactly: root-jail via the existing `path_escape_reason` choke point, `execute()` performs the
delete), the genuine "executor branch" that lets a `code.delete_file` Decision validate, execute,
and hash-chain log exactly like `code.write_file` does.

**HONEST STATUS (Tenet 3, TASK-18):** `_jailed_delete` now mirrors `_jailed_write` exactly, and a
new `.jaros-data/tools/delete_file_tool.py` custom tool (`NAME = "code.delete_file"`) is registered
so a `code.delete_file` Decision genuinely validates, executes, and hash-chain logs through
`Runtime.apply` — proven by a real `harness.coding_loop.Runtime` end to end
(`tests/test_ext037_delete_decision.py`). **Adaptation note:** the originating task description
named `harness/coding_loop.py` as the file to add "the executor branch" in; inspection showed that
file's only `code.write_file`-adjacent branch is a cosmetic verbose-transcript print inside
`fix_loop` (unrelated to how `code.write_file` Decisions actually validate/execute/hash-chain
log — that happens via the Jaros custom-tool registry under `.jaros-data/tools/`, exactly where
`code.write_file` itself is implemented in `write_file_tool.py`). The genuine "executor branch"
was therefore implemented as the new peer tool `delete_file_tool.py`, the only way a
`code.delete_file` Decision can actually be dispatched by the generic `Runtime.apply` →
`executor.apply` → registered-tool pipeline; `harness/coding_loop.py` itself is unmodified by
this task.

#### Acceptance Criteria
- [x] A new Jaros custom tool registered as `code.delete_file` (`.jaros-data/tools/
  delete_file_tool.py`, mirroring `write_file_tool.py`'s `validate()`/`execute()` structure and
  root-jail via the existing `path_escape_reason` choke point) lets a `code.delete_file` Decision
  genuinely validate, execute, and hash-chain log through `Runtime.apply` exactly like
  `code.write_file` does
- [x] `harness/system_builder.py`'s `_jailed_delete(root, name, runtime=None)` gains the optional
  `runtime` parameter with the same structure as `_jailed_write`: the local `path_jail` pre-check
  runs first, unconditionally, preserving the current rejection messages/behavior; on success,
  `runtime=None` performs the existing raw `Path(resolved).unlink()` (guarded by `is_file()`)
  byte-for-byte; a supplied `runtime` builds a `code.delete_file` Decision (`payload={"path":
  resolved, "root": str(root)}`) and applies it via `runtime.apply(...)` inside a
  `try`/`except Exception`, returning `None` on success or an honest error string on any gate
  rejection/executor failure — never raises
- [x] A missing file is a silent no-op success on both the `runtime=None` and `runtime`-supplied
  paths
- [x] The two leaf-repair "adopt" call sites in `build_system` (the stale-free-form-module cleanup,
  and the fail-safe `main.py` cleanup) thread the already-in-scope `runtime` through to
  `_jailed_delete`
- [x] `runtime=None` (the default) preserves the exact current raw-delete behavior byte-for-byte —
  no existing eval/test/suite caller against a throwaway sandbox directory is affected
- [x] Proven by `tests/test_ext037_delete_decision.py`: a fake/mock runtime records exactly one
  `code.delete_file` Decision with the expected `path`/`root` payload when deleting an existing
  in-root file; `runtime=None` raw-deletes an existing file and returns `None`, and a missing file
  is a silent no-op returning `None`; a path-jail escape (`"../evil.py"`) is rejected with no
  Decision emitted and nothing deleted, whether or not a runtime is supplied

### [REQ-15] Egress-scan PRECISION for listener/parser submodules — no weakening (covered)

**Owner-directed, security-sensitive (2026-07-10) — measured false-positive, PRECISION not
relaxation.** `harness/secure_exec.py::scan_code`'s NETWORK/EGRESS import classification
(REQ-7) matched on the ROOT module name (`root in _NETWORK_ROOT_MODULES`), so `import
http.server`, `import socketserver`, and `from urllib.parse import ...` were all flagged as
egress purely because they share a root package name (`http`, `urllib`) with a genuinely
egress-capable module (`http.client`, `urllib.request`). `http.server`/`socketserver` are
INBOUND LISTENERS — they bind a local socket and accept connections; they cannot themselves
initiate outbound traffic. `urllib.parse` is a PURE STRING PARSER — no I/O of any kind. This
over-flagging measurably blocked `build_system`'s acceptance/repair machinery for every
stdlib HTTP-service class (the scan-refusal short-circuits before any acceptance/repair logic
runs, per REQ-7's TASK-10 gate). This requirement makes the egress scan's import matching
SUBMODULE-PRECISE instead of root-name matching, closing that false-positive — the HARD
BOUNDARY (every genuinely egress-capable module — `urllib.request`, `http.client`, raw
`socket`, third-party HTTP clients, `ftplib`/`smtplib`/`telnetlib`/`xmlrpc.client`, etc.) stays
flagged exactly as before. This is a precision fix, never a relaxation of the security posture.

**HONEST STATUS (Tenet 3, TASK-19):** `harness/secure_exec.py`'s import classification gained
`_is_network_module(mod)`, a small explicit-precedence classifier: (1) an exact match in a new
`_NETWORK_ALLOWED_SUBMODULES` allowlist (`http.server`, `socketserver`, `urllib.parse`,
`html.parser`, `email.parser`) is NEVER egress; (2) an exact match in the existing
`_NETWORK_MODULES` set (`socket`, `urllib.request`, `http.client`, `requests`, `httpx`,
`aiohttp`, `ftplib`, `smtplib`, `telnetlib`, `xmlrpc.client`, `paramiko`, `urllib`/`urllib2`
bare) is ALWAYS egress; (3) any other submodule (or a bare `import <root>`) under a new
`_NETWORK_PRECISE_ROOTS` set (`urllib`, `http`, `xmlrpc`) DEFAULT-DENIES exactly as before —
only the explicit allowlist is exempted, nothing else changes behavior. `_classify_import` was
updated to call this classifier for both `ast.Import` and `ast.ImportFrom` nodes, and — for the
mixed-import case (`from urllib import parse, request`) where `node.module` is itself a precise
root — classifies EACH imported name individually as its own submodule
(`f"{node.module}.{alias.name}"`) so a sneaky mixed import still flags on the unsafe name even
though a sibling name in the same statement is allowlisted. `socket` is deliberately NOT
allowlisted even though servers use it too — a raw `socket.socket()` can `connect()` out, so it
stays flagged; the STANDING SECURITY ORDER (owner, non-negotiable) is precision, not relaxation.
Only import-statement classification changed; the scan's other categories (filesystem escape,
subprocess, dynamic-exec, the CALL-site network detection for `requests.get(...)`-style calls)
are untouched.

**Honest scope note:** this task closes the SCAN's false-positive only. The separate control-flow
issue this false-positive exposed — `harness/system_builder.py`'s early-return on scan refusal
(~line 3439-3451) skipping acceptance/governed-repair/single-file-retry/leaf-repair — is an
explicit, separate follow-up NOT touched by this task (a different owning file, out of this
task's scope boundary).

#### Acceptance Criteria
- [x] `import http.server`, `import socketserver`, `from urllib.parse import ...`, and
  `from http.server import ...` no longer flag as NETWORK/EGRESS (`report.ok is True`,
  `report.egress_ops == []`)
- [x] `from urllib import parse` (submodule-of-precise-root form) is allowed, but `from urllib
  import parse, request` (a sneaky mixed import) still flags — the unsafe name in the same
  statement is never hidden by an allowlisted sibling
- [x] Every genuinely egress-capable form STAYS flagged, unchanged: `import urllib.request`,
  `from urllib import request`, `from urllib.request import urlopen`, `import http.client`,
  `import socket`, `import requests`, and a bare `import urllib` (no submodule, can't prove
  which part is used, default-deny)
- [x] A mixed file (`http.server` alongside `urllib.request`) is still refused
- [x] An integration proof: a modules dict for a stdlib HTTP service (`http.server` +
  `socketserver` + `sqlite3` + `urllib.parse`) now passes `scan_code` cleanly, while the same
  shape using `urllib.request` still fails
- [x] The scan's other categories (SUBPROCESS/SHELL, DYNAMIC-EXEC, DESTRUCTIVE/FS-OUTSIDE-ROOT,
  and the CALL-site network/host detection) are unchanged
- [x] Proven by `tests/test_ext037_secure_exec.py`: each allowlisted import form passes, each
  still-flagged form is refused (including the sneaky mixed `from urllib import parse, request`
  and the bare `import urllib`), the mixed-file case is refused, and both integration
  (stdlib-HTTP-service-passes / urllib.request-still-fails) cases pass; the full pre-existing
  `test_ext037_secure_exec.py` suite remains green with no regression

### [REQ-16] Dependency-security gate — Phase 1: deprecated/dangerous stdlib + EOL interpreter (offline, advisory)  (covered)

**Owner directive (2026-07-10) — "gate builds on dependency security."** Generated systems in
this harness are STDLIB-ONLY by design (Tenet 2 / no network egress), so the usual SCA/CVE-
database approach doesn't apply — the stdlib has no independently-versioned packages to look
up. The honest risk model instead has three axes: (1) a stdlib module that is
DEPRECATED/REMOVED across supported CPython versions (PEP 594 "dead batteries" + a handful of
older removals — code using one will break on a newer interpreter); (2) a stdlib API that is
DANGEROUS when used carelessly (weak hashing, `subprocess(shell=True)`, bare `eval`/`exec`, a
racy `tempfile.mktemp`, unpickling untrusted bytes); (3) an EOL interpreter. Phase 1 is fully
OFFLINE (no network, no CVE-DB call), deterministic, and ADDS a check — it never weakens any
existing gate (`harness/secure_exec.py`'s egress/subprocess/dynamic-exec/destructive-fs scan,
REQ-7, is untouched). It also hardens the just-shipped REQ-66 affordance hint (which
recommends spec-permitted stdlib modules) so it can never recommend a dangerous/deprecated
module.

**HONEST STATUS (Tenet 3, TASK-20):** a new, standalone, PURE-STDLIB module
`harness/stdlib_safety.py` mirrors the house pattern already established by
`harness/secure_exec.py::scan_code` and `harness/code_quality.py::assess_quality` (never
raises; AST-based; conservative/precise detectors, no false-positive storms). It exposes:
`DEPRECATED_REMOVED` (a dict of stdlib module name -> a short PEP-594/removal note, covering
`telnetlib`/`cgi`/`cgitb`/`crypt`/`imghdr`/`nntplib`/`asyncore`/`asynchat`/`imp`/`smtpd`/
`sndhdr`/`spwd`/`nis`/`ossaudiodev`/`audioop`/`chunk`/`mailcap`/`msilib`/`pipes`/`uu`/
`xdrlib`/`formatter`/`distutils`); `DANGEROUS_AFFORDANCES` (that set unioned with
`{pickle, marshal, shelve, telnetlib, crypt, cgi}` — modules that must never be RECOMMENDED as
an affordance even though some, like `pickle`, are not deprecated); `is_safe_affordance(module)`
(the REQ-66 gate); `stdlib_safety_findings(code)` (an AST scan returning
`{kind, module|api, message, severity}` dicts for a deprecated-module import or one of five
precise dangerous-use call shapes — `hashlib.md5(`/`sha1(`, `subprocess.*(shell=True)`, bare
`eval(`/`exec(`, `tempfile.mktemp(`, `pickle.load`/`loads` — deliberately SKIPPING a
`random.`-for-secrets detector, too ambiguous to flag reliably without false-positiving on
legitimate simulation/sampling use); and `interpreter_eol_warning(version_info=None)` (pure,
testable with a fake version tuple, comparing against `MIN_SUPPORTED = (3, 9)`).

Two wiring points in `harness/system_builder.py`: (a) `_spec_affordance_hint` now FILTERS its
module list through `is_safe_affordance` before rendering the hint — a pure removal (can only
shrink the recommended list, never add to it), so the empty-list-when-nothing-safe path stays
byte-identical to before this task, proven by a new REQ-66-coupling test (`pickle` yields no
hint, `base64` still does); (b) `build_system` computes a `stdlib_security` field (findings
across every built module, tagged with `file`, plus the interpreter EOL warning) in the SAME
spot/pattern as the REQ-8 `quality` signal — right after the REQ-7 security scan gate has
already passed — and attaches it via a new additive `stdlib_security=None` default kwarg on
`_result`, threaded to the exact same relevant return paths `quality` already reaches. This is
ADVISORY ONLY, exactly like `quality`: no return path's `shipped`/`done`/`unmet` computation
reads `stdlib_security` in any way, and no pre-existing caller/test that ignores the field is
affected except for the new `"stdlib_security"` key on the result dict.

**Honest scope note (Phase 1 only):** this is offline/static only — no CVE database, no
package-version lookup (moot for stdlib), and the findings are ADVISORY, not gating. Whether
any of this becomes a hard gate (e.g. refuse a build over `pickle.loads` on untrusted input)
is deferred to a later phase, once real measured data exists on false-positive rate and
whether the model actually reaches for these patterns.

#### Acceptance Criteria
- [x] `harness/stdlib_safety.py::DEPRECATED_REMOVED` covers the PEP-594 "dead batteries" +
  known removals/deprecations named above, each with a short version/reason note
- [x] `DANGEROUS_AFFORDANCES` includes `pickle`/`marshal`/`shelve`/`telnetlib`/`crypt`/`cgi`
  unioned with `DEPRECATED_REMOVED`; `is_safe_affordance(module)` returns `False` for any
  member of either set, `True` otherwise (e.g. `base64`/`difflib`/`hashlib`/`textwrap`)
- [x] `stdlib_safety_findings(code)` never raises (syntactically broken code returns `[]`),
  flags a deprecated-module import and each of the five dangerous-use call shapes on a
  positive example, and returns `[]` for clean code
- [x] `interpreter_eol_warning(version_info=None)` returns a warning string for an EOL tuple
  (e.g. `(3, 7)`) and `None` for a current one (e.g. `(3, 12)`), pure/testable via the
  `version_info` parameter
- [x] `_spec_affordance_hint` never recommends a `DANGEROUS_AFFORDANCES`/`DEPRECATED_REMOVED`
  module even when the spec explicitly names it — proven by a spec naming `pickle` yielding no
  hint while a spec naming `base64` still yields one
- [x] `build_system` attaches an ADVISORY `stdlib_security` field (findings + EOL warning) on
  the same relevant return paths `quality` already reaches, via `_result`'s additive
  `stdlib_security=None` default kwarg — never gates `done`/`shipped`/`unmet`
- [x] The REQ-7 `secure_exec.py` egress/subprocess/dynamic-exec/destructive-fs scan gate is
  completely untouched — no weakening of any existing security check
- [x] Proven by `tests/test_ext037_stdlib_safety.py`: `is_safe_affordance` true/false cases,
  each `stdlib_safety_findings` detector firing on a positive example and staying silent on
  clean/broken code, `interpreter_eol_warning`'s EOL/current cases, and the REQ-66-coupling
  test; no regression in `tests/test_ext036_spec_affordance_hint.py` or
  `tests/test_ext060_*.py`
