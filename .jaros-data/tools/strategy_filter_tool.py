"""Deterministic strategy filter (EXT-015 / plan-then-code decomposition).

Tool name: ``code.filter_strategy``
Execution plane (Tenet 1): PURE + DETERMINISTIC, no LLM.

Research basis ('Strategic Decomposition & Filtering for SLMs'): filtering >
diversity for small models.  Small models can't improve their own scaffold, so
the filter MUST be deterministic (two-plane).

execute(strategy_text) -> cleaned strategy:
  - Strip few-shot contamination: lines starting with 'Example:', 'example:',
    fenced code blocks (```...```), full-solution snippets (lines starting with
    'def ' / 'return ' / '    ' indented blocks), copied I/O lines.
  - Strip preamble/boilerplate: lines that are greetings, transitional prose,
    'Here is ...', 'Now we ...', 'The function ...', etc.
  - KEEP concrete actionable lines: numbered steps (^\\d+\\.),
    bulleted imperative steps (^[-*]\\s+), edge-case mentions
    (contain 'edge case', 'handle', 'check', 'if ', 'when ', 'return ').
  - If nothing survives, return the original unchanged (graceful no-op).

validate(decision) -> ValidationResult: rejects empty/non-str payload.content.
"""
from __future__ import annotations

import re
from typing import Any

# #EXT-015-REQ-2 Start

# ---------------------------------------------------------------------------
# Pattern constants (all deterministic, no LLM)
# ---------------------------------------------------------------------------

# Lines that represent few-shot contamination or copied I/O
_CONTAMINATION_PREFIXES = (
    "example:",
    "examples:",
    "input:",
    "output:",
    ">>> ",
    "# ",          # inline Python comments inside strategy = code leakage
)

# Lines that are pure boilerplate/preamble with no actionable content
_BOILERPLATE_PATTERNS = [
    re.compile(r"^(here is|here's|now (we|let's)|the function|this function|"
               r"to (implement|solve|handle)|sure[,!]|certainly[,!]|"
               r"okay[,!]|of course[,!]|let me)", re.I),
    re.compile(r"^(in (this|the) (approach|solution|implementation))", re.I),
]

# A line is a CODE line if it looks like Python source
_CODE_LINE_PATTERNS = [
    re.compile(r"^\s{4,}"),                         # indented (Python body)
    re.compile(r"^(def |class |return |import |from |if __name__)"),
    re.compile(r"=\s*(None|True|False|\[|\{|\()"),  # assignment to literals
]

# A line is ACTIONABLE if it is a numbered/bulleted step or contains a
# concrete imperative keyword
_ACTIONABLE_PATTERNS = [
    re.compile(r"^\d+[\.\)]\s+\S"),                 # "1. " or "1) "
    re.compile(r"^[-*]\s+\S"),                       # "- " or "* " bullet
    re.compile(r"\b(check|handle|if |when |return |raise |ensure|validate|"
               r"compute|calculate|iterate|loop|sort|filter|edge case|"
               r"base case|empty|none|zero|boundary|negative)\b", re.I),
]


def _is_contamination(line: str) -> bool:
    """True if the line is few-shot contamination or copied I/O."""
    stripped = line.strip().lower()
    return any(stripped.startswith(p) for p in _CONTAMINATION_PREFIXES)


def _is_boilerplate(line: str) -> bool:
    """True if the line is a preamble/boilerplate with no actionable content."""
    stripped = line.strip()
    return any(pat.match(stripped) for pat in _BOILERPLATE_PATTERNS)


def _is_code_line(line: str) -> bool:
    """True if the line looks like raw Python source (not a strategy step)."""
    return any(pat.match(line) for pat in _CODE_LINE_PATTERNS)


def _is_actionable(line: str) -> bool:
    """True if the line is a concrete, actionable strategy step."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(pat.search(stripped) for pat in _ACTIONABLE_PATTERNS)


def filter_strategy(strategy_text: str) -> str:
    """Pure deterministic strategy filter.  No LLM.

    Strips contamination, boilerplate, and code lines; keeps actionable steps.
    Returns the cleaned strategy, or the original if nothing survives.
    """
    # Phase 1: remove fenced code blocks entirely (```...``` possibly multi-line)
    text = re.sub(r"```[\w+-]*[\s\S]*?```", "", strategy_text)

    kept: list[str] = []
    for line in text.splitlines():
        raw = line.rstrip()
        stripped = raw.strip()
        if not stripped:
            continue  # blank lines are dropped
        if _is_contamination(stripped):
            continue
        if _is_code_line(raw):
            continue
        if _is_boilerplate(stripped):
            continue
        # Keep if actionable OR if it's a short non-prose line (likely a step
        # that doesn't happen to match our keyword list)
        if _is_actionable(stripped) or len(stripped) > 0:
            kept.append(stripped)

    cleaned = "\n".join(kept).strip()
    return cleaned if cleaned else strategy_text.strip()


# ---------------------------------------------------------------------------
# Jaros tool interface
# ---------------------------------------------------------------------------

class _ValidationResult:
    """Plain class (not dataclass) so importlib.util.module_from_spec works with any module name."""

    def __init__(self, ok: bool, error: str = "") -> None:
        self.ok = ok
        self.error = error


class StrategyFilterTool:
    """Jaros tool: ``code.filter_strategy``

    Decision payload expected:
        {
            "strategy": str   -- the raw strategy text to filter
        }

    Result:
        {
            "tool": "code.filter_strategy",
            "filtered": str   -- the cleaned strategy
        }
    """

    def validate(self, decision) -> _ValidationResult:
        payload = getattr(decision, "payload", {}) or {}
        strategy = payload.get("strategy")
        if not isinstance(strategy, str):
            return _ValidationResult(ok=False, error="payload.strategy must be a str")
        if not strategy.strip():
            return _ValidationResult(ok=False, error="payload.strategy must not be empty")
        return _ValidationResult(ok=True)

    def execute(self, decision) -> dict[str, Any]:
        payload = getattr(decision, "payload", {}) or {}
        raw = payload.get("strategy", "")
        filtered = filter_strategy(raw)
        return {"tool": "code.filter_strategy", "filtered": filtered}

# #EXT-015-REQ-2 End
