"""Execution-plane tool ``code.repair`` (EXT-013 / REQ-2).

Parse-gated syntax-repair tool: wraps ``repair_indentation`` from the proven
body_completer_agent so the repair step runs through the Runtime gate -> executor ->
DecisionLog path instead of as a direct function call. Implements the Tenet-1
two-plane discipline for the repair grain.

Decision payload:
  content  (str, required)  — Python source to repair.
  seed     (int, optional)  — RNG seed for the LLM repair call (default 0).

Returns:
  {"tool": "code.repair", "content": <str>, "repaired": <bool>}

The tool validates that ``content`` is a non-empty string, then calls
``repair_indentation``. If the source already parses cleanly, ``repaired`` is
False and the content is returned unchanged (the parse gate skips the LLM call).

Test-injection
--------------
Call ``set_llm_factory(fn)`` before applying the Decision to inject a stub LLM
(zero-argument callable returning an llm-like object with ``.complete()``).
Call ``set_llm_factory(None)`` to restore production behaviour.  The factory is
kept module-level (NOT in the Decision payload) because ``create_decision``
enforces JSON-only payloads and functions are not serialisable.
"""

from __future__ import annotations

import ast
import sys
import os

from jaros.core.decision_gate import ValidationResult

# #EXT-013-REQ-2 Start

NAME = "code.repair"

# Module-level injection point for tests (never touches the Decision payload).
_llm_factory = None  # type: ignore[assignment]


def set_llm_factory(fn) -> None:  # noqa: ANN001
    """Set (or clear) the LLM factory used by RepairTool.execute.

    *fn* must be a zero-argument callable returning an llm-like object with a
    ``.complete(LlmRequest) -> obj`` method where ``obj.text`` is the completion.
    Pass ``None`` to restore the production path (``harness.coding_loop.build_llm``).
    """
    global _llm_factory  # noqa: PLW0603
    _llm_factory = fn


def _parses(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


class RepairTool:
    NAME = "code.repair"

    def validate(self, decision) -> ValidationResult:
        payload = decision.payload if isinstance(decision.payload, dict) else {}
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            return ValidationResult.reject(
                "code.repair requires a non-empty 'content' string"
            )
        return ValidationResult.accept(decision)

    def execute(self, decision, **collaborators) -> dict:
        payload = decision.payload
        content = payload["content"]
        seed = int(payload.get("seed", 0))

        # Fast path: if source already parses, skip the model call entirely.
        if _parses(content):
            return {
                "tool": self.NAME,
                "content": content,
                "repaired": False,
            }

        # Resolve the LLM: module-level factory (test injection) takes priority
        # over the production build_llm path.
        factory = _llm_factory
        if factory is not None:
            llm = factory()
        else:
            # Production path: build the same client as coding_loop.build_llm().
            # We import lazily to avoid pulling in the entire harness at load time.
            try:
                root = os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))))
                if root not in sys.path:
                    sys.path.insert(0, root)
                from harness.coding_loop import build_llm  # noqa: PLC0415
                llm = build_llm()
            except Exception as exc:
                return {
                    "tool": self.NAME,
                    "content": content,
                    "repaired": False,
                    "error": f"llm unavailable: {exc}",
                }

        # Import repair_indentation from body_completer_agent without editing it.
        agents_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "agents")
        if agents_dir not in sys.path:
            sys.path.insert(0, agents_dir)
        from body_completer_agent import repair_indentation  # noqa: PLC0415

        fixed = repair_indentation(llm, content, seed=seed)
        return {
            "tool": self.NAME,
            "content": fixed,
            "repaired": fixed != content,
        }

# #EXT-013-REQ-2 End
