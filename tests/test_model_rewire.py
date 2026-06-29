"""Tests for harness/model_rewire.py — EXT-021 TASK-3 (REQ-3).

All tests are OFFLINE: serving_state / swap_fn / activate_fn are injected
stubs; no live Jetson, no network call, no real filesystem writes (except
where explicitly tested with tmp_path).

Acceptance criteria covered
----------------------------
(a) Target already served  -> swapped=False, swap_fn NOT called, adaptation active.
(b) Target differs         -> swap_fn called once with the target's serve params,
                              swapped=True, served_after == target alias.
(c) Mocked swap FAILURE    -> ok=False with an honest non-empty error string
                              surfaced in the return dict, never hidden.
(d) Unknown model_id       -> ok=False with honest error naming the bad id.
(e) Guarded _jetson_swap   -> accepts serve-params dict only; passing an
                              arbitrary command string (or any non-dict) raises
                              TypeError; dict with no gguf raises ValueError.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_registry import ModelProfile, ModelRegistry
from harness.model_rewire import (
    rewire,
    _jetson_swap,
    _manager_current,
    _manager_swap,
)


# ---------------------------------------------------------------------------
# Helpers: build offline stub profiles + registries
# ---------------------------------------------------------------------------

def _make_profile(
    model_id: str,
    alias: Optional[str] = None,
    serve: Optional[dict] = None,
    adaptation: Optional[dict] = None,
) -> ModelProfile:
    return ModelProfile(
        id=model_id,
        alias=alias if alias is not None else model_id,
        serve=serve if serve is not None else {
            "gguf": f"/models/{model_id}.gguf",
            "ctx": 4096,
            "ngl": 99,
            "fits_jetson": True,
        },
        classes=[],
        adaptation=adaptation if adaptation is not None else {
            "tools": ["tool_a"],
            "agents": ["agent_b"],
            "config": {"backend": "llamacpp"},
            "prompts": {"solve_style": "gherkin-decompose"},
        },
    )


def _make_registry(*profiles: ModelProfile) -> ModelRegistry:
    default_id = profiles[0].id if profiles else "gemma-4-e2b"
    return ModelRegistry(profiles=list(profiles), default_id=default_id)


# Canonical profiles used across tests
_GEMMA = _make_profile("gemma-4-e2b", alias="gemma-4-e2b")
_STRONG = _make_profile("strong-7b", alias="strong-7b")


def _stub_activate(adaptation: dict, alias: str) -> list:
    """Offline stub activate: returns category names that have non-empty values."""
    return [k for k in ("tools", "agents", "config", "prompts") if adaptation.get(k)]


# ---------------------------------------------------------------------------
# (a) Target already served -> no swap, adaptation still activated
# ---------------------------------------------------------------------------

class TestAlreadyServed:
    """rewire() to a model that IS already served -> swapped=False, no swap call."""

    def test_no_swap_when_already_served(self):
        registry = _make_registry(_GEMMA)
        swap_calls: list = []

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: "gemma-4-e2b",       # already serving it
            swap_fn=lambda p: swap_calls.append(p),
            activate_fn=_stub_activate,
        )

        assert result["swapped"] is False
        assert swap_calls == [], "swap_fn must NOT be called when model is already served"

    def test_adaptation_active_even_without_swap(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is True
        assert len(result["adaptation_active"]) > 0, (
            "adaptation_active must be non-empty even when no swap occurs"
        )

    def test_served_before_and_after_are_target_alias(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["served_before"] == "gemma-4-e2b"
        assert result["served_after"] == "gemma-4-e2b"

    def test_idempotent_multiple_rewires_no_swap(self):
        """Re-rewiring to the same model repeatedly never triggers a swap."""
        registry = _make_registry(_GEMMA)
        swap_count = [0]

        def counting_swap(params: dict) -> None:
            swap_count[0] += 1

        for _ in range(3):
            rewire(
                "gemma-4-e2b",
                registry,
                serving_state=lambda: "gemma-4-e2b",
                swap_fn=counting_swap,
                activate_fn=_stub_activate,
            )

        assert swap_count[0] == 0, "swap must never be called across multiple idempotent rewires"

    def test_ok_true_when_already_served(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is True
        assert result["error"] is None


# ---------------------------------------------------------------------------
# (b) Target differs -> swap_fn called once with target's serve params
# ---------------------------------------------------------------------------

class TestSwapDifferentModel:
    """rewire() to a different model -> swap_fn called once with correct serve params."""

    def test_swap_called_once_with_model_id(self):
        """swap_fn is called exactly once, receiving the target model_id string."""
        registry = _make_registry(_GEMMA, _STRONG)
        swap_calls: list = []

        rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",       # currently serving gemma
            swap_fn=lambda p: swap_calls.append(p),
            activate_fn=_stub_activate,
        )

        assert len(swap_calls) == 1, "swap_fn must be called exactly once"
        # swap_fn now receives the model_id string (not the serve-params dict);
        # the manager API accepts the id directly.
        assert swap_calls[0] == "strong-7b", (
            "swap_fn must receive the target model_id string"
        )

    def test_swapped_true_after_different_model(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["swapped"] is True

    def test_served_after_is_target_alias(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["served_after"] == "strong-7b"

    def test_served_before_is_original(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["served_before"] == "gemma-4-e2b"

    def test_ok_true_on_success(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is True
        assert result["error"] is None

    def test_adaptation_active_after_swap(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert len(result["adaptation_active"]) > 0

    def test_model_id_in_result_matches_requested(self):
        registry = _make_registry(_GEMMA, _STRONG)

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["model_id"] == "strong-7b"

    def test_serving_state_none_triggers_swap(self):
        """If serving_state returns None (first run), a swap is still performed."""
        registry = _make_registry(_GEMMA)
        swap_calls: list = []

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: None,            # no prior state
            swap_fn=lambda p: swap_calls.append(p),
            activate_fn=_stub_activate,
        )

        assert len(swap_calls) == 1, (
            "Unknown prior state (None) should trigger a swap to ensure the target is live"
        )
        assert result["swapped"] is True


# ---------------------------------------------------------------------------
# (c) Mocked swap FAILURE -> ok=False, honest error surfaced
# ---------------------------------------------------------------------------

class TestSwapFailure:
    """A swap_fn that raises -> ok=False, error is a non-empty honest string."""

    def test_swap_failure_returns_ok_false(self):
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise RuntimeError("SSH connection refused")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False

    def test_swap_failure_has_non_empty_error(self):
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise RuntimeError("SSH connection refused")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert result["error"] is not None
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0, (
            "error must be a non-empty string — Tenet 3 (honest, never hidden)"
        )

    def test_swap_failure_error_contains_exception_reason(self):
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise RuntimeError("SSH connection refused")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert "SSH connection refused" in result["error"], (
            "The original exception message must appear in the error (Tenet 3)"
        )

    def test_swap_failure_swapped_is_false(self):
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise ValueError("bad gguf path")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert result["swapped"] is False

    def test_swap_failure_served_after_is_none(self):
        """After a failed swap, served_after must be None (swap did not happen)."""
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise OSError("device unreachable")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert result["served_after"] is None

    def test_value_error_from_swap_also_surfaces_honestly(self):
        registry = _make_registry(_STRONG)

        def failing_swap(params: dict) -> None:
            raise ValueError("bad param")

        result = rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=failing_swap,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False
        assert "bad param" in result["error"]


# ---------------------------------------------------------------------------
# (d) Unknown model_id -> ok=False, honest error naming the bad id
# ---------------------------------------------------------------------------

class TestUnknownModelId:
    """registry has no profile for model_id -> ok=False, error names the id."""

    def test_unknown_id_ok_false(self):
        registry = _make_registry(_GEMMA)
        swap_calls: list = []

        result = rewire(
            "nonexistent-model-xyz",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda p: swap_calls.append(p),
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False
        assert swap_calls == [], "swap_fn must NOT be called for unknown model"

    def test_unknown_id_has_honest_error_naming_the_id(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "nonexistent-model-xyz",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["error"] is not None
        assert "nonexistent-model-xyz" in result["error"], (
            "error must contain the unknown model_id for honest diagnosis (Tenet 3)"
        )

    def test_unknown_id_swapped_false(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "nonexistent-model-xyz",
            registry,
            serving_state=lambda: None,
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["swapped"] is False

    def test_unknown_id_adaptation_active_empty(self):
        registry = _make_registry(_GEMMA)

        result = rewire(
            "nonexistent-model-xyz",
            registry,
            serving_state=lambda: None,
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["adaptation_active"] == []

    def test_empty_registry_unknown_id_ok_false(self):
        """Even with an empty registry, an unknown id returns ok=False honestly."""
        registry = ModelRegistry(profiles=[], default_id="gemma-4-e2b")

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: None,
            swap_fn=lambda _: None,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False
        assert "gemma-4-e2b" in result["error"]


# ---------------------------------------------------------------------------
# (e) Guarded _jetson_swap: accepts serve-params dict only
# ---------------------------------------------------------------------------

class TestJetsonSwapGuard:
    """_jetson_swap must NOT accept an arbitrary command string — Tenet 1."""

    def test_signature_has_exactly_one_param_named_serve_params(self):
        """The sole parameter must be named 'serve_params' — not a command."""
        sig = inspect.signature(_jetson_swap)
        params = list(sig.parameters.values())
        assert len(params) == 1, (
            f"_jetson_swap must have exactly 1 parameter, got {len(params)}: "
            f"{[p.name for p in params]}"
        )
        assert params[0].name == "serve_params", (
            f"Parameter must be named 'serve_params', got '{params[0].name}'"
        )

    def test_passing_string_raises_type_error(self):
        """An arbitrary command string must be rejected with TypeError."""
        with pytest.raises(TypeError):
            _jetson_swap("sudo systemctl restart gemma")  # type: ignore[arg-type]

    def test_passing_shell_injection_string_raises_type_error(self):
        """A shell-injection attempt string must raise TypeError immediately."""
        with pytest.raises(TypeError):
            _jetson_swap("sudo rm -rf /")  # type: ignore[arg-type]

    def test_passing_list_raises_type_error(self):
        """A list (potential argv injection) must raise TypeError."""
        with pytest.raises(TypeError):
            _jetson_swap(["sudo", "systemctl", "restart", "gemma"])  # type: ignore[arg-type]

    def test_passing_none_raises_type_error(self):
        """None is not a valid serve-params dict."""
        with pytest.raises(TypeError):
            _jetson_swap(None)  # type: ignore[arg-type]

    def test_passing_int_raises_type_error(self):
        """An int is not a serve-params dict."""
        with pytest.raises(TypeError):
            _jetson_swap(42)  # type: ignore[arg-type]

    def test_dict_without_gguf_raises_value_error(self):
        """A dict missing 'gguf' must raise ValueError before any SSH call."""
        with pytest.raises(ValueError):
            _jetson_swap({"ctx": 4096, "ngl": 99})

    def test_dict_with_empty_gguf_raises_value_error(self):
        """A dict with an empty 'gguf' string must raise ValueError."""
        with pytest.raises(ValueError):
            _jetson_swap({"gguf": "", "ctx": 4096, "ngl": 99})

    def test_dict_with_whitespace_only_gguf_raises_value_error(self):
        """A whitespace-only 'gguf' must also raise ValueError."""
        with pytest.raises(ValueError):
            _jetson_swap({"gguf": "   ", "ctx": 4096, "ngl": 99})

    def test_serve_params_annotation_is_dict(self):
        """The type annotation for serve_params must be dict (or absent).

        ``from __future__ import annotations`` stores annotations as strings
        at runtime, so we accept both the live type and its string form.
        """
        sig = inspect.signature(_jetson_swap)
        param = list(sig.parameters.values())[0]
        annotation = param.annotation
        if annotation is not inspect.Parameter.empty:
            assert annotation in (dict, "dict"), (
                f"serve_params annotation should be 'dict', got {annotation!r}"
            )

    def test_error_message_mentions_tenet_1_or_arbitrary(self):
        """The TypeError must explain the guard (arbitrary command forbidden)."""
        with pytest.raises(TypeError) as exc_info:
            _jetson_swap("rm -rf /")  # type: ignore[arg-type]
        msg = str(exc_info.value).lower()
        assert "arbitrary" in msg or "forbidden" in msg or "tenet" in msg, (
            f"TypeError message should mention 'arbitrary', 'forbidden', or 'Tenet': {msg!r}"
        )


# ---------------------------------------------------------------------------
# Return-dict schema sanity
# ---------------------------------------------------------------------------

class TestReturnSchema:
    """Ensure every rewire() path returns the expected dict schema."""

    _REQUIRED_KEYS = {"model_id", "swapped", "served_before", "served_after",
                      "adaptation_active", "ok", "error"}

    def _assert_schema(self, result: dict) -> None:
        assert isinstance(result, dict)
        missing = self._REQUIRED_KEYS - result.keys()
        assert not missing, f"Missing keys in result: {missing}"
        assert isinstance(result["swapped"], bool)
        assert isinstance(result["ok"], bool)
        assert isinstance(result["adaptation_active"], list)

    def test_schema_on_success_no_swap(self):
        registry = _make_registry(_GEMMA)
        result = rewire(
            "gemma-4-e2b", registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None, activate_fn=_stub_activate,
        )
        self._assert_schema(result)

    def test_schema_on_success_with_swap(self):
        registry = _make_registry(_GEMMA, _STRONG)
        result = rewire(
            "strong-7b", registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: None, activate_fn=_stub_activate,
        )
        self._assert_schema(result)

    def test_schema_on_unknown_model(self):
        registry = _make_registry(_GEMMA)
        result = rewire(
            "unknown-xyz", registry,
            serving_state=lambda: None,
            swap_fn=lambda _: None, activate_fn=_stub_activate,
        )
        self._assert_schema(result)

    def test_schema_on_swap_failure(self):
        registry = _make_registry(_STRONG)
        result = rewire(
            "strong-7b", registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda _: (_ for _ in ()).throw(RuntimeError("fail")),
            activate_fn=_stub_activate,
        )
        self._assert_schema(result)


# ---------------------------------------------------------------------------
# Manager HTTP control API unit tests — OFFLINE (urlopen mocked, no network)
# ---------------------------------------------------------------------------

class TestManagerHttp:
    """Unit tests for _manager_current and _manager_swap — mocked urlopen, no network."""

    # -- helpers --------------------------------------------------------------

    def _make_cm(self, response_body: dict) -> MagicMock:
        """Return a mock context manager yielding response_body JSON bytes."""
        cm = MagicMock()
        cm.read.return_value = json.dumps(response_body).encode()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    # -- _manager_swap: correct POST URL + body --------------------------------

    def test_manager_swap_posts_to_serve_url(self):
        """_manager_swap must POST to {base}/serve."""
        ok_body = {"ok": True, "current": "gemma-4-e2b", "swapped": True, "ready": True}
        cm = self._make_cm(ok_body)
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return cm

        with patch("urllib.request.urlopen", fake_urlopen):
            _manager_swap("gemma-4-e2b")

        assert len(captured) == 1
        assert captured[0].full_url.endswith("/serve"), (
            f"Expected URL to end with '/serve', got: {captured[0].full_url!r}"
        )

    def test_manager_swap_post_body_contains_model_id(self):
        """_manager_swap body must be JSON {\"model\": model_id}."""
        ok_body = {"ok": True, "current": "qwen2.5-coder-3b", "swapped": True, "ready": True}
        cm = self._make_cm(ok_body)
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return cm

        with patch("urllib.request.urlopen", fake_urlopen):
            _manager_swap("qwen2.5-coder-3b")

        posted = json.loads(captured[0].data.decode())
        assert posted == {"model": "qwen2.5-coder-3b"}, (
            f"POST body must be {{\"model\": model_id}}, got {posted!r}"
        )

    def test_manager_swap_returns_response_dict_on_success(self):
        """_manager_swap returns the manager response dict on success."""
        ok_body = {"ok": True, "current": "gemma-4-e2b", "swapped": True, "ready": True}
        cm = self._make_cm(ok_body)

        with patch("urllib.request.urlopen", lambda req, timeout=None: cm):
            result = _manager_swap("gemma-4-e2b")

        assert result["ok"] is True
        assert result["ready"] is True

    # -- _manager_swap: honest failure on ok=false ----------------------------

    def test_manager_swap_raises_on_ok_false(self):
        """_manager_swap raises RuntimeError if manager response has ok=false."""
        fail_body = {"ok": False, "current": None, "swapped": False, "ready": False}
        cm = self._make_cm(fail_body)

        with patch("urllib.request.urlopen", lambda req, timeout=None: cm):
            with pytest.raises(RuntimeError) as exc_info:
                _manager_swap("qwen2.5-coder-3b")

        msg = str(exc_info.value).lower()
        assert "ok" in msg or "ready" in msg, (
            f"RuntimeError must mention 'ok' or 'ready', got: {msg!r}"
        )

    def test_manager_swap_raises_on_ready_false(self):
        """_manager_swap raises RuntimeError if ready=false even when ok=true."""
        body = {"ok": True, "current": "gemma-4-e2b", "swapped": True, "ready": False}
        cm = self._make_cm(body)

        with patch("urllib.request.urlopen", lambda req, timeout=None: cm):
            with pytest.raises(RuntimeError):
                _manager_swap("gemma-4-e2b")

    def test_manager_swap_raises_on_network_error(self):
        """_manager_swap raises RuntimeError if the manager is unreachable."""
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            with pytest.raises(RuntimeError) as exc_info:
                _manager_swap("gemma-4-e2b")
        assert "unreachable" in str(exc_info.value).lower() or "connection" in str(exc_info.value).lower()

    # -- _manager_current: returns current field -------------------------------

    def test_manager_current_returns_current_field(self):
        """_manager_current returns the 'current' field string on success."""
        ok_body = {"current": "gemma-4-e2b", "serving_ok": True}
        cm = self._make_cm(ok_body)

        with patch("urllib.request.urlopen", lambda url, timeout=None: cm):
            result = _manager_current()

        assert result == "gemma-4-e2b"

    def test_manager_current_returns_none_on_network_error(self):
        """_manager_current returns None if the endpoint is unreachable."""
        with patch("urllib.request.urlopen", side_effect=OSError("unreachable")):
            result = _manager_current()
        assert result is None

    def test_manager_current_returns_none_on_null_current(self):
        """_manager_current returns None when the manager reports current=null."""
        ok_body = {"current": None, "serving_ok": False}
        cm = self._make_cm(ok_body)

        with patch("urllib.request.urlopen", lambda url, timeout=None: cm):
            result = _manager_current()

        assert result is None

    # -- rewire() integration: ok=False on manager failure --------------------

    def test_rewire_ok_false_when_manager_swap_fails(self):
        """rewire() returns ok=False if the injected swap_fn raises (manager failure)."""
        registry = _make_registry(_GEMMA)

        def manager_fail_swap(model_id: str):
            raise RuntimeError("Manager swap not ok/ready: ok=False, ready=False")

        result = rewire(
            "gemma-4-e2b",
            registry,
            serving_state=lambda: None,   # unknown -> swap triggered
            swap_fn=manager_fail_swap,
            activate_fn=_stub_activate,
        )

        assert result["ok"] is False
        assert result["error"] is not None
        assert "ok=False" in result["error"] or "False" in result["error"]

    def test_rewire_swap_fn_receives_model_id_string(self):
        """rewire() passes the model_id string (not serve dict) to swap_fn."""
        registry = _make_registry(_GEMMA, _STRONG)
        captured = []

        rewire(
            "strong-7b",
            registry,
            serving_state=lambda: "gemma-4-e2b",
            swap_fn=lambda mid: captured.append(mid),
            activate_fn=_stub_activate,
        )

        assert len(captured) == 1
        assert captured[0] == "strong-7b", (
            f"swap_fn must receive the model_id string, got {captured[0]!r}"
        )
