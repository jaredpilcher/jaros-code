# Implementation Tasks

### [TASK-1] Root-jailed filesystem writes — shared `path_jail` helper wired into every writer tool

Add a single deterministic path-jail helper that resolves a write target to its absolute real
path (resolving both `..` traversal and symlinks) and rejects anything that escapes a caller-
supplied project root. Wire the helper into the `validate()` gate of every existing writer tool
(`code.write_file`, `code.apply_patch`, `code.search_replace`) so an out-of-root target is
refused, honestly, before any host effect — with no change to legitimate in-root writes.

#### Steps
1. Create `.jaros-data/tools/_pathjail.py` (underscore-prefixed so the Jaros tool loader skips
   it, mirroring `_codesafety.py`): a `PathEscapeError` exception, a `path_jail(root, target)`
   function that resolves `target` (absolute or joined onto `root`) via `os.path.realpath` and
   raises `PathEscapeError` if the resolved real path is not contained within
   `os.path.realpath(root)` (via `os.path.commonpath`, case-normalized), and a
   `path_escape_reason(root, target) -> str | None` convenience wrapper returning a human
   rejection reason (or `None` if the target is safely contained) for one-line use in a tool's
   `validate()`.
2. In `.jaros-data/tools/write_file_tool.py`, import `path_escape_reason` (with the same
   fail-open-on-missing-helper try/except pattern already used for `_codesafety`) and, in
   `WriteFileTool.validate()`, when the payload includes an optional `root` string, call
   `path_escape_reason(root, path)` and `ValidationResult.reject(...)` with the reason if the
   target escapes root. Omitting `root` leaves current behavior unchanged (no regression to
   existing callers that do not yet supply a root).
3. Apply the same `root`-gated `path_escape_reason` check to `ApplyPatchTool.validate()` in
   `.jaros-data/tools/apply_patch_tool.py` and `SearchReplaceTool.validate()` in
   `.jaros-data/tools/search_replace_tool.py`, so all three writer tools share the identical
   single choke point (no duplicated containment logic).
4. Add `tests/test_ext037_pathjail.py` covering: `path_jail` accepts an in-root relative path;
   rejects `..`-escape, an outside absolute path, and (where the OS/test env supports it) a
   symlink inside root pointing outside root; and each of the three writer tools' `validate()`
   refuses an out-of-root `root`+`path` pair (no file created) while still accepting/succeeding
   for an in-root pair and for calls that omit `root` entirely.
5. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline count plus the
   new tests) with no regression to the existing EXT-001 writer-tool tests or the EXT-036
   sentence-to-system build/modify tests.

#### Implements
- [REQ-1] Root-jailed filesystem writes — create/write/update confined to the project root

### [TASK-2] Thread root-context so the path-jail enforces (REQ-1/REQ-5)

TASK-1 built the `path_jail` mechanism and gated every writer tool's `validate()` on an
optional `root` in the Decision payload — but no real caller supplied `root`, so the jail
never fired in production. This task threads an actual project root into the two real
write paths so the jail enforces for real, without touching agents that don't yet have a
root concept: (a) the sentence-to-system product surface (`harness/system_builder.py`
`build_system`/`modify_system`, which write module files directly by a model-chosen
`name`, bypassing the Decision/tool layer entirely — so it gets its own direct
`path_jail` guard using the `root` it is already given), and (b) the Jaros-native
Decision-dispatch choke point (`harness.coding_loop.Runtime`), which gains an optional
`root` and stamps it onto every `code.write_file`/`code.apply_patch`/`code.search_replace`
Decision just before `validate()` — reused live by the `/agent` loop's `edit` step
(`harness/agent_loop.py`), where `cwd` is already the loop's authoritative project root.

#### Steps
1. In `harness/system_builder.py`, import `path_jail`/`PathEscapeError` from
   `.jaros-data/tools/_pathjail.py` (add its directory to `sys.path`, mirroring the
   existing `_REPO_ROOT` pattern in `search_replace_tool.py`) and add a small
   `_jailed_write(root, name, content) -> str | None` helper (returns `None` on a
   successful in-root write, or a rejection-reason string with NO write performed when
   `name` resolves outside `root`).
2. Replace every model-controlled-name write site in `build_system`/`modify_system`/
   `_repair_system` (the plan-derived ASSEMBLE step, the acceptance-repair apply/revert
   writes, and `modify_system`'s assemble/regenerate/revert writes) with calls through
   `_jailed_write`, so a plan or modification that names a module outside the target
   `root` (e.g. `"../../evil.py"`) is refused before any host effect — never raising,
   matching the existing non-degrading/never-raise contract of these functions.
3. In `harness/coding_loop.py`, add an optional `root: str | None = None` parameter to
   `Runtime.__init__`, store it, and in `Runtime.apply()`, when `self._root` is set and
   the Decision's `type` is one of `code.write_file`/`code.apply_patch`/
   `code.search_replace` and its payload is a dict without an existing `root` key,
   construct a new Decision (`dataclasses.replace`) whose payload adds `root` before
   calling `validate_decision` — a single, opt-in (default `None`, fully backward
   compatible) choke point any caller can adopt.
4. In `harness/agent_loop.py`'s `execute_step`, change the `edit` action's
   `Runtime().apply(d)` to `Runtime(root=cwd).apply(d)` — `cwd` is already the loop's
   authoritative project root (grounds `find`/`read`/`run`/`fix` today), so this closes
   the jail for the one live interactive write path where the root is already known and
   unambiguous. The general interactive CLI (`harness/cli.py`'s `JcodeCli.rt`) is
   intentionally left UNWIRED — its existing commands (e.g. `/patch <file-outside-cwd>`)
   legitimately target paths outside the process cwd today (proven by
   `tests/test_ext004_cli.py::test_files_and_patch_wire_those_tools`, which patches a
   `tmp_path` file via a bare `Runtime()`), so forcing `root=cwd` there would be a
   regression, not a fix; this is an honest scope boundary, not an oversight.
5. Add tests covering: an out-of-root `build_system`/`modify_system` module name is
   rejected end-to-end (no file written outside the temp root) while in-root names still
   ship unchanged; `Runtime(root=...).apply(...)` rejects an out-of-root
   `code.write_file`/`code.apply_patch`/`code.search_replace` Decision and still accepts
   an in-root one and one with no `root` configured; and `execute_step`'s `edit` action
   refuses an escaping `fname` while an in-`cwd` edit still succeeds.
6. Run `python -m pytest tests/ -q` to confirm the full suite is green with no
   regression to the EXT-001 writer-tool tests, the EXT-004 CLI tests, or the EXT-036
   sentence-to-system build/modify tests.

#### Implements
- [REQ-1] Root-jailed filesystem writes — create/write/update confined to the project root
- [REQ-5] Toolbelt is Jaros-native + Foundry-safe end to end

### [TASK-3] Gated CLI execution (REQ-2)

`shell_exec_tool.py` (EXT-001 / REQ-5 / REQ-7) already carries the timeout + process-tree
kill and a safety denylist, but was missing two REQ-2 specifics: an explicit per-command
override path for the denylist gate (never default-on), and a `cwd` default anchored to a
caller-supplied project `root` rather than the ambient process directory. This task closes
that gap without touching the existing denylist patterns or the tree-kill mechanism, and
hardens `execute()` so it never raises uncaught on a bad `cwd`/unresolvable command.

#### Steps
1. In `.jaros-data/tools/shell_exec_tool.py`'s `ShellExecTool.validate()`, add an explicit,
   payload-scoped `allow_unsafe` override: only when the payload's `allow_unsafe` key is the
   literal boolean `True` does the existing deny-pattern check get skipped for that one
   command; any other value (missing, `False`, a truthy string) leaves the existing
   denylist gate fully in effect (never default-on).
2. In `ShellExecTool.execute()`, resolve `cwd` from `payload.get("cwd") or payload.get("root")
   or None` so a caller that supplies a project `root` (and no explicit `cwd`) gets its
   command anchored there by default, matching REQ-1's root concept without importing the
   path-jail helper (no writes happen in this tool to jail).
3. Wrap the `subprocess.Popen(...)` call in `execute()` in a `try`/`except Exception` that
   returns a structured, honest failure observation (`exitCode: None`, an `error` field, a
   descriptive `stderr`) instead of letting a bad `cwd` or unresolvable command raise
   uncaught — the timeout/tree-kill path already returns structured results, this closes the
   same contract for process-start failures.
4. Add `tests/test_ext037_gated_exec.py` (offline, no network, no real destructive ops)
   covering: a fast safe in-root command succeeds with a structured stdout/exit-code
   observation and `cwd` defaulting to a supplied `root`; a short `time.sleep` command
   exceeding a short `timeout_s` is killed cleanly with an honest `timedOut` result; a
   destructive command (`rm -rf ...`) and an egress command (`curl ...`) are each rejected
   by `validate()` by default, the override is NOT default-on (only literal `allow_unsafe:
   True` opts in, tested with a harmless `echo` stand-in so nothing unsafe is ever actually
   run), and `execute()` never raises for a bad `cwd`/nonexistent command (returns a
   structured error observation instead).
5. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline 1408
   passed, 1 skipped, plus the new REQ-2 tests) with no regression to the existing EXT-001
   `shell.exec` tests (timeout, denylist, output-capture).

#### Implements
- [REQ-2] Gated host CLI execution — run commands as a deterministic, safeguarded tool

### [TASK-4] Environment tools — python/venv/deps (REQ-3)

Add the missing environment-setup capability so the product can hand back a RUNNABLE,
dependency-complete project, not just source: four deterministic Jaros tools (Python
detection, project-root venv creation, venv-scoped dependency install, and requirements
pinning), all sharing the existing `path_jail`/`path_escape_reason` choke point (REQ-1)
for every write (the venv directory, the requirements file) so they inherit the same
root-jail containment as `write_file`/`apply_patch`/`search_replace`, plus a new
`_envtools.py` helper (underscore-prefixed, skipped by the tool loader) for the
cross-platform venv-python path and the global-install-flag denylist.

#### Steps
1. Add `.jaros-data/tools/_envtools.py`: `venv_python_path(venv_dir) -> str` (returns
   `<venv>/Scripts/python.exe` on Windows, `<venv>/bin/python` on POSIX — the expected
   path, not required to exist yet) and `global_install_flag(args: list[str]) -> str |
   None` (returns the first disallowed global-scope pip flag — `--user`, `--target`,
   `--prefix`, `--system`, `--global`, `--root`, `--break-system-packages` — found in
   `args`, or `None`).
2. Add `.jaros-data/tools/python_detect_tool.py` (`env.python_detect`): read-only —
   `validate()` always accepts (nothing to gate for a detection). `execute()` probes a
   caller-supplied `candidates` list (default `[sys.executable, "python3", "python",
   "py"]`), resolves each via `shutil.which`/absolute check, runs `<interp> --version`
   (bounded timeout, never raises), dedupes by real path, and returns `{found: [...],
   primary, available}` as a structured observation.
3. Add `.jaros-data/tools/venv_create_tool.py` (`env.venv_create`): `validate()` requires
   a non-empty `root` that already exists as a directory, and a `venv_path` (default
   `.venv`) that `path_escape_reason(root, venv_path)` accepts (root-jailed, mirroring
   the existing writer tools). `execute()` resolves the jailed target via `path_jail`,
   calls stdlib `venv.create(target, with_pip=True)` (offline — `ensurepip` bootstraps
   from bundled wheels, no network), and returns `{venvPath, pythonPath, created,
   pythonExists}`; never raises (wraps `venv.create` in try/except, returns a structured
   error observation on failure).
4. Add `.jaros-data/tools/venv_install_tool.py` (`env.venv_install`): installs into the
   venv's OWN python only — never a system/global pip. `validate()` root-jails
   `venv_path`, requires a non-empty `package`/`packages`, rejects a package spec that
   looks like a flag (starts with `-`), rejects any `extra_args` entry that is a
   global-scope pip flag (`global_install_flag`, never default-on — no flag list means
   nothing is blocked, but nothing broadens scope either since the command is always
   `<venv-python> -m pip install`), and rejects the whole decision if the venv's python
   does not already exist (no silent fallback to an ambient/system interpreter) unless
   `dry_run: true`. `execute()` builds `[venv_python, "-m", "pip", "install",
   *extra_args, *packages]`; when `dry_run` is set (or the venv python is missing)
   returns the constructed command WITHOUT running it (`installed: false, dryRun:
   true`); otherwise runs it (bounded timeout, never raises) and returns exit
   code/stdout/stderr.
5. Add `.jaros-data/tools/venv_pin_tool.py` (`env.venv_pin`): writes a root-jailed
   requirements file (default `requirements.txt`). Default mode runs the venv's own
   `pip freeze` (fully offline — lists only already-installed packages, no network);
   callers may instead supply an explicit `packages` list to skip the freeze. `execute()`
   never raises (wraps the freeze subprocess and the file write in try/except) and
   returns `{requirementsPath, source: "freeze"|"explicit", written, bytesWritten}`.
6. Add `tests/test_ext037_env_tools.py` (offline, no network, mirrors the
   `_load_tool`/`_decision` conventions of `test_ext037_gated_exec.py`) covering:
   `env.python_detect` returns at least one interpreter with a parsable version;
   `env.venv_create` creates a real venv in a temp root (assert the venv python file
   exists) and its `validate()` rejects a `venv_path` escaping root (no venv created);
   `env.venv_install`'s `validate()` rejects a global-scope `extra_args` flag and a
   missing-venv target, and its `execute()` (via `dry_run: true`, no network) builds the
   correct venv-scoped `-m pip install` command; `env.venv_pin` writes a root-jailed
   `requirements.txt` from a real (offline) `pip freeze` against the created venv, and
   its `validate()` rejects a requirements path escaping root; every tool's `execute()`
   never raises on a bad/missing root or venv.
7. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline 1417
   passed, 1 skipped, plus the new REQ-3 tests) with no regression.

#### Implements
- [REQ-3] Environment tools — Python + virtualenv + dependencies

### [TASK-5] Git tools — init/commit/history/branch (REQ-4)

Add the missing version-control capability so the product can version its work like Claude Code:
seven new deterministic Jaros tools (`git.init`, `git.commit`, `git.status`, `git.log`, `git.diff`,
`git.branch`, `git.history_update`), all sharing a new `_gittools.py` git-CLI choke point (never
raises; a bad `cwd`/missing binary/timeout comes back as a structured, honest result) and a new
`_gitsecrets.py` deterministic secret/ignored-path guard, plus reuse of the existing `_pathjail`
choke point (REQ-1) for every explicit path a commit stages.

#### Steps
1. Add `.jaros-data/tools/_gittools.py` (underscore-prefixed so the Jaros tool loader skips it,
   mirroring `_pathjail.py`/`_envtools.py`): `has_git_repo(root) -> bool` (checks for a `.git`
   entry) and `run_git(cwd, args, timeout_s=30) -> dict` (runs `git <args>` in `cwd` via
   `subprocess.run`, never raises — a bad `cwd`, missing `git` binary, or a command exceeding the
   timeout all come back as a structured result dict with `command`/`exitCode`/`stdout`/`stderr`/
   `timedOut`, never an uncaught exception).
2. Add `.jaros-data/tools/_gitsecrets.py` (underscore-prefixed): a deterministic
   `secret_or_ignored_reason(path) -> str | None` pattern guard mirroring jaros-code's own commit
   discipline (CLAUDE.md: never commit `.env`, secrets, logs, or runtime state) — refuses `.env`
   (and `.env.*`), `*.pem`/`*.key`/`*.pfx`/`*.p12`/`*.jks`, SSH private keys (`id_rsa`, `id_dsa`,
   `id_ecdsa`, `id_ed25519`), common credential/secrets files (`credentials.json`, `secrets.yaml`,
   `.npmrc`, `.netrc`, `.pypirc`, AWS credentials), and ignored/runtime paths (`.log`,
   `__pycache__`, `*.pyc`, `node_modules`, the runtime `.jaros-data` subpaths).
3. Add `.jaros-data/tools/git_init_tool.py` (`git.init`): `validate()` requires a non-empty `root`
   that already exists as a directory. `execute()` runs `git init` at `root` via `run_git` and
   returns `{alreadyInitialized, initialized, ...}`; never raises on a bad root.
4. Add `.jaros-data/tools/git_commit_tool.py` (`git.commit`): stages `paths` (or the whole working
   tree via `git add -A` when `paths` is omitted) and commits with `message`. `validate()`
   root-jails every explicit path (reusing `_pathjail.path_escape_reason`, REQ-1's choke point),
   then runs a READ-ONLY `git status --porcelain --untracked-files=all` (scoped to `paths` when
   given) to enumerate the candidate files a commit would ACTUALLY stage — whether the caller
   named files or asked for "everything" — and refuses the WHOLE commit (before any `git add`
   ever runs) if any candidate matches `_gitsecrets.secret_or_ignored_reason`. `execute()` stages
   via `git add -A [-- paths]`, reads the actually-staged file list via
   `git diff --cached --name-only`, commits via `git commit -m message`, and resolves the new
   commit hash via `git rev-parse HEAD`; never raises on a bad root or failed git invocation.
5. Add `.jaros-data/tools/git_status_tool.py` (`git.status`), `git_log_tool.py` (`git.log`), and
   `git_diff_tool.py` (`git.diff`) as read-only observation tools (no root-jail needed — reads may
   range broadly, mirroring the existing `_pathjail.py` rule): `git.status` parses
   `git status --porcelain` into structured `{path, indexStatus, worktreeStatus}` entries plus a
   `clean` flag; `git.log` parses `git log --pretty=format:...` into `{hash, author, date,
   subject}` commits (an empty/uninitialized repo returns an honest `hasCommits: false`, not an
   error); `git.diff` returns the raw unified diff (`staged` flag selects `--cached`) plus a
   `hasChanges` flag.
6. Add `.jaros-data/tools/git_branch_tool.py` (`git.branch`): `action` is `"list"` (default,
   read-only), `"create"`, or `"switch"` (the latter two require a `name` sanity-checked against a
   restrictive charset so it can't be mistaken for a CLI flag). `execute()` runs
   `git branch --list`/`git branch <name>`/`git checkout [-b] <name>` respectively and returns a
   structured result including the current branch on `list`.
7. Add `.jaros-data/tools/git_history_update_tool.py` (`git.history_update`): the ONE
   explicitly-gated history-mutating operation (`action` one of `amend`/`reset_hard`/
   `force_push`). `validate()` REJECTS unless the payload's `allow_unsafe` key is the literal
   boolean `True` (mirroring `shell_exec_tool.py`'s REQ-2 override exactly — never default-on, any
   other value including a truthy string leaves the gate fully in effect), plus action-specific
   required fields (`ref` for `reset_hard`; `remote`/`branch` for `force_push`). `execute()` runs
   `git commit --amend`/`git reset --hard <ref>`/`git push --force <remote> <branch>`
   respectively; never raises.
8. Add `tests/test_ext037_git_tools.py` (offline, no network — no remote is ever configured, so
   even the `force_push` gate test only proves the rejection, never runs a push), skipping cleanly
   if `git` is not on `PATH`. Cover: `git.init` creates a real repo and never raises on a bad root;
   `git.commit` stages + commits a file end-to-end (asserting `commitHash`/`staged`); a `.env`
   secret file is refused whether staged implicitly ("commit everything") or named explicitly,
   confirmed via `git.log` showing zero commits, while committing only the safe file still
   succeeds; an out-of-root `paths` entry is rejected; `git.status`/`git.log`/`git.diff` report
   real state (untracked files, the committed subject/hash, an unstaged diff) including the
   honest empty-repo `git.log` case; `git.branch` creates/lists a branch and switches to a new one
   via `create_if_missing`, and rejects a bad name; `git.history_update` is rejected by default for
   `amend`/`reset_hard`/`force_push` (including non-boolean `allow_unsafe` values), succeeds for
   `amend` once explicitly gated (replacing, not adding to, the commit history), and
   `reset_hard`/`force_push` still require their action-specific fields even once gated; every
   tool's `execute()` never raises on a bad/missing root; and the `_gitsecrets` helper is
   unit-tested directly against representative safe/unsafe paths.
9. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline 1434 passed, 1
   skipped, plus the 20 new REQ-4 tests) with no regression.

#### Implements
- [REQ-4] Git tools — version the work like Claude Code

### [TASK-6] Orchestrator wields the toolbelt in `/buildsystem` (REQ-5)

TASK-1 through TASK-5 built and hardened the toolbelt itself, but nothing in the
product actually CALLED the git/env tools yet — `/buildsystem` shipped source files
and stopped. This task adds a deterministic, conservative post-build FINALIZE step
(`harness.system_finalize.finalize_system`) that runs after a successful
`/buildsystem` ship: git-init + commit the shipped system (through the
secret-guarded `git.init`/`git.commit` tools, REQ-4), create a root venv only when
the system actually declares a dependency (an existing `requirements.txt`, or a
detected non-stdlib top-level import) and pin the detected package names into
`requirements.txt` (REQ-3) — never installing anything over the network — and NEVER
auto-run the generated code. Every finalize effect is dispatched through
`harness.coding_loop.Runtime` (the real gate -> executor -> decision-log choke
point), so the effects are hash-chain logged and replayable exactly like any other
Runtime-mediated Decision, closing REQ-5's own bar end to end.

#### Steps
1. Add `harness/system_finalize.py` with `finalize_system(root, modules=None, *,
   git=True, venv="auto", commit_message=None, data_dir=None) -> dict`: dispatches
   `git.init`/`git.commit` (when `git=True`) and, when a dependency is detected (an
   existing `requirements.txt` in `root`, or a non-stdlib top-level import found by
   an `ast`-based scan across `modules`) and `venv` is `"auto"` (or always when
   `venv="always"`), `env.venv_create` plus `env.venv_pin` (explicit `packages`
   mode, only when no `requirements.txt` already exists) — every effect built as a
   real `Decision` and routed through `harness.coding_loop.Runtime(root=root)` so
   it is validated by the real gate and hash-chain logged via the real
   `DecisionLog`/`TransitionLog`, not called ad hoc. `venv="off"` and `git=False`
   independently and cleanly disable each half. NEVER raises: every `Runtime.apply`
   call is wrapped so a rejected commit (e.g. a secret path), a venv failure, or any
   other exception is caught and reported in the returned `steps`/`note`, and the
   whole function is wrapped in an outer try/except as a final backstop.
2. Wire `harness/cli.py`'s `cmd_buildsystem` to call `finalize_system` after a
   shipped build, gated by a new `_buildsystem_finalize_config()` helper: env-var
   driven (`JCODE_FINALIZE_SYSTEM` to disable the whole step, `JCODE_FINALIZE_GIT`
   to disable only git, `JCODE_FINALIZE_VENV` to override `auto`/`always`/`off`),
   defaulting to git-commit ON, venv `"auto"`, and (always, unconditionally)
   auto-run OFF — `finalize_system` never executes the built system. The
   finalize outcome (`ok`/which steps ran) is appended to the command's report
   text; a disabled finalize is reported honestly too. No change to
   `build_system`/`build_system_escalating`/the escalation core, or to the
   built system's own files/output.
3. Add `tests/test_ext037_finalize.py` (offline, no network, skip-if-no-git)
   covering: `finalize_system` git-inits + commits a shipped build end-to-end
   (`git log` shows the commit); a system with a `requirements.txt` (or a detected
   non-stdlib import) triggers `env.venv_create` (a real offline venv) and pins
   detected packages into `requirements.txt` via `env.venv_pin` when one doesn't
   already exist; a stdlib-only system skips the venv step entirely (no `.venv`
   created); a `.env` secret in the build root is refused by the existing secret
   guard and NOT committed, confirmed via zero commits in `git log`; a simulated
   `Runtime` failure (monkeypatched) and a nonexistent root both prove
   `finalize_system` never raises and reports honestly instead; `git=False` and
   `venv="off"` cleanly skip both halves; and the CLI's
   `_buildsystem_finalize_config()` env-var gate is unit-tested directly (default
   config, each override, and a bogus env value falling back to the safe default).
4. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline
   1454 passed, 1 skipped, plus the 10 new REQ-5 tests) with no regression to the
   EXT-036 `/buildsystem` tests or any prior EXT-037 task's tests.

#### Implements
- [REQ-5] Toolbelt is Jaros-native + Foundry-safe end to end

### [TASK-7] Interactive CLI wields the git toolbelt (REQ-5)

TASK-5 built the git tools and TASK-6 wired them into the automated `/buildsystem`
finalize step, but a REPL user still had no direct way to inspect or commit git
state — the only place the CLI touched git was that one post-build finalize call.
This task adds five REPL commands (`/gitstatus`, `/gitlog [n]`, `/gitdiff [file]`,
`/gitbranch`, `/commit <message>`) to `harness/cli.py`, each dispatching the
existing git.* Decision through a root-anchored `Runtime`, the SAME two-plane path
`harness/system_finalize.py` already uses — no new tool logic, purely a new caller
of the existing REQ-4 toolbelt.

#### Steps
1. In `harness/cli.py`, add a `JcodeCli._git_tool(dtype, payload)` helper that
   defaults `payload["root"]` to `os.path.abspath(".")` (mirroring how `/agent`'s
   `cwd`-aware steps resolve their root), builds a Decision via
   `self._mk(...)`, applies it through a fresh `Runtime(root=root)`, and NEVER
   raises — any gate rejection (a not-a-repo root, git.commit's secret/ignored-path
   guard) or executor failure is caught and returned as `(None, error_text)` instead
   of propagating to the REPL.
2. Add a `_git_read_failed(out)` static helper that reports an honest one-line
   failure reason for a read-only git tool's output (`exitCode != 0`), used by the
   read commands to detect a non-repo directory without raising.
3. Add `cmd_gitstatus`, `cmd_gitlog`, `cmd_gitdiff`, `cmd_gitbranch` — each calls
   `_git_tool` with the corresponding `git.status`/`git.log`/`git.diff`/
   `git.branch` type and formats the returned observation as readable text
   (`/gitlog` accepts an optional count argument; `/gitdiff` accepts an optional
   file argument scoping the diff via `paths`).
4. Add `cmd_commit` — requires a non-empty message (else returns a usage string),
   calls `_git_tool("git.commit", {"message": message})`, and surfaces the tool's
   secret-guard rejection reason honestly (never forces the commit through) or the
   new commit hash + staged file count on success.
5. Add the five new commands to the module docstring's `/help` text, grouped near
   `/diff`/`/undo`. No explicit `dispatch()` registration needed — `dispatch()`
   already resolves `cmd_<name>` via `getattr` reflection.
6. Add `tests/test_ext037_cli_git.py` (offline, no network, skip-if-no-git,
   mirrors `tests/test_ext037_git_tools.py`'s temp-repo conventions) covering: each
   read command against a real dirty/clean temp repo; `/gitlog [n]` respecting an
   explicit count and rejecting a non-numeric one; `/commit <msg>` growing the real
   git log and requiring a non-empty message; a `.env` file present triggers a
   refused/rejected commit (no new commit created); and every handler returning a
   clean string (never raising) in a directory that is not a git repo at all.
7. Run `python -m pytest tests/ -q` to confirm the full suite is green (baseline
   1454 passed, 1 skipped, plus the 11 new REQ-5 CLI tests) with no regression to
   any prior EXT-037 task's tests or the EXT-004 CLI tests.

#### Implements
- [REQ-5] Toolbelt is Jaros-native + Foundry-safe end to end

### [TASK-8] Scratch research-script investigation plane (REQ-6)

Add the missing INVESTIGATION capability so the product can write a throwaway probe script,
run it, and read the result — the exact Claude-Code "write a probe, run it, read the result"
loop — as a native, deterministic, two-plane execution-plane module. This is invoked directly
by orchestration code (not dispatched as a Decision), so it lands as a plain function module
rather than a Jaros custom tool, but reuses the existing `_pathjail`/tree-kill choke points so
it inherits the same root-jail and no-orphan guarantees as the rest of the toolbelt. The script
and any file it writes live only in a scratch dir strictly outside the target repo; this module
never mutates the target repo.

#### Steps
1. Add `harness/research_scripts.py` importing `path_jail`/`PathEscapeError` from
   `.jaros-data/tools/_pathjail.py` (add its directory to `sys.path`, mirroring the existing
   `_REPO_ROOT` pattern in `search_replace_tool.py`) and a private `_kill_tree(proc)` helper
   copied from `shell_exec_tool.py` (`taskkill /F /T /PID` on Windows, `os.killpg` +
   `SIGKILL` on POSIX, both wrapped so a kill failure never raises).
2. Implement `run_research_script(code: str, *, scratch_dir: str | None = None,
   timeout: float = 30, args: list | None = None, stdout_limit: int = 20000) -> dict`:
   resolve `scratch_dir` to a fresh `tempfile.mkdtemp(prefix="jcode_research_")` when not
   supplied (creating it if a caller-supplied directory doesn't yet exist), write `code` to
   `<scratch_dir>/script.py` via `path_jail(scratch_dir, "script.py")` (rejecting, honestly,
   if the resolved script path ever escapes scratch — it never should for a fixed filename,
   but this keeps the same choke point as every other writer), and launch
   `[sys.executable, script_path, *(args or [])]` with `cwd=scratch_dir`,
   `subprocess.Popen(..., stdout=PIPE, stderr=PIPE, text=True)` (POSIX gets
   `start_new_session=True` so `_kill_tree` can reach descendants).
3. On `proc.communicate(timeout=timeout)`: if stdout length `<= stdout_limit`, return
   `{"ok": returncode == 0, "returncode": returncode, "stdout": stdout,
   "stderr": stderr[-stdout_limit:], "timed_out": False, "scratch_dir": scratch_dir,
   "note": ...}`. If stdout exceeds `stdout_limit`, write the FULL stdout to
   `<scratch_dir>/output.txt` (path-jailed the same way) and return
   `{"ok": ..., "returncode": ..., "stdout_file": <path>, "stdout_head": stdout[:N],
   "stdout_tail": stdout[-N:], "truncated": True, "total_bytes": len(stdout), "stderr": ...,
   "timed_out": False, "scratch_dir": scratch_dir, "note": ...}` (`N` a fixed head/tail slice
   size, e.g. 2000 chars, independent of `stdout_limit`).
4. On `subprocess.TimeoutExpired`: call `_kill_tree(proc)`, drain any already-buffered
   output with a short bounded `communicate(timeout=5)`, and return
   `{"ok": False, "returncode": None, "stdout": ..., "stderr": ..., "timed_out": True,
   "scratch_dir": scratch_dir, "note": "timed out after Ns, process tree killed"}`.
5. Wrap the whole function body in a `try`/`except Exception` backstop (invalid `code`,
   an unwritable `scratch_dir`, a `Popen` start failure, a `PathEscapeError`, etc.) that
   returns `{"ok": False, "returncode": None, "stdout": "", "stderr": "", "timed_out": False,
   "scratch_dir": scratch_dir or "", "note": f"research script failed to run: {exc}"}` instead
   of ever raising.
6. Implement `read_research_output(path, *, max_bytes: int = 20000) -> str`: reads `path` in
   binary, and when the file is larger than `max_bytes` returns a head+tail slice (roughly
   `max_bytes // 2` from the start and end, joined by a `"...[truncated N bytes]..."` marker)
   decoded with `errors="replace"`; returns the whole decoded content when the file is small
   enough; wraps all I/O in `try`/`except Exception` and returns a short diagnostic string
   (never raises) on a missing/unreadable path or garbage input.
7. Add `tests/test_ext037_research_scripts.py` covering: a script that prints a small result
   returns `ok=True` with the result inline in `stdout`, and `scratch_dir` exists and is
   outside the repo root; a script whose stdout exceeds `stdout_limit` returns
   `truncated=True` with a real `stdout_file` in scratch containing the full output plus
   non-empty `stdout_head`/`stdout_tail`, and `read_research_output` on that file returns a
   bounded slice; a script that raises/exits non-zero returns `ok=False`,
   `returncode != 0`, and a captured `stderr` tail, without raising; a script that hangs
   (`while True: pass`) with a short `timeout` returns `timed_out=True`, `ok=False`, within a
   bounded wall-clock time, and leaves no orphaned process (verified, e.g., by writing a PID
   file from the child and confirming the PID is gone after `run_research_script` returns);
   the repo working tree is unchanged (`git status --porcelain` empty or unaffected) after
   every case above; and both functions never raise on garbage input (non-string `code`, a
   nonexistent `path` for `read_research_output`, etc.).
8. Run `python -m pytest tests/test_ext037_research_scripts.py -q` first, then the full
   `python -m pytest tests/ -q` to confirm the whole suite is green with no regression to any
   prior EXT-037 task's tests.

#### Implements
- [REQ-6] Scratch research-script investigation plane — throwaway probes, native two-plane

### [TASK-9] Secure sandboxed execution of generated code + gated egress — foundation (REQ-7)

Add the standalone `harness/secure_exec.py` sandbox module — the FOUNDATION that closes the live
gap of `build_system`'s acceptance step running model-generated code as a plain, unrestricted host
subprocess. Deterministic, self-contained, never-raises: an AST scanner that classifies dangerous
operations, a first-class `EgressPolicy` that GATES (default-deny + explicit allow-list) rather than
blankets network egress, and a sandboxed runner with a scrubbed environment and POSIX resource caps.
This task lands the module + its offline tests only; wiring it into `system_builder.py`'s acceptance
step is an explicit, separate follow-up (named, not silently deferred).

#### Steps
1. Create `harness/secure_exec.py` with an `EgressPolicy` dataclass: `mode: Literal["deny",
   "allow_list"] = "deny"`, `allowed_hosts: set[str] = frozenset()`. Add `is_host_allowed(host) ->
   bool` (False for `"deny"` mode; membership check against `allowed_hosts` for `"allow_list"`), a
   class-level `DENY_ALL` instance, and a classmethod/constructor `allow(*hosts) ->
   EgressPolicy` that builds an `"allow_list"` policy from the given hosts.
2. In the same module, add a `ScanPolicy` dataclass holding the per-category default-deny flags
   (`deny_subprocess: bool = True`, `deny_dynamic_exec: bool = True`, `deny_destructive_fs: bool =
   True`) so a caller can deliberately loosen one category, and a `SecurityReport` dataclass
   (`ok: bool`, `violations: list[dict]`, `egress_ops: list[dict]`, `notes: list[str]`).
3. Implement `scan_code(sources, *, egress_policy=None, scan_policy=None) -> SecurityReport`:
   accept `sources` as a single code string or a `{filename: code}` dict; for each file, `ast.parse`
   inside a `try`/`except SyntaxError` (an unparseable file becomes a `violation`, not a crash), then
   walk the AST (`ast.walk`) classifying `ast.Import`/`ast.ImportFrom`/`ast.Call`/`ast.Attribute`
   nodes into NETWORK/EGRESS (`socket`, `urllib`, `http.client`, `requests`, `httpx`, `aiohttp`,
   `ftplib`, `smtplib`, etc.), SUBPROCESS/SHELL (`os.system`, `os.popen`, `subprocess.*`, `pty`),
   DYNAMIC-EXEC (`eval`, `exec`, `compile`, `__import__`, `importlib.import_module`), and
   DESTRUCTIVE/FS-OUTSIDE-ROOT (`shutil.rmtree`, `os.remove`/`unlink`/`rmdir`, `os.chmod`, and an
   `open()`/`Path.write_*` call whose first argument is a string literal that is an absolute path or
   contains a parent-escaping `".."` segment). Each match records `{category, detail, lineno}`.
4. Decide `ok` in `scan_code` by policy: any SUBPROCESS/SHELL, DYNAMIC-EXEC, or
   DESTRUCTIVE/FS-OUTSIDE-ROOT match (when its `ScanPolicy` flag is True, the default) appends to
   `violations` and sets `ok=False`. An EGRESS match appends to `egress_ops` always, but only becomes
   a `violations` entry (forcing `ok=False`) when `egress_policy` is `None` or does not permit the
   specific host/module in question (egress is GATED, not auto-forbidden) — when an `allow_list`
   policy is supplied, egress ops are recorded but do not by themselves flip `ok=False`.
5. Implement `run_sandboxed(cmd, *, cwd, egress_policy=EgressPolicy.DENY_ALL, timeout=30,
   mem_mb=512, extra_env=None) -> dict`: build a SCRUBBED environment dict (a minimal safe allow-list
   — `PATH`, `SYSTEMROOT`/`WINDIR` on Windows, `LANG`, `TMP`/`TEMP`, `PYTHONPATH` if present in the
   current env — plus whatever `extra_env` supplies; nothing else from `os.environ` is copied), launch
   `subprocess.Popen(cmd, cwd=cwd, env=scrubbed_env, stdout=PIPE, stderr=PIPE, text=True)` (POSIX gets
   `start_new_session=True` and, when the stdlib `resource` module is importable, a `preexec_fn`
   applying `resource.setrlimit(RLIMIT_AS, ...)`/`RLIMIT_CPU` from `mem_mb`/`timeout` — guarded in a
   `try`/`except` so a platform without `resource` just skips the cap), reuse the existing
   timeout + process-tree-kill pattern (mirroring `.jaros-data/tools/shell_exec_tool.py::_kill_tree`:
   `taskkill /F /T /PID` on Windows, `os.killpg` + `SIGKILL` on POSIX) on `subprocess.TimeoutExpired`,
   and return `{ok, returncode, stdout, stderr, timed_out, killed, note}` — document inline that
   runtime egress blocking is NOT implemented here (a Linux network namespace/firewall follow-up);
   never raises (an outer `try`/`except` backstop returns an honest `ok=False` result on any failure
   to even start the process).
6. Implement `secure_run_generated(sources, cmd, *, cwd, egress_policy=EgressPolicy.DENY_ALL) ->
   dict`: call `scan_code(sources, egress_policy=egress_policy)`; if `not report.ok`, return
   `{"ran": False, "blocked": True, "report": report}` without running anything; else call
   `run_sandboxed(cmd, cwd=cwd, egress_policy=egress_policy)` and return `{"ran": True, "blocked":
   False, "report": report, **run_result}`.
7. Add `tests/test_ext037_secure_exec.py` (offline, deterministic) covering: `scan_code` flags each
   category on crafted snippets (`os.system`, `subprocess.run`, `eval`/`exec`/`__import__`,
   `shutil.rmtree`, `open('/etc/x', 'w')`, a `socket`/`requests` import) and a clean stdin-reading CLI
   script has `ok=True` with no violations; an egress-using snippet is flagged under `DENY_ALL` but
   passes the egress category under `EgressPolicy.allow("pypi.org")` (proving GATED-not-blocked);
   `EgressPolicy.is_host_allowed` permits a listed host and denies an unlisted one under `allow_list`,
   and denies everything under `DENY_ALL`; `run_sandboxed` scrubs the environment (set
   `os.environ["SECRET_TOKEN"]` in the test, run a child that prints
   `os.environ.get("SECRET_TOKEN", "<none>")`, assert the child sees `<none>` while a safe var like
   `PATH` is still present in the child); `run_sandboxed` enforces its timeout (a hang is killed,
   `timed_out=True`, no orphan) and never raises on garbage `cmd`/`cwd`; a POSIX-only test proves a
   memory-bombing child is killed by the `RLIMIT_AS` cap (skipped on Windows, per platform honesty);
   and `secure_run_generated` refuses to run a violating snippet (`blocked=True`, nothing executed)
   while running a clean one successfully.
8. Run `python -m pytest tests/test_ext037_secure_exec.py -q` first, then the full
   `python -m pytest tests/ -q` synchronously in the foreground to confirm the whole suite is green
   with no regression to any prior EXT-037 task's tests.

#### Implements
- [REQ-7] Secure sandboxed execution of generated code + gated egress

### [TASK-10] Wire `harness/secure_exec.py` into `build_system`'s acceptance execution — close the live gap (REQ-7)

TASK-9 landed the standalone sandbox module (`EgressPolicy`, `scan_code`, `run_sandboxed`,
`secure_run_generated`) but left it deliberately unwired — `build_system`'s acceptance step still ran
model-generated code as a plain subprocess with the FULL host environment and no static scan. This task
closes that live gap by wiring the module into `harness/system_builder.py` itself: a SECURITY SCAN GATE
that refuses to execute a build whose generated modules trip a dangerous-operation classification, and
a SANDBOXED execution path (scrubbed environment, resource caps, DENY_ALL egress by default) for the
acceptance-check subprocess that used to be a plain `harness.multi_file._run` call.

#### Steps
1. Import `EgressPolicy`, `run_sandboxed`, `scan_code` from `harness.secure_exec` into
   `harness/system_builder.py`.
2. Add a SECURITY SCAN GATE in `build_system`, immediately after ASSEMBLE and before EITHER
   acceptance path (the HTTP/web-service branch or the plain checklist branch) ever executes
   anything: call `scan_code(built, egress_policy=EgressPolicy.DENY_ALL)`; on `not report.ok`,
   return a result with `shipped=True` (assembly preserved for inspection), `done=False`, an
   honest `"SECURITY: build refused — <violation categories/details>"` note, and a new additive
   `security` field on the result dict carrying the full `SecurityReport`. Add the `security`
   keyword (default `None`, backward compatible) to the shared `_result(...)` helper.
3. Add a `_run_acceptance_cmd(cwd, cmd)` helper that calls `harness.secure_exec.run_sandboxed`
   (egress `DENY_ALL`, timeout from `JCODE_TEST_TIMEOUT_S`/120s default) and returns the same
   `(ok, combined_stdout_stderr)` shape the prior `harness.multi_file._run` call returned. Route
   both `_run_check` and `_run_check_verbose` (shared by the REQ-5 acceptance-repair loop and by
   `modify_system`'s own acceptance checks) through this helper instead of the plain subprocess
   call, so the acceptance-check script — and anything it in turn spawns, e.g. its own
   `python main.py` subprocess — runs with a SCRUBBED environment (no ambient host secrets),
   POSIX resource caps, and the existing timeout + process-tree-kill discipline.
4. Add three tests to `tests/test_ext036_system_builder.py` (offline, fake-llm, no live model):
   a build whose generated module contains a dangerous op (`os.system(...)`) is refused before
   its acceptance checklist is ever derived or executed (`done=False`, a `"SECURITY"` note, a
   populated `security` field, no `ACCEPTANCE CHECKS` prompt issued, no acceptance-check temp
   file ever written); a normal clean fake-llm build still assembles, runs, and passes acceptance
   exactly as before (proving the sandbox wiring doesn't break a normal build); and a host secret
   env var set in the test process is genuinely invisible to the sandboxed acceptance subprocess
   (an acceptance check asserting the secret is absent actually passes — this check would have
   FAILED before this task, since the prior plain-subprocess path inherited the full host
   environment).
5. Run `python -m pytest tests/ -q` synchronously in the foreground to confirm the whole suite is
   green with no regression to any prior EXT-036/EXT-037 task's tests.

#### Implements
- [REQ-7] Secure sandboxed execution of generated code + gated egress

### [TASK-11] Sandbox the two remaining unsandboxed execution sites — `server_oracle` + `system_suite` (REQ-7)

TASK-10 wired `harness.secure_exec` into `build_system`'s OWN acceptance path only, and named the
two remaining live gaps as an explicit follow-up rather than silently deferring them:
`harness/server_oracle.py`'s `serve_and_check` (the HTTP acceptance oracle for a detected web
service) launches its `uvicorn`/`flask` subprocess as a plain, full-host-environment
`subprocess.Popen`, and `harness/system_suite.py`'s `_run_cli` (used by the creation suite,
`modification_suite`, and `coherence_suite`) runs the built CLI's entrypoint the same
unsandboxed way. This task closes both gaps by routing each through
`harness.secure_exec.run_sandboxed`, preserving EXACT existing behavior for legitimate builds
(the scan gate from TASK-10 already refuses a *dangerous* build before either site ever
executes; this task only adds the env-scrub + resource-cap SANDBOXING of the execution itself).

#### Steps
1. In `harness/secure_exec.py`, add an optional `stdin: str | None = None` parameter to
   `run_sandboxed`, distinguished from "omitted entirely" via a private `_STDIN_UNSET`
   sentinel default: when a caller explicitly passes `stdin` (a string, or `None`), the child's
   stdin is piped (`subprocess.PIPE`) and fed via `proc.communicate(input=stdin, timeout=...)`
   (`None` sends an immediate EOF); when `stdin` is omitted entirely, behavior is UNCHANGED from
   before this parameter existed (no stdin pipe constructed, every existing caller stays
   byte-for-byte backward compatible).
2. In `harness/system_suite.py`, replace `_run_cli`'s plain `subprocess.Popen` +
   `communicate`/`TimeoutExpired`/tree-kill implementation with a call to
   `harness.secure_exec.run_sandboxed(cmd, cwd=str(cwd), egress_policy=EgressPolicy.DENY_ALL,
   timeout=timeout, stdin=stdin)`, keeping the exact same `(ok, combined stdout+stderr)` return
   shape callers (`system_suite`, `modification_suite`, `coherence_suite`) already depend on.
   Remove the now-unused `subprocess`/`os` imports from the module.
3. In `harness/server_oracle.py`, add a `_launch(..., *, mem_mb=512, cpu_budget_s=120)` variant
   that builds its subprocess environment via `harness.secure_exec._scrubbed_env` (reused, not
   reimplemented) instead of `dict(os.environ)`, and (POSIX only) applies the same
   `harness.secure_exec._make_preexec_fn`-built `RLIMIT_AS`/`RLIMIT_CPU` resource-cap
   `preexec_fn` `run_sandboxed` itself uses. `run_sandboxed` is NOT called directly here (it is
   a blocking helper incompatible with a long-running server the caller must poll/query/kill
   across its own lifecycle) — only its scrub/cap BUILDING BLOCKS are reused. `serve_and_check`
   computes a generous `cpu_budget_s` (startup_timeout + request_timeout * len(checks) + a
   buffer) and passes `mem_mb`/`cpu_budget_s` through to `_launch`; the existing
   `_wait_for_port`/per-check `request_timeout`/unconditional `_kill_tree` teardown remain the
   actual enforcement mechanism, unchanged. A module-level `SERVER_EGRESS_POLICY =
   EgressPolicy.allow("127.0.0.1", "localhost")` documents (without newly enforcing anything
   beyond what `run_sandboxed` already documents as static-only) that the server is expected to
   need only localhost — it binds a listen socket (not egress) and the PARENT process makes the
   HTTP requests to it (not sandboxed itself).
4. Add `test_run_cli_scrubs_host_secret_env` and `test_run_cli_timeout_kills_hanging_entrypoint_no_orphan`
   to `tests/test_ext036_suite.py` (a host secret set in the test process is invisible to the
   built CLI's subprocess; a hanging entrypoint is killed within its timeout with no orphaned
   process). Add `TestServeAndCheckEnvScrub::test_server_subprocess_cannot_see_host_secret` to
   `tests/test_ext036_server_oracle.py` (a host secret is invisible to the real FastAPI server
   subprocess, proven via a `/secret` endpoint that echoes the env var back). Add
   `test_run_sandboxed_stdin_feeds_child_and_still_scrubbed`,
   `test_run_sandboxed_stdin_none_sends_immediate_eof`, and
   `test_run_sandboxed_omitted_stdin_param_still_runs_fine` to `tests/test_ext037_secure_exec.py`
   proving the new `stdin` parameter feeds data correctly, still scrubs the environment, and
   leaves every pre-existing (no-`stdin`) caller unaffected. Confirm every existing
   `tests/test_ext036_server_oracle.py` fixture test (real FastAPI + Flask servers) still passes
   unchanged — the scrub must not break serving.
5. Run `python -m pytest tests/test_ext036_server_oracle.py tests/test_ext036_suite.py
   tests/test_ext036_modsuite.py tests/test_ext036_coherence.py tests/test_ext037_secure_exec.py
   -q` first, then the full `python -m pytest tests/ -q` synchronously in the foreground to
   confirm the whole suite is green with no regression to any prior EXT-036/EXT-037 task's
   tests, and confirm (via a process listing) no orphaned uvicorn/flask/python process survives
   the run.

#### Implements
- [REQ-7] Secure sandboxed execution of generated code + gated egress

### [TASK-12] Code-quality signal on generated systems — advisory (REQ-8)

Answer the owner's open question (2026-07-04) "are we checking the actual code it's writing for
quality?" — previously honestly NO. Add a deterministic, PURE-STDLIB (`ast`-only — no
`ruff`/`radon`/`pyflakes`; none installed, none added) code-quality signal over a built system's
modules, and attach it as an ADDITIVE, ADVISORY `quality` field on `build_system`'s result. This
NEVER gates the build — a working-but-smelly system stays exactly as shipped/done as before.

#### Steps
1. Create `harness/code_quality.py` with `assess_quality(sources: dict[str, str]) ->
   QualityReport`, mirroring `harness/secure_exec.py::scan_code`'s AST-walk house pattern
   (never raises; a single code string or a `{filename: code}` dict; unparseable source is
   recorded as a note and skipped, not a crash).
2. Compute per-function McCabe cyclomatic complexity (`1 + count of If/For/AsyncFor/While/
   ExceptHandler/With-items/BoolOp-extra-values/IfExp/comprehension-if/assert/match-case`,
   never descending into a nested function/lambda's own body so its decision points aren't
   double-counted into the outer function's score), function length in lines, and max nesting
   depth; aggregate into `max_complexity`/`worst_function` across the whole scanned system.
3. Detect conservative structural smells (each a `{category, detail, lineno, file}` dict): bare
   `except:`; `except Exception: pass` swallow; a mutable list/dict/set literal default
   argument; a star-import; an overly-long function (> 80 lines); a high-complexity function
   (CC > 15); deep nesting (> 5 levels). Deliberately OMIT unused-import detection (cannot be
   done reliably from a single module's own AST — better to omit than false-positive).
4. Define `QualityReport(ok: bool, max_complexity: int, worst_function: str | None,
   smells: list[dict], per_file: dict, notes: list[str])`. `ok` is ADVISORY ONLY: `True` unless
   a *critical* smell (`bare_except`/`swallowed_exception` — the two patterns that actively HIDE
   a bug/error) fires; it MUST NOT be used to gate a build.
5. Wire into `harness/system_builder.py::build_system`: add a `quality=None` default kwarg to
   the shared `_result(...)` helper (mirroring the existing `security=None` kwarg), compute
   `quality = dataclasses.asdict(assess_quality(built))` immediately AFTER the REQ-7 security
   scan gate has already passed (built modules exist and are cleared to run), and pass
   `quality=quality` on every RELEVANT return path that has `built` — both `done=True` and
   `done=False` acceptance-outcome paths. Never touch the security-scan refusal logic itself,
   and never let `quality` influence `shipped`/`done`/`unmet` on any path.
6. Add `tests/test_ext037_code_quality.py` covering: a hand-computed known McCabe complexity
   value; each smell detector firing on a positive example and staying silent on clean code;
   `assess_quality` on clean code returning empty smells + `ok=True` (and never raising on
   garbage input); a `build_system` result carrying a populated `quality` field; the
   load-bearing proof that a deliberately-smelly-but-WORKING generated system (a bare `except:`
   around code that never actually raises) still returns `done=True`/`shipped=True`/`unmet=[]`
   (advisory, not gating); and `_result`'s omitted `quality` kwarg defaulting to `None`,
   byte-compatible for every pre-existing caller.
7. Run `python -m pytest tests/test_ext037_code_quality.py tests/test_ext036_suite.py -q` first,
   then the full `python -m pytest tests/ -q` synchronously in the foreground to confirm the
   whole suite is green with no regression to any prior EXT-036/EXT-037 task's tests.

#### Implements
- [REQ-8] Code-quality signal on generated systems — advisory

### [TASK-13] `refactor.py`'s `/rename`/`/move` writes are Jaros-native (REQ-9)

Tenet-1 compliance sweep (tracker #112), refactor.py slice only. `harness/refactor.py`'s
`rename_symbol`/`move_symbol` write to the user's repo via raw `Path.write_text`, bypassing the
gate + REQ-1 root-jail + hash-chain log. Mirror the PROVEN EXT-042 REQ-5 idiom
(`harness/jcode_md.py::init_jcode_md`): an optional `runtime` parameter that, when supplied,
performs the write as a `code.write_file` Decision through `Runtime.apply`; `runtime=None`
preserves the exact current raw-write behavior for every existing eval/test caller.

#### Steps
1. In `harness/refactor.py`, add `import uuid` and a private `_jaros_write(path, content, root,
   runtime=None) -> str | None` helper: when `runtime is None`, writes `content` to `path` via the
   existing raw `Path.write_text(..., encoding="utf-8", newline="\n")` call (byte-identical
   fallback); when `runtime` is given, builds a `jaros.core.create_decision(type="code.write_file",
   payload={"path": str(path), "content": content, "root": str(root)})` and applies it via
   `runtime.apply(decision)` inside a `try`/`except Exception`, returning `None` on success or an
   honest `f"failed to write {path}: {exc}"` string on any gate rejection/executor failure (never
   raises).
2. Add an optional keyword-only `runtime: object | None = None` parameter to `rename_symbol` and
   `move_symbol`. In `rename_symbol`'s per-file write loop, replace the raw
   `p.write_text(new_src, ...)` call with `_jaros_write(p, new_src, cwd, runtime)`; if it returns a
   non-`None` error string, call `_restore(snap)` (never ship a partially-renamed, ungated repo) and
   return `{"renamed": False, "occurrences": occ, "files": files, "note": err}`. In `move_symbol`,
   replace both `src_p.write_text(...)` and `dst_p.write_text(...)` calls the same way; on either
   returning an error, `_restore(snap)` and return `{"moved": False, "note": err}`.
3. In `harness/cli.py`'s `cmd_rename` and `cmd_move`, pass `runtime=self._write_runtime()` to
   `rename_symbol(...)`/`move_symbol(...)` — the same root-anchored `Runtime` `/init`/`/remember`/
   `/rewind` already use — so a real `/rename`/`/move` invocation is gated, root-jailed, and
   hash-chain logged. No other CLI change.
4. Confirm (do not modify) that every non-CLI caller of `rename_symbol`/`move_symbol` —
   `harness/daily_driver.py` (eval, temp `workdir`), `harness/refactor_eval.py` (eval harness, temp
   dir `d`), `tests/test_ext003_refactor.py`, `tests/test_ext003_scoped_rename.py` (both `tmp_path`)
   — keeps calling with no `runtime` argument, so they stay on the byte-identical raw-write
   fallback (their temp-dir paths are not under any repo root and must never be forced through the
   root-jail).
5. Add `tests/test_ext037_refactor_jaros_write.py` covering: `rename_symbol`/`move_symbol` with a
   fake `runtime` object (recording `.apply(decision)` calls) route every write through a
   `code.write_file` Decision with the expected `path`/`content`/`root` payload; a fake runtime
   whose `.apply` raises (simulating a gate rejection / root-jail escape) produces an honest
   `renamed: False`/`moved: False` result with the error in `note`, no crash, and the suite-green
   snapshot/restore leaves the repo unchanged; `runtime=None` (the default, omitted entirely)
   produces byte-identical output to the pre-existing behavior for both functions; and a real
   `harness.coding_loop.Runtime(root=tmp_path)` end-to-end proves an in-root rename/move still
   succeeds while a crafted out-of-root target is refused via the real REQ-1 gate.
6. Run `python -m pytest tests/ -q` synchronously in the foreground (background it with
   `run_with_heartbeat` per the observability convention) and confirm the exit code and full pass
   count, with no regression to `tests/test_ext003_refactor.py`, `tests/test_ext003_scoped_rename.py`,
   `tests/test_ext004_cli.py`, `harness/daily_driver.py`'s refactor-routing eval, or any prior
   EXT-037 task's tests.

#### Implements
- [REQ-9] Deterministic refactor writes (`/rename`, `/move`) are Jaros-native (Tenet 1)

### [TASK-14] `multi_file.py`'s `/fixrepo` (and the shared `_restore` used by `/undo`) writes are Jaros-native (REQ-10)

Tenet-1 compliance sweep (tracker #112), `multi_file.py` slice (SLICE 2). `harness/multi_file.py`'s
`_restore` and `_minimize_edits` write to the user's repo via raw `Path.write_text`, bypassing the
gate + REQ-1 root-jail + hash-chain log. Mirror the PROVEN REQ-9 idiom exactly
(`harness/refactor.py`'s `_jaros_write`): an optional `runtime` parameter that, when supplied,
performs the write as a `code.write_file` Decision through `Runtime.apply`; `runtime=None`
preserves the exact current raw-write behavior for every existing eval/test/sandbox caller.
`_restore` is SHARED with `harness/cli.py`'s `cmd_undo` (EXT-009 `/undo`) — wiring it once closes
the gap for both `/fixrepo` and `/undo`.

#### Steps
1. In `harness/multi_file.py`, add `import uuid` and a private `_jaros_write(path, content, root,
   runtime=None) -> str | None` helper, identical in contract to `harness/refactor.py`'s REQ-9
   helper: `runtime=None` performs the existing raw `Path.write_text(..., encoding="utf-8",
   newline="\n")`; a supplied `runtime` builds a `jaros.core.create_decision(type=
   "code.write_file", payload={"path": str(path), "content": content, "root": str(root)})` and
   applies it via `runtime.apply(decision)` inside a `try`/`except Exception`, returning `None` on
   success or an honest `f"failed to write {path}: {exc}"` string on any gate rejection/executor
   failure (never raises).
2. Add optional keyword-only `runtime: object | None = None` and `root: str | None = None`
   parameters to `_restore(snap, ...)`; replace its per-file `Path(path).write_text(...)` call
   with `_jaros_write(path, text, root, runtime)`, accumulating and returning the first honest
   error string encountered (or `None` on full success) instead of the current bare `-> None`.
   Every existing caller that ignores the return value (every pre-existing caller) is unaffected.
3. Add an optional keyword-only `runtime: object | None = None` parameter to `_minimize_edits(cwd,
   test_cmd, orig, kept_paths, ...)`; replace both raw `Path(path).write_text(...)` calls (the
   temporary revert-to-original probe write, and the restore-of-the-necessary-fix write) with
   `_jaros_write(path, ..., cwd, runtime)` calls. If the FIRST (probe) write is refused, `continue`
   to the next kept path without running the suite probe (conservatively leave that edit KEPT,
   exactly as it was) rather than risk a half-reverted file; never raise.
4. Add an optional keyword-only `runtime: object | None = None` parameter to `multi_file_fix(cwd,
   test_cmd, instruction, test_file, ...)`; thread it to the internal `_restore(snap,
   runtime=runtime, root=cwd)` call (the no-progress revert) and to `_minimize_edits(cwd, test_cmd,
   orig, kept_paths, runtime=runtime)`.
5. In `harness/cli.py`'s `cmd_fixrepo`, pass `runtime=self._write_runtime()` to `multi_file_fix`.
   In `cmd_undo`, pass `runtime=self._write_runtime()` and `root=os.path.abspath(".")` to
   `_restore`; on a non-`None` error return, report it honestly (`f"undo failed: {err}"`) without
   clearing `self._agent_snapshot`, so `/undo` can be retried. No other CLI change.
6. Confirm (do not modify) that every non-CLI caller of `multi_file_fix`/`_restore`/
   `_minimize_edits` -- `harness/daily_driver.py`, `harness/multifile_eval.py`,
   `harness/agent_loop.py`'s `execute_step` "fix" action (eval-only, never live-wired to any CLI
   command), `harness/refactor.py`'s rename/move revert paths (REQ-9), `tests/test_ext003_multifile.py`,
   `tests/test_ext010_minimal_diff.py` -- keeps calling with no `runtime` argument, so they stay on
   the byte-identical raw-write fallback. `harness/system_builder.py` (`/buildsystem`) and
   `harness/spec_loop.py` (`/agent`'s structured flow) are explicitly out of scope for this task.
   FLAG (do not silently wire) `harness/cli.py`'s `cmd_plan` (`/plan`) and `_nl_fix` (the plain
   natural-language routing fallback) as additional real-host callers of `multi_file_fix` left
   unwired by this task's explicit scope -- a follow-up candidate, not an oversight.
7. Add `tests/test_ext037_fixrepo_jaros_write.py` covering: `_restore`/`_minimize_edits` route
   writes through a `code.write_file` Decision with a fake recording runtime (path/content/root
   payload); a rejecting fake runtime produces an honest error string, no crash, and the escaping
   path is never created; `runtime=None` is byte-identical to the pre-existing behavior for
   `_restore`/`_minimize_edits`/`multi_file_fix`; a real `harness.coding_loop.Runtime` proves an
   in-root write/restore actually lands through the gate while an out-of-root target is refused
   via the real REQ-1 path-jail; `multi_file_fix`'s own internal revert-on-no-progress lands
   through a REAL Decision end to end (spied via `DecisionLog.append_decision`); `/fixrepo` and
   `/undo` (via `JcodeCli.dispatch`/`cmd_undo`) each genuinely record a `code.write_file` Decision
   for a real host-rooted temp repo; and `/undo`'s escaping-snapshot gate rejection is honest and
   leaves the snapshot retryable.
8. Run `python -m pytest tests/ -q` synchronously in the foreground (background it with
   `run_with_heartbeat` per the observability convention) and confirm the exit code and full pass
   count, with no regression to `tests/test_ext003_multifile.py`, `tests/test_ext010_minimal_diff.py`,
   `tests/test_agent_loop.py`, `tests/test_ext049_checkpoint.py`, `tests/test_ext037_refactor_jaros_write.py`,
   or any prior EXT-037 task's tests.

#### Implements
- [REQ-10] Deterministic multi-file-fix writes (`/fixrepo`, and the SHARED `/undo` restore) are Jaros-native (Tenet 1)

### [TASK-15] `system_builder.py`'s `/buildsystem`/`/modifysystem` writes are Jaros-native (REQ-11)

Tenet-1 compliance sweep (tracker #112), `system_builder.py` slice (SLICE 3).
`harness/system_builder.py`'s single write chokepoint, `_jailed_write(root, name, content)`,
already applies the REQ-1 `path_jail` root-jail but performs the write via raw
`Path.write_text`, bypassing the gate + hash-chain log. Mirror the PROVEN REQ-9/REQ-10 idiom
exactly (`harness/refactor.py`'s and `harness/multi_file.py`'s `_jaros_write`): an optional
`runtime` parameter that, when supplied, performs the write as a `code.write_file` Decision
through `Runtime.apply`; `runtime=None` preserves the exact current raw-write behavior for
every existing eval/test/suite caller. Because every model-controlled-name write in this
module already funnels through `_jailed_write`, threading `runtime` through that one helper
(plus `_repair_system`, the module-level helper `build_system` calls) closes the gap for all
five public entry points in one move.

#### Steps
1. In `harness/system_builder.py`, add `import uuid` and give `_jailed_write(root, name,
   content, runtime=None) -> str | None` an optional `runtime` parameter: the existing local
   `path_jail(str(root), name)` pre-check (and its `PathEscapeError` handling) runs
   UNCONDITIONALLY first, unchanged — this preserves the exact current rejection messages
   regardless of `runtime`. On a successful jail resolution, `runtime is None` keeps the
   existing raw `Path(resolved).parent.mkdir(...)` + `Path(resolved).write_text(content,
   encoding="utf-8", newline="\n")` call; a supplied `runtime` instead builds
   `jaros.core.create_decision(id=f"system-builder-write-{uuid.uuid4().hex}",
   source="system_builder", type="code.write_file", payload={"path": resolved, "content":
   content, "root": str(root)})` and applies it via `runtime.apply(decision)` inside a
   `try`/`except Exception`, returning `None` on success or an honest `f"failed to write
   {name}: {exc}"` string on any gate rejection/executor failure — never raises.
2. Add an optional keyword-only `runtime: object | None = None` parameter to `_repair_system`
   and thread it to its two `_jailed_write(root, name, code, runtime)` / `_jailed_write(root,
   name, prev_code, runtime)` call sites (the applied-fix write and the regression-revert
   write).
3. Add an optional keyword-only `runtime: object | None = None` parameter to `build_system`;
   thread it to every `_jailed_write` call in the ASSEMBLE step and to the
   `_repair_system(spec, root, built, checks, unmet, llm, runtime=runtime)` call.
4. Add an optional keyword-only `runtime: object | None = None` parameter to `modify_system`;
   thread it to every `_jailed_write` call (the current-system assembly loop, the modified-
   module assembly loop and its half-written revert, and the regression-gate revert loop).
5. Add an optional keyword-only `runtime: object | None = None` parameter to
   `build_system_escalating`; thread it straight through to both internal
   `build_system(spec, root, llm=primary_llm, runtime=runtime)` /
   `build_system(spec, root, llm=fallback_llm, runtime=runtime)` calls (same target `root`, so
   no special-casing needed).
6. Add an optional keyword-only `runtime: object | None = None` parameter to
   `build_system_governed`; thread it to its internal `build_system(spec, root, llm=llm,
   runtime=runtime)` call and to its own two repair-loop `_jailed_write` call sites (the
   applied-fix write and the regression-revert write) plus the final no-regress-floor
   `_jailed_write` revert loop.
7. Add an optional keyword-only `runtime: object | None = None` parameter to
   `build_system_best_of_k`; thread it ONLY to the final winner-assembly `_jailed_write` loop
   that writes onto the caller's real `root` — its own per-attempt `build_system(spec,
   attempt_root, llm=llm)` calls into isolated `tempfile.mkdtemp()` subdirectories are left
   unchanged (`runtime=None`), since `attempt_root` is a throwaway directory `shutil.rmtree`'d
   before the function returns, not a meaningful project root to gate.
8. Leave the two `chk_path.write_text(code, ...)` sites in `_run_check`/`_run_check_verbose`
   (`_s2s_acceptance_check.py`, ~lines 822/862) unrouted and unmodified — document inline (a
   one-line comment) that this is deliberate: each is a transient acceptance-check script
   written immediately before running it and unconditionally `unlink()`d in the same call's
   `finally` block, never part of the shipped system.
9. In `harness/cli.py`'s `cmd_buildsystem`, pass `runtime=self._write_runtime()` to both the
   `build_system_escalating(...)` and `build_system(sentence, subdir, llm=self.llm)` call
   sites. In `cmd_modifysystem`, pass `runtime=self._write_runtime()` to
   `modify_system(modules, sentence, target_dir, llm=self.llm)`. No other CLI change.
10. Confirm (do not modify) that every non-CLI caller of `build_system`/`modify_system`/
    `build_system_escalating`/`build_system_governed`/`build_system_best_of_k` — every test in
    `tests/test_ext036_*.py` and `tests/test_ext037_root_enforcement.py`/
    `tests/test_ext037_code_quality.py`/`tests/test_ext040_heartbeat.py`, and every creation/
    modification-suite or Foundry probe script under `.jaros-data/` — keeps calling with no
    `runtime` argument, so they stay on the byte-identical raw-write fallback.
11. Add `tests/test_ext037_buildsystem_jaros_write.py` covering: `_jailed_write` routes a write
    through a `code.write_file` Decision with the expected `path`/`content`/`root` payload when
    a fake recording runtime is supplied; the local `path_jail` rejection (an escaping `name`)
    is honest and identical whether or not a runtime is supplied, and no Decision is built for
    a rejected path; `runtime=None` (the default, omitted entirely) produces byte-identical
    output to the pre-existing behavior for a full fake-llm `build_system` run; a real
    `harness.coding_loop.Runtime(root=tmp_path)` end-to-end proves a real `build_system`/
    `modify_system` call genuinely records a `code.write_file` Decision on the hash-chain
    `DecisionLog` for a real host-rooted temp directory; and `build_system_best_of_k`'s
    per-attempt temp-dir builds stay raw (no Decision recorded for attempt-root writes) while
    its final winner-assembly write is routed through a supplied runtime.
12. Run `python -m pytest tests/ -q` synchronously in the foreground (background it with
    `run_with_heartbeat` per the observability convention) and confirm the exit code and full
    pass count, with no regression to any prior EXT-036/EXT-037 task's tests.

#### Implements
- [REQ-11] `system_builder.py`'s `/buildsystem`/`/modifysystem` writes are Jaros-native (Tenet 1)

### [TASK-16] `spec_loop.py`'s `/agent`/`/plan`/`_nl_fix` writes are Jaros-native (REQ-12)

Tenet-1 compliance sweep (tracker #112), FINAL SLICE (4). `multi_file_fix` is already
runtime-capable (TASK-14/REQ-10) — it just needs the `runtime` PASSED at the remaining real-host
call sites REQ-10 explicitly flagged and left out of scope: `harness/cli.py`'s `cmd_plan`
(`/plan`'s `fix` step) and `_nl_fix` (the no-file-named fallback), and `harness/spec_loop.py`'s
`spec_driven_loop` (reached by `cmd_agent`/`/agent`). `spec_driven_loop`'s BUILD flow
(`_decompose_build` → `_build_class`/`_build_per_function`/`_build_whole_file`) ALSO writes
directly onto the real host `cwd` when reached via `/agent` with no failing test present — a
genuine real-host write path, not eval scaffolding — so this task routes those raw
`Path.write_text` sites through `harness/multi_file.py`'s existing `_jaros_write` helper too,
reusing it rather than duplicating it.

#### Steps
1. In `harness/cli.py`'s `cmd_plan`, add `runtime=self._write_runtime()` to the `fix`-step's
   `multi_file_fix(".", "python -m pytest -q", a or arg, test_file, verbose=False)` call.
2. In `harness/cli.py`'s `_nl_fix`, add `runtime=self._write_runtime()` to the no-file-named
   fallback's `multi_file_fix(".", "python -m pytest -q", instruction, test_file, max_iters=3,
   verbose=True)` call.
3. In `harness/cli.py`'s `cmd_agent`, add `runtime=self._write_runtime()` to
   `spec_driven_loop(arg, ".")`.
4. In `harness/spec_loop.py`, extend the existing `from harness.multi_file import _run,
   multi_file_fix` line to also import `_jaros_write`. Add an optional keyword-only
   `runtime: object | None = None` parameter to `spec_driven_loop(intent, cwd, ...)`; thread it to
   the FIX-flow's `multi_file_fix(cwd, _TEST_CMD, instr, test_file, max_iters=max_iters,
   verbose=verbose, runtime=runtime)` call and to the BUILD-flow's
   `_decompose_build(intent, cwd, max_iters=max_iters, verbose=verbose, runtime=runtime)` call.
5. Add an optional keyword-only `runtime: object | None = None` parameter to
   `_decompose_build(intent, cwd, ...)`; thread it to its `_build_class(..., runtime=runtime)`,
   `_build_per_function(..., runtime=runtime)`, and the FALLBACK `_build_whole_file(intent, cwd,
   [n for n, _ in reqs], max_iters=max_iters, verbose=verbose, runtime=runtime)` calls (all three
   pass the caller's real `cwd`, unchanged).
6. Add an optional keyword-only `runtime: object | None = None` parameter to `_build_class(intent,
   cwd, class_name, methods, ...)`; route its stub write (`(Path(cwd) / "solution.py").write_text
   (stub, ...)`) and its final `_sanitize_source` write (`sp.write_text(_sanitize_source(...))`)
   through `_jaros_write(path, content, cwd, runtime)` in place of the raw `Path.write_text` calls.
7. Add an optional keyword-only `runtime: object | None = None` parameter to `_build_whole_file(
   intent, cwd, names, ...)`; route its stub write (`(Path(cwd) / f"{module}.py").write_text(...)`)
   and its final `_sanitize_source` write through `_jaros_write(path, content, cwd, runtime)`.
8. Add an optional keyword-only `runtime: object | None = None` parameter to
   `_build_per_function(intent, cwd, sigs, ...)`; route its per-function stub write (`fp.write_text
   (_stub(...), ...)`), its combined `solution.py` assembly write, its hybrid winner swap-in write
   (`(Path(cwd) / "solution.py").write_text(wf_sol, ...)`), and its final `_sanitize_source` write
   through `_jaros_write(path, content, cwd, runtime)`. Its internal hybrid-probe call
   `_build_whole_file(intent, alt, [f for f, _ in sigs], max_iters=max_iters, verbose=verbose)`
   (building into a throwaway `tempfile.mkdtemp()` subdirectory `alt`, `shutil`-cleaned before this
   function returns) stays UNCHANGED at `runtime=None` — `alt` is never the caller's real root.
9. Add `tests/test_ext037_agent_plan_jaros_write.py` covering: `cmd_plan`'s `fix` step, `cmd_agent`
   (both its FIX flow and its BUILD flow — a request naming no existing test file and ≥2 concrete
   function signatures, e.g. per-function and whole-file paths), and `_nl_fix`'s no-file-named
   fallback each route their host writes through a `code.write_file` Decision when a runtime is
   supplied (a fake recording runtime, and a real `harness.coding_loop.Runtime` proving the gate +
   REQ-1 root-jail actually fire on an escaping target); `runtime=None` is byte-identical to the
   pre-existing behavior for `spec_driven_loop` (FIX and BUILD flows) and each of
   `_decompose_build`'s three build strategies (`_build_class`, `_build_per_function`,
   `_build_whole_file`); and `_build_per_function`'s hybrid-probe temp-dir build records no
   Decision (stays raw) even when its own outer call is given a runtime.
10. Run `python -m pytest tests/ -q` synchronously in the foreground (background it with
    `run_with_heartbeat` per the observability convention) and confirm the exit code and full pass
    count, with no regression to `tests/test_spec_loop.py`, `harness/build_eval.py`,
    `harness/agentic_eval.py`'s tests, `tests/test_ext004_planner.py`, or any prior EXT-037 task's
    tests.

#### Implements
- [REQ-12] `spec_loop.py`'s `/agent`/`/plan`/`_nl_fix` writes are Jaros-native (Tenet 1)
