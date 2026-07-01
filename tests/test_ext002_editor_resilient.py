"""Offline unit tests for EXT-002 / REQ-8 — EditorBoundary opt-in resilient emission.

No network, no Jetson, no Docker: the model is injected via a canned stub
(mirrors ``tests/test_ext013_locate.py``'s ``_FakeLlm`` pattern).

Coverage (task's step 3):
  (a) With ``ctx["resilient"] = True`` and a parseable edit, the emitted
      Decision is ``code.search_replace`` with payload ``{path, search, replace}``.
  (b) WITHOUT the flag, the emitted Decision is ``code.apply_patch`` with
      payload ``{path, old, new}`` (backward-compat, byte-for-byte unchanged).
  (c) Unparseable model output emits an honest ``advance`` Decision in BOTH modes.
"""
from __future__ import annotations

# #EXT-002-REQ-8 Start

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or from the tests/ directory
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_AGENTS_DIR = _REPO_ROOT / ".jaros-data" / "agents"


def _load_agent():
    agent_path = _AGENTS_DIR / "editor_agent.py"
    spec = importlib.util.spec_from_file_location("editor_agent", agent_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM that always returns a predetermined text response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def complete(self, request):  # noqa: ANN001
        self.call_count += 1
        return _FakeCompletion(self._response)


_VALID_EDIT_REPLY = (
    "<<<OLD\n"
    "def foo():\n"
    "    return 1\n"
    "OLD>>>\n"
    "<<<NEW\n"
    "def foo():\n"
    "    return 2\n"
    "NEW>>>\n"
)

_UNPARSEABLE_REPLY = "I refuse to answer that.\n"

_CTX_BASE = {
    "path": "pkg/mod.py",
    "content": "def foo():\n    return 1\n",
    "instruction": "make foo return 2",
}


# ---------------------------------------------------------------------------
# (a) ctx["resilient"] = True -> code.search_replace with {path, search, replace}
# ---------------------------------------------------------------------------

def test_resilient_flag_emits_search_replace_decision():
    mod = _load_agent()
    llm = _FakeLlm(_VALID_EDIT_REPLY)
    agent = mod.build(llm)

    ctx = dict(_CTX_BASE, resilient=True)
    decisions = agent.decide(ctx)

    assert len(decisions) == 1, "must emit exactly one Decision"
    d = decisions[0]
    assert d.type == "code.search_replace", f"wrong type: {d.type}"
    assert d.source == mod.NAME
    assert set(d.payload.keys()) == {"path", "search", "replace"}
    assert d.payload["path"] == "pkg/mod.py"
    assert d.payload["search"] == "def foo():\n    return 1"
    assert d.payload["replace"] == "def foo():\n    return 2"


# ---------------------------------------------------------------------------
# (b) absent/falsey flag -> code.apply_patch with {path, old, new} (backward-compat)
# ---------------------------------------------------------------------------

def test_default_mode_still_emits_apply_patch_decision():
    mod = _load_agent()
    llm = _FakeLlm(_VALID_EDIT_REPLY)
    agent = mod.build(llm)

    decisions = agent.decide(dict(_CTX_BASE))  # no "resilient" key at all

    assert len(decisions) == 1
    d = decisions[0]
    assert d.type == "code.apply_patch", f"wrong type: {d.type}"
    assert d.source == mod.NAME
    assert set(d.payload.keys()) == {"path", "old", "new"}
    assert d.payload["path"] == "pkg/mod.py"
    assert d.payload["old"] == "def foo():\n    return 1"
    assert d.payload["new"] == "def foo():\n    return 2"


def test_falsey_resilient_flag_also_emits_apply_patch_decision():
    mod = _load_agent()
    llm = _FakeLlm(_VALID_EDIT_REPLY)
    agent = mod.build(llm)

    for falsey in (False, 0, "", None):
        ctx = dict(_CTX_BASE, resilient=falsey)
        d = agent.decide(ctx)[0]
        assert d.type == "code.apply_patch", f"falsey {falsey!r} should not opt in"
        assert set(d.payload.keys()) == {"path", "old", "new"}


# ---------------------------------------------------------------------------
# (c) unparseable model output -> honest advance Decision in BOTH modes
# ---------------------------------------------------------------------------

def test_unparseable_output_emits_advance_in_resilient_mode():
    mod = _load_agent()
    llm = _FakeLlm(_UNPARSEABLE_REPLY)
    agent = mod.build(llm)

    ctx = dict(_CTX_BASE, resilient=True)
    decisions = agent.decide(ctx)

    assert len(decisions) == 1
    d = decisions[0]
    assert d.type == "advance"
    assert d.payload["events"] == ["start", "fail"]
    assert "could not parse" in d.payload["note"]


def test_unparseable_output_emits_advance_in_default_mode():
    mod = _load_agent()
    llm = _FakeLlm(_UNPARSEABLE_REPLY)
    agent = mod.build(llm)

    decisions = agent.decide(dict(_CTX_BASE))  # no "resilient" key

    assert len(decisions) == 1
    d = decisions[0]
    assert d.type == "advance"
    assert d.payload["events"] == ["start", "fail"]
    assert "could not parse" in d.payload["note"]


# ---------------------------------------------------------------------------
# Structural: NAME constant and build() factory exist (unchanged by this task)
# ---------------------------------------------------------------------------

def test_name_constant_and_build_factory_exist():
    mod = _load_agent()
    assert isinstance(mod.NAME, str) and mod.NAME
    assert callable(mod.build)


# #EXT-002-REQ-8 End
