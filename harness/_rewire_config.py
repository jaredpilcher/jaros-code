"""Shared injectable configuration for the model.rewire Jaros tool (EXT-021, TASK-25).

Singleton state (one copy in sys.modules via the harness package) that survives the
importlib dynamic-loading path used by load_custom_tools for .jaros-data/tools/.

ModelRewireTool.validate() and ModelRewireTool.execute() import lazily from this
module at call time; callers (solve_routed_native, tests) set state here before
applying a model.rewire Decision.

Why not module-level globals in the tool file?
----------------------------------------------
load_custom_tools() imports each tool with a FRESH importlib module object
(module_name = "jaros_tool_<stem>", NOT registered in sys.modules).  Any setter
called on ``import model_rewire_tool`` from the normal sys.path would target a
DIFFERENT module object than the one the executor has bound.  Using a stable
harness package module as the shared store avoids this — there is always exactly
ONE copy of harness._rewire_config in sys.modules, so setters and lazy getters
always see the same state.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# #EXT-021-REQ-3 Start

_registry: Any = None
_swap_fn: Optional[Callable] = None
_serving_state_fn: Optional[Callable] = None
_activate_fn: Optional[Callable] = None


def set_registry(r: Any) -> None:
    """Set the ModelRegistry used by ModelRewireTool for validate + execute."""
    global _registry  # noqa: PLW0603
    _registry = r


def get_registry() -> Any:
    """Return the current ModelRegistry (None if not set)."""
    return _registry


def set_swap_fn(fn: Optional[Callable]) -> None:
    """Override the manager HTTP swap callable (inject a mock for offline tests)."""
    global _swap_fn  # noqa: PLW0603
    _swap_fn = fn


def get_swap_fn() -> Optional[Callable]:
    return _swap_fn


def set_serving_state_fn(fn: Optional[Callable]) -> None:
    """Override the serving-state reader (inject a stub for offline tests)."""
    global _serving_state_fn  # noqa: PLW0603
    _serving_state_fn = fn


def get_serving_state_fn() -> Optional[Callable]:
    return _serving_state_fn


def set_activate_fn(fn: Optional[Callable]) -> None:
    """Override the adaptation activate callable (inject a stub for offline tests)."""
    global _activate_fn  # noqa: PLW0603
    _activate_fn = fn


def get_activate_fn() -> Optional[Callable]:
    return _activate_fn


def reset_all() -> None:
    """Reset all injectable state to None (call in test teardown for isolation)."""
    global _registry, _swap_fn, _serving_state_fn, _activate_fn  # noqa: PLW0603
    _registry = None
    _swap_fn = None
    _serving_state_fn = None
    _activate_fn = None

# #EXT-021-REQ-3 End
