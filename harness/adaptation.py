"""Per-model adaptation registry (EXT-021, REQ-3).

Each model profile's ``adaptation`` field declares the code-gen style the model
uses.  This module maps those style labels to a code-gen callable with a
**uniform signature**::

    code_gen(subject_or_spec: str, name: str, context: str = "") -> str

The registry is intentionally thin — each entry is a lazy shim (no import cost
until the callable is actually invoked).

Labels
------
``"qwen-instruct-direct"``
    Direct instruct prompt — Qwen-Coder's proven style (no Gherkin scaffolding).
    Backed by ``harness.qwen_adapt.qwen_code``.

``"gherkin-decompose"``
    Gherkin-decompose pipeline — Gemma's path: ``g_gherkin`` then ``g_code``.
    Do NOT change ``harness.commit_replay``; the wrapper adapts the signature only.

``"r1-reasoning"``
    Reasoning-model path — DeepSeek-R1-Distill-Qwen-7B's chain-of-thought style.
    Strips ``<think>...</think>`` block, extracts the LAST fenced code block.
    Backed by ``harness.r1_adapt.r1_code``.

DEFAULT fallback
    Any unknown or missing label resolves to ``"gherkin-decompose"`` (Gemma's
    path).  ``code_gen_for`` NEVER raises — safe to call with any input.
"""
from __future__ import annotations

from typing import Any, Callable

# #EXT-021-REQ-3 Start

# ---------------------------------------------------------------------------
# Code-gen shims (lazy imports — no Jetson connection at import time)
# ---------------------------------------------------------------------------

def _gemma_gherkin_code_gen(subject_or_spec: str, name: str, context: str = "") -> str:
    """Thin wrapper: Gemma's gherkin-decompose path (g_gherkin -> g_code).

    Calls ``g_gherkin`` to produce a Gherkin behaviour spec, then ``g_code``
    to generate the function body.  Signature matches the uniform registry
    interface; ``g_code``/``g_gherkin`` internals are NOT changed.
    """
    from harness.commit_replay import g_gherkin, g_code  # noqa: PLC0415
    gherkin = g_gherkin(subject_or_spec, name, None, context)
    return g_code(subject_or_spec, name, None, context, gherkin)


def _qwen_instruct_code_gen(subject_or_spec: str, name: str, context: str = "") -> str:
    """Thin shim: Qwen's direct instruct path (qwen_code).

    Maps the uniform ``(spec, name, context)`` signature onto
    ``harness.qwen_adapt.qwen_code``'s identical signature.
    """
    from harness.qwen_adapt import qwen_code  # noqa: PLC0415
    return qwen_code(subject_or_spec, name, context)


def _r1_reasoning_code_gen(subject_or_spec: str, name: str, context: str = "") -> str:
    """Thin shim: DeepSeek-R1-Distill-Qwen-7B reasoning path (r1_code).

    Strips ``<think>...</think>`` reasoning trace and extracts the LAST fenced
    code block — R1 reasons at length before emitting the final answer.
    Maps the uniform ``(spec, name, context)`` signature onto
    ``harness.r1_adapt.r1_code``'s identical signature.
    """
    from harness.r1_adapt import r1_code  # noqa: PLC0415
    return r1_code(subject_or_spec, name, context)


# ---------------------------------------------------------------------------
# Registry: style label -> code-gen callable
# ---------------------------------------------------------------------------

ADAPTATION_REGISTRY: dict[str, Callable[[str, str, str], str]] = {
    "gherkin-decompose": _gemma_gherkin_code_gen,
    "qwen-instruct-direct": _qwen_instruct_code_gen,
    "r1-reasoning": _r1_reasoning_code_gen,
}

_DEFAULT_LABEL: str = "gherkin-decompose"


# ---------------------------------------------------------------------------
# Label extraction helpers
# ---------------------------------------------------------------------------

def _extract_label(profile_or_adaptation: Any) -> str:
    """Extract the style label from a profile, adaptation dict, label string, or None.

    Label resolution order
    ----------------------
    1. ``str``  — treated as the label directly.
    2. Object with ``.adaptation`` attr (``ModelProfile``) — reads the adaptation dict.
    3. ``dict`` — reads ``["prompts"]`` then ``["solve_style"]``.
       If ``["prompts"]`` is itself a dict (Gemma's nested form), reads
       ``["prompts"]["solve_style"]`` inside it.
    4. Anything else / any error → ``_DEFAULT_LABEL``.
    """
    try:
        if profile_or_adaptation is None:
            return _DEFAULT_LABEL
        if isinstance(profile_or_adaptation, str):
            return profile_or_adaptation or _DEFAULT_LABEL

        # ModelProfile: has .adaptation attribute
        if hasattr(profile_or_adaptation, "adaptation"):
            adaptation: Any = profile_or_adaptation.adaptation
        elif isinstance(profile_or_adaptation, dict):
            adaptation = profile_or_adaptation
        else:
            return _DEFAULT_LABEL

        # "prompts" key: may be a string label (qwen) or a nested dict (gemma)
        label: Any = adaptation.get("prompts") or adaptation.get("solve_style")
        if isinstance(label, dict):
            # Gemma: {"prompts": {"solve_style": "gherkin-decompose", ...}}
            label = label.get("solve_style")
        if not label or not isinstance(label, str):
            return _DEFAULT_LABEL
        return label
    except Exception:  # noqa: BLE001
        return _DEFAULT_LABEL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def code_gen_for(
    profile_or_adaptation: Any,
) -> Callable[[str, str, str], str]:
    """Return the code-gen callable for *profile_or_adaptation*.

    Parameters
    ----------
    profile_or_adaptation :
        One of:
        - A ``ModelProfile`` instance (reads ``.adaptation``).
        - An adaptation ``dict`` (reads ``["prompts"]`` / ``["solve_style"]``).
        - A style label ``str`` (used directly).
        - ``None`` or anything else → DEFAULT fallback.

    Returns
    -------
    Callable[[str, str, str], str]
        A code-gen callable with signature ``(subject_or_spec, name, context) -> str``.
        NEVER raises — unknown or missing labels silently fall back to
        ``"gherkin-decompose"`` (Gemma's path).
    """
    label = _extract_label(profile_or_adaptation)
    return ADAPTATION_REGISTRY.get(label, ADAPTATION_REGISTRY[_DEFAULT_LABEL])

# #EXT-021-REQ-3 End
