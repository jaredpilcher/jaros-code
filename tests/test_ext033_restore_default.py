"""Offline tests for EXT-033 REQ-7: harness/eval_routed.py::_restore_default_model.

Real operational bug: the CLI __main__ block rewires the Jetson to routed
models (qwen etc.) during a routed eval but never restored the registry
default (gemma-4-e2b) afterward. These tests verify the restore helper
calls ``rewire`` with the registry default, and that a raising ``rewire``
is swallowed (best-effort — a restore failure must never mask the eval
result). No Jetson call is made; ``harness.model_rewire.rewire`` is
monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness import eval_routed  # noqa: E402


# #EXT-033-REQ-7 Start
class _FakeRegistry:
    """Minimal stand-in for ModelRegistry — only default_model() is used."""

    def default_model(self) -> str:
        return "gemma-4-e2b"


def test_restore_default_model_calls_rewire_with_default(monkeypatch):
    """_restore_default_model rewires back to registry.default_model()."""
    calls: list[tuple] = []

    def _fake_rewire(model_id, registry, **kwargs):
        calls.append((model_id, registry))
        return {"ok": True}

    monkeypatch.setattr("harness.model_rewire.rewire", _fake_rewire)

    fake_registry = _FakeRegistry()
    eval_routed._restore_default_model(fake_registry)

    assert len(calls) == 1
    assert calls[0][0] == "gemma-4-e2b"
    assert calls[0][1] is fake_registry


def test_restore_default_model_swallows_rewire_error(monkeypatch):
    """A raising rewire() must NOT propagate — best-effort restore (Tenet 3)."""

    def _raising_rewire(model_id, registry, **kwargs):
        raise RuntimeError("simulated rewire failure")

    monkeypatch.setattr("harness.model_rewire.rewire", _raising_rewire)

    fake_registry = _FakeRegistry()
    # Must not raise.
    eval_routed._restore_default_model(fake_registry)
# #EXT-033-REQ-7 End
