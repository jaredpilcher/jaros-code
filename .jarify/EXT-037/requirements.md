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
