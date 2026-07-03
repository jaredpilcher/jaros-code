"""EXT-036 REQ-8: ask the user when a plain-language request is genuinely ambiguous.

ONE narrow, CONSERVATIVE model judgment (Claude Code's AskUserQuestion analog): given a
request, decide whether a critical choice is missing that the system would otherwise have to
guess, and if so emit a SINGLE clarifying question -- else the literal token ``NONE``.

Grounded + degeneracy-guarded so it does NOT over-ask: any doubt (model failure/exception,
empty output, an answer that doesn't even look like a real question) falls back to ``None``
(no question) -- under-asking is safer than annoying over-asking (Tenet 3: never fabricate a
question just to seem helpful). Deterministic parse of the model's raw text; no side effects.
"""

# #EXT-036-REQ-8 Start
from __future__ import annotations

_PROMPT = (
    "You help a coding assistant decide whether to ask ONE clarifying question before "
    "acting on a user's request. Most requests are clear enough to act on directly, even if "
    "it means picking a reasonable default -- only ask when a CRITICAL choice is missing and "
    "guessing would risk doing the wrong thing.\n\n"
    "Request: {request}\n\n"
    "If the request is clear enough to act on, reply with EXACTLY the single word: NONE\n"
    "Only if it is genuinely ambiguous, reply with ONE short clarifying question (a single "
    "sentence ending in '?'), nothing else.\n\n"
    "Answer:"
)

_DEGENERATE = {"NONE", "N/A", "NA", "NO", "NONE.", "NONE!", ""}
MAX_QUESTION_CHARS = 300   # bound the returned question -- small-model, small context


def detect_ambiguity(request: str, llm=None) -> "str | None":
    """Return a single clarifying question when `request` is genuinely ambiguous, else
    None. Conservative by construction (see module docstring): None on an empty request,
    a missing/failing model, or any degenerate/non-question output."""
    request = (request or "").strip()
    if not request:
        return None
    try:
        if llm is None:
            from harness.coding_loop import build_llm
            llm = build_llm()
        from jaros.llm import LlmRequest
        raw = llm.complete(LlmRequest(prompt=_PROMPT.format(request=request),
                                       params={"temperature": 0.0, "max_tokens": 60})).text
    except Exception:
        return None
    return _parse(raw)


def _parse(raw: "str | None") -> "str | None":
    """Deterministic parse of the model's raw text -> a clarifying question or None.
    Defaults to None on anything that isn't clearly a single, real question."""
    text = (raw or "").strip()
    if not text:
        return None
    first = text.splitlines()[0].strip().strip('"\'').strip()
    if not first:
        return None
    bare = first.strip(".! ").upper()
    if bare in {"NONE", "N/A", "NA", "NO"}:
        return None
    if not first.endswith("?"):          # not shaped like a real question -> don't over-ask
        return None
    if len(first) < 8:                   # too short to be a genuine clarifying question
        return None
    return first[:MAX_QUESTION_CHARS]
# #EXT-036-REQ-8 End
