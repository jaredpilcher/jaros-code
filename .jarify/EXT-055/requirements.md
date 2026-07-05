---
id: EXT-055
title: Graceful interrupt + steer mid-run
status: partial
priority: medium
---

# EXT-055 — Graceful interrupt + steer mid-run

**Owner directive:** close `docs/GAP-MAP.md` Product-surface parity row #21 — a running command
can be interrupted SAFELY (partial work preserved, no corruption) and the user can immediately
steer it with a new instruction. ★ Highest regression-risk constraint: with NO interrupt
requested (the default, for every existing caller/test, today and after this spec), every touched
multi-step loop runs BYTE-IDENTICAL to before. The mechanism is a pure cooperative CHECK, never a
signal-raised exception — it can never land mid-write/mid-Decision.

### [REQ-1] `InterruptController` — a cooperative cancel flag

A new `harness/interrupt.py` module provides `InterruptController`, a threadsafe (`threading.Event`
-backed) flag with `request_cancel()`, `is_cancelled() -> bool`, and `reset()`, plus a process-wide
singleton accessor (`get_interrupt_controller()`/`reset_interrupt_controller()`) mirroring the
`harness.mcp_session` singleton precedent.

#### Acceptance Criteria
- [x] `InterruptController()` starts un-cancelled; `is_cancelled()` returns `False`.
- [x] `request_cancel()` makes `is_cancelled()` return `True`; calling it again is a no-op
      (idempotent) — still `True`.
- [x] `reset()` clears the flag back to `False`, regardless of how many times `request_cancel()`
      was called before it.
- [x] `get_interrupt_controller()` returns the SAME object on repeated calls (a process-wide
      singleton); `reset_interrupt_controller()` resets that singleton's flag.
- [x] Nothing in this module ever raises on ordinary use (pure, deterministic bookkeeping — no I/O,
      no model call, Tenet 1).

### [REQ-2] Cooperative checks in the multi-step loops

`harness/multi_file.py::multi_file_fix`'s per-candidate loop and `harness/spec_loop.py`'s
`_decompose_build`/`_build_per_function` each accept an OPTIONAL `interrupt` parameter (default
`None`) and poll `interrupt.is_cancelled()` ONLY at the TOP of an iteration — a safe point, before
starting the next unit of work (the next candidate file / the next function), never mid-fix,
mid-write, or mid-Decision. On a genuine cancel, the loop STOPS and returns its CURRENT partial
result with an honest `"interrupted after N step(s) — partial work preserved; /rewind to undo"`
note, rather than continuing or raising. No new persistence mechanism is introduced — whatever was
already kept relies entirely on the existing EXT-049 checkpoint ring / EXT-009 whole-run snapshot.

#### Acceptance Criteria
- [x] `multi_file_fix(..., interrupt=None)`: with `interrupt=None` (the default), behavior,
      iteration count, and return shape are byte-identical to before this spec for every existing
      eval/test caller.
- [x] `multi_file_fix(..., interrupt=<a cancelled controller>)`: the loop does not attempt any
      FURTHER candidate once cancelled is observed; it returns `{"solved": False, "tried": [...
      only what was actually attempted ...], "fixed": [... only what was actually kept ...], ...,
      "note": "interrupted after N step(s) ..."}` — never a half-written file, never an exception
      escaping.
- [x] `_build_per_function(..., interrupt=None)`: byte-identical default behavior (same as above).
- [x] `_build_per_function(..., interrupt=<cancelled after step K>)`: functions `0..K-1` keep
      whatever the loop already produced for them; every function from `K` on is honestly stubbed
      (`raise NotImplementedError`) so the assembled module still parses; the TASK-10 hybrid
      whole-file fallback is SKIPPED once interrupted (stop, not "try harder"); the returned
      `note` says "interrupted after K step(s) ...".
- [x] `_decompose_build(..., interrupt=<already cancelled>)`: returns immediately with
      `flow="interrupted"` and performs NO writes at all when cancelled before the first step.
- [x] `spec_driven_loop(..., interrupt=None)` threads the parameter through unchanged to whichever
      flow (FIX via `multi_file_fix`, BUILD via `_decompose_build`) it dispatches to; default
      behavior is unaffected.

### [REQ-3] REPL SIGINT wiring — graceful stop, stay in the REPL

`harness/cli.py`'s interactive REPL wires a REAL Ctrl-C that arrives WHILE a command is running to
the shared `InterruptController` (via a new `_run_command_interruptible` helper) instead of
letting an uncaught `KeyboardInterrupt` tear through and kill the session (today's actual
behavior — a `KeyboardInterrupt` is a `BaseException`, not caught by the REPL's existing `except
Exception` guard). The controller is reset before each new command; the SIGINT handler is
installed only for the duration of `cli.handle()` and always restored afterward. On a cancel, the
REPL reports an honest "interrupted — partial work preserved" note and returns to the prompt,
where the user's next typed line is the "steer" — routed through the SAME `handle()`/
`_route_plain` chain every ordinary turn already uses (no new amend mode). Idle-prompt Ctrl-C
(the pre-existing `except (EOFError, KeyboardInterrupt)` around `input()`) is completely
unaffected.

#### Acceptance Criteria
- [x] `_run_command_interruptible(cli, line)` resets the shared controller, installs a SIGINT
      handler that calls `request_cancel()` (never raises), calls `cli.handle(line,
      interactive=True)`, and restores the prior SIGINT handler in a `finally` — whether or not a
      cancel happened, whether or not `handle()` raised.
- [x] When no interrupt occurs, `_run_command_interruptible` returns EXACTLY what
      `cli.handle(line, interactive=True)` returned (byte-identical to calling it directly) — the
      existing `except Exception` crash-safety behavior for a bad command is preserved unchanged.
- [x] When a cancel IS observed during the command (the controller's `is_cancelled()` is `True`
      after `handle()` returns), the output has an honest "interrupted — partial work preserved
      (/rewind to undo, or type a new instruction to steer)" note appended.
- [x] A genuine `KeyboardInterrupt` that still escapes `cli.handle()` (e.g. the signal wiring
      couldn't be installed on this platform/thread) is caught and treated the same as a
      cooperative cancel — never propagates out of `_run_command_interruptible`, never crashes the
      REPL.
- [x] `repl()`'s idle-prompt Ctrl-C (at `input()`, between commands) is UNCHANGED — this wiring
      only wraps the `cli.handle()` call itself.
- [x] `JcodeCli.cmd_agent`/`cmd_fixrepo`/`_nl_fix`/`cmd_plan` pass
      `interrupt=get_interrupt_controller()` into the loops they invoke (`spec_driven_loop`/
      `multi_file_fix`), so a real REPL Ctrl-C actually reaches those loops' cooperative checks.

### [REQ-4] Honest Product-Parity Checklist update

`harness/product_parity.py` row `id=21` (Interrupt + steer mid-run) is flipped to `"partial"` —
NOT `"works"` — because graceful interrupt genuinely lands on the two flows this spec touches, but
`/buildsystem`'s system-build loop and other long-running commands have no cooperative check yet,
and "steer" is only the pre-existing ordinary-next-turn mechanism, not a dedicated amend UX; its
`current_state` names exactly what is delivered and what remains deferred. `docs/GAP-MAP.md` row
#21 and `tests/test_ext041_product_parity.py`'s honesty-pin/aggregate assertions are updated to
match.

#### Acceptance Criteria
- [x] `harness/product_parity.py`'s row `id=21` `state` is `"partial"`, with `current_state`
      naming exactly what is delivered (the `InterruptController`, the two cooperative loops, the
      REPL SIGINT wiring, no new persistence path) and what remains deferred (`/buildsystem`'s
      loop, other long-running commands, a dedicated amend/steer mode); `next_lever` names only
      the residual gap.
- [x] `docs/GAP-MAP.md` row #21's `State`/`Current honest state`/`Next lever` columns are updated
      to match.
- [x] `tests/test_ext041_product_parity.py`'s aggregate baseline assertions
      (`n_works`/`n_partial`/`n_missing`) are updated to reflect row #21 moving from `missing` to
      `partial` (row #21 is NOT added to the `works == [...]` pin, since it is honestly `partial`,
      not `works`).
