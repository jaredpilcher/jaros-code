"""OFFLINE tests for the Jaros-native routing layer (EXT-021, TASK-25).

Verifies:
  (a) route_native emits a model.route Decision through Runtime.apply and the
      DecisionLog records it.
  (b) ModelRewireTool.validate() rejects an unknown model_id and a non-on-device
      (fits_jetson=False) target — Tenet 1/2.
  (c) ModelRewireTool.execute() calls the (mocked) swap and returns an ok result.
  (d) solve_routed_native drives route->rewire->solve through ONE Runtime; the
      DecisionLog records both model.route and model.rewire in order (replayable).
  (e) solve_routed_native short-circuits honestly on rewire failure (Tenet 3).

All tests are OFFLINE: no live Jetson, no network call.  All swap / serving-state /
activate callables are injected stubs.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

import pytest

# Ensure the repo root is on sys.path for all harness imports.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TOOLS_DIR = _REPO_ROOT / ".jaros-data" / "tools"


# ---------------------------------------------------------------------------
# Helpers: offline stub registry / profiles
# ---------------------------------------------------------------------------

def _make_profile(model_id: str, fits_jetson: bool = True, **kwargs):
    from harness.model_registry import ModelProfile
    serve = {"gguf": f"/models/{model_id}.gguf", "ctx": 4096, "ngl": 99,
             "fits_jetson": fits_jetson}
    adaptation = kwargs.get("adaptation", {
        "tools": ["tool_a"], "agents": [], "config": {}, "prompts": {},
    })
    classes = kwargs.get("classes", [
        {"name": "standalone-fn-gen", "bar": "humaneval", "score": "76%", "date": "2026-01-01"}
    ])
    return ModelProfile(
        id=model_id, alias=model_id, serve=serve,
        classes=classes, adaptation=adaptation,
    )


def _make_registry(*profiles, default_id: Optional[str] = None):
    from harness.model_registry import ModelRegistry
    did = default_id or (profiles[0].id if profiles else "gemma-4-e2b")
    return ModelRegistry(profiles=list(profiles), default_id=did)


# Canonical offline profiles
_GEMMA = _make_profile("gemma-4-e2b")
_OFF_DEVICE = _make_profile("cloud-model-20b", fits_jetson=False)


def _stub_activate(adaptation: dict, alias: str) -> list:
    return [k for k in ("tools", "agents", "config", "prompts") if adaptation.get(k)]


# ---------------------------------------------------------------------------
# Helper: load model_rewire_tool.ModelRewireTool freshly for direct testing
# ---------------------------------------------------------------------------

def _load_rewire_tool():
    """Load ModelRewireTool via importlib (same path as load_custom_tools uses)."""
    spec = importlib.util.spec_from_file_location(
        "_test_model_rewire_tool",
        str(_TOOLS_DIR / "model_rewire_tool.py"),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.ModelRewireTool()


def _load_route_tool():
    """Load ModelRouteTool via importlib."""
    spec = importlib.util.spec_from_file_location(
        "_test_model_route_tool",
        str(_TOOLS_DIR / "model_route_tool.py"),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.ModelRouteTool()


# ---------------------------------------------------------------------------
# Helper: build a real Runtime with tmp_path isolation for DecisionLog tests
# ---------------------------------------------------------------------------

def _make_runtime(tmp_path: Path):
    from harness.coding_loop import Runtime
    return Runtime(data_dir=tmp_path)


def _logged_decision_types(rt) -> list[str]:
    """Return decision types recorded in rt's DecisionLog, in append order."""
    return [rec.decision.get("type") for rec in rt._dlog.read()]


# ---------------------------------------------------------------------------
# (a) route_native: emits a logged model.route Decision via Runtime
# ---------------------------------------------------------------------------

# #EXT-021-REQ-2 Start
class TestRouteNative:
    """route_native logs the routing Decision through the Runtime."""

    def test_returns_routing_dict(self, tmp_path):
        """route_native returns the same inert routing dict as route()."""
        from harness.model_router import route_native, route
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)
        problem = {"source": "def foo(x): ...", "has_examples": True}

        d_plain = route(problem, registry, record=False)
        d_native = route_native(problem, registry, rt, record=False)

        assert d_native["model_id"] == d_plain["model_id"]
        assert d_native["problem_class"] == d_plain["problem_class"]
        assert isinstance(d_native["confidence"], float)

    def test_decision_logged_in_decision_log(self, tmp_path):
        """route_native records a model.route Decision in the DecisionLog."""
        from harness.model_router import route_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)
        problem = {"source": "def bar(): pass", "has_examples": False}

        route_native(problem, registry, rt, record=False)

        logged = _logged_decision_types(rt)
        assert "model.route" in logged, (
            f"expected model.route in DecisionLog; got: {logged}"
        )

    def test_decision_payload_contains_model_id(self, tmp_path):
        """The logged model.route Decision's payload carries model_id."""
        from harness.model_router import route_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)
        problem = {"source": "def baz(): pass"}

        route_native(problem, registry, rt, record=False)

        records = list(rt._dlog.read())
        route_records = [r for r in records if r.decision.get("type") == "model.route"]
        assert route_records, "no model.route Decision in log"
        payload = route_records[0].decision.get("payload", {})
        assert "model_id" in payload
        assert payload["model_id"] == "gemma-4-e2b"

    def test_returns_same_class_as_route(self, tmp_path):
        """route_native and route() classify the same problem identically."""
        from harness.model_router import route_native, route
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)
        # Explicit repo task -> should classify as multi-step-repo
        problem = {"is_repo_task": True, "source": "..."}

        d_plain = route(problem, registry, record=False)
        d_native = route_native(problem, registry, rt, record=False)

        assert d_native["problem_class"] == d_plain["problem_class"]
# #EXT-021-REQ-2 End


# ---------------------------------------------------------------------------
# (b) ModelRewireTool.validate(): rejects unknown model_id + non-on-device
# ---------------------------------------------------------------------------

# #EXT-021-REQ-3 Start
class TestModelRewireToolValidate:
    """ModelRewireTool.validate() enforces Tenet 1/2 before any swap attempt."""

    def setup_method(self):
        """Reset injectable config before each test."""
        from harness._rewire_config import reset_all
        reset_all()

    def teardown_method(self):
        """Always reset config after each test (isolation)."""
        from harness._rewire_config import reset_all
        reset_all()

    def _make_decision(self, model_id: str):
        from jaros.core import create_decision
        return create_decision(
            id="test-rewire",
            source="test",
            type="model.rewire",
            payload={"model_id": model_id},
        )

    def test_accepts_known_on_device_model(self):
        """validate() accepts a known, on-device model_id."""
        from harness._rewire_config import set_registry
        registry = _make_registry(_GEMMA)
        set_registry(registry)

        tool = _load_rewire_tool()
        result = tool.validate(self._make_decision("gemma-4-e2b"))

        assert result.ok, f"expected accept; got reason: {result.reason}"

    def test_rejects_empty_model_id(self):
        """validate() rejects an empty model_id string."""
        tool = _load_rewire_tool()
        from jaros.core import create_decision
        decision = create_decision(
            id="t", source="s", type="model.rewire", payload={"model_id": ""}
        )
        result = tool.validate(decision)
        assert not result.ok

    def test_rejects_unknown_model_id(self):
        """validate() rejects a model_id not in the registry (Tenet 1)."""
        from harness._rewire_config import set_registry
        registry = _make_registry(_GEMMA)  # only gemma-4-e2b is known
        set_registry(registry)

        tool = _load_rewire_tool()
        result = tool.validate(self._make_decision("nonexistent-model-xyz"))

        assert not result.ok, "unknown model_id must be rejected by validate()"
        assert "nonexistent-model-xyz" in result.reason, (
            f"reason must name the bad model_id; got: {result.reason!r}"
        )

    def test_rejects_non_on_device_target(self):
        """validate() rejects a model with fits_jetson=False (Tenet 2)."""
        from harness._rewire_config import set_registry
        registry = _make_registry(_GEMMA, _OFF_DEVICE)
        set_registry(registry)

        tool = _load_rewire_tool()
        result = tool.validate(self._make_decision("cloud-model-20b"))

        assert not result.ok, "non-on-device model must be rejected by validate()"
        assert "fits_jetson" in result.reason or "off-device" in result.reason or "Tenet 2" in result.reason, (
            f"reason must mention Tenet 2 / off-device / fits_jetson; got: {result.reason!r}"
        )

    def test_accepts_without_registry_set(self):
        """When no registry is set, validate() does basic field checks only (accepts)."""
        # No set_registry() call — _rewire_config._registry is None
        tool = _load_rewire_tool()
        result = tool.validate(self._make_decision("any-model-id"))
        # Without a registry we cannot check model_id resolution; basic check passes.
        assert result.ok, (
            "without a registry, validate() should perform only basic field checks"
        )


# ---------------------------------------------------------------------------
# (c) ModelRewireTool.execute(): performs the (mocked) swap
# ---------------------------------------------------------------------------

class TestModelRewireToolExecute:
    """ModelRewireTool.execute() calls the injected swap_fn (mocked Jetson swap)."""

    def setup_method(self):
        from harness._rewire_config import reset_all
        reset_all()

    def teardown_method(self):
        from harness._rewire_config import reset_all
        reset_all()

    def _make_decision(self, model_id: str):
        from jaros.core import create_decision
        return create_decision(
            id="test-rewire-exec",
            source="test",
            type="model.rewire",
            payload={"model_id": model_id},
        )

    def test_execute_calls_mocked_swap(self):
        """execute() calls swap_fn exactly once with the target model_id."""
        from harness._rewire_config import set_registry, set_swap_fn, set_serving_state_fn, set_activate_fn

        swap_calls: list = []
        registry = _make_registry(_GEMMA)
        set_registry(registry)
        set_swap_fn(lambda mid: swap_calls.append(mid))
        set_serving_state_fn(lambda: None)   # unknown -> triggers swap
        set_activate_fn(_stub_activate)

        tool = _load_rewire_tool()
        result = tool.execute(self._make_decision("gemma-4-e2b"))

        assert len(swap_calls) == 1, f"swap_fn must be called once; called {len(swap_calls)} times"
        assert result.get("ok") is True, f"execute() must return ok=True on success: {result}"

    def test_execute_returns_ok_result(self):
        """execute() returns a dict with ok=True on a successful (mocked) swap."""
        from harness._rewire_config import set_registry, set_swap_fn, set_serving_state_fn, set_activate_fn

        registry = _make_registry(_GEMMA)
        set_registry(registry)
        set_swap_fn(lambda mid: None)             # no-op swap
        set_serving_state_fn(lambda: None)
        set_activate_fn(_stub_activate)

        tool = _load_rewire_tool()
        result = tool.execute(self._make_decision("gemma-4-e2b"))

        assert isinstance(result, dict)
        assert result.get("ok") is True
        assert result.get("tool") == "model.rewire"

    def test_execute_returns_ok_false_on_swap_failure(self):
        """execute() surfaces swap failures honestly (Tenet 3)."""
        from harness._rewire_config import set_registry, set_swap_fn, set_serving_state_fn, set_activate_fn

        def _failing_swap(mid: str) -> None:
            raise RuntimeError("Jetson unreachable")

        registry = _make_registry(_GEMMA)
        set_registry(registry)
        set_swap_fn(_failing_swap)
        set_serving_state_fn(lambda: None)
        set_activate_fn(_stub_activate)

        tool = _load_rewire_tool()
        result = tool.execute(self._make_decision("gemma-4-e2b"))

        assert result.get("ok") is False, "failed swap must produce ok=False"
        assert result.get("error") is not None, "error must be non-None (Tenet 3)"
        assert "Jetson unreachable" in str(result.get("error")), (
            "error must surface the original exception message"
        )

    def test_execute_returns_ok_false_without_registry(self):
        """execute() returns ok=False when no registry is configured."""
        # No set_registry() call
        tool = _load_rewire_tool()
        result = tool.execute(self._make_decision("gemma-4-e2b"))

        assert result.get("ok") is False
        assert "registry" in str(result.get("error", "")).lower()
# #EXT-021-REQ-3 End


# ---------------------------------------------------------------------------
# (d) + (e) solve_routed_native: full route->rewire->solve on ONE Runtime
# ---------------------------------------------------------------------------

# #EXT-021-REQ-2 Start (native)
# #EXT-021-REQ-3 Start (native)
class TestSolveRoutedNative:
    """solve_routed_native runs the full Jaros-native flow on a single Runtime."""

    def _stub_solve(self, problem, decision, rewire_result):
        return {"code": "def foo(): pass", "self_pass": True}

    def _stub_swap(self, model_id: str) -> None:
        """No-op mocked swap (no Jetson call)."""
        pass

    def test_applied_decisions_contains_route_and_rewire(self, tmp_path):
        """solve_routed_native applies model.route then model.rewire (in that order)."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        result = solve_routed_native(
            {"source": "def foo(): pass", "has_examples": True},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        assert "model.route" in result["applied_decisions"], (
            f"model.route missing from applied_decisions: {result['applied_decisions']}"
        )
        assert "model.rewire" in result["applied_decisions"], (
            f"model.rewire missing from applied_decisions: {result['applied_decisions']}"
        )

    def test_decision_log_records_both_types(self, tmp_path):
        """The DecisionLog records model.route + model.rewire in order (replayable)."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        solve_routed_native(
            {"source": "def foo(): pass"},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        logged = _logged_decision_types(rt)
        assert "model.route" in logged, f"model.route not in DecisionLog: {logged}"
        assert "model.rewire" in logged, f"model.rewire not in DecisionLog: {logged}"
        # Route must appear before rewire
        assert logged.index("model.route") < logged.index("model.rewire"), (
            f"model.route must precede model.rewire; order: {logged}"
        )

    def test_returns_ok_true_on_success(self, tmp_path):
        """solve_routed_native returns ok=True when route + rewire + solve succeed."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        result = solve_routed_native(
            {"source": "def foo(): pass"},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is True
        assert result["error"] is None
        assert result["solve"] is not None

    def test_short_circuits_on_rewire_failure(self, tmp_path):
        """solve_routed_native returns ok=False and solve=None when the swap fails (Tenet 3)."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        def _failing_swap(mid: str) -> None:
            raise RuntimeError("swap failed in test")

        result = solve_routed_native(
            {"source": "def foo(): pass"},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=_failing_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False
        assert result["solve"] is None, "solve must NOT be called when rewire fails"
        assert result["error"] is not None

    def test_solve_result_is_returned(self, tmp_path):
        """solve_routed_native threads the solve result through to the caller."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        sentinel = {"code": "def sentinel(): pass", "self_pass": True}

        result = solve_routed_native(
            {"source": "def foo(): pass"},
            registry,
            runtime=rt,
            solve_fn=lambda p, d, r: sentinel,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        assert result["solve"] == sentinel

    def test_decision_dict_is_correct(self, tmp_path):
        """result['decision'] contains model_id and problem_class from routing."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        result = solve_routed_native(
            {"source": "def foo(x): ...", "has_examples": True},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        assert "model_id" in result["decision"]
        assert "problem_class" in result["decision"]
        assert result["decision"]["model_id"] == "gemma-4-e2b"

    def test_decision_log_replayable_entries_present(self, tmp_path):
        """DecisionLog entries for model.route + model.rewire carry correct payloads."""
        from harness.solve_routed import solve_routed_native
        rt = _make_runtime(tmp_path)
        registry = _make_registry(_GEMMA)

        solve_routed_native(
            {"source": "def foo(): pass"},
            registry,
            runtime=rt,
            solve_fn=self._stub_solve,
            swap_fn=self._stub_swap,
            serving_state=lambda: None,
            activate_fn=_stub_activate,
        )

        records = list(rt._dlog.read())
        route_recs = [r for r in records if r.decision.get("type") == "model.route"]
        rewire_recs = [r for r in records if r.decision.get("type") == "model.rewire"]

        assert route_recs, "model.route must have a DecisionLog entry"
        assert rewire_recs, "model.rewire must have a DecisionLog entry"

        # model.route payload must carry model_id
        route_payload = route_recs[0].decision.get("payload", {})
        assert "model_id" in route_payload

        # model.rewire payload must carry model_id
        rewire_payload = rewire_recs[0].decision.get("payload", {})
        assert "model_id" in rewire_payload
        assert rewire_payload["model_id"] == route_payload["model_id"]
# #EXT-021-REQ-3 End (native)
# #EXT-021-REQ-2 End (native)
