# Implementation Tasks

### [TASK-1] Cooperative interrupt controller + safe-point checks + REPL SIGINT wiring

Add a new `harness/interrupt.py` module providing a cooperative, threadsafe cancel flag; thread an
OPTIONAL `interrupt` parameter through `harness/multi_file.py::multi_file_fix`'s per-candidate loop
and `harness/spec_loop.py`'s `spec_driven_loop`/`_decompose_build`/`_build_per_function`, checked
ONLY at the top of an iteration (never mid-write); wire the REPL's Ctrl-C handling in
`harness/cli.py` to this same controller so a running command stops gracefully instead of an
uncaught `KeyboardInterrupt` crashing the session; and update the Product-Parity Checklist honestly.

#### Steps
1. Create `harness/interrupt.py`: `InterruptController` (`threading.Event`-backed) with
   `request_cancel()`, `is_cancelled() -> bool`, `reset()`; a process-wide singleton
   `get_interrupt_controller()` (constructs on first use, guarded by a module-level lock) and
   `reset_interrupt_controller()` (a convenience wrapper). Pure deterministic bookkeeping — no
   model call, no I/O, never raises.
2. In `harness/multi_file.py::multi_file_fix`: add a keyword-only `interrupt: "object | None" =
   None` parameter (appended after the existing `runtime` parameter). At the TOP of the
   `for cand in cands:` loop, before any per-candidate work starts, check
   `if interrupt is not None and interrupt.is_cancelled():` and if so return
   `{"solved": False, "file": None, "tried": tried, "fixed": kept, "dropped": [], "note":
   f"interrupted after {len(tried)} step(s) — partial work preserved; /rewind to undo"}` instead
   of continuing. `interrupt=None` (the default) makes this check a complete no-op — byte-identical
   to before this task.
3. In `harness/spec_loop.py`: add `interrupt: "object | None" = None` to `spec_driven_loop`
   (checked once at entry — an already-cancelled controller returns immediately with
   `flow="interrupted"` and does nothing; otherwise threaded unchanged into the `multi_file_fix`
   FIX-flow call and the `_decompose_build` BUILD-flow call), to `_decompose_build` (checked once
   at entry the same way, before dispatching to any build strategy; threaded into
   `_build_per_function`'s call when `len(sigs) >= 2`), and to `_build_per_function` (checked at
   the top of its `for func, params in sigs:` loop via `enumerate`, recording the index it was
   interrupted at and `break`ing; every remaining, not-yet-started function is then honestly
   stubbed with `raise NotImplementedError` so the assembled `solution.py` still parses; the
   TASK-10 hybrid whole-file-fallback probe is SKIPPED entirely when interrupted — `if failed and
   interrupted_at is None:` — since an interrupt means stop, not try harder; the returned `note`
   becomes `f"interrupted after {interrupted_at} step(s) — partial work preserved; /rewind to
   undo"` when interrupted, else the existing note text unchanged). `interrupt=None` (the default)
   makes every added check a no-op in all three functions.
4. In `harness/cli.py`: add a new module-level `_run_command_interruptible(cli, line) -> str`
   function (placed just above `def repl(...)`) that: imports
   `get_interrupt_controller`/`reset_interrupt_controller` from `harness.interrupt`; calls
   `reset_interrupt_controller()`; installs a `signal.signal(signal.SIGINT, ...)` handler (wrapped
   in `try/except (ValueError, OSError)`, degrading to no wiring on failure) whose callback calls
   `controller.request_cancel()` and never raises; calls `cli.handle(line, interactive=True)`
   inside a `try/except KeyboardInterrupt` (treated identically to a cooperative cancel — sets
   `request_cancel()` and produces `"(interrupted before completion)"`) and
   `except Exception as exc` (unchanged `f"\033[31merror:\033[0m {exc}"` behavior); restores the
   prior SIGINT handler in a `finally` (guarded the same way); and, if
   `controller.is_cancelled()` after the call, appends an
   `"interrupted — partial work preserved (/rewind to undo, or type a new instruction to steer)"`
   note to the output. Update `repl()`'s main loop to call `out =
   _run_command_interruptible(cli, line)` (still wrapped in its existing outer
   `try/except Exception` as defense-in-depth) instead of calling `cli.handle(...)` directly —
   idle-prompt Ctrl-C at `input()` is untouched. In `JcodeCli.cmd_agent`, `cmd_fixrepo`, `_nl_fix`,
   and `cmd_plan`'s `fix` step, import `get_interrupt_controller` and pass
   `interrupt=get_interrupt_controller()` into the `spec_driven_loop`/`multi_file_fix` calls each
   already makes (alongside the existing `runtime=self._write_runtime()`), so a real REPL Ctrl-C
   actually reaches the cooperative checks added in Steps 2-3.
5. Update `harness/product_parity.py` row `id=21` (Interrupt + steer mid-run): flip `state` to
   `"partial"`; `current_state` names what is genuinely delivered (the `InterruptController`, the
   cooperative checks in `multi_file_fix`/`_build_per_function`, the REPL SIGINT wiring, no new
   persistence path) and what remains deferred (`/buildsystem`'s own build loop and other
   long-running commands have no cooperative check yet; "steer" is only the pre-existing
   ordinary-next-turn mechanism, not a dedicated amend UX); `next_lever` names only that residual.
   Mirror the same honest update into `docs/GAP-MAP.md` row #21's `State`/`Current honest
   state`/`Next lever` columns.
6. Update `tests/test_ext041_product_parity.py`: `test_score_default_rows_reflects_honest_current_
   baseline`'s `n_partial`/`n_missing` assertions to reflect row #21 moving from `missing` to
   `partial` (row #21 is NOT added to the `works == [...]` pin — it is honestly `partial`, not
   `works`).
7. Write `tests/test_ext055_interrupt.py` (deterministic, no live gemma, hermetic): cover —
   `InterruptController`'s request_cancel/is_cancelled/reset semantics and the singleton
   accessor's identity + reset behavior; `multi_file_fix` with `interrupt=None` and with a live
   but never-cancelled controller both run the SAME number of steps and reach the SAME result as
   each other (the default-byte-identical guarantee); a scenario where a monkeypatched `fix_loop`
   calls `controller.request_cancel()` after fixing the first of two candidate files, asserting
   the loop stops BEFORE the second candidate (never attempted, file untouched), the first
   candidate's fix is KEPT and persisted (no half-written file, no exception escaping), and the
   returned `note` mentions "interrupted"; the equivalent scenario for `_build_per_function`
   (interrupted after the first of two functions — the first function's module is genuinely
   implemented, the second is honestly stubbed, `solved is False`, the hybrid fallback never
   runs); `_decompose_build` returning immediately with no writes when the controller is
   ALREADY cancelled before the call; and the REPL's `_run_command_interruptible` helper —
   default (no interrupt) returns `cli.handle`'s output unchanged, a simulated SIGINT firing
   mid-command (by invoking the currently-installed `signal.getsignal(signal.SIGINT)` handler
   from inside a stubbed `cli.handle`) results in an "interrupted" note appended and the prior
   SIGINT handler restored afterward, and a `KeyboardInterrupt` raised directly from a stubbed
   `cli.handle` is caught (never propagates) and reported the same way.

#### Implements
- [REQ-1] `InterruptController` — a cooperative cancel flag
- [REQ-2] Cooperative checks in the multi-step loops
- [REQ-3] REPL SIGINT wiring — graceful stop, stay in the REPL
- [REQ-4] Honest Product-Parity Checklist update
