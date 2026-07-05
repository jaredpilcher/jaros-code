# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #23 names a gap Claude Code closes but jcode does
not: a **background runs surface**. In Claude Code you can kick off a long build/task, keep
working, and later check on it, read its output, watch it live, or cancel it. jaros-code already
has the internal machinery a background job needs — the EXT-043 headless one-shot path
(`_run_one_shot`), a hash-chain-logged gated `Runtime`, and observability primitives
(`harness/heartbeat.py`, `harness/run_with_heartbeat.py`, `scripts/run_forever.py`) — but none of
it is exposed as something a USER can reach for. Today submitting a long request means blocking
the terminal until it finishes; there is no `jcode --bg`, no job id, no way to check status, read
logs, attach, or stop.

This spec closes that gap the same way EXT-046/EXT-050 closed their respective gaps: a small,
deterministic, execution-plane module (`harness/bg_jobs.py`) that submits a request to run
DETACHED as a real OS process, persists a durable job record (id, request, status, pid,
started/ended, log path) under `.jaros-data/`, and gives the user `jcode --bg`, `jcode jobs`,
`jcode logs <id>`, `jcode attach <id>`, `jcode stop <id>` (plus `/jobs`, `/logs <id>`, `/stop <id>`
in the REPL) to manage it. No new reasoning mechanism and no new process model are invented: the
backgrounded job's actual work is the EXACT SAME EXT-043 `_run_one_shot` call a foreground
`jcode "<request>"` already makes, just run out-of-process; process spawn/kill mirrors the
established tree-kill pattern (`harness/secure_exec.py`/`.jaros-data/tools/shell_exec_tool.py`)
rather than inventing a new one.

This converges PRIME-001 on two tenets at once. **Tenet 1 (two-plane discipline):** submission,
listing, log-reading, and stop are pure deterministic bookkeeping — no model judgement anywhere in
`harness/bg_jobs.py`. The backgrounded job's own work still passes through the SAME gated
`JcodeCli`/`Runtime` pipeline as a foreground run, so any host-project write it performs still
goes through a real `code.write_file` Decision — backgrounding a request changes WHERE it runs,
never what safety gates it passes through. **Tenet 5 (Claude-Code-like UX):** this is direct
product-surface parity — "kick off a long build, keep working" is precisely what row #23 asks for.
Per Tenet 3 (honesty), the Product-Parity Checklist (EXT-041) is only flipped for row #23 once
whatever subset of `--bg`/`jobs`/`logs`/`attach`/`stop` is genuinely built and test-covered is
named exactly — if only part lands, the row stays honestly `partial` rather than inflated.
