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
