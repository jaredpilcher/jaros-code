---
id: EXT-045
title: Terminal UX — streaming tool events + statusline
status: covered
priority: medium
---

# EXT-045 — Terminal UX: streaming + statusline

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #24 — Claude Code's
live, streaming terminal feel and one-line statusline. The Jaros hash-chain already records every
accepted `Decision` the instant it is applied (`harness.coding_loop.Runtime.apply` →
`jaros.state.record_decision`); this spec is presentation over that SAME seam — no new
event-logging mechanism, no orchestrator changes, no model call.

### [REQ-1] Streaming tool events

As a tool call is applied through `harness.coding_loop.Runtime` (the seam every CLI command and
agent tool call already goes through), a concise, human-readable line narrates it to stdout AS IT
HAPPENS: a `→ <type>(<arg>)` line when the call is accepted for execution, and a `✓ <summary>` /
`✗ <type> failed: <reason>` line once it completes or is rejected. Streaming is suppressed
UNCONDITIONALLY under `--output-format json` (EXT-043) so machine-composable output stays a
single clean parseable object; otherwise it defaults to whether stdout is a live terminal, and
`JCODE_STREAM_EVENTS=1|0` can force it on or off either way. A plain invocation with streaming not
enabled is byte-identical (return values, exit codes) to before this spec — streaming only ever
ADDS lines to stdout via a side channel, never changes what any command returns.

#### Acceptance Criteria
- [x] `harness.coding_loop.Runtime` accepts an optional `on_event` callback; when set, `apply()` invokes it with a `{"phase": "call", ...}` event before executing a Decision and a `{"phase": "result", ...}` (or `{"phase": "error", ...}` on a gate rejection / executor refusal) event after — at the SAME point the Decision is durably recorded to the hash-chain, not a second mechanism.
- [x] `on_event` defaults to `None`; a `Runtime(...)` constructed with no `on_event` behaves byte-identically to before this spec (no crash, no behavior change) from the mere presence of the new hook.
- [x] `harness.tool_stream.render_event`/`format_call`/`format_result`/`format_error` render a concise, human-readable line per event; `stream_events` maps a SEQUENCE of events to lines, in order, skipping anything malformed rather than raising.
- [x] `harness.tool_stream.should_stream` returns `False` under `output_format == "json"` regardless of TTY/env; otherwise `JCODE_STREAM_EVENTS` (`0`/`1`/etc.) overrides either way; otherwise defaults to whether stdout is a TTY.
- [x] `harness.tool_stream.make_printer`/`Runtime._emit` never raise on a malformed event or a broken output stream — an observability failure can never break the tool call it is narrating.
- [x] `JcodeCli(stream=True)` (and `_git_tool`'s root-anchored Runtime) narrates real tool dispatches (e.g. `/read`) to stdout, in addition to (not instead of) the command's normal return value; `JcodeCli(stream=False)` (the default) produces no such narration — plain output stays byte-identical to before this spec.

### [REQ-2] Statusline

A `statusline()` function renders `model · problem-class · $0 · latency` from CURRENT state: the
active model label, the last routed action ("problem class"), and the measured wall-clock latency
of the last `handle()` turn — the honest, always-`$0` cost marker (Tenet 2: no paid/cloud model is
ever in the loop). `JcodeCli.handle()` times each turn and records the routed action, best-effort,
so a clock/attribute failure can never affect what `handle()` returns. `/statusline [on|off]`
toggles a persistent statusline the REPL prints above every prompt, and always shows the CURRENT
value either way.

#### Acceptance Criteria
- [x] `harness.statusline.statusline(model, problem_class, latency_s, cost="$0")` renders a string containing the model, the `$0` marker, and a latency field (`"Xs"` when `latency_s` is a non-negative number, else `"-"`); never raises on `None`/garbage inputs.
- [x] `JcodeCli.statusline()` reflects `self.model`, `self._last_action`, and `self._last_latency_s` — all three updated at the end of every `handle()` call (best-effort, wrapped so a failure never changes `handle()`'s return value).
- [x] `JcodeCli.cmd_statusline("on"/"off")` toggles `self._show_statusline` and always returns the CURRENT statusline text; the REPL prints it above every prompt when the flag is `True`.
- [x] `/help` documents `/statusline` alongside the other commands.

### [REQ-3] Honest Product-Parity Checklist update

`harness/product_parity.py` row #24 (Terminal UX polish) is flipped to `"works"` ONLY because
streaming + statusline + `/help` discoverability are genuinely delivered and test-covered; its
`current_state` honestly names what remains deferred (a live in-flight spinner for a single long
tool call, `/export`, tab-completion, themes) rather than inflating the whole feature bundle.
`docs/GAP-MAP.md` row #24 and `tests/test_ext041_product_parity.py`'s honesty-pin are updated to
match, mirroring how EXT-042/EXT-043/EXT-044 each did on landing.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=24` `state` is `"works"`, with `current_state` naming exactly what is delivered and what remains deferred, and `next_lever` naming only the residual gap.
- [x] `docs/GAP-MAP.md` row #24's `State`/`Current honest state`/`Next lever` columns are updated to match.
- [x] `tests/test_ext041_product_parity.py`'s `works == [...]` pin and `n_works`/aggregate-bound assertions include row #24.
