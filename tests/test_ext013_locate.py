"""Offline unit tests for EXT-013 / REQ-6 — LocateBoundary + resolve_location.

No network, no Jetson, no Docker: the model is injected via a canned stub
(mirrors ``tests/test_ext013_orchestrator_judge.py``'s ``_FakeLlm`` pattern).

Coverage (task's step 4):
  (a) The agent returns an ``orchestrate.locate`` Decision naming the CORRECT
      candidate for a synthetic intent + candidate set when the model answers
      with the right index.
  (b) The degeneracy-guard falls back to the content-match candidate when the
      model reply is garbage (no valid in-range index).
  (c) The resolver reuses ``locate_region`` and returns the right (start, end).
"""
from __future__ import annotations

# #EXT-013-REQ-6 Start

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
    agent_path = _AGENTS_DIR / "locate_agent.py"
    spec = importlib.util.spec_from_file_location("locate_agent", agent_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM that always returns a predetermined text response."""

    def __init__(self, response: str = "1") -> None:
        self._response = response
        self.call_count = 0

    def complete(self, request):  # noqa: ANN001
        self.call_count += 1
        return _FakeCompletion(self._response)


# A synthetic candidate set: two functions, the intent clearly refers to the 2nd.
_CANDIDATES = [
    {"file": "pkg/models.py", "function": "save_user", "anchor_line": 5},
    {"file": "pkg/serializers.py", "function": "serialize_type", "anchor_line": 14},
]
_INTENT = "Fix serialize_type so it returns the qualified name, not just __name__."


# ---------------------------------------------------------------------------
# (a) Correct model reply -> Decision names the right candidate
# ---------------------------------------------------------------------------

def test_agent_returns_locate_decision_for_correct_candidate():
    mod = _load_agent()
    llm = _FakeLlm("2")  # model picks candidate #2 (1-based) -> serialize_type
    agent = mod.build(llm)

    decisions = agent.decide({"intent": _INTENT, "candidates": _CANDIDATES})

    assert len(decisions) == 1, "must emit exactly one Decision"
    d = decisions[0]
    assert d.type == "orchestrate.locate", f"wrong type: {d.type}"
    assert d.source == mod.NAME
    assert d.payload["file"] == "pkg/serializers.py"
    assert d.payload["function"] == "serialize_type"
    assert d.payload["anchor_line"] == 14
    assert d.payload["matched_by"] == "model"


def test_agent_no_host_effect_pure_decision_only():
    """Two-plane discipline (Tenet 1): decide() must return only inert Decisions,
    never perform I/O — calling it twice with the same stub must be side-effect-free."""
    mod = _load_agent()
    llm = _FakeLlm("1")
    agent = mod.build(llm)
    ctx = {"intent": _INTENT, "candidates": _CANDIDATES}
    d1 = agent.decide(ctx)[0]
    d2 = agent.decide(ctx)[0]
    assert d1.payload["file"] == d2.payload["file"] == "pkg/models.py"


# ---------------------------------------------------------------------------
# (b) Degeneracy-guard: garbage model reply -> deterministic content-match fallback
# ---------------------------------------------------------------------------

def test_degeneracy_guard_falls_back_to_content_match_on_garbage():
    mod = _load_agent()
    for garbage in ("I am not sure which one", "", "the second one probably", "abc"):
        llm = _FakeLlm(garbage)
        agent = mod.build(llm)
        decisions = agent.decide({"intent": _INTENT, "candidates": _CANDIDATES})
        d = decisions[0]
        # The intent shares tokens with "serialize_type" (serialize_type, name) far more
        # than with "save_user" -> the fallback must land on the correct candidate anyway.
        assert d.payload["function"] == "serialize_type", (
            f"garbage reply {garbage!r} should fall back to the content-matched candidate")
        assert d.payload["matched_by"] == "content_match_fallback"


def test_degeneracy_guard_falls_back_on_out_of_range_index():
    mod = _load_agent()
    llm = _FakeLlm("99")  # out of range for a 2-candidate set
    agent = mod.build(llm)
    decisions = agent.decide({"intent": _INTENT, "candidates": _CANDIDATES})
    assert decisions[0].payload["matched_by"] == "content_match_fallback"
    assert decisions[0].payload["function"] == "serialize_type"


def test_never_a_no_op_even_with_empty_intent():
    """The fallback must still pick SOME candidate (never a no-op) even when the intent
    gives no useful signal — ties break to the earliest candidate, deterministically."""
    mod = _load_agent()
    llm = _FakeLlm("not a number")
    agent = mod.build(llm)
    decisions = agent.decide({"intent": "", "candidates": _CANDIDATES})
    d = decisions[0]
    assert d.payload["function"] in {"save_user", "serialize_type"}
    assert d.payload["function"] == "save_user"  # tie -> earliest index


# ---------------------------------------------------------------------------
# (c) The resolver reuses locate_region and returns the right (start, end)
# ---------------------------------------------------------------------------

# A django-12125-shaped fixture (same shape as tests/test_swebench_live.py) so the
# resolver's reuse of locate_region is exercised on a realistic multi-function file.
_FILE_TEXT = (
    "import builtins\n"
    "\n"
    "class TypeSerializer:\n"
    "    def serialize(self):\n"
    "        special_cases = []\n"
    "        for case, string, imports in special_cases:\n"
    "            if case is self.value:\n"
    "                return string, set(imports)\n"
    "        if hasattr(self.value, \"__module__\"):\n"
    "            module = self.value.__module__\n"
    "            if module == builtins.__name__:\n"
    "                return self.value.__name__, set()\n"
    "            else:\n"
    "                return \"%s.%s\" % (module, self.value.__name__), {\"import %s\" % module}\n"
    "\n"
    "def other():\n"
    "    return 1\n"
)
_ANCHOR_LINE = 14  # the buggy `return "%s.%s" % (...)` line, 1-based


def test_resolver_reuses_locate_region_for_right_range():
    mod = _load_agent()
    from harness.swebench_live import locate_region

    expected = locate_region(_FILE_TEXT, _ANCHOR_LINE)
    start, end = mod.resolve_location(_FILE_TEXT, _ANCHOR_LINE)

    assert (start, end) == expected
    region = "\n".join(_FILE_TEXT.split("\n")[start:end])
    assert "def serialize(self):" in region
    assert "def other()" not in region


def test_resolve_decision_wrapper_matches_resolve_location():
    mod = _load_agent()
    llm = _FakeLlm("1")
    agent = mod.build(llm)
    decisions = agent.decide({
        "intent": "x",
        "candidates": [{"file": "serializer.py", "function": "serialize",
                         "anchor_line": _ANCHOR_LINE}],
    })
    d = decisions[0]
    assert d.payload["anchor_line"] == _ANCHOR_LINE

    start, end = mod.resolve_decision(d, _FILE_TEXT)
    assert (start, end) == mod.resolve_location(_FILE_TEXT, _ANCHOR_LINE)


# ---------------------------------------------------------------------------
# Structural: NAME constant and build() factory exist
# ---------------------------------------------------------------------------

def test_name_constant_and_build_factory_exist():
    mod = _load_agent()
    assert isinstance(mod.NAME, str) and mod.NAME
    assert callable(mod.build)


def test_build_returns_agent_with_decide():
    mod = _load_agent()
    agent = mod.build(_FakeLlm())
    assert hasattr(agent, "decide") and callable(agent.decide)


# --- locate_where: deterministic-signal-first WHERE-to-act (honest REQ-6 design) ---

def test_locate_where_prefers_traceback_signal():
    mod = _load_agent()
    tb = ('Traceback:\n  File "/testbed/pkg/serializers.py", line 14, in serialize_type\n'
          "    raise TypeError\n")
    dec = mod.locate_where({"target_file": "pkg/serializers.py", "traceback": tb,
                            "candidates": _CANDIDATES, "intent": _INTENT}, llm=_FakeLlm("1"))
    # deterministic: the exact failing line, no reliance on the (weak) model judgement
    assert dec.payload["matched_by"] == "traceback"
    assert dec.payload["anchor_line"] == 14


def test_locate_where_falls_back_to_model_without_signal():
    mod = _load_agent()
    dec = mod.locate_where({"candidates": _CANDIDATES, "intent": _INTENT}, llm=_FakeLlm("2"))
    assert dec.payload["matched_by"] == "model"
    assert dec.payload["function"] == "serialize_type"


def test_locate_where_no_signal_no_llm_is_inert():
    mod = _load_agent()
    dec = mod.locate_where({"target_file": "x.py"})  # no traceback, no llm -> inert, never crashes
    assert dec.type == "orchestrate.locate" and dec.payload["matched_by"] == "none"


def test_locate_where_uses_test_name_tier_without_traceback():
    mod = _load_agent()
    # no traceback -> deterministic failing-test-name -> function match, beats the (weak) model tier
    dec = mod.locate_where({"test_name": "test_serialize_type_qualified_name",
                            "candidates": _CANDIDATES}, llm=_FakeLlm("1"))
    assert dec.payload["matched_by"] == "test_name"
    assert dec.payload["function"] == "serialize_type"


# #EXT-013-REQ-6 End
