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
