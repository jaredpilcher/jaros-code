# EXT-007 — Continuous Harness Self-Improvement (the jarify way)

```text
   CONTINUOUS LAYER (always on)            SUPERVISOR LAYER (jarify loop, frequent)
   ───────────────────────────            ─────────────────────────────────────────
   scripts/run_forever.py        ──►  heartbeat.json / REPORT.md
     eval → report → heartbeat              │ reads metrics + frontier + census
     forever, fault-isolated                ▼
                                       pick next EXT-007 tasks.md TASK (frontier-first)
                                          │
                                          ▼  implement the jarify way (decompose, 2B-only)
                                       add/sharpen ONE agent|tool|eval  (+ prune dead weight)
                                          │
                                          ▼
                                       pytest tests/ green  →  commit locally  →  mark task
                                          │
                                          ▼
                                       push report iff due (every 30m, not 02:00–08:00)
                                          │
                                          ▼
                                       ScheduleWakeup (continuous) — repeat indefinitely
```

The two layers separate *measurement* (continuous, cheap to keep running) from
*improvement* (intelligent, the jarify loop). Improvements land between cycles and the
running runner picks them up automatically — so the metric trend reflects them without
restarts.

## Success is a rising trend on four axes

```text
   pass rate     ↑   (capability)
   Wilson CI     ↓   (measurement accuracy)
   #agents/#tools/#evals  ↑  (the swarm grows — toward thousands/tens of thousands)
   quality       ↑   (prune dead weight; what remains is sharper)
```

If any of these stalls, the loop is not doing its job. Growth without quality (adding
useless agents) is as much a failure as quality without growth. The census + report
make both visible to the owner every 30 minutes.
