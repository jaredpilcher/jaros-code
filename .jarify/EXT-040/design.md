# EXT-040 — Design

## Problem

Long jaros-code operations (a sub-agent's `pytest tests/`, a live `build_system` loop) go
opaque: a watcher cannot distinguish *working* from *wedged*, so it blind-waits 20–40 min.
Measured repeatedly this session (2026-07-04).

## Mechanism

```
long op ──beat(activity, phase)──►  .jaros-data/artifacts/heartbeat/
                                        ├── <run_id>.jsonl   (append-only trail)
                                        └── current.json     (latest state, overwritten)
                                                 ▲
   /status ── status()/format_status() ─────────┘   → "jcode: <activity> - <phase>
   watcher ── read current.json ────────────────┘       (elapsed Ns, last beat Ns ago) [STALLED]"
```

- **`beat(activity, detail, run_id, started_at)`** — append + overwrite `current.json`.
  `started_at` anchors elapsed across many beats. Never raises.
- **`status(stall_after_s=300)`** — read `current.json`; compute `elapsed_s`,
  `since_last_beat_s`, `stalled` (last beat older than 5 min = the owner's heartbeat), honest
  `idle` when nothing is current.
- **`heartbeat(activity)` context** — START on entry, `.beat(phase)` for transitions, END on
  clean exit / ERROR (re-raised) on exception; a daemon keepalive re-beats every ~30s so a
  healthy long step keeps a fresh beat (absence ⇒ real stall).
- **`run_with_heartbeat(cmd, label, interval)`** — the anti-wedge runner: spawn the child,
  block in the foreground until it exits (no backgrounding / no lost monitor), pulse a
  heartbeat every `interval`s, record exit code + tail. A watcher reads `current.json` to see
  "running Ns" vs a stale beat. This is the fix for the recurring pytest wedge: run the suite
  through it and the run is always observable.

## Two-plane / honesty

Deterministic execution-plane code — no model calls. Observability must never break the thing
it observes, so every public function swallows its own errors and returns an honest empty/
best-effort result; `idle` and `stalled` are never fabricated as "running/ok".

## Follow-up (REQ-3)

Emit phase beats from `build_system` (PLAN/VALIDATE/ASSEMBLE/SCAN/ACCEPTANCE/REPAIR/DONE) and
`run_creation_suite` (per task) so autonomous builds show their phase, not `idle`.
