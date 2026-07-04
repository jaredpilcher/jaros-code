# Intent

This spec exists to make jaros-code's own activity observable, so a long operation is never an
opaque wedge. The owner named the recurring failure mode directly: a sub-agent's test run or a
live build loop goes silent for tens of minutes with no cheap way to tell *working* from
*wedged*, forcing a blind wait, then a nudge, then sometimes a kill-and-take-over. This spec adds
a 5-minute heartbeat: a timestamped activity trail (an append-only per-run log plus an overwritten
`current.json`) that any reader can turn into a status — what is running, since when, elapsed,
seconds since the last beat, and a `stalled` flag when the last beat is older than five minutes. A
context-managed heartbeat beats start/phase/end with a daemon keepalive so a healthy long step
keeps showing life, a foreground command runner wraps any long command (like `pytest tests/`) with
periodic beats so it is never a 0-byte blind wait, and `build_system` emits live phase beats so
`/status` shows exactly where a build is (or where it stuck).

It converges toward the Prime Directive by serving the Claude-Code-like transparent experience
(Tenet 5) and the supervised convergence loop that must watch the system closely and correct it —
observability is what lets the supervisor tell a working overnight grind from a wedged one without
guessing. It stays within the tenets above UX: purely deterministic bookkeeping, no model calls,
and it never raises on its own logging, so the instrument can never itself break a run.
