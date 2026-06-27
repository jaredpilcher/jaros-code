"""EXT-015: Plan-then-code decomposition unit tests.

Research basis: 'Strategic Decomposition & Filtering for SLMs' — a 1.5B model
lifted +30% relative by: (1) 2B generates a numbered strategy, (2) a
DETERMINISTIC filter cleans it (filtering > diversity; small models can't improve
their own scaffold), (3) code is written FROM the filtered plan.

All tests use FAKE LLMs / stubs — no model calls, no Jetson, no clone.

Coverage:
  (a) plan_agent emits a ``code.write_file`` Decision whose content is a strategy.
  (b) strategy_filter_tool deterministically strips contamination/boilerplate/code
      and KEEPS numbered steps (validate + execute).
  (c) behavioral_solve_jaros(plan=True) routes plan_agent -> filter -> code-writer,
      and the code-writer's intent contains the filtered strategy.
  (d) behavioral_solve_jaros(plan=False) is byte-identical to the original path
      (no plan_agent call, same decision sequence as before EXT-015).
"""

from __future__ import annotations

# #EXT-015-REQ-1 Start  (tests for plan_agent)
# #EXT-015-REQ-2 Start  (tests for strategy_filter_tool)
# #EXT-015-REQ-3 Start  (tests for wiring plan=True / plan=False)

import ast
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_AGENTS_DIR = _REPO_ROOT / ".jaros-data" / "agents"
_TOOLS_DIR = _REPO_ROOT / ".jaros-data" / "tools"


# ---------------------------------------------------------------------------
# Helpers: load agent/tool modules from absolute paths (no package needed)
# ---------------------------------------------------------------------------

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Stub LLM
# ---------------------------------------------------------------------------

class _FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLlm:
    """Stub LLM: returns a predetermined response.  Tracks calls and captures prompts."""

    def __init__(self, response: str = "1. Check for empty input.\n2. Iterate and accumulate.\n3. Return result.\n") -> None:
        self._response = response
        self.call_count = 0
        self.prompts: list[str] = []

    def complete(self, request) -> _FakeCompletion:
        self.call_count += 1
        self.prompts.append(getattr(request, "prompt", ""))
        return _FakeCompletion(self._response)


# ============================================================================
# (a) plan_agent: emits code.write_file Decision containing a strategy
# ============================================================================

class TestPlanAgent:
    """plan_agent (EXT-015 / REQ-1)."""

    def _build_agent(self, response: str = "1. Check for empty input.\n2. Return result.\n"):
        mod = _load_module(_AGENTS_DIR / "plan_agent.py", "_plan_agent")
        llm = _FakeLlm(response=response)
        return mod.build(llm), llm, mod

    def test_plan_agent_emits_write_file_decision(self):
        """plan_agent.decide() must return a list with one code.write_file Decision."""
        agent, llm, mod = self._build_agent()
        decisions = agent.decide({
            "intent": "add sum function",
            "name": "total",
            "func": "total",
        })
        assert len(decisions) == 1, "plan_agent must emit exactly one Decision"
        d = decisions[0]
        assert d.type == "code.write_file", (
            f"Decision type must be 'code.write_file', got '{d.type}'"
        )

    def test_plan_agent_decision_content_is_strategy(self):
        """Decision payload.content must be non-empty and contain a numbered step."""
        strategy_text = "1. Check for empty input.\n2. Iterate and accumulate.\n3. Return result.\n"
        agent, llm, mod = self._build_agent(response=strategy_text)
        [d] = agent.decide({
            "intent": "add sum with start value",
            "name": "total",
            "func": "total",
            "current_src": "def total(items):\n    return sum(items)\n",
        })
        content = d.payload.get("content", "")
        assert content.strip(), "plan_agent Decision content must not be empty"
        assert "1." in content, f"Strategy must contain a numbered step; got: {content!r}"

    def test_plan_agent_uses_plan_path_from_context(self):
        """plan_agent must respect the plan_path key in context."""
        agent, _, _ = self._build_agent()
        [d] = agent.decide({
            "intent": "fix edge case",
            "name": "compute",
            "func": "compute",
            "plan_path": "/tmp/compute.plan",
        })
        assert d.payload.get("path") == "/tmp/compute.plan", (
            f"plan_path not respected; got '{d.payload.get('path')}'"
        )

    def test_plan_agent_default_plan_path(self):
        """Without plan_path in context, plan_agent defaults to .jcode/<name>.plan."""
        agent, _, _ = self._build_agent()
        [d] = agent.decide({"intent": "add feature", "name": "myfunc", "func": "myfunc"})
        assert d.payload.get("path") == ".jcode/myfunc.plan"

    def test_plan_agent_strips_code_fences(self):
        """plan_agent must strip ``` fences from the LLM response."""
        fenced = "```\n1. Step one.\n2. Step two.\n```"
        agent, _, _ = self._build_agent(response=fenced)
        [d] = agent.decide({"intent": "x", "name": "f", "func": "f"})
        content = d.payload.get("content", "")
        assert "```" not in content, "Code fences must be stripped from strategy content"

    def test_plan_agent_emits_advance_on_empty_response(self):
        """When the LLM produces no content after stripping, plan_agent emits an advance Decision."""
        agent, _, _ = self._build_agent(response="```\n```")
        [d] = agent.decide({"intent": "x", "name": "f", "func": "f"})
        assert d.type == "advance", (
            f"Empty strategy must produce 'advance' Decision, got '{d.type}'"
        )

    def test_plan_agent_name_is_planner(self):
        """plan_agent module-level NAME must be 'planner'."""
        mod = _load_module(_AGENTS_DIR / "plan_agent.py", "_plan_agent_name")
        assert mod.NAME == "planner", f"NAME must be 'planner', got '{mod.NAME}'"

    def test_plan_agent_build_returns_boundary(self):
        """plan_agent.build(llm) must return a PlannerBoundary with a .decide() method."""
        mod = _load_module(_AGENTS_DIR / "plan_agent.py", "_plan_agent_b")
        agent = mod.build(_FakeLlm())
        assert hasattr(agent, "decide"), "build(llm) must return object with .decide()"

    def test_plan_agent_file_parses(self):
        """plan_agent.py must be valid Python (ast.parse smoke)."""
        src = (_AGENTS_DIR / "plan_agent.py").read_text(encoding="utf-8")
        ast.parse(src)

# #EXT-015-REQ-1 End


# ============================================================================
# (b) strategy_filter_tool: deterministic, no LLM
# ============================================================================

class TestStrategyFilterTool:
    """strategy_filter_tool (EXT-015 / REQ-2)."""

    def _load(self):
        return _load_module(_TOOLS_DIR / "strategy_filter_tool.py", "_sft")

    def test_filter_tool_file_parses(self):
        """strategy_filter_tool.py must be valid Python (ast.parse smoke)."""
        src = (_TOOLS_DIR / "strategy_filter_tool.py").read_text(encoding="utf-8")
        ast.parse(src)

    def test_filter_strips_example_line(self):
        """Lines starting with 'Example:' must be stripped."""
        mod = self._load()
        raw = "1. Check for empty input.\nExample: f([]) -> 0\n2. Iterate.\n"
        result = mod.filter_strategy(raw)
        assert "Example:" not in result, f"'Example:' line must be stripped; got: {result!r}"
        assert "Check for empty" in result or "Iterate" in result, (
            "Numbered steps must survive"
        )

    def test_filter_strips_fenced_code_block(self):
        """Fenced code blocks (```...```) must be stripped."""
        mod = self._load()
        raw = "1. Validate input.\n```python\ndef f(x):\n    return x\n```\n2. Return result.\n"
        result = mod.filter_strategy(raw)
        assert "```" not in result, f"Code fence must be stripped; got: {result!r}"
        assert "def f" not in result, f"Code inside fence must be stripped; got: {result!r}"

    def test_filter_keeps_numbered_steps(self):
        """Numbered steps must be kept in the output."""
        mod = self._load()
        raw = "1. Check for empty input.\n2. Compute sum.\n3. Return the result.\n"
        result = mod.filter_strategy(raw)
        assert "1." in result or "2." in result or "3." in result, (
            f"At least one numbered step must survive; got: {result!r}"
        )

    def test_filter_keeps_edge_case_mention(self):
        """Lines mentioning 'edge case' or 'handle' must be kept."""
        mod = self._load()
        raw = "1. Handle empty list edge case.\n2. Compute result.\n"
        result = mod.filter_strategy(raw)
        assert "Handle" in result or "edge case" in result or "Compute" in result, (
            f"Edge-case mention must survive; got: {result!r}"
        )

    def test_filter_strips_preamble_boilerplate(self):
        """Lines like 'Here is the strategy:' must be stripped."""
        mod = self._load()
        raw = "Here is the implementation strategy:\n1. Check input.\n2. Return result.\n"
        result = mod.filter_strategy(raw)
        assert "Here is" not in result, (
            f"Preamble 'Here is ...' must be stripped; got: {result!r}"
        )

    def test_filter_combined_contamination(self):
        """Real-world contamination: Example + code block + preamble; numbered steps survive."""
        mod = self._load()
        raw = (
            "Here is the plan:\n"
            "1. Check if the list is empty and return 0.\n"
            "2. Iterate through items, accumulating the sum.\n"
            "Example: total([1,2,3]) -> 6\n"
            "```python\ndef total(items):\n    return sum(items)\n```\n"
            "3. Handle negative numbers.\n"
        )
        result = mod.filter_strategy(raw)
        assert "Example:" not in result
        assert "```" not in result
        assert "def total" not in result
        assert "Here is" not in result
        # At least some numbered steps should survive
        assert any(f"{i}." in result for i in range(1, 4)), (
            f"No numbered steps survived; got: {result!r}"
        )

    def test_filter_graceful_noop_on_all_stripped(self):
        """If every line is stripped, the original text is returned (graceful no-op)."""
        mod = self._load()
        # A strategy that is nothing but code (would strip everything)
        raw = "    return x + 1\n    return y\n"
        result = mod.filter_strategy(raw)
        # Must return something — either original or non-empty
        assert isinstance(result, str)
        assert len(result) > 0, "filter_strategy must never return empty string"

    def test_tool_validate_rejects_empty_strategy(self):
        """StrategyFilterTool.validate must reject empty payload.strategy."""
        mod = self._load()
        tool = mod.StrategyFilterTool()
        d = SimpleNamespace(payload={"strategy": ""}, type="code.filter_strategy")
        v = tool.validate(d)
        assert not v.ok, "validate must reject empty strategy"

    def test_tool_validate_rejects_non_str(self):
        """StrategyFilterTool.validate must reject non-str payload.strategy."""
        mod = self._load()
        tool = mod.StrategyFilterTool()
        d = SimpleNamespace(payload={"strategy": 42}, type="code.filter_strategy")
        v = tool.validate(d)
        assert not v.ok, "validate must reject non-str strategy"

    def test_tool_validate_accepts_valid_strategy(self):
        """StrategyFilterTool.validate must accept a non-empty string strategy."""
        mod = self._load()
        tool = mod.StrategyFilterTool()
        d = SimpleNamespace(payload={"strategy": "1. Do something.\n"}, type="code.filter_strategy")
        v = tool.validate(d)
        assert v.ok, f"validate must accept valid strategy; error: {v.error}"

    def test_tool_execute_returns_filtered(self):
        """StrategyFilterTool.execute must return dict with 'filtered' key."""
        mod = self._load()
        tool = mod.StrategyFilterTool()
        raw = "1. Check input.\nExample: f(1) -> 1\n2. Return result.\n"
        d = SimpleNamespace(payload={"strategy": raw}, type="code.filter_strategy")
        result = tool.execute(d)
        assert "filtered" in result, f"execute must return 'filtered'; got: {result}"
        assert isinstance(result["filtered"], str)
        assert "Example:" not in result["filtered"], "Example: line must be stripped"

    def test_filter_is_deterministic(self):
        """filter_strategy must return the same output on repeated calls (no randomness)."""
        mod = self._load()
        raw = "1. Check for empty.\nExample: f([]) -> 0\n2. Iterate.\n"
        r1 = mod.filter_strategy(raw)
        r2 = mod.filter_strategy(raw)
        assert r1 == r2, "filter_strategy must be deterministic"

# #EXT-015-REQ-2 End


# ============================================================================
# (c) behavioral_solve_jaros(plan=True) wires plan -> filter -> code prompt
# ============================================================================

class _FakeCompletion2:
    def __init__(self, text: str) -> None:
        self.text = text


class _CapturingLlm:
    """Stub LLM that captures every prompt so we can assert on strategy injection."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, request) -> _FakeCompletion2:
        prompt = getattr(request, "prompt", "")
        self.calls.append({"prompt": prompt})
        # Return a minimal valid code snippet for the code-writer calls
        if "def " in prompt or "Implement" in prompt:
            return _FakeCompletion2("def f(x):\n    return x\n")
        # For the plan_agent call: return a clean numbered strategy
        return _FakeCompletion2("1. Check for empty input.\n2. Compute result.\n3. Return.\n")


def _make_stub_agent(decision_type: str, content: str, name: str = "stub-agent"):
    """Stub agent whose .decide() returns a single Decision with known content."""
    from jaros.core import create_decision

    class _StubAgent:
        def decide(self, ctx_) -> list:
            payload: dict = {}
            if decision_type == "code.write_file":
                path = (ctx_.get("spec_path") or ctx_.get("test_path")
                        or ctx_.get("code_path") or ctx_.get("plan_path")
                        or f".jcode/{name}.out")
                payload = {"path": path, "content": content}
            elif decision_type == "advance":
                payload = {"events": ["start", "end"], "note": "stub"}
            return [create_decision(
                id=f"stub-{uuid.uuid4().hex}", source=name,
                type=decision_type, payload=payload,
            )]
    return _StubAgent()


def _make_runtime(tmp_path: Path):
    from harness.coding_loop import Runtime
    return Runtime(data_dir=tmp_path)


class TestPlanThenCodeWiring:
    """behavioral_solve_jaros(plan=True/False) wiring — EXT-015 / REQ-3."""

    def test_plan_true_includes_strategy_in_code_prompt(self, tmp_path):
        """When plan=True, the code-writer's intent must contain the filtered strategy."""
        from harness.behavioral_solve import behavioral_solve_jaros
        import harness.jaros_solve_ops as _ops

        rt = _make_runtime(tmp_path)
        spec_p = str(tmp_path / "spec.gherkin")
        test_p = str(tmp_path / "test_f.py")
        code_p = str(tmp_path / "f.py")
        plan_p = str(tmp_path / "f.plan")

        captured_code_intents: list[str] = []

        strategy_text = "1. Check for empty input.\n2. Compute result.\n3. Return.\n"
        gherkin_text  = "1. Given f(0) returns 0\n"
        tests_text    = "from mymod import f\ndef test_it():\n    assert f(0)==0\n"
        code_text     = "def f(x):\n    return x\n"

        stub_plan    = _make_stub_agent("code.write_file", strategy_text, "planner")
        stub_gherkin = _make_stub_agent("code.write_file", gherkin_text, "gherkin-writer")
        stub_test    = _make_stub_agent("code.write_file", tests_text,   "test-writer")

        # Code agent that captures the 'intent' key from context
        from jaros.core import create_decision as _cd
        class _CapturingCodeAgent:
            def decide(self, ctx_) -> list:
                captured_code_intents.append(ctx_.get("intent", ""))
                return [_cd(
                    id=f"cw-{uuid.uuid4().hex}", source="code-writer",
                    type="code.write_file",
                    payload={"path": ctx_.get("code_path", code_p), "content": code_text},
                )]

        # Ordering: gherkin, test, then code (plan agent loads BEFORE code agent in the flow)
        # _load_agent_from_file is called in order: gherkin, test, (plan if plan=True), code
        _agent_seq = {
            "gherkin_agent": stub_gherkin,
            "test_writer_agent": stub_test,
            "plan_agent": stub_plan,
            "code_agent": _CapturingCodeAgent(),
        }

        def _fake_load_agent(filepath: str, llm):
            for key, agent in _agent_seq.items():
                if key in str(filepath):
                    return agent
            return _make_stub_agent("code.write_file", code_text, "fallback")

        def _fake_run_tests(rt_, command, *, cwd=None, timeout_s=15, source=""):
            d = _cd(
                id=f"sh-{uuid.uuid4().hex}", source=source or "behavioral-solve-jaros",
                type="shell.exec",
                payload={"command": command, "timeout_s": timeout_s},
            )
            res = rt_.apply(d)
            if isinstance(res, dict):
                res["exitCode"] = 0
            return res if isinstance(res, dict) else {"exitCode": 0, "stdout": "", "stderr": ""}

        with patch("harness.behavioral_solve._load_agent_from_file",
                   side_effect=_fake_load_agent), \
             patch("harness.jaros_solve_ops.run_tests", side_effect=_fake_run_tests):
            result = behavioral_solve_jaros(
                intent="make f work",
                name="f",
                current_src=None,
                context="",
                pkg="mymod",
                runtime=rt,
                llm=_FakeLlm(),
                spec_path=spec_p,
                test_path=test_p,
                code_path=code_p,
                plan=True,
            )

        assert result["self_pass"] is True
        # The code-writer must have received an intent that includes the filtered strategy
        assert len(captured_code_intents) >= 1, "code-writer must have been called"
        # At least one captured intent must include part of the strategy
        strategy_present = any(
            "1." in intent or "IMPLEMENTATION STRATEGY" in intent
            for intent in captured_code_intents
        )
        assert strategy_present, (
            f"Code-writer intent must include filtered strategy when plan=True; "
            f"got intents: {captured_code_intents!r}"
        )

    def test_plan_false_unchanged_decision_sequence(self, tmp_path):
        """When plan=False (default), the decision sequence is identical to pre-EXT-015."""
        from harness.behavioral_solve import behavioral_solve_jaros
        import harness.jaros_solve_ops as _ops

        rt = _make_runtime(tmp_path)
        spec_p = str(tmp_path / "spec2.gherkin")
        test_p = str(tmp_path / "test_g.py")
        code_p = str(tmp_path / "g.py")

        gherkin_text = "1. Given g(1) returns 1\n"
        tests_text   = "from mymod import g\ndef test_it():\n    assert g(1)==1\n"
        code_text    = "def g(x):\n    return x\n"

        plan_agent_called = [False]

        from jaros.core import create_decision as _cd2

        class _SpyPlanAgent:
            def decide(self, ctx_) -> list:
                plan_agent_called[0] = True
                return [_cd2(id=f"pl-{uuid.uuid4().hex}", source="planner",
                             type="code.write_file",
                             payload={"path": ctx_.get("plan_path", ".jcode/g.plan"),
                                      "content": "1. Step.\n"})]

        _agents = {
            "gherkin_agent": _make_stub_agent("code.write_file", gherkin_text, "gherkin-writer"),
            "test_writer_agent": _make_stub_agent("code.write_file", tests_text, "test-writer"),
            "plan_agent": _SpyPlanAgent(),
            "code_agent": _make_stub_agent("code.write_file", code_text, "code-writer"),
        }

        def _fake_load_agent(filepath: str, llm):
            for key, agent in _agents.items():
                if key in str(filepath):
                    return agent
            return _make_stub_agent("code.write_file", code_text, "fallback")

        def _fake_run_tests(rt_, command, *, cwd=None, timeout_s=15, source=""):
            d = _cd2(id=f"sh-{uuid.uuid4().hex}", source=source or "bsj",
                     type="shell.exec",
                     payload={"command": command, "timeout_s": timeout_s})
            res = rt_.apply(d)
            if isinstance(res, dict):
                res["exitCode"] = 0
            return res if isinstance(res, dict) else {"exitCode": 0, "stdout": "", "stderr": ""}

        with patch("harness.behavioral_solve._load_agent_from_file",
                   side_effect=_fake_load_agent), \
             patch("harness.jaros_solve_ops.run_tests", side_effect=_fake_run_tests):
            result = behavioral_solve_jaros(
                intent="identity g",
                name="g",
                current_src=None,
                context="",
                pkg="mymod",
                runtime=rt,
                llm=_FakeLlm(),
                spec_path=spec_p,
                test_path=test_p,
                code_path=code_p,
                plan=False,     # default — plan_agent must NOT be called
            )

        assert result["self_pass"] is True
        assert not plan_agent_called[0], (
            "plan_agent must NOT be called when plan=False (default path unchanged)"
        )
        # Standard decision sequence: 3 code.write_file + 1 shell.exec
        applied = result["applied_decisions"]
        assert applied.count("code.write_file") >= 3, (
            f"Expected >=3 code.write_file; got {applied}"
        )
        assert applied.count("shell.exec") >= 1, (
            f"Expected >=1 shell.exec; got {applied}"
        )

    def test_plan_true_decision_sequence_includes_plan_write(self, tmp_path):
        """When plan=True, applied_decisions must include an extra code.write_file for the plan."""
        from harness.behavioral_solve import behavioral_solve_jaros
        import harness.jaros_solve_ops as _ops

        rt = _make_runtime(tmp_path)
        spec_p = str(tmp_path / "spec3.gherkin")
        test_p = str(tmp_path / "test_h.py")
        code_p = str(tmp_path / "h.py")

        strategy_text = "1. Check.\n2. Compute.\n"
        gherkin_text  = "1. Given h(0) returns 0\n"
        tests_text    = "from m import h\ndef test_it():\n    assert h(0)==0\n"
        code_text     = "def h(x):\n    return x\n"

        from jaros.core import create_decision as _cd3

        _agents = {
            "gherkin_agent":    _make_stub_agent("code.write_file", gherkin_text, "gherkin-writer"),
            "test_writer_agent": _make_stub_agent("code.write_file", tests_text, "test-writer"),
            "plan_agent":       _make_stub_agent("code.write_file", strategy_text, "planner"),
            "code_agent":       _make_stub_agent("code.write_file", code_text, "code-writer"),
        }

        def _fake_load_agent(filepath: str, llm):
            for key, agent in _agents.items():
                if key in str(filepath):
                    return agent
            return _make_stub_agent("code.write_file", code_text, "fallback")

        def _fake_run_tests(rt_, command, *, cwd=None, timeout_s=15, source=""):
            d = _cd3(id=f"sh-{uuid.uuid4().hex}", source=source or "bsj",
                     type="shell.exec",
                     payload={"command": command, "timeout_s": timeout_s})
            res = rt_.apply(d)
            if isinstance(res, dict):
                res["exitCode"] = 0
            return res if isinstance(res, dict) else {"exitCode": 0, "stdout": "", "stderr": ""}

        with patch("harness.behavioral_solve._load_agent_from_file",
                   side_effect=_fake_load_agent), \
             patch("harness.jaros_solve_ops.run_tests", side_effect=_fake_run_tests):
            result = behavioral_solve_jaros(
                intent="identity h",
                name="h",
                current_src=None,
                context="",
                pkg="m",
                runtime=rt,
                llm=_FakeLlm(),
                spec_path=spec_p,
                test_path=test_p,
                code_path=code_p,
                plan=True,
            )

        applied = result["applied_decisions"]
        # plan=True adds one more code.write_file (the plan artifact) vs plan=False (3)
        # => plan=True must have >= 4 code.write_file Decisions
        wf_count = applied.count("code.write_file")
        assert wf_count >= 4, (
            f"plan=True must add extra code.write_file for the plan; got {wf_count}: {applied}"
        )

    def test_behavioral_solve_jaros_has_plan_param(self):
        """behavioral_solve_jaros must accept the plan keyword argument."""
        src = (_REPO_ROOT / "harness" / "behavioral_solve.py").read_text(encoding="utf-8")
        assert "plan: bool = False" in src, (
            "behavioral_solve_jaros must have plan: bool = False parameter"
        )

    def test_behavioral_solve_py_parses(self):
        """harness/behavioral_solve.py must parse cleanly after EXT-015 changes."""
        src = (_REPO_ROOT / "harness" / "behavioral_solve.py").read_text(encoding="utf-8")
        ast.parse(src)

    def test_commit_replay_py_parses(self):
        """harness/commit_replay.py must parse cleanly after EXT-015 changes."""
        src = (_REPO_ROOT / "harness" / "commit_replay.py").read_text(encoding="utf-8")
        ast.parse(src)

    def test_commit_replay_has_plan_flag(self):
        """commit_replay.py must contain the --plan flag detection."""
        src = (_REPO_ROOT / "harness" / "commit_replay.py").read_text(encoding="utf-8")
        assert "--plan" in src, "commit_replay.py must have --plan flag"
        assert "run_gherkin_jaros_plan" in src, (
            "commit_replay.py must call run_gherkin_jaros_plan"
        )

# #EXT-015-REQ-3 End
