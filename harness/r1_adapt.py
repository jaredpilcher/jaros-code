"""DeepSeek-R1-Distill-Qwen-7B code-generation adaptation (EXT-021, REQ-3).

r1_code uses a direct instruct prompt suited for R1's chain-of-thought reasoning
style.  R1 outputs a reasoning trace (sometimes wrapped in ``<think>...</think>``
tags, sometimes as plain explanatory prose) FOLLOWED BY the answer code in a
triple-backtick python fence, and may append explanation AFTER the code block.

This module:

1. Builds a direct instruct prompt asking for the function implementation.
2. Calls the LLM with ``max_tokens=3500`` — the reasoning trace needs room or
   R1 truncates before reaching the code answer.
3. Strips any ``<think>...</think>`` reasoning block (DOTALL; also handles an
   unclosed ``<think>`` when the model ran out of tokens).
4. Extracts the content of the **LAST** triple-backtick python fenced block —
   R1 may show intermediate code snippets in its reasoning; the FINAL fenced
   block is the definitive answer.
5. Locates ``def {name}`` (any ``def`` as fallback) within the extracted code.
6. Applies parse-gated indentation repair (the same proven +12 % layer from the
   gemma/qwen paths).

Uniform signature (matches ``qwen_code`` / the adaptation registry interface):

    r1_code(task_or_spec: str, name: str, context: str = "") -> str
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

from jaros.llm import LlmRequest

# #EXT-021-REQ-3 Start

_ROOT = Path(__file__).resolve().parents[1]

# Lazy LLM singleton — mirrors qwen_adapt._llm; uses whatever is served on :8000.
# Tests monkeypatch _LLM directly (no live Jetson needed).
_LLM = None


def _llm():
    global _LLM
    if _LLM is None:
        from harness.coding_loop import build_llm
        _LLM = build_llm()
    return _LLM


def _parses(src: str) -> bool:
    """Deterministic parse gate (mirrors qwen_adapt._parses)."""
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _repair_indentation(src: str) -> str:
    """Parse-gated indentation repair — reuses body_completer_agent.repair_indentation.

    Fires ONLY when src does NOT parse, so it never adds noise to correct code.
    Falls back gracefully to the unrepaired source if the agent module cannot be
    loaded, so r1_code never hard-crashes on repair failure.
    """
    if _parses(src):
        return src
    try:
        spec = importlib.util.spec_from_file_location(
            "_r1_bc",
            _ROOT / ".jaros-data" / "agents" / "body_completer_agent.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.repair_indentation(_llm(), src)
    except Exception:
        return src  # best-effort; never crash the solve pipeline


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Matches ```python / ```py / ``` followed by a newline and captures the body.
_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove ``<think>...</think>`` reasoning blocks (DOTALL).

    Also handles an unclosed ``<think>`` (model ran out of tokens): in that
    case the second sub drops from ``<think>`` to end-of-string.
    """
    # Remove properly closed blocks first.
    result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Drop any remaining unclosed <think> (from here to end of string).
    result = re.sub(r"<think>.*", "", result, flags=re.DOTALL)
    return result


def _last_fenced_block(text: str) -> str | None:
    """Return the content of the **last** triple-backtick python block, or None.

    Prefers python/py language-tagged blocks; falls back to any plain
    triple-backtick block.  Returns ``None`` when no fenced block is found.
    """
    matches = _FENCE_RE.findall(text)
    if matches:
        return matches[-1]
    # Fallback: any generic ``` block (no language tag)
    generic = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
    if generic:
        return generic[-1]
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def r1_code(task_or_spec: str, name: str, context: str = "") -> str:
    """Generate a Python function using DeepSeek-R1-Distill-Qwen-7B's reasoning style.

    Parameters
    ----------
    task_or_spec : str
        The visible spec / task description.  For HumanEval: the instruction +
        signature+docstring.  For repo tasks: the commit subject ("COMMIT
        INTENT: …"); the context carries current source + failing test.
    name : str
        The Python function name to implement.
    context : str
        Optional context block (signature, docstring, current source, etc.).
        Pass empty string when not needed.

    Returns
    -------
    str
        The generated function definition starting with ``def {name}`` (or the
        best-effort extracted code).  Fences stripped; ``<think>`` block
        stripped; parse-gated indentation repair applied.  Never raises.
    """
    ctx_block = f"\n{context.strip()}\n" if context.strip() else ""
    prompt = (
        f"Implement the Python function `{name}`.\n\n"
        f"{task_or_spec}{ctx_block}\n"
        f"Output the complete function definition (def {name}(...): ...) — "
        f"valid Python, correct indentation, no markdown outside the code block."
    )
    reply = _llm().complete(
        LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 3500})
    ).text

    # Step 1: strip <think>...</think> reasoning trace
    after_think = _strip_think(reply)

    # Step 2: extract the LAST ```python fenced block (final answer)
    fenced = _last_fenced_block(after_think)
    if fenced is not None:
        src = fenced.strip()
    else:
        # No fences found — clean the raw text as best we can
        src = re.sub(r"```[\w+-]*", "", after_think).replace("```", "").strip()

    # Step 3: locate def {name}; fall back to any def
    i = src.find(f"def {name}")
    if i >= 0:
        src = src[i:]
    elif not src.lstrip().startswith("def "):
        m = re.search(r"def\s+\w+", src)
        if m:
            src = src[m.start():]

    src = src.rstrip() + "\n"

    # Step 4: parse-gated indentation repair (proven +12 % on HumanEval via gemma/qwen path)
    return _repair_indentation(src)

# #EXT-021-REQ-3 End
