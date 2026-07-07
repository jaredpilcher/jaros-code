# Design — Interactive CLI Rebuild (Claude-Code-grade REPL)

## The felt-experience gap, mapped to code

```text
  TODAY (silent command-runner)                 TARGET (Claude-Code-grade)
  ─────────────────────────────                 ──────────────────────────
  jcode› fix the bug in foo.py                  jcode› fix the bug in foo.py
  [   … long silent wait …   ]                  ● reading foo.py               ← tool event, live
  [   nothing on screen …    ]                  I see it — the loop off-by-one  ← model TOKENS stream
  <entire answer dumps at once>                  on line 12 uses <= …           ← as generated
                                                ● editing foo.py … ✓            ← tool card live
                                                ● running tests … ✓ 12 passed   ← live
                                                Done — fixed the boundary.

  Root causes:
   1. harness/llamacpp_client.py:56  "stream": False   → model call is a blocking black box
   2. harness/cli.py repl()          out = handle(line); print(out)  → silent-run-then-dump
   3. harness/cli.py repl() banner   "slash-command REPL"  → command-first, not NL-first
```

## Architecture — four layers, built bottom-up

```text
  ┌─────────────────────────────────────────────────────────────────────┐
  │ L4  REPL RENDER  — NL-first prompt, streamed assistant text, tool    │
  │     cards (● action → ✓/✗), working/thinking indicator, statusline   │
  │     (harness/cli.py repl() + a new harness/repl_render.py)           │
  ├─────────────────────────────────────────────────────────────────────┤
  │ L3  STREAM BUS   — a single ordered event stream the REPL consumes:  │
  │     {assistant_token} | {tool_start} | {tool_result} | {thinking} |  │
  │     {ask} | {done}. Unifies model tokens (L1) + Decision events      │
  │     (the existing EXT-045 on_event hook) into ONE render loop.       │
  ├─────────────────────────────────────────────────────────────────────┤
  │ L2  HANDLE/ORCHESTRATE  — handle() yields events instead of building │
  │     a final string; the orchestrator emits tool_start/result around  │
  │     each Decision (reuses Runtime.on_event) and forwards model tokens│
  ├─────────────────────────────────────────────────────────────────────┤
  │ L1  STREAMING LLM CLIENT  — llamacpp_client streams SSE tokens       │
  │     ("stream": true, parse `data:` chunks, yield deltas); a          │
  │     non-streaming complete() stays for eval/headless callers         │
  └─────────────────────────────────────────────────────────────────────┘
```

### L1 — Streaming LLM client (the foundation, TASK-1)
`harness/llamacpp_client.py` gains a `stream_complete(req) -> Iterator[str]` that POSTs with
`"stream": true` and yields token deltas by parsing the server's SSE `data:` lines (llama.cpp /
OpenAI-compatible `chat.completions` streaming). The existing blocking `complete()` is KEPT unchanged
for eval/headless/deterministic callers (Tenet 3 — replay + measurement paths must stay byte-stable);
streaming is an ADDITIVE capability the interactive REPL opts into, never the default for measurement.
A hard wall-clock timeout still bounds the whole stream. Non-streaming replay is unaffected.

### L2 — Handle path yields events
The interactive solve path (orchestrator + `handle`) becomes a generator of stream-bus events rather
than a function that returns a final string. Model tokens forward from L1; tool activity reuses the
**existing EXT-045 `Runtime.on_event` seam** (already fires at the Decision record point) — so tool
cards need NO new decision path (Tenet 1 preserved: pure presentation over the hash-chain). Headless
one-shot (`_run_one_shot`) keeps returning its final string/JSON — streaming is REPL-only.

### L3 — Stream bus
One ordered event vocabulary the REPL renders: `assistant_token`, `tool_start`, `tool_result`,
`thinking`, `ask` (mid-task clarifying question — EXT-036 REQ-8 surfaced live), `done`. Interrupt
(EXT-055) injects a `cancel` that the bus honors cooperatively. This is the single seam that makes the
experience feel live and unified instead of block-dumped.

### L4 — REPL render + NL-first
`repl()` is rebuilt: a new banner/prompt that invites natural language ("Ask me to build, fix, or
explain… `/help` for commands"); plain input routes to the orchestrator by default, `/`-prefixed input
is the command escape hatch (the existing slash dispatch is retained, just demoted from the headline).
A small `harness/repl_render.py` renders the stream bus — streamed assistant text inline, tool cards
(`● reading foo.py` → `✓`/`✗ <result>`), a spinner/working indicator while the model thinks with no
token yet, and the EXT-045 statusline. Rendering degrades cleanly when stdout is not a TTY (piped /
headless → the existing non-streaming text/JSON path, unchanged).

## What is REUSED vs REPLACED (minimize churn, honor prior work)

```text
  REUSE (already good):                         REPLACE / ADD:
   - Runtime.on_event tool-event seam (EXT-045)   - llamacpp: add stream_complete() (L1)
   - slash-command dispatch (all EXT-04x cmds)    - handle path: yield events (L2)
   - interrupt/steer plumbing (EXT-055)           - stream bus vocabulary (L3, new)
   - ask-user plumbing (EXT-036 REQ-8)            - repl() render + NL-first banner (L4)
   - session/hash-chain transcript (EXT-044)      - harness/repl_render.py (new)
   - statusline (EXT-045 REQ-2)                   - felt-quality dimension in product_parity
```

## Guardrails (bind every task)
- **Tenet 1**: streaming is presentation only — tool cards come from the existing Decision/on_event
  seam; no model output performs a side effect directly.
- **Tenet 2**: still local Jetson Gemma at $0; streaming is the same endpoint, `stream:true`.
- **Tenet 3**: the non-streaming `complete()` + headless/eval/replay paths stay byte-stable; the
  streamed transcript is the same hash-chain truth; measurement is never run over the streaming path.
- **Non-TTY safety**: piped/headless/JSON output is unchanged (streaming is TTY-gated, mirroring the
  existing EXT-045 `should_stream` decision).
