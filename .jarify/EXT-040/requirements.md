---
id: EXT-040
title: Observability heartbeat — see what jaros-code is doing, for how long, and whether it is stalled
status: partial
priority: high
implementation:
  - harness/heartbeat.py
  - harness/run_with_heartbeat.py
  - harness/cli.py
---

# EXT-040 — Observability heartbeat

**Owner directive (2026-07-04):** "maybe jaros code can have an observability layer so you
can see what it has been doing and what it's doing and for how long ... we've been stuck a
lot, with no way for you to address the stuck nature. I think we need jaros code to have a
5 minute heartbeat and you need to keep an eye on it."

**Motivation (measured, this session):** the recurring "stuck" failure mode is a long
operation (a sub-agent's `pytest tests/`, a live build loop) going silent for 20–40 minutes
with no cheap way to tell *working* from *wedged* — forcing a blind wait, then a nudge, then
sometimes a kill-and-take-over. This spec makes activity observable and stall detectable.

## [REQ-1] Activity heartbeat + `/status` — what is running, since when, stalled?  (covered)

`harness/heartbeat.py` records a timestamped ACTIVITY TRAIL to
`.jaros-data/artifacts/heartbeat/` (append-only per-run log + an overwritten `current.json`).
A reader gets `status()` → `{activity, detail, started_at, last_beat, elapsed_s,
since_last_beat_s, stalled, idle}` where **`stalled` = last beat older than 5 minutes**
(`DEFAULT_STALL_S = 300`, the owner's "5 minute heartbeat"). A `heartbeat(activity)` context
manager beats START / phase / END (or ERROR on exception, re-raised) with a daemon keepalive
that re-beats every ~30s so a healthy long step keeps showing life (its absence ⇒ a real
stall). `/status` (`harness/cli.py::cmd_status`) prepends a one-line live activity readout
(`jcode: <activity> - <detail> (elapsed Ns, last beat Ns ago, pid X) [!! STALLED]`).

Acceptance criteria:
- [x] `beat()` writes `current.json` + appends the per-run log; never raises.
- [x] `status()` reports elapsed + since-last-beat + a `stalled` flag past the 5-min threshold; honest `idle` when nothing is running.
- [x] `heartbeat()` context beats START/END and ERROR-on-exception (re-raised); daemon keepalive.
- [x] `/status` shows the live activity line above the existing model/census view.
- [x] Deterministic (no model calls); never raises on its own bookkeeping.

## [REQ-2] Heartbeat command runner — a long command is never an opaque wedge  (covered)

`harness/run_with_heartbeat.py::run_with_heartbeat(cmd, label, interval)` runs a long command
(e.g. `pytest tests/ -q`) to completion in the FOREGROUND (always blocks until the child
exits — no backgrounding, no monitor to get lost), while a daemon thread updates the
heartbeat every `interval` seconds with elapsed time; on completion it records the exit code +
an output tail. CLI: `python -m harness.run_with_heartbeat --label L -- <cmd...>` (drop-in;
returns the child's exit code). This is the anti-wedge path: while it runs, a watcher reads
`current.json` and sees "running Ns" vs a stalled/absent beat — never a 0-byte blind wait.

Acceptance criteria:
- [x] Runs the command to completion, blocking; returns `{ok, exit_code, elapsed_s, timed_out, tail}`.
- [x] Heartbeats every `interval`s while running; records a final `done exit=N (Ns)` beat.
- [x] Honest `ok=False` (never raises) on spawn failure / non-zero exit / timeout.
- [x] Usable as a CLI wrapper that any agent (or the watcher) runs instead of raw pytest.

## [REQ-3] build_system phase beats — /status shows the live build phase  (covered)

`build_system` (`harness/system_builder.py`) emits additive `harness.heartbeat` phase beats
(START / PLAN / ASSEMBLE / SCAN / ACCEPTANCE / REPAIR / DONE|NOT-DONE) anchored to one
per-build `run_id` + `started_at`, so `/status` shows the live phase (e.g.
`build_system - ACCEPTANCE`) instead of `idle`, and a wedged build reveals where it stuck.

Acceptance criteria:
- [x] `build_system` beats each phase; a run leaves a non-idle heartbeat trail (tested).
- [x] Additive + never-raises: no control-flow / return-value change (the beats can't break a build).
- [x] `run_creation_suite` per-task beats — DEFERRED (a follow-up; `build_system` phase beats already give live visibility for every build the suite runs).
