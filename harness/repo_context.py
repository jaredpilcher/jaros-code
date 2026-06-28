"""harness/repo_context.py — EXT-017: enriched, PRECISE repo-context retrieval.

Deterministic (no LLM, no I/O, no network).  Gathers the module preamble PLUS
the signatures (and short bodies) of functions the target DIRECTLY calls — the
"direct-dependency" set.  Unrelated siblings are excluded.

Research anchor: precise direct-dependency context helps; a naive whole-file dump
hurts (arxiv 2503.20589 + prior retrieval-fewshot negative result).
"""

from __future__ import annotations

import ast
from collections import Counter

__all__ = ["enriched_file_context"]


# #EXT-017-REQ-1 Start
def _preamble(src: str) -> str:
    """Lines before the first top-level def / class / decorator — same logic as
    commit_replay._file_context but without the char cap (caller applies cap)."""
    keep: list[str] = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("def ", "class ", "@", "async def ")) and keep:
            break
        keep.append(line)
    return "\n".join(keep).strip()


def _module_funcs(tree: ast.Module, src: str) -> dict[str, str]:
    """Return {func_name -> full_source_text} for every module-level function."""
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = ast.get_source_segment(src, node) or ""
            if text:
                result[node.name] = text
    return result


def _called_names(target_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Counter:
    """Count how many times each plain function name is called in the target's body.

    Only counts bare Name calls (e.g. ``helper(x)``), not attribute calls
    (e.g. ``obj.method()``), since only module-level siblings are Name-calls.
    """
    counts: Counter = Counter()
    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                counts[func.id] += 1
    return counts


def _func_lines(text: str) -> int:
    """Number of non-empty lines in a function source text."""
    return sum(1 for ln in text.splitlines() if ln.strip())


def enriched_file_context(src: str, name: str, max_chars: int = 1500) -> str:
    """Return an enriched module context for the target function `name`.

    Includes:
      1. Module preamble (imports + module-level constants/__all__/sentinels).
      2. Direct-dependency helpers: functions whose names appear as plain calls
         in the target's body.  Included as full source when <= 10 lines,
         signature-only otherwise.  Sorted by call-frequency DESC; capped at
         ``max_chars`` total.

    Falls back to preamble-only if ``src`` cannot be parsed or ``name`` is not
    found in the module.  Never raises.
    """
    pre = _preamble(src)

    # Attempt AST parse; fall back on syntax error.
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return pre[:max_chars]

    # Locate the target function node.
    target_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            target_node = node
            break
    if target_node is None:
        return pre[:max_chars]

    # Module-level functions map (excluding the target itself).
    mod_funcs = _module_funcs(tree, src)
    mod_funcs.pop(name, None)

    # Names called directly in the target body, sorted by frequency.
    call_counts = _called_names(target_node)
    candidates = sorted(
        [(n, cnt) for n, cnt in call_counts.items() if n in mod_funcs],
        key=lambda t: t[1],
        reverse=True,
    )

    # Build helper snippets within the char budget.
    header = "\n\n# Direct dependencies:\n"
    budget = max_chars - len(pre) - len(header)
    helper_parts: list[str] = []
    for dep_name, _ in candidates:
        text = mod_funcs[dep_name]
        n_lines = _func_lines(text)
        snippet = text if n_lines <= 10 else text.splitlines()[0]  # signature only
        sep = "\n\n" if helper_parts else ""
        if budget - len(sep) - len(snippet) < 0:
            # Try signature-only as a fallback if full body didn't fit.
            sig = text.splitlines()[0]
            if budget - len(sep) - len(sig) >= 0:
                helper_parts.append(sig)
                budget -= len(sep) + len(sig)
            # Either way, stop adding more helpers.
            break
        helper_parts.append(snippet)
        budget -= len(sep) + len(snippet)

    if not helper_parts:
        return pre[:max_chars]

    result = pre + header + "\n\n".join(helper_parts)
    return result[:max_chars]
# #EXT-017-REQ-1 End
