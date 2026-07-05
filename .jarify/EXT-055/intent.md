# Intent

`docs/GAP-MAP.md`'s Product-surface parity row #21 names a gap Claude Code closes but jcode does
not: **interrupt + steer mid-run** — press Esc/Ctrl-C while a task is running and it stops
*safely*, preserving whatever partial work already landed, and the user can immediately redirect
it with a new instruction. Today jcode has Ctrl-C *crash-safety* (a bare `except (EOFError,
KeyboardInterrupt)` around the idle prompt's `input()` call) but nothing graceful for a Ctrl-C
that arrives *while* a multi-step command (`/agent`, `/fixrepo`, a natural-language fix or build)
is actually running: an uncaught `KeyboardInterrupt` there is a `BaseException`, not caught by the
REPL's existing `except Exception` guard, so it tears straight through the running loop and kills
the whole session — the opposite of "safely."

This spec closes that gap the SAFEST possible way for a run-loop control-flow change: not by
catching an asynchronous exception (which can land at any bytecode instruction, including
mid-write or mid-Decision, and corrupt state), but by adding a plain **cooperative cancel flag**
(`harness/interrupt.py`'s `InterruptController`) that a running loop *polls itself*, only at a
SAFE point — the top of an iteration, before starting the next unit of work, never mid-write.
`harness/spec_loop.py`'s build-flow and `harness/multi_file.py`'s cumulative fix-flow each grow
one such check; on cancel they stop and return their CURRENT partial result with an honest note,
rather than continuing or raising. The REPL wires a real Ctrl-C during a running command to this
same flag (`harness/cli.py`'s `_run_command_interruptible`) instead of leaving the loop's fate to
an uncaught asynchronous exception — turning today's crash into a graceful stop that returns to
the prompt, where the user can steer by simply typing their next instruction.

This converges PRIME-001 on **Tenet 1 (two-plane discipline)** and **Tenet 5 (Claude-Code-like
UX)** at once: the interrupt decision itself is pure deterministic execution-plane bookkeeping (a
flag, never a model judgement, never a new Decision type, never a new persistence mechanism — the
existing EXT-049 checkpoint ring / EXT-009 whole-run snapshot already covers whatever partial
state a graceful stop leaves behind), while the product-facing behavior is precisely the
Claude-Code "Esc to stop safely mid-task" experience row #21 asks for. Per **Tenet 3 (honesty)**,
this spec is scoped and named honestly: only two loops (the FIX flow's `multi_file_fix` and the
BUILD flow's per-function build) grow cooperative checks in this pass — `/buildsystem`'s own
system-build loop and other long-running commands are NOT yet wired, and there is no dedicated
"amend the in-flight plan" mode beyond typing a fresh instruction after the stop. The
Product-Parity Checklist (EXT-041) row #21 is flipped to `"partial"`, not `"works"`, and names
exactly that residual, rather than inflating the claim.

The **overriding constraint** (stated first in the owner's directive, and repeated here because it
governs every line of this spec): with **no interrupt requested — the default, for every existing
caller and test, today and after this spec** — every touched loop runs **byte-identical** to
before. The cooperative check is a pure no-op unless a live, already-cancelled controller is
passed in; nothing about this spec may restructure a loop's control flow, its return shape, or
its default behavior in any way a caller could observe.
