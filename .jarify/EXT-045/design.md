# EXT-045 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #24 names Claude Code's live terminal feel: tool
calls stream progress as they happen, and a statusline shows the model/cost/latency at a glance.
Today, `harness/cli.py`'s REPL prints only the FINAL return value of `JcodeCli.handle()` — a
multi-step `/agent` or `/fix` run is silent for its whole duration, then dumps everything at once.
There is no statusline at all.

The fix must not re-plumb the orchestrator or invent a second event-logging mechanism: every
accepted `Decision` already passes through ONE seam — `harness.coding_loop.Runtime.apply` — which
validates it at the gate, executes it, and durably records it to the Jaros hash-chain
(`jaros.state.record_decision`) before returning its output. That IS the tool-event stream this
spec narrates from.

## Mechanism

```
  TOOL CALL SEAM (harness/coding_loop.py — Runtime.apply, UNCHANGED control flow)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ Runtime(data_dir, root=None, on_event=None)          <- NEW optional 3rd param    │
  │   self._on_event = on_event   (None -> complete no-op, byte-identical to before)   │
  │                                                                                     │
  │ apply(decision):                                                                   │
  │   [root-jail stamping -- EXT-037, unchanged]                                       │
  │   _emit({"phase": "call", "type", "payload", "source"})        <- NEW              │
  │   gated = validate_decision(decision)                                              │
  │   if not gated.ok: _emit({"phase": "error", ...}); raise         <- NEW            │
  │   outcome = executor.apply(..., on_accept=record_decision, ...)  <- UNCHANGED       │
  │                                                                    (hash-chain write)│
  │   if not outcome.applied: _emit({"phase": "error", ...}); raise   <- NEW            │
  │   _emit({"phase": "result", "type", "output": outcome.output})    <- NEW            │
  │   return outcome.output                                                             │
  │                                                                                       │
  │ _emit(event): calls self._on_event(event) in a try/except -- NEVER raises,          │
  │   NEVER affects apply()'s own control flow even if the hook itself is broken        │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ event dicts: {phase, type, payload/output/reason}
                                          ▼
  PRESENTATION LAYER (harness/tool_stream.py — NEW module, pure formatting, no model calls)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ format_call(type, payload)   -> "→ fs.read(foo.py)"                                │
  │ format_result(type, output)  -> "✓ 42 line(s)" / "✓ 3 match(es)" / "✓ exit=0" / ... │
  │ format_error(type, reason)   -> "✗ fs.read failed: <reason>"                        │
  │ render_event(event)          -> one of the above, or None for anything malformed    │
  │ stream_events(events)        -> render_event mapped over a SEQUENCE, order preserved│
  │ should_stream(fmt, is_tty, env) -> False under "json"; JCODE_STREAM_EVENTS overrides│
  │                                    either way; else defaults to is_tty              │
  │ make_printer(stream=stdout)  -> an on_event callback that prints render_event(ev)   │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ wired as Runtime(on_event=make_printer())
                                          ▼
  CLI WIRING (harness/cli.py)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ JcodeCli(session_id=None, stream=False)   <- NEW optional param, default OFF        │
  │   self.stream = bool(stream); self.rt = Runtime(on_event=make_printer() if stream)  │
  │   _git_tool() builds its own root-anchored Runtime the same way                     │
  │                                                                                       │
  │ repl(session_id=None)   <- SIGNATURE UNCHANGED (EXT-044 backward-compat constraint)  │
  │   internally: stream = should_stream("text", _stdout_is_tty())                      │
  │   prints cli.statusline() above every prompt when cli._show_statusline is True       │
  │                                                                                       │
  │ _run_one_shot(..., name_to_set=None, stream=False)   <- NEW defaulted 6th param      │
  │ main(): do_stream = should_stream(output_format, _stdout_is_tty()); threaded through │
  └───────────────────────────────────────────────────────────────────────────────────┘

  STATUSLINE (harness/statusline.py — NEW module, pure formatting, no model calls)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ statusline(model, problem_class, latency_s, cost="$0") -> "model · class · $0 · Xs" │
  │                                                                                       │
  │ JcodeCli.statusline()  -> statusline(self.model, self._last_action,                 │
  │                                      self._last_latency_s)                          │
  │ JcodeCli.handle(): times the whole turn (_t0/time.time()), records the routed        │
  │   action ("chat" / slash-command name / fast-path action / orchestrator action)      │
  │   into self._last_action + self._last_latency_s at the end -- best-effort, wrapped   │
  │   in try/except so a clock failure never changes `out`                              │
  │ JcodeCli.cmd_statusline("on"/"off")  -> toggles self._show_statusline, always        │
  │   returns the CURRENT statusline text either way                                    │
  └───────────────────────────────────────────────────────────────────────────────────┘
```

- **No second event-logging mechanism.** `Runtime.apply`'s existing gate → executor →
  `record_decision` control flow is UNCHANGED; `on_event` is a side-channel notification fired at
  the same three points (call, error, result) that already exist in that function. Nothing here
  changes what gets written to the hash-chain.
- **Streaming is opt-in and layered defensively.** `should_stream` is `False` under
  `--output-format json` UNCONDITIONALLY (machine output must stay one clean parseable object,
  EXT-043); otherwise `JCODE_STREAM_EVENTS` (`0`/`1`) overrides either way; otherwise it defaults to
  whether stdout is a TTY. `make_printer`'s callback and `Runtime._emit` both swallow their own
  exceptions — a broken/malformed event, or even a broken output stream, degrades to "no line
  printed", never a crash of the tool call being narrated.
- **`repl()`'s call SHAPE stays unchanged** (one keyword argument, `session_id`), mirroring the
  EXT-044 backward-compat constraint some tests stub `repl()` against — streaming is decided
  INTERNALLY inside `repl()` rather than threaded in as a new parameter.
- **`statusline()` is pure presentation over state the CLI already maintains** (the active model
  label from EXT-014, plus two new small fields — `_last_action`/`_last_latency_s` — updated once
  per `handle()` call). No new measurement mechanism, no polling.

## Two-plane / honesty

Every function this spec adds (`Runtime._emit`, everything in `harness/tool_stream.py` and
`harness/statusline.py`, `JcodeCli.statusline`/`cmd_statusline`, the `_last_action`/
`_last_latency_s` bookkeeping in `handle()`) is pure deterministic execution-plane code (Tenet 1):
string formatting, a linear event dispatch, and a wall-clock delta. None of it calls the LLM or
changes what the orchestrator/agents decide — it only narrates decisions that were already made
and applied. Per Tenet 3, `harness/product_parity.py` row #24 is flipped to `"works"` only because
streaming + statusline + `/help` are genuinely delivered and test-covered; the row's
`current_state` honestly names what remains deferred (a live in-flight spinner for a single long
tool call, `/export`, tab-completion, themes) rather than inflating the whole feature bundle.

## Backward compatibility (no regression)

- `Runtime(data_dir, root=None)` — the pre-EXT-045 call shape — behaves byte-identically: the new
  `on_event` parameter defaults to `None`, which is a complete no-op (`_emit` returns immediately).
- `JcodeCli(session_id=None)` — the pre-EXT-045 call shape — behaves byte-identically: `stream`
  defaults to `False`, so no `on_event` hook is ever constructed and `self.rt` is the same
  `Runtime()` as before.
- `repl(session_id=None)` keeps its EXACT pre-EXT-045 signature (one keyword argument) so the
  EXT-043/EXT-044 tests that stub `repl` with `def fake_repl(session_id=None)` are unaffected.
- `_run_one_shot`'s new `stream` parameter is the 6th, defaulted (`False`) — the existing 4- and
  5-positional-argument call sites (tests and `main()`'s pre-EXT-045 call) are unaffected.
- A plain invocation with `stream` unset/`False` produces output BYTE-IDENTICAL to before this
  spec — streaming only ever ADDS lines to stdout via a side-channel `print()`, it never changes
  what any `handle()`/`dispatch()` call RETURNS.

## Out of scope (this task)

A live in-flight spinner/elapsed counter for a SINGLE long-running tool call (today's line only
appears at call-start and at call-completion, not mid-flight); `/export` (dump the session
transcript to a file); tab-completion for slash commands; theme/color configuration. These remain
honestly named in `docs/GAP-MAP.md` row #24's "Next lever" as the residual gap, per Tenet 3.
