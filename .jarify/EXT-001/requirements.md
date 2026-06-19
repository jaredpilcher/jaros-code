---
id: EXT-001
title: Deterministic Execution-Plane Tool Primitives
status: partial
priority: high
implementation:
  - file: .jaros-data/tools/fs_read_tool.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/tools/fs_list_tool.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/tools/fs_grep_tool.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/tools/apply_patch_tool.py
    ranges:
      - - 1
        - 200
  - file: .jaros-data/tools/shell_exec_tool.py
    ranges:
      - - 1
        - 200
---

This spec serves **Tenet 1 (two-plane discipline)** of PRIME-001: every host
effect the harness performs is a deterministic Jaros tool with `validate()` +
`execute()`. The reasoning plane never touches the host; it only emits inert
`Decision` data whose `type` selects one of these tools. These are the execution
primitives the single-purpose coding agents (EXT-002) compose.

Read-only tools are purely replay-safe (re-running them reconstructs identical
output). Effectful tools (write, shell) are recorded as Decisions first, so a run
remains attributable and re-executable per Tenet 3.

### [REQ-1] fs.read — read a file's contents

A tool named `fs.read` reads a UTF-8 text file and returns its contents plus line
and byte counts, bounded by a size cap so the action stays inert.

#### Acceptance Criteria
- [ ] Reject a payload lacking a non-empty `path` string
- [ ] Return `{content, lines, bytes, path}` for an existing file
- [ ] Enforce a maximum byte cap and report `truncated` when the cap is hit
- [ ] Never write or mutate the host (read-only / replay-safe)

### [REQ-2] fs.list — list a directory

A tool named `fs.list` returns the sorted entries of a directory, each tagged as
`dir` or `file` with its size, so an agent can decide where to look next.

#### Acceptance Criteria
- [ ] Reject a payload lacking a non-empty `path` string
- [ ] Return entries sorted by name, each `{name, type, sizeBytes}`
- [ ] Report a clear error for a missing or non-directory path
- [ ] Never write or mutate the host (read-only / replay-safe)

### [REQ-3] fs.grep — search files by regex

A tool named `fs.grep` searches files under a root for a regular expression and
returns the matching locations, deterministically ordered.

#### Acceptance Criteria
- [ ] Reject a payload lacking a non-empty `pattern` string
- [ ] Return matches as `{file, line, text}` sorted by (file, line)
- [ ] Bound results by a `max_matches` cap and report when truncated
- [ ] Never write or mutate the host (read-only / replay-safe)

### [REQ-4] code.apply_patch — apply an exact edit

A tool named `code.apply_patch` applies a single exact `old`→`new` string edit to a
file (the small, reliable edit format a 2B model can produce). An empty `old` with a
non-existent path creates a new file.

#### Acceptance Criteria
- [ ] Reject a payload lacking a `path` string or an `old`/`new` pair
- [ ] Require `old` to occur exactly once; reject on zero or multiple matches
- [ ] Apply the replacement and report `{applied, path, bytesBefore, bytesAfter}`
- [ ] Support new-file creation when `old` is empty and the file is absent

### [REQ-7] shell.exec safety denylist (unattended-safe)

Because the harness runs unattended, `shell.exec` must deterministically REFUSE
dangerous commands at the gate: any network egress (no internet writes/exfiltration,
no remote pushes/installs) and any destructive or privilege-escalating host
operation. A refused command never executes.

#### Acceptance Criteria
- [ ] Reject network commands (curl/wget/ssh/scp, git push/pull/clone, pip/npm install, http(s) URLs)
- [ ] Reject destructive commands (rm -rf, del /, format, mkfs, dd, shutdown/reboot, recursive deletes)
- [ ] Reject privilege escalation (sudo/runas/doas)
- [ ] Allow ordinary build/test commands (e.g. `python -m pytest -q`); rejection states the match

### [REQ-5] shell.exec — run a bounded command

A tool named `shell.exec` runs a command with a timeout and captures stdout,
stderr, and the exit code — the primitive agents use to run builds and tests. It is
effectful and is recorded as a Decision before it runs.

#### Acceptance Criteria
- [ ] Reject a payload lacking a non-empty `command`
- [ ] Enforce a default and overridable timeout, reporting `timedOut` on expiry
- [ ] Return `{exitCode, stdout, stderr, timedOut}` with output bounded/truncated
- [ ] Honor an optional `cwd` working directory
