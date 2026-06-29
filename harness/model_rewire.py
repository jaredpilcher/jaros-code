"""Deterministic rewire clerk — multi-model routing harness (EXT-021, REQ-3).

Given a model_id from the router's Decision, ``rewire()`` makes the harness
BECOME that model: swap the Jetson llama.cpp serving params if needed, point
the LLM client at the chosen alias, and activate that model's adaptation
(tools/agents/config/prompts).

Public entry point::

    result = rewire(model_id, registry)
    # -> {model_id, swapped, served_before, served_after,
    #     adaptation_active, ok, error}

All three side-effecting operations (swap, client update, activation) are
injectable so the module is OFFLINE-testable without a live Jetson.

Tenet guarantees
----------------
Tenet 1: the swap path is a constrained clerk — ``_jetson_swap`` accepts only
    a validated serve-params dict and cannot run an arbitrary command string.
Tenet 2: the Jetson swap is scoped to the single known device and never
    escalates off-device (SSH to a fixed host, fixed service name only).
Tenet 3: all failures are surfaced honestly in the return dict; nothing is
    hidden or silently swallowed.
"""
from __future__ import annotations

# #EXT-021-REQ-3 Start
import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# State file — tracks the currently-active model alias (offline-readable)
# ---------------------------------------------------------------------------
_STATE_PATH: Path = (
    Path(os.environ.get("JAROS_DATA_DIR", str(Path(__file__).parent.parent / ".jaros-data")))
    / "state"
    / "active_model.json"
)

# Fixed Jetson SSH host (not user-supplied — Tenet 2: no off-device escalation)
_JETSON_SSH_HOST: str = os.environ.get("JETSON_SSH_HOST", "jetson")


# ---------------------------------------------------------------------------
# SSH fallback swap — guarded, constrained, never arbitrary; NOT the default
# (Default swap path is _manager_swap via the HTTP model-manager API below.)
# ---------------------------------------------------------------------------

def _jetson_swap(serve_params: dict) -> None:
    """SSH fallback: swap the Jetson llama.cpp model via gemma.service env + restart.

    Accepts ONLY a validated serve-params dict (keys: gguf, ctx, ngl).
    It does NOT accept or execute an arbitrary command string — Tenet 1.
    It targets only the fixed Jetson device (``_JETSON_SSH_HOST``) — Tenet 2
    (never off-device).  Any failure raises an exception, which ``rewire()``
    surfaces — Tenet 3.

    Parameters
    ----------
    serve_params : dict
        Must be a plain ``dict`` with at least a non-empty ``gguf`` key
        (path to the ``.gguf`` file on the Jetson).  Optional ``ctx``
        (context size, int) and ``ngl`` (GPU layers, int).

    Raises
    ------
    TypeError
        If *serve_params* is not a ``dict`` — guards against arbitrary
        command injection (Tenet 1).
    ValueError
        If the ``gguf`` key is absent or empty.
    RuntimeError
        If the SSH command exits non-zero or times out.
    """
    if not isinstance(serve_params, dict):
        raise TypeError(
            f"_jetson_swap accepts only a serve-params dict, "
            f"not {type(serve_params).__name__!r}. "
            "Passing an arbitrary command string is forbidden (Tenet 1)."
        )

    gguf: str = str(serve_params.get("gguf", "")).strip()
    if not gguf:
        raise ValueError(
            "serve_params must include a non-empty 'gguf' path for the Jetson swap"
        )

    ctx: int = int(serve_params.get("ctx", 4096))
    ngl: int = int(serve_params.get("ngl", 99))

    # Build the remote command from VALIDATED, type-safe values only.
    # shlex.quote() ensures the gguf path cannot inject shell metacharacters.
    # The command structure is FIXED; no user-supplied string is ever executed.
    remote_cmd = (
        "sudo systemctl set-environment "
        f"LLAMACPP_GGUF={shlex.quote(gguf)} "
        f"LLAMACPP_CTX={ctx} "
        f"LLAMACPP_NGL={ngl} "
        "&& sudo systemctl restart gemma"
    )

    result = subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            _JETSON_SSH_HOST,
            remote_cmd,
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Jetson swap failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )


# ---------------------------------------------------------------------------
# Jetson model-manager HTTP control API (default swap + serving-state path)
# ---------------------------------------------------------------------------


def _manager_base() -> str:
    """Return the model-manager control URL.

    Configurable via env var ``JCODE_MODEL_MANAGER_URL``.  Defaults to the
    fixed LAN address of the Jetson model-manager daemon (port 8001).
    """
    return os.environ.get("JCODE_MODEL_MANAGER_URL", "http://192.168.1.183:8001")


def _manager_current() -> Optional[str]:
    """Query the on-device model-manager for the currently-served model id.

    GET {_manager_base()}/current -> {"current": "<model_id>"|null, "serving_ok": bool}

    Returns the ``"current"`` field string, or ``None`` on any error (network
    unreachable, timeout, JSON parse error, etc.) — the caller treats ``None``
    as "unknown / not yet serving" and triggers a swap to the target.

    This is the DEFAULT ``serving_state`` provider for ``rewire()``.
    """
    try:
        url = f"{_manager_base()}/current"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return data.get("current") or None
    except Exception:
        return None


def _manager_swap(model_id: str) -> dict:
    """Swap the Jetson to *model_id* via the model-manager HTTP control API.

    POST {_manager_base()}/serve  body: {"model": model_id}

    The manager daemon blocks until llama-server is up on :8000 (typically
    15-20 s) and returns ``{"ok": True, "current": ..., "swapped": ...,
    "ready": True}`` on success.  Raises ``RuntimeError`` honestly if the
    manager returns a non-ok/non-ready response or if the endpoint is
    unreachable — Tenet 3.

    This is the DEFAULT ``swap_fn`` for ``rewire()``.  The manager daemon
    (``scripts/jetson_model_manager.py``) is the ONLY agent that touches
    llama-server; this call never escalates off-device beyond the LAN
    control endpoint — Tenet 2.

    Parameters
    ----------
    model_id : str
        The model id as known to the manager catalog
        (e.g. ``"gemma-4-e2b"``, ``"qwen2.5-coder-3b"``).

    Returns
    -------
    dict
        The manager's response body: ``{ok, current, swapped, ready}``.

    Raises
    ------
    RuntimeError
        If the manager is unreachable, returns an HTTP error, or its
        response has ``ok=false`` / ``ready=false`` — always raised, never
        silently swallowed (Tenet 3).
    """
    url = f"{_manager_base()}/serve"
    body = json.dumps({"model": model_id}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result: dict = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Manager HTTP error {exc.code}: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Manager unreachable: {exc}") from exc

    if not result.get("ok") or not result.get("ready"):
        raise RuntimeError(
            f"Manager swap not ok/ready: "
            f"ok={result.get('ok')!r}, ready={result.get('ready')!r}, "
            f"response={result!r}"
        )
    return result


# ---------------------------------------------------------------------------
# Default serving-state provider (reads local state file — no network call)
# ---------------------------------------------------------------------------

def _default_serving_state() -> Optional[str]:
    """Return the alias of the currently-active model from local state.

    Reads ``.jaros-data/state/active_model.json`` written by the last
    successful ``rewire()``.  Returns ``None`` if no state file exists yet
    (first run — will trigger a swap to the target model).

    Purely local I/O — no network call, fully offline-safe and stubbable.
    """
    if _STATE_PATH.is_file():
        try:
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return data.get("alias")
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Default activate function (records active adaptation in state file)
# ---------------------------------------------------------------------------

def _default_activate_fn(adaptation: dict, alias: str) -> list:
    """Record the chosen model's adaptation set as the active harness config.

    Writes to ``.jaros-data/state/active_model.json`` so subsequent reads
    of ``_default_serving_state()`` see the new alias.

    Returns a list of activated component-category names (non-empty keys
    among tools, agents, config, prompts).
    """
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {"alias": alias, "adaptation": adaptation}
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    activated = []
    for key in ("tools", "agents", "config", "prompts"):
        if adaptation.get(key):
            activated.append(key)
    return activated


# ---------------------------------------------------------------------------
# LLM client pointer (env-var update, pure, no I/O)
# ---------------------------------------------------------------------------

def _point_client_at(alias: str) -> None:
    """Point the active LLM client at *alias* via the ``LLAMACPP_MODEL`` env var.

    Any subsequently constructed ``DeterministicLlamaCppClient()`` (or any
    client that reads ``LLAMACPP_MODEL``) will pick up the new alias.
    Pure environment mutation — no network, no file I/O.
    """
    os.environ["LLAMACPP_MODEL"] = alias


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def rewire(
    model_id: str,
    registry: Any,
    *,
    serving_state: Optional[Callable[[], Optional[str]]] = None,
    swap_fn: Optional[Callable[[str], Any]] = None,
    activate_fn: Optional[Callable[[dict, str], Any]] = None,
) -> dict:
    """Deterministically rewire the harness to *model_id*.

    Resolves the profile, checks the currently-served model, swaps only when
    needed (idempotent), points the LLM client at the chosen alias, and
    activates the model's adaptation set (tools/agents/config/prompts).

    Parameters
    ----------
    model_id : str
        The registry id to rewire to.  Must exist in *registry*.
    registry :
        A ``ModelRegistry`` instance (``harness.model_registry``).
    serving_state :
        Optional callable ``() -> str | None`` returning the id/alias of the
        currently-served model.  Default is ``_manager_current``, which
        queries the on-device model-manager HTTP API (GET /current) and
        returns ``None`` on any error (triggers a swap to ensure the target
        is live).  Inject a lambda stub for unit tests.
    swap_fn :
        Optional callable ``(model_id: str) -> Any`` that performs the
        Jetson model swap.  Default is ``_manager_swap``, which POST-s to
        the on-device model-manager HTTP control API — no SSH required (the
        manager daemon is the only agent that touches llama-server — Tenet 2).
        Inject a mock for unit tests so no live Jetson or network is needed.
        The old SSH path (``_jetson_swap``) is still importable as a labeled
        fallback but is no longer the default.
    activate_fn :
        Optional callable ``(adaptation: dict, alias: str) -> Any`` that
        records and activates the model's adaptation.  Default writes
        ``active_model.json``.  Inject a stub for unit tests.

    Returns
    -------
    dict
        ``{model_id, swapped, served_before, served_after,
           adaptation_active, ok, error}``

        ``ok`` is ``False`` with an honest ``error`` string on any failure
        (unknown id, swap failure, activation failure) — Tenet 3 guarantees
        every failure path is surfaced, never hidden.

    Tenet guarantees
    ----------------
    - **Tenet 1**: ``_jetson_swap`` accepts only a serve-params dict; no
      arbitrary command execution path exists.
    - **Tenet 2**: swap uses the LAN model-manager control endpoint only;
      the manager daemon owns llama-server — we never escalate off-device.
    - **Tenet 3**: all failures are in the return dict; none are hidden.
    - **Idempotent**: re-rewiring to the already-served model performs no swap
      and still ensures activation is current.
    """
    # -- resolve callables (defaults when not injected) ----------------------
    _ss: Callable[[], Optional[str]] = (
        serving_state if serving_state is not None else _manager_current
    )
    _swap: Callable[[str], Any] = (
        swap_fn if swap_fn is not None else _manager_swap
    )
    _activate: Callable[[dict, str], Any] = (
        activate_fn if activate_fn is not None else _default_activate_fn
    )

    # 1. Resolve profile — honest error if unknown (Tenet 3) -----------------
    profile = registry.lookup_by_id(model_id)
    if profile is None:
        return {
            "model_id": model_id,
            "swapped": False,
            "served_before": None,
            "served_after": None,
            "adaptation_active": [],
            "ok": False,
            "error": f"Unknown model_id '{model_id}' — not found in registry",
        }

    # 2. Determine currently-served model (injected or default state reader) -
    try:
        served_before: Optional[str] = _ss()
    except Exception:
        # State-read failure treated as "unknown" — safer to attempt the swap
        served_before = None

    # 3. Guard swap: only swap when served alias differs from target -----------
    #    (idempotent: no swap when already serving the target)
    swapped = False
    if served_before != profile.alias:
        try:
            _swap(model_id)
            swapped = True
        except Exception as exc:
            return {
                "model_id": model_id,
                "swapped": False,
                "served_before": served_before,
                "served_after": None,
                "adaptation_active": [],
                "ok": False,
                "error": f"Swap failed: {exc}",
            }

    # 4. Point the active LLM client at the new/current alias -----------------
    _point_client_at(profile.alias)

    # 5. Activate adaptation (tools/agents/config/prompts for this model) -----
    try:
        activated = _activate(profile.adaptation, profile.alias)
    except Exception as exc:
        return {
            "model_id": model_id,
            "swapped": swapped,
            "served_before": served_before,
            "served_after": profile.alias,
            "adaptation_active": [],
            "ok": False,
            "error": f"Activation failed: {exc}",
        }

    activated_list = list(activated) if isinstance(activated, (set, list)) else []

    return {
        "model_id": model_id,
        "swapped": swapped,
        "served_before": served_before,
        "served_after": profile.alias,
        "adaptation_active": activated_list,
        "ok": True,
        "error": None,
    }
# #EXT-021-REQ-3 End
