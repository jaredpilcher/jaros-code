"""Qwen2.5-Coder-3B code-generation adaptation (EXT-021, REQ-4/REQ-5).

qwen_code builds a DIRECT instruct prompt (no Gherkin scaffolding, no intermediate
steps) matched to Qwen-Coder's proven raw-probe behavior: given a clean
"Implement the Python function `{name}` ... Output ONLY the function definition"
prompt, qwen2.5-coder-3b returns clean ```python-fenced output that the harness
strips to a bare function definition.

This is qwen's analogue of commit_replay.g_code / baseline_solve_2b — adapted
for qwen-coder's clean instruct style rather than Gemma's Gherkin decomposition.
The probe result (2026-06-28, owner note): "qwen2.5-coder-3b, given a clean
instruct prompt 'Implement the Python function ... Output only the function',
returns clean ```python-fenced code."

Works for both problem classes:
  - standalone-fn-gen (HumanEval): instruction + signature+docstring as context
  - multi-step-repo: commit subject + current source + failing test as context
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

from jaros.llm import LlmRequest

# #EXT-021-REQ-4 Start
# #EXT-021-REQ-5 Start

_ROOT = Path(__file__).resolve().parents[1]

# Lazy LLM singleton — mirrors pass1_eval._llm; uses whatever is SERVED on :8000
# (operator serves qwen before profiling; tests monkeypatch _LLM directly).
_LLM = None


def _llm():
    global _LLM
    if _LLM is None:
        from harness.coding_loop import build_llm
        _LLM = build_llm()
    return _LLM


def _parses(src: str) -> bool:
    """Deterministic parse gate (mirrors body_completer_agent._parses)."""
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _repair_indentation(src: str) -> str:
    """Parse-gated indentation repair — reuses body_completer_agent.repair_indentation.

    Fires ONLY when src does NOT parse, so it never adds noise to correct code.
    Falls back gracefully to the unrepaired source if the agent module cannot be
    loaded (e.g. missing file) so qwen_code never hard-crashes on repair failure.
    """
    if _parses(src):
        return src
    try:
        spec = importlib.util.spec_from_file_location(
            "_qwen_bc",
            _ROOT / ".jaros-data" / "agents" / "body_completer_agent.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.repair_indentation(_llm(), src)
    except Exception:
        return src  # best-effort; never crash the solve pipeline


def qwen_code(task_or_spec: str, name: str, context: str = "") -> str:
    """Generate a Python function implementation using qwen2.5-coder-3b's direct instruct style.

    Builds a DIRECT, clean instruct prompt matched to qwen-coder's proven behavior:

        Implement the Python function `{name}`.

        {task_or_spec}

        [{context}]

        Output ONLY the function definition (def {name}(...): ...) — valid Python,
        correct indentation, no markdown, no explanation, no test code.

    Qwen-Coder wants this clean instruct form (not Gemma's Gherkin scaffolding).
    The raw-probe confirmed qwen returns clean ```python-fenced output which the
    harness strips.  Parse-gated indentation repair runs on the stripped result,
    mirroring the proven +12% repair layer from the gemma/pass1_eval path.

    Parameters
    ----------
    task_or_spec : str
        The visible spec.  For standalone-fn-gen (HumanEval): the task instruction
        + the signature+docstring block as context.  For multi-step-repo: the commit
        subject ("COMMIT INTENT: ..."); the context carries current source + failing
        test + module preamble.
    name : str
        The Python function name to implement.
    context : str
        Optional context block: the function's signature+docstring (HumanEval), or
        the current source + failing test + module preamble (repo tasks).  Pass empty
        string when not needed.

    Returns
    -------
    str
        The generated function definition starting with ``def {name}``.
        Fences stripped; parse-gated indentation repair applied.
    """
    ctx_block = f"\n{context.strip()}\n" if context.strip() else ""
    prompt = (
        f"Implement the Python function `{name}`.\n\n"
        f"{task_or_spec}{ctx_block}\n"
        f"Output ONLY the function definition (def {name}(...): ...) — "
        f"valid Python, correct indentation, no markdown, no explanation, no test code."
    )
    reply = _llm().complete(
        LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 800})
    ).text

    # Strip markdown fences (qwen returns ```python ... ``` by default)
    src = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()

    # Locate the target function definition
    i = src.find(f"def {name}")
    if i >= 0:
        src = src[i:]
    elif not src.lstrip().startswith("def "):
        # Fallback: find any def (qwen may have renamed the function)
        m = re.search(r"def\s+\w+", src)
        if m:
            src = src[m.start():]

    src = src.rstrip() + "\n"

    # Parse-gated indentation repair (proven +12% on HumanEval via gemma path)
    return _repair_indentation(src)

# #EXT-021-REQ-4 End
# #EXT-021-REQ-5 End
