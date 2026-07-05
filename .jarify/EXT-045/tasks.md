# Implementation Tasks

### [TASK-1] Streaming tool-event narration + statusline, wired into the CLI

Add an opt-in `on_event` hook to `harness.coding_loop.Runtime` at the exact seam where each
accepted Decision is already recorded to the hash-chain; a new `harness/tool_stream.py` module
that formats those events into concise call/result/error lines and decides whether streaming
should be active; a new `harness/statusline.py` module rendering `model · class · $0 · latency`;
and wire both into `harness/cli.py` (`JcodeCli`, `repl()`, `_run_one_shot()`, `main()`,
`/statusline`, `/help`) without changing the orchestrator or any agent.

#### Steps
1. In `harness/coding_loop.py`, add an optional `on_event: callable | None = None` parameter to
   `Runtime.__init__`, stored as `self._on_event`. Add `Runtime._emit(event: dict)`: a no-op when
   `self._on_event` is `None`, else calls it wrapped in `try/except` (never raises). In
   `Runtime.apply`, emit a `{"phase": "call", "type", "payload", "source"}` event right after the
   root-jail stamping (before `validate_decision`), a `{"phase": "error", "type", "reason"}` event
   on a gate rejection or an executor refusal, and a `{"phase": "result", "type", "output"}` event
   right before returning `outcome.output` on success.
2. Create `harness/tool_stream.py`: `format_call(type_, payload)` (a short human arg pulled from
   known payload keys — `path`/`pattern`/`command`/`message`/`old`/`symbol`/`action` — else the
   first scalar value, else empty), `format_result(type_, output)` (recognizes known tool-output
   shapes — `matches`/`entries`/`symbols`/`content`/`exitCode`/`committed`/`bytesAfter` — else a
   generic `"done"`), `format_error(type_, reason)`, `render_event(event)` (dispatches on
   `event["phase"]`, returns `None` for anything malformed), `stream_events(events)` (maps
   `render_event` over a sequence, skipping unrenderable entries, never raising),
   `should_stream(output_format, is_tty, env=None)` (`False` under `"json"` unconditionally;
   `JCODE_STREAM_EVENTS` env override either way; else defaults to `is_tty`), and
   `make_printer(stream=None)` (returns an `on_event` callback that prints `render_event(event)`
   to `stream` or `sys.stdout`, swallowing any exception).
3. Create `harness/statusline.py`: `statusline(model, problem_class=None, latency_s=None,
   cost="$0")` rendering `"{model} · {problem_class} · {cost} · {latency}"`, where latency renders
   as `"Xs"` for a non-negative number and `"-"` otherwise; never raises (degrades to a minimal
   honest fallback on bad input).
4. In `harness/cli.py`: add `stream: bool = False` to `JcodeCli.__init__`, constructing
   `Runtime(on_event=make_printer())` only when `stream` is truthy (else `Runtime(on_event=None)`,
   byte-identical to before this spec); mirror the same in `_git_tool`'s root-anchored `Runtime`.
   Add `self._last_action`/`self._last_latency_s`/`self._show_statusline` state, and a
   `statusline()` method delegating to `harness.statusline.statusline`. Add `cmd_statusline(arg)`
   (`"on"`/`"off"`/toggle, always returns the current statusline text). In `handle()`, time the
   whole turn and record the routed action (slash-command name, multistep-agent flag, fast-path
   intent action, or orchestrator action) into `self._last_action`/`self._last_latency_s` at the
   end, wrapped so a failure never changes `handle()`'s return value. In `repl()`, compute
   `should_stream("text", _stdout_is_tty())` internally (keeping `repl(session_id=...)`'s call
   SHAPE unchanged — one keyword argument, per the EXT-044 backward-compat constraint) and print
   `cli.statusline()` above every prompt when `cli._show_statusline` is set. Add a 6th, defaulted
   `stream: bool = False` parameter to `_run_one_shot`, threaded into `JcodeCli`. In `main()`,
   compute `do_stream = should_stream(output_format, _stdout_is_tty())` and pass it to
   `_run_one_shot`. Add `_stdout_is_tty()` (mirrors the existing `_stdin_is_tty()`). Update the
   `/help` docstring with `/statusline` and a note on streaming.
5. Write `tests/test_ext045_terminal_ux.py` (deterministic, no live gemma — synthetic events for
   `harness.tool_stream`'s pure formatting/gating functions, a real deterministic `fs.read`
   Decision through a fresh `Runtime(on_event=...)` to prove the hook fires call-then-result in
   the right shape and order, a real `JcodeCli(stream=True)` dispatch to prove end-to-end
   narration, and a stubbed `JcodeCli` through `main()` to prove `--output-format json` forces
   streaming off even on a "live terminal"). Update the two existing stub `JcodeCli` classes in
   `tests/test_ext043_headless.py` and `tests/test_ext044_sessions.py` to accept the new
   `stream=False` keyword `_run_one_shot`/`main()` now always pass (previously-untyped stubs would
   otherwise raise `TypeError` on the new keyword) — a mechanical backward-compat fix, not a
   weakened assertion.
6. Update `harness/product_parity.py` row #24 (`id=24`) honestly: flip `state` to `"works"` (all
   of REQ-1/REQ-2/REQ-3 delivered and test-covered), with `current_state` naming exactly what
   remains deferred (a live in-flight spinner, `/export`, tab-completion, themes) and `next_lever`
   naming only that residual gap. Mirror the same honest update into `docs/GAP-MAP.md` row #24's
   `State`/`Current honest state`/`Next lever` columns, and update
   `tests/test_ext041_product_parity.py`'s honesty-pin (`works == [...]`) and the
   `n_works`/aggregate-bound assertions to match — the same mirroring EXT-042/EXT-043/EXT-044 each
   did on landing.

#### Implements
- [REQ-1] Streaming tool events
- [REQ-2] Statusline
- [REQ-3] Honest Product-Parity Checklist update
