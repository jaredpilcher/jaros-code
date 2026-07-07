# Implementation Tasks

### [TASK-1] Streaming LLM client (the foundation — kill the silent black box)

Add token streaming to `harness/llamacpp_client.py` so the model's output can appear as it generates,
without disturbing the blocking `complete()` path that eval/headless/replay depend on. This is the
load-bearing first slice; REQ-2/3 (event bus, REPL render) build on it, so it lands first and alone.

#### Steps
1. In `harness/llamacpp_client.py`, add `stream_complete(self, req: LlmRequest) -> "Iterator[str]"`
   inside `# #EXT-057-REQ-1` markers. Build its payload from the existing `build_payload(req)` but
   with `"stream": True` (do NOT mutate the shared builder — copy the dict and flip the flag).
2. POST to the same endpoint with `stream=True` handling: open the response and iterate lines; for each
   `data: <json>` line parse the JSON and extract the token delta (OpenAI-compatible
   `choices[0].delta.content`, or llama.cpp's field); yield each non-empty delta. Stop on the `[DONE]`
   sentinel. Skip keep-alive blank lines and any line that fails to parse (never crash on a bad chunk).
3. Bound the whole stream with a hard wall-clock deadline (reuse/mirror the `_urlopen_hard` timeout
   discipline): if the deadline passes or the connection errors mid-stream, stop cleanly (the generator
   returns after yielding what it has) — never hang. Use a background-thread or deadline-check pattern
   consistent with the existing client.
4. Leave `complete()`, `build_payload()` (`"stream": False`), `parse_response()`, and `health()`
   BYTE-UNCHANGED. Streaming is purely additive.
5. Add `tests/test_ext057_streaming_client.py`: (a) a pure-parser test that feeds a synthetic SSE byte
   sequence (a few `data:` chunks + `[DONE]`, including one malformed line and one keep-alive blank)
   and asserts the yielded tokens reconstruct the expected full string; (b) a test asserting the
   non-streaming `build_payload` still emits `"stream": false` (byte-stable); (c) a timeout/early-close
   test that the generator terminates cleanly without hanging (use a fake/stubbed response). NO network
   in tests — stub the HTTP layer.
6. Run ONLY the focused file via `timeout 240 python -m pytest tests/test_ext057_streaming_client.py -q`,
   then `python -c "import harness.llamacpp_client"` for an import-regression check. Do NOT run the
   full suite. Update `index.json` (jarify-manage-links) for the new `# #EXT-057-REQ-1` range.

#### Implements
- [REQ-1] Streaming LLM client

---
**SHARED INTERFACE CONTRACT (all EXT-057 tasks build to these exact signatures so parallel builds
integrate):**
- `llamacpp_client.LlamacppClient.stream_complete(req) -> Iterator[str]` (TASK-1) — yields token deltas.
- Stream-bus event = a `dict` with `"type"` ∈ `{"assistant_token","tool_start","tool_result","thinking","ask","done","cancel"}` and payload keys: token events carry `"text"`; `tool_start`/`tool_result` carry `"name"` + (`tool_result`) `"ok"`+`"summary"`; `ask` carries `"prompt"`; `done` carries `"final"` (str). Defined in `harness/stream_bus.py` (TASK-2).
- `coding_loop.solve_streaming(request: str, *, llm, root=None, ...) -> Iterator[dict]` (TASK-2) — the interactive solve path as a generator of stream-bus events; forwards `stream_complete` tokens as `assistant_token`, emits `tool_start`/`tool_result` from the existing `Runtime.on_event` seam, ends with `done`.
- `repl_render.render_stream(events: Iterable[dict], out=stdout) -> str` (TASK-3) — consumes bus events, renders live, returns the final assembled text.

---

### [TASK-2] Event-yielding solve path + stream bus (REQ-2)

Make the interactive solve path EMIT the live stream-bus event stream. Owns `harness/coding_loop.py`
(add `solve_streaming`) + NEW `harness/stream_bus.py` (the event vocabulary + a small helper). Does NOT
touch `harness/cli.py` or `harness/llamacpp_client.py` (other tasks own those).

#### Steps
1. Create `harness/stream_bus.py` (`# #EXT-057-REQ-2` markers): define the event constructors/vocabulary
   per the SHARED CONTRACT above (`assistant_token`, `tool_start`, `tool_result`, `thinking`, `ask`,
   `done`, `cancel`) as small dict factories + a validator; pure data, no I/O.
2. In `harness/coding_loop.py`, add `solve_streaming(request, *, llm, root=None, on_cancel=None, ...)
   -> Iterator[dict]` (`# #EXT-057-REQ-2` markers) that runs the interactive orchestrator/solve and
   YIELDS stream-bus events: forward model tokens from `llm.stream_complete(...)` as `assistant_token`
   events; emit `tool_start`/`tool_result` from the EXISTING `Runtime.on_event` seam (wire on_event to
   push into the generator — NOT a new decision path, Tenet 1); honor a cooperative `cancel`
   (EXT-055); end with a `done` event carrying the final text.
3. Keep the existing non-streaming solve/`complete()` callers unchanged (eval/headless/replay). Guard
   `stream_complete` absence gracefully (fall back to a single `assistant_token` from `complete()` if
   streaming unavailable) so this integrates even before TASK-1 lands.
4. Tests `tests/test_ext057_stream_bus.py`: event-factory shapes match the contract; `solve_streaming`
   with a STUBBED llm (fake `stream_complete` yielding known tokens) + a stubbed Runtime emits the
   expected ordered event sequence ending in `done`; cancel stops it. NO network.
5. Run ONLY those focused files; import-regression `python -c "import harness.coding_loop, harness.stream_bus"`. Update `index.json` for REQ-2.

#### Implements
- [REQ-2] Event-yielding solve path + stream bus

### [TASK-3] Natural-language-first REPL render (REQ-3)

Rebuild the REPL to be NL-first and render the stream bus live. Owns `harness/cli.py` (`repl()` + banner)
+ NEW `harness/repl_render.py`. Does NOT touch `coding_loop.py`/`llamacpp_client.py`/`stream_bus.py`
(build `repl_render` against the SHARED CONTRACT; stub `solve_streaming`/bus events in tests).

#### Steps
1. Create `harness/repl_render.py` (`# #EXT-057-REQ-3` markers): `render_stream(events, out) -> str`
   that renders bus events live — `assistant_token` inline (streamed), `tool_start` as `● <name>` and
   `tool_result` as `  ✓`/`  ✗ <summary>`, `thinking` as a spinner/working indicator, `ask` as a
   prompt — and returns the assembled final text. Pure-ish (takes an `out` writer); testable against a
   synthetic event list.
2. Rebuild `repl()` in `harness/cli.py`: new banner/prompt inviting natural language ("Ask me to build,
   fix, or explain… `/help` for commands"); plain input → `coding_loop.solve_streaming(...)` rendered
   via `render_stream`; `/`-prefixed input → the EXISTING slash dispatch (retain all EXT-04x commands,
   `/quit`,`/clear`, resume, statusline, permission prompts, interrupt). TTY-gate the streaming render
   via the existing `should_stream`; non-TTY/piped falls back to the CURRENT behavior byte-stable.
3. Tests `tests/test_ext057_repl_render.py`: `render_stream` over a synthetic event list writes the
   expected surface (tool cards + streamed text) and returns the right final text; a non-TTY test that
   the fallback path is unchanged. Stub `solve_streaming` (do not require it to exist for the render test).
4. Run ONLY focused files; import-regression `python -c "import harness.cli, harness.repl_render"`. Update `index.json` for REQ-3.

#### Implements
- [REQ-3] Natural-language-first REPL render

### [TASK-4] Felt-quality dimension in the parity instrument (REQ-4)

Fix the Tenet-3 gap where the checklist reported ~84% while the UX was awful. Owns
`harness/product_parity.py` only. Fully independent of the other tasks.

#### Steps
1. In `harness/product_parity.py` (`# #EXT-057-REQ-4` markers), add an interactivity/felt-quality
   scoring dimension: sub-scores for `streams_model_output`, `live_tool_feedback`,
   `natural_language_first`, `working_indicator`, `interrupt_surfaced` — each scored
   works/partial/missing against the CURRENT build (honestly: pre-EXT-057 most are missing/partial).
2. Fold the dimension into the aggregate so the instrument can no longer report high while the felt
   experience is poor; document each sub-score's meaning + how it's measured.
3. Tests `tests/test_ext057_felt_quality.py`: the dimension exists, scores the current state honestly,
   and the aggregate reflects it. Run ONLY that file; import-regression. Update `index.json` for REQ-4.

#### Implements
- [REQ-4] Felt-quality dimension in the parity instrument
