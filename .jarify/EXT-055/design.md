# EXT-055 — Design

## Problem

`docs/GAP-MAP.md` Product-surface parity row #21 names Claude Code's "Esc to stop safely mid-task"
UX: a running command can be interrupted, whatever it already did is kept, and the user can
immediately redirect it. Today jcode's ONLY Ctrl-C handling is a bare
`except (EOFError, KeyboardInterrupt)` around the REPL's idle-prompt `input()` call
(`harness/cli.py::repl`) — it says nothing about a Ctrl-C that arrives WHILE a command
(`/agent`, `/fixrepo`, a plain-language fix/build) is actually executing. A `KeyboardInterrupt`
raised there is a `BaseException`, NOT caught by the REPL's existing `except Exception` guard
around `cli.handle(...)`, so it propagates straight out of the REPL loop and out of the process —
today's actual behavior for a mid-command Ctrl-C is a hard crash, not a graceful stop.

The fix must not introduce a new way for state to get corrupted. `harness/multi_file.py`'s
`multi_file_fix` and `harness/spec_loop.py`'s `_decompose_build`/`_build_per_function` already
perform several WRITE operations per run (one per candidate file / one per function); an
asynchronous exception-based interrupt could land mid-write, leaving a half-written file or an
inconsistent kept/reverted bookkeeping state. A COOPERATIVE flag — checked only at a point the
loop itself already considers "between steps" — cannot do that: it is either seen (and the loop
stops cleanly before the next write) or not seen yet (and the loop behaves exactly as if no
interrupt existed).

## Mechanism

```text
  InterruptController (harness/interrupt.py -- NEW module, pure deterministic bookkeeping)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ threading.Event()-backed flag:                                                     │
  │   request_cancel()   -> sets the flag (idempotent)                                 │
  │   is_cancelled()     -> pure read, no side effect                                  │
  │   reset()            -> clears the flag (before each new run/command)              │
  │                                                                                       │
  │ get_interrupt_controller() -> the process-wide singleton (mirrors                   │
  │                                harness.mcp_session's session-manager precedent)     │
  │ reset_interrupt_controller() -> convenience wrapper, called before every command    │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ an OPTIONAL `interrupt` param, `None` by default,
                                          │ threaded into the two touched loops below
                                          ▼
  COOPERATIVE CHECKS (harness/multi_file.py + harness/spec_loop.py -- additive, existing loops)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ multi_file_fix(cwd, test_cmd, instruction, test_file, ..., interrupt=None):         │
  │   for cand in candidates:                                                           │
  │       if interrupt is not None and interrupt.is_cancelled():   <- SAFE POINT:       │
  │           return {..partial result so far.., note="interrupted after N step(s)…"}   │       before the NEXT
  │       <try to fix `cand`, keep/revert as today, UNCHANGED>                          │       candidate; never
  │                                                                                       │       mid-fix/mid-write
  │ _decompose_build(intent, cwd, ..., interrupt=None):                                  │
  │   if interrupt.is_cancelled(): return {interrupted, nothing done}   <- entry check   │
  │   ... dispatch to _build_class / _build_per_function / whole-file fallback ...       │
  │                                                                                       │
  │ _build_per_function(intent, cwd, sigs, ..., interrupt=None):                         │
  │   for i, (func, params) in enumerate(sigs):                                          │
  │       if interrupt is not None and interrupt.is_cancelled():                         │
  │           interrupted_at = i; break            <- SAFE POINT: before the NEXT        │
  │       <build `func` as today, UNCHANGED>                          function's build   │
  │   if interrupted_at is not None:                                                     │
  │       stub every REMAINING function honestly (module still parses)                  │
  │       SKIP the TASK-10 hybrid whole-file fallback (an interrupt means stop, not      │
  │       try harder)                                                                    │
  └─────────────────────────────────────┬─────────────────────────────────────────────┘
                                          │ `interrupt=get_interrupt_controller()` passed in
                                          │ from the CLI call sites that reach these loops
                                          ▼
  REPL SIGINT WIRING (harness/cli.py -- NEW `_run_command_interruptible`, wraps `cli.handle`)
  ┌───────────────────────────────────────────────────────────────────────────────────┐
  │ repl():                                                                              │
  │   while True:                                                                        │
  │     line = input(...)                 <- idle-prompt Ctrl-C: UNCHANGED (existing     │
  │                                            except (EOFError, KeyboardInterrupt))     │
  │     out = _run_command_interruptible(cli, line):                                     │
  │       reset_interrupt_controller()                        <- clear any stale cancel  │
  │       prev = signal.signal(SIGINT, lambda *_: controller.request_cancel())            │
  │       try:     out = cli.handle(line, interactive=True)     <- a real Ctrl-C here     │
  │       finally: signal.signal(SIGINT, prev)                    sets the flag, does NOT │
  │                                                                 raise KeyboardInterrupt│
  │       if controller.is_cancelled(): out += "\ninterrupted — partial work preserved    │
  │                                             (/rewind to undo, or type a new           │
  │                                             instruction to steer)"                    │
  │     print(out)                          <- REPL returns to the prompt; the next       │
  │                                             typed line is the "steer" -- an ORDINARY  │
  │                                             next turn, no special amend mode           │
  └───────────────────────────────────────────────────────────────────────────────────┘
```

- **Cooperative, not signal-exception-based.** The whole point of routing Ctrl-C to a flag rather
  than letting Python's default SIGINT handler raise `KeyboardInterrupt` is that the flag is only
  ever OBSERVED at a point the loop itself picked as safe — it can never land mid-write. This is
  the single biggest safety property of this spec and the reason a signal-raising design was
  rejected.
- **No new persistence.** A graceful stop's "partial work preserved" claim rests entirely on
  mechanisms that already exist — the EXT-049 fine-grained checkpoint ring and the EXT-009
  whole-run snapshot (`/rewind`, `/undo`). This spec adds no new Decision type, no new snapshot
  format, no new state file.
- **Byte-identical default.** Every touched function's new `interrupt` parameter defaults to
  `None`; every existing eval/test caller that omits it takes the exact prior code path. Even a
  live, NEVER-cancelled controller (the real CLI's default, day-to-day case) changes nothing
  observable — the added check is a cheap read that always evaluates `False` until an actual
  cancel is requested.
- **Steer = the existing next-turn mechanism.** No new "amend mode" is built. After a graceful
  stop, the REPL is back at its ordinary prompt; the user's next typed line goes through the
  SAME `handle()`/`_route_plain` routing every turn already uses. This is honestly named a
  first-pass `partial` in the Product-Parity Checklist rather than a dedicated steering feature.

## Two-plane / honesty

`harness/interrupt.py` is pure deterministic execution-plane bookkeeping (Tenet 1): a
`threading.Event`, no model call, no Decision type, no I/O. The cooperative CHECKS added to
`multi_file.py`/`spec_loop.py` are likewise deterministic control flow, not a model judgement —
the model is never asked "should I stop?". Per Tenet 3, `harness/product_parity.py` row #21 is
flipped to `"partial"`, not `"works"`: interrupt lands genuinely (graceful stop, no corruption,
honest note) on the two flows this spec touches, but `/buildsystem`'s system-build loop and other
long-running commands (`/run`, a raw `/build`) have no cooperative check yet, and "steer" is only
the pre-existing next-turn mechanism, not a dedicated amend UX — both residuals are named in
`next_lever`, not hidden.

## Backward compatibility (no regression) — THE #1 CONSTRAINT

- Every touched function (`multi_file_fix`, `spec_driven_loop`, `_decompose_build`,
  `_build_per_function`) gets ONE new keyword-only parameter, `interrupt: object | None = None`,
  added at the END of its existing keyword-only parameter list — no existing positional or
  keyword call site changes shape.
- `interrupt=None` (the default, and what every existing eval/test caller passes implicitly by
  omitting it) makes every new check a no-op: `if interrupt is not None and
  interrupt.is_cancelled(): ...` never enters its body. The loop's steps, iteration count, return
  shape, and file-write behavior are all IDENTICAL to before this spec for every such caller.
- The REPL's `repl()` function's own control flow is unchanged except that the direct
  `cli.handle(line, interactive=True)` call is now made through
  `_run_command_interruptible(cli, line)`, which performs the identical call internally and
  returns the identical string when no interrupt is requested (the ordinary case) — the visible
  behavior for a normal command, and for the existing `except Exception` crash-safety guard, is
  unchanged.
- Idle-prompt Ctrl-C (the pre-existing `except (EOFError, KeyboardInterrupt)` around `input()`) is
  completely untouched by this spec — the SIGINT wiring only wraps the `cli.handle()` call itself,
  installed immediately before and torn down immediately after (in a `finally`).

## Out of scope (this task)

`/buildsystem`'s (`harness/system_builder.py`) own module-by-module build loop — explicitly
OUT OF SCOPE per the owner's scope-isolation directive (a parallel effort owns that file); a
dedicated "amend the in-flight plan" mode distinct from typing a fresh instruction after a
graceful stop; interrupting a single long BLOCKING call that has no internal iteration to check
between (e.g. one `shell.exec` invocation, one LLM completion call) — Ctrl-C during such a command
still sets the cooperative flag, but since nothing polls it mid-call, the command runs to
completion rather than stopping early (a safety improvement over today's crash, not a full
interrupt of that specific blocking call). These residuals are named honestly in
`docs/GAP-MAP.md` row #21's "Next lever," per Tenet 3.
