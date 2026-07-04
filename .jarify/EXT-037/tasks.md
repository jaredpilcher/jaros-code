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
