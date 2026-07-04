# EXT-040 — Tasks

## [TASK-1] Activity heartbeat + `/status` (REQ-1)

Build `harness/heartbeat.py` (`beat`, `status`, `format_status`, `heartbeat` context manager
with daemon keepalive; `.jaros-data/artifacts/heartbeat/`; 5-min stall threshold). Wire the
live activity line into `harness/cli.py::cmd_status`. Tests in
`tests/test_ext040_heartbeat.py` (beat/status/idle/stall/context/error/never-raises).

Implements — [REQ-1]

## [TASK-2] Heartbeat command runner (REQ-2)

Build `harness/run_with_heartbeat.py` (`run_with_heartbeat` + `python -m` CLI) — run a long
command foreground with a live heartbeat + final exit-code beat; the anti-wedge path for
`pytest`. Tests: runs-and-records, non-zero exit, spawn-failure-is-honest.

Implements — [REQ-2]

## [TASK-3] build_system phase beats (REQ-3) — NOT STARTED (named follow-up)

Emit `heartbeat()` phase beats from `build_system` / `run_creation_suite`.
