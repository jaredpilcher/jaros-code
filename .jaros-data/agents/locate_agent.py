"""Single-purpose agent ``locate`` — orchestrator WHERE-to-act (EXT-013 / REQ-6).

Gives the orchestrator its first design-axis variable: instead of being handed a
fixed function ``name``, it decides WHICH candidate function/region the solve
intent refers to. ``LocateBoundary.decide(context)`` builds a grounded prompt
that NUMBERS the candidate targets and asks the local model for the SINGLE
index whose function the intent is about, then emits an inert
``orchestrate.locate`` Decision naming the chosen candidate (file + function +
anchor_line). It never touches the host (Tenet 1) — a separate deterministic
resolver (below) turns the Decision into a concrete line range.

Grounding / degeneracy-guard (mirrors ``orchestrator_judge_agent``): the model
reply is parsed for a single in-range candidate index. If it drifts, abstains,
or returns an out-of-range value, the agent falls back DETERMINISTICALLY to
the candidate whose ``function`` (and any ``snippet``) best content-matches
the intent by token overlap — never a no-op, never free text.

The deterministic resolver, ``resolve_location``, REUSES the proven SWE-bench
localization primitive ``harness.swebench_live.locate_region`` (content-match
the anchor line -> enclosing def/class region) rather than a fresh ad-hoc scan
— this was the single biggest lever in the SWE-bench slice (2/8 -> 4/8; see
memory jaros-code-swebench).
"""
from __future__ import annotations

# #EXT-013-REQ-6 Start
import os
import re
import sys
import uuid

from jaros.core import create_decision
from jaros.llm import LlmRequest

NAME = "locate"

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _words(text: str) -> set[str]:
    """Lowercase alnum tokens, splitting snake_case/camelCase identifiers too."""
    out: set[str] = set()
    for tok in _WORD_RE.findall(text or ""):
        out.add(tok.lower())
        # split camelCase (fooBar -> foo, bar) so identifiers match prose words
        parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", tok)
        out.update(p.lower() for p in parts if p)
    return out


def _content_match_score(intent_words: set[str], candidate: dict) -> int:
    """Deterministic content-match score: token overlap between the intent and the
    candidate's function name (+ optional snippet), highest wins."""
    text = str(candidate.get("function", "")) + " " + str(candidate.get("snippet", ""))
    return len(intent_words & _words(text))


def _best_content_match_index(intent: str, candidates: list) -> int:
    """Fallback pick — never a no-op: highest-scoring candidate, ties -> earliest index."""
    intent_words = _words(intent)
    best_i, best_score = 0, -1
    for i, cand in enumerate(candidates):
        score = _content_match_score(intent_words, cand if isinstance(cand, dict) else {})
        if score > best_score:
            best_i, best_score = i, score
    return best_i


_INT_RE = re.compile(r"\d+")


def _parse_index(raw: str, n: int) -> int | None:
    """Pull the first integer from the model reply; return a 0-based index if it is a
    valid 1-based candidate number, else None (signals drift/abstain/out-of-range)."""
    m = _INT_RE.search(raw or "")
    if not m:
        return None
    idx = int(m.group(0))
    if 1 <= idx <= n:
        return idx - 1
    return None


_PROMPT = (
    "You are deciding WHERE to act to satisfy this intent:\n"
    "INTENT: {intent}\n\n"
    "Here are the candidate functions:\n"
    "{menu}\n\n"
    "Which candidate NUMBER does the intent refer to? "
    "Answer with ONLY the number."
)


def _build_prompt(intent: str, candidates: list) -> str:
    lines = []
    for i, cand in enumerate(candidates):
        cand = cand if isinstance(cand, dict) else {}
        lines.append(f"  {i + 1}. {cand.get('file', '?')} :: {cand.get('function', '?')}")
    return _PROMPT.format(intent=intent, menu="\n".join(lines))


class LocateBoundary:
    """Grounded judge: emit the ``orchestrate.locate`` Decision naming WHERE to act.

    Parameters
    ----------
    llm:
        LLM client (jaros.llm-compatible).
    """

    def __init__(self, llm) -> None:
        self._llm = llm

    def decide(self, context) -> list:
        ctx = context if isinstance(context, dict) else {}
        intent = str(ctx.get("intent", ""))
        candidates = ctx.get("candidates") or []
        did = f"loc-{uuid.uuid4().hex}"

        if not candidates:
            # Never a no-op: nothing to choose from is a malformed context, not our job to
            # invent a target — surface it inertly rather than crashing the caller.
            return [create_decision(
                id=did, source=NAME, type="orchestrate.locate",
                payload={"file": "", "function": "", "anchor_line": 0,
                         "note": "locate: no candidates supplied"})]

        params: dict = {"temperature": 0.0, "max_tokens": 8}
        if "seed" in ctx:
            params["seed"] = ctx["seed"]
        if "temperature" in ctx:
            params["temperature"] = ctx["temperature"]

        prompt = _build_prompt(intent, candidates)
        raw = self._llm.complete(LlmRequest(prompt=prompt, params=params)).text

        idx = _parse_index(raw, len(candidates))
        matched_by = "model"
        if idx is None:
            idx = _best_content_match_index(intent, candidates)
            matched_by = "content_match_fallback"

        chosen = candidates[idx] if isinstance(candidates[idx], dict) else {}
        return [create_decision(
            id=did, source=NAME, type="orchestrate.locate",
            payload={
                "file": chosen.get("file", ""),
                "function": chosen.get("function", ""),
                "anchor_line": int(chosen.get("anchor_line", 0)),
                "matched_by": matched_by,
            })]


def build(llm) -> LocateBoundary:
    """Factory — mirrors the ``build(llm)`` convention used by all agents in this package."""
    return LocateBoundary(llm)


# ---------------------------------------------------------------------------
# Deterministic resolver — turns the Decision into a concrete (start, end) line
# range.  A plain, pure, host-effect-free function (no model, no I/O of its own):
# the CALLER supplies the already-read file text.  REUSES the proven
# ``locate_region`` content-match primitive rather than a fresh ad-hoc scan.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from harness.swebench_live import locate_region, locate_from_traceback  # noqa: E402


def resolve_location(file_text: str, anchor_line: int, max_lines: int = 70) -> tuple[int, int]:
    """Resolve a chosen locate candidate's ``anchor_line`` to a concrete (start, end)
    line range, reusing ``harness.swebench_live.locate_region`` (content-match the
    anchor line to its enclosing def/class) — not a fresh ad-hoc scan."""
    return locate_region(file_text, anchor_line, max_lines=max_lines)


def resolve_decision(decision, file_text: str, max_lines: int = 70) -> tuple[int, int]:
    """Convenience wrapper: resolve directly from an ``orchestrate.locate`` Decision."""
    payload = decision.payload if isinstance(decision.payload, dict) else {}
    return resolve_location(file_text, int(payload.get("anchor_line", 0)), max_lines=max_lines)


def locate_where(context, llm=None):
    """Choose WHERE to act, DETERMINISTIC-SIGNAL-FIRST — the honest design from the REQ-6
    measurement (model-driven localization-from-prose scored ~1/5; a real failure signal names the
    exact line).  ``context`` may carry ``target_file`` + ``traceback`` (a failure signal) and/or
    ``candidates`` (for the model fallback).

    Strategy: if a traceback names the target file, emit an ``orchestrate.locate`` Decision at that
    exact line (matched_by="traceback") — no model call.  Otherwise fall back to the grounded model
    judgement ``LocateBoundary`` (bounded, but weak) when an ``llm`` is supplied.  Two-plane: still
    only ever emits an inert Decision.
    """
    ctx = context if isinstance(context, dict) else {}
    tb = ctx.get("traceback")
    tf = ctx.get("target_file")
    if tb and tf:
        line = locate_from_traceback(tb, tf)
        if line:
            return create_decision(
                id=f"loc-{uuid.uuid4().hex}", source=NAME, type="orchestrate.locate",
                payload={"file": tf, "function": "", "anchor_line": int(line),
                         "matched_by": "traceback"})
    # (A failing-test-NAME token-match tier was tried here and MEASURED 0/5 with clean targets —
    # SWE-bench test names describe the scenario, not the function — so it was removed rather than
    # shipped as an unvalidated signal.  See EXT-013/design.md.)
    if llm is not None:
        return LocateBoundary(llm).decide(ctx)[0]
    return create_decision(
        id=f"loc-{uuid.uuid4().hex}", source=NAME, type="orchestrate.locate",
        payload={"file": tf or "", "function": "", "anchor_line": 0,
                 "matched_by": "none", "note": "no failure signal and no llm"})
# #EXT-013-REQ-6 End
