"""EXT-036 TASK-40 (REQ-30): 7B REVIEW+CORRECT of model-proposed acceptance checks.

MEASURED PROBLEM (session 2026-07-05, memory [[jaros-code-build-acceptance-honesty]]):
``build_system``'s ``done`` grader composes a deterministic MINIMUM checklist (REQ-26)
UNIONED with MODEL-PROPOSED checks (the same small model that built the system also writes
checks for its own build, REQ-2). The model-proposed checks are a MIXED bag -- some
HALLUCINATE (an invented API ``from main import encode``, an invented value
``assert convert(300,'K','C')==27.78`` when the spec's own conversion rule gives 26.85),
FALSE-NEGATIVING 8/20 genuinely-correct systems; others correctly CATCH real breakage
(rpn-calc, kv-store-ttl). Blanket-TRUSTING them false-negatives; blanket-DEMOTING them (a
reverted attempt, parked in ``git stash@{0}``) introduced 2 FALSE-DONES.

VALIDATED FIX (owner's idea, PRE-REGISTERED KILL CRITERION probed 2026-07-05,
``.jaros-data/sevenb_review_probe.py``, task #122): have a STRONGER model
(qwen2.5-coder-7b) REVIEW+CORRECT each model-proposed check from the VISIBLE SPEC + CODE
ONLY -- never any hidden/expected output (NO ORACLE LEAK). Probe result: the 7B fixed 3/4
hallucinated checks (turning a currently-failing bogus check into a passing-or-dropped one)
AND preserved 1/1 real-bug check (left it genuinely failing). This module is the pure,
injectable mechanism that probe validated -- the SAME prompt wording and parse logic,
extracted so ``harness.system_builder`` can use it without duplicating the probe.

Scope note (this module only): which model actually SERVES as the reviewer (e.g. swapping
the Jetson from gemma to qwen2.5-coder-7b and back) is a CALLER concern -- this module takes
a plain injected ``reviewer_llm`` (any object exposing ``.complete(LlmRequest) -> .text``)
and never touches model-manager/Jetson serving itself.
"""

from __future__ import annotations

from jaros.llm import LlmRequest

# #EXT-036-REQ-30 Start
# TASK-40: the EXACT reviewer prompt validated by the pre-registered-kill-criterion probe
# (`.jaros-data/sevenb_review_probe.py::REVIEW_PROMPT`) -- same wording, so the validated
# result transfers directly to this production wiring.
REVIEW_PROMPT = (
    "You are REVIEWING a proposed acceptance test for a program built from a SPEC.\n"
    "Use ONLY the SPEC and CODE below. You have NO hidden expected outputs.\n\n"
    "SPEC:\n{spec}\n\nCODE:\n{code}\n\nPROPOSED TEST:\n{check}\n\n"
    "Rules:\n"
    "1. If the test imports/references an API that does not exist in the CODE, CORRECT it to the real one.\n"
    "2. If it asserts an expected VALUE, recompute the correct value FROM THE SPEC'S STATED RULES; "
    "if the spec does not determine it, DROP that assertion.\n"
    "3. If the test cannot be verified from the spec+code alone, output exactly: DROP\n"
    "Output ONLY corrected runnable Python, or exactly DROP. No prose, no markdown fences."
)


def _clean_reviewed_code(rev: str) -> str:
    """Parse the reviewer's raw response into runnable Python -- mirrors the validated
    probe's own fence-stripping exactly (`.jaros-data/sevenb_review_probe.py::_review_body`):
    strip whitespace, strip backtick fence characters, and drop a leading bare ``python``
    language tag line if the model echoed one."""
    clean = rev.strip().strip("`")
    if clean.lower().startswith("python"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean
    return clean


def review_checks(spec: str, modules: "dict[str, str]", proposed_checks: "list[dict]",
                   reviewer_llm) -> "list[dict]":
    """7B-REVIEW+CORRECT each model-proposed acceptance ``check`` (REQ-30) against ONLY the
    visible ``spec`` + built ``modules`` source -- NEVER any hidden/expected output (NO
    ORACLE LEAK, Tenet 3). For each check in `proposed_checks` (each a dict with at least a
    ``code`` key), calls
    ``reviewer_llm.complete(LlmRequest(prompt=..., params={"temperature": 0.0,
    "max_tokens": 1024})).text`` with the validated `REVIEW_PROMPT`, and:

    - corrects a hallucinated API/import reference to the real one (per the code shown),
    - recomputes an asserted VALUE from the spec's stated rules, or DROPS that assertion if
      the spec doesn't determine it,
    - or DROPS the whole check (parsed exactly as the probe does: the literal token
      ``DROP``, case-insensitively, or an empty response) when it can't be verified from
      spec+code alone.

    Returns the corrected checklist with dropped checks OMITTED (never included as `None`/
    empty entries). Preserves every other key on a corrected check (e.g. ``name``), only
    ``code`` is replaced. NEVER raises: an exception from `reviewer_llm.complete` (network
    failure, malformed response object, anything) leaves that ONE check UNCHANGED
    (conservative -- keep the model's original proposal rather than silently losing or
    mangling it); it does not abort the whole review or crash the caller."""
    if not proposed_checks:
        return []
    code_blob = "\n\n".join(
        f"# {name}\n{src}" for name, src in (modules or {}).items()
    )[:6000]
    spec_blob = (spec or "")[:1500]
    reviewed: list[dict] = []
    for chk in proposed_checks:
        if not isinstance(chk, dict):
            continue
        original_code = chk.get("code", "") or ""
        prompt = REVIEW_PROMPT.format(spec=spec_blob, code=code_blob, check=original_code[:1500])
        try:
            rev = (reviewer_llm.complete(
                LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 1024})
            ).text or "").strip()
        except Exception:
            # Reviewer failure: conservative -- keep the original check unchanged.
            reviewed.append(dict(chk))
            continue
        dropped = rev.strip().upper().startswith("DROP") or not rev.strip()
        if dropped:
            continue  # omitted -- the reviewer judged this check unverifiable/wrong
        corrected = dict(chk)
        corrected["code"] = _clean_reviewed_code(rev)
        reviewed.append(corrected)
    return reviewed
# #EXT-036-REQ-30 End
