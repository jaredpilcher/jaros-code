---
id: EXT-057
title: Interactive CLI Rebuild (Claude-Code-grade REPL)
status: covered
priority: high
implementation:
  - file: harness/llamacpp_client.py
    ranges:
      - - 125
        - 223
  - file: harness/repl_render.py
    ranges:
      - - 28
        - 145
  - file: harness/cli.py
    ranges:
      - - 2414
        - 2454
      - - 2495
        - 2499
      - - 2521
        - 2533
  - file: harness/product_parity.py
    ranges:
      - - 456
        - 635
      - - 725
        - 743
---

### [REQ-1] Streaming LLM client

The llama.cpp client must be able to STREAM token deltas so the model's output can appear as it is
generated, killing the silent-black-box wait that is the single biggest felt gap. Add a streaming
entry point to `harness/llamacpp_client.py` that POSTs with `"stream": true` and yields token deltas
parsed from the server's SSE `data:` chunks. The existing blocking `complete()` MUST stay unchanged
and remain the path used by eval/headless/replay callers (Tenet 3 — measurement and byte-identical
replay must not change). Streaming is an additive capability, bounded by the same hard wall-clock
timeout, that the interactive REPL opts into.

#### Acceptance Criteria
- [ ] Add `stream_complete(req) -> Iterator[str]` (or equivalent generator) to `LlamacppClient` that
      requests `"stream": true` and yields token-delta strings as they arrive.
- [ ] Robustly parse the SSE stream: handle `data:` prefixed lines, the `[DONE]` sentinel, keep-alive
      blanks, and partial/split chunks; ignore malformed lines rather than crashing.
- [ ] A hard wall-clock timeout bounds the whole stream (mirrors `complete()`'s `_urlopen_hard`); on
      timeout or connection error it terminates cleanly (yields what it has, then stops) — never hangs.
- [ ] The existing blocking `complete()` and its `build_payload` (`"stream": false`) path are
      BYTE-UNCHANGED for eval/headless/replay callers; a focused test proves non-streaming behavior is
      identical to before.
- [ ] Offline unit test: feed a synthetic SSE byte stream to the parser and assert the yielded token
      sequence reconstructs the full message (no network needed in the test).

### [REQ-2] Event-yielding solve path + stream bus

The interactive solve path must EMIT a live ordered event stream instead of running silently and
returning one final string. Reuse the existing EXT-045 `Runtime.on_event` seam for tool activity (no
new side-effect path — Tenet 1) and forward REQ-1 model tokens, unified into one stream-bus vocabulary
the REPL renders: `assistant_token`, `tool_start`, `tool_result`, `thinking`, `ask`, `done`, `cancel`.

#### Acceptance Criteria
- [ ] Define the stream-bus event vocabulary and a producer that yields it from the interactive
      orchestrator/handle path (model tokens from REQ-1; tool_start/tool_result from the existing
      `Runtime.on_event` Decision seam — NOT a new decision path).
- [ ] The headless one-shot path (`_run_one_shot`) and slash-command handlers keep their current
      return-string / JSON behavior unchanged (streaming is REPL-interactive only).
- [ ] Interrupt-and-steer (EXT-055) injects a `cancel` the bus honors cooperatively; mid-task
      clarifying questions (EXT-036 REQ-8) surface as an `ask` event.
- [ ] Tenet-1 check: no event producer performs a host side effect directly — tool effects still flow
      through the Jaros gate; the bus is pure presentation over the hash-chain.

### [REQ-3] Natural-language-first REPL render

Rebuild `repl()` so talking to it is the default and slash-commands are the escape hatch, and so the
stream bus renders live (streamed assistant text, tool cards, a working indicator) instead of a silent
run then a block dump.

#### Acceptance Criteria
- [ ] New banner/prompt that invites natural language (e.g. "Ask me to build, fix, or explain… /help
      for commands"); plain input routes to the orchestrator by default, `/`-prefixed input dispatches
      the existing slash commands (all EXT-04x commands retained).
- [ ] A `harness/repl_render.py` renders the stream bus: assistant tokens inline as they stream, tool
      cards (`● <action>` → `✓`/`✗ <result>`), and a spinner/working indicator while the model is
      thinking with no token yet.
- [ ] Non-TTY safety: piped/headless/JSON output is UNCHANGED (streaming is TTY-gated via the existing
      `should_stream` decision); a test proves the non-TTY path is byte-stable.
- [ ] `/quit`, `/clear`, session resume, statusline, permission prompts, interrupt all still work.

### [REQ-4] Felt-quality dimension in the parity instrument

The Product-Parity Checklist measured feature presence and reported ~84% while the lived UX was poor —
a Tenet-3 gap. Add a felt-quality/interactivity dimension so the instrument can no longer report high
while the experience is awful.

#### Acceptance Criteria
- [ ] Add an interactivity/felt-quality scoring dimension to `harness/product_parity.py` (e.g.
      streams-model-output, live-tool-feedback, natural-language-first, working-indicator,
      interrupt-surfaced) scored honestly against the current build.
- [ ] The aggregate reflects felt quality, not just feature checkboxes; document what each sub-score
      means and how it is measured.
