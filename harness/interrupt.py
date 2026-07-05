"""Cooperative interrupt-and-steer (EXT-055): closes `docs/GAP-MAP.md` Product-surface parity
row #21 -- "Interrupt + steer mid-run" (Esc to stop safely mid-task, queue a correction, agent
adjusts).

★ HIGHEST REGRESSION RISK NOTE (this is a run-loop control-flow change): this module is a pure,
additive, COOPERATIVE mechanism -- a plain flag a running loop CHECKS at a SAFE iteration
boundary (never mid-write/mid-Decision). It is deliberately NOT signal-based exception raising
(which could tear through a loop at an arbitrary bytecode instruction, mid-write, corrupting
state). Every loop that grew a cooperative check accepts an OPTIONAL `interrupt` parameter,
`None` by default -- the exact, byte-identical path every existing caller/test takes today. A
caller that wants graceful cancel passes a live `InterruptController` and calls
`request_cancel()` from anywhere (a REPL SIGINT handler, another thread, a test) at any time; the
loop only ever CHECKS `is_cancelled()` at the TOP of an iteration, before starting new work, so a
cancel can never land mid-write.

Two-plane discipline (Tenet 1): pure execution-plane bookkeeping -- no model call, no new
Decision type, no new persistence path (partial state is already checkpointed via the existing
EXT-049 checkpoint ring / EXT-009 whole-run snapshot; this module adds nothing new there).
"""
from __future__ import annotations

import threading

# #EXT-055-REQ-1 Start
class InterruptController:
    """A cooperative cancel flag, threadsafe (backed by `threading.Event`). `is_cancelled()` is a
    pure read with no side effect, so it is safe to poll from a hot loop."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request_cancel(self) -> None:
        """Ask any loop polling this controller to stop at its NEXT safe point. Idempotent --
        calling it more than once (e.g. a double Ctrl-C) has the same effect as calling it once."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Has a cancel been requested? Never raises."""
        return self._event.is_set()

    def reset(self) -> None:
        """Clear the flag -- call before starting a NEW run/command so a stale cancel from a
        prior interrupted run can never bleed into the next one."""
        self._event.clear()


# Process-wide singleton (mirrors `harness.mcp_session`'s session-manager singleton precedent):
# the CLI REPL's SIGINT wiring and a running command's cooperative loop need to share ONE
# controller without threading a fresh instance through every call site by hand. A caller that
# wants an ISOLATED controller (e.g. a hermetic test) should construct its own
# `InterruptController()` directly and pass it explicitly -- the singleton below is only a
# convenience for the real CLI wiring, never the only way to use this module.
_controller: "InterruptController | None" = None
_lock = threading.Lock()


def get_interrupt_controller() -> InterruptController:
    """Return the process-wide `InterruptController`, constructing it on first use."""
    global _controller
    with _lock:
        if _controller is None:
            _controller = InterruptController()
        return _controller


def reset_interrupt_controller() -> None:
    """Reset the process-wide controller's flag (a convenience wrapper around
    `get_interrupt_controller().reset()`) -- called before every new REPL command."""
    get_interrupt_controller().reset()
# #EXT-055-REQ-1 End
