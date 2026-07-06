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

import ast
import re

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


# #EXT-036-REQ-31 Start
# TASK-41 (REQ-31): 7B-GENERATE -- the owner's extension of REQ-30. Where `review_checks`
# is BOUNDED by Gemma's own proposed checks (it can only correct/drop what Gemma wrote), this
# writes acceptance checks FROM SCRATCH -- unshackled from Gemma's hallucinations -- using
# ONLY the visible spec + built module sources (NO ORACLE LEAK, same honesty framing as
# `REVIEW_PROMPT`/`.jaros-data/sevenb_review_probe.py`). Standalone + injectable, for an A/B
# live-gate measurement against `review_checks` and the unassisted baseline (not wired into
# `build_system` in this task -- see EXT-036 REQ-31 acceptance criteria).
GENERATE_PROMPT = (
    "You are WRITING acceptance tests for a program built from a SPEC.\n"
    "Use ONLY the SPEC and CODE below. You have NO hidden expected outputs.\n\n"
    "SPEC:\n{spec}\n\nCODE:\n{code}\n\n"
    "Write up to {max_checks} concrete acceptance checks proving the SPEC is satisfied. Each "
    "check is standalone runnable Python that imports the built module(s) shown above and "
    "asserts REAL behavior derived from the code.\n"
    "Rules:\n"
    "1. Reference ONLY APIs that actually exist in the CODE shown above -- never invent one.\n"
    "2. If a check asserts an expected VALUE, compute that value FROM THE SPEC'S STATED RULES "
    "ONLY -- never guess or invent one.\n"
    "3. If you cannot derive ANY check that is verifiable from the spec+code alone, output "
    "exactly: DROP\n"
    "Output EACH check as its own fenced Python block, e.g.:\n"
    "```python\n# <short name>\n<runnable check code>\n```\n"
    "No prose outside the fenced blocks."
)

_FENCED_BLOCK_RE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def _is_runnable_check(code: str) -> bool:
    """A generated check is only usable if it parses as valid Python AND contains a real
    ``assert`` -- mirrors the deterministic executable-check filter used elsewhere in the
    acceptance pipeline (``harness.system_builder._is_executable_check``), reimplemented here
    so this module stays self-contained (no import of the builder's internals)."""
    if not isinstance(code, str) or not code.strip():
        return False
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return any(isinstance(node, ast.Assert) for node in ast.walk(tree))


def _name_for_block(code: str, index: int) -> str:
    """Derive a short check name from a leading ``# comment`` line, if the generator left
    one; otherwise fall back to a positional label."""
    for line in code.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            label = line.lstrip("#").strip()
            if label:
                return label
        break
    return f"generated check {index + 1}"


def _parse_generated_checks(raw: str, max_checks: int) -> "list[dict]":
    """Parse the generator's raw response into `{"name", "code"}` dicts: strip markdown
    fences (reusing `_clean_reviewed_code`, the SAME fence-stripping `review_checks` uses),
    split multiple fenced blocks into separate checks, honor a whole-response ``DROP`` (the
    generator judged nothing derivable), and OMIT any block that isn't runnable Python with a
    real assertion (a check the model can't write is dropped, never fabricated). Bounded to
    `max_checks`. Never raises -- any parse error simply yields fewer (possibly zero) checks."""
    text = (raw or "").strip()
    if not text or text.upper().startswith("DROP"):
        return []
    blocks = _FENCED_BLOCK_RE.findall(text)
    if not blocks:
        blocks = [text]
    out: list[dict] = []
    for i, block in enumerate(blocks):
        if len(out) >= max_checks:
            break
        try:
            cleaned = _clean_reviewed_code(block)
        except Exception:
            continue
        if not cleaned or cleaned.strip().upper() == "DROP":
            continue
        if not _is_runnable_check(cleaned):
            continue  # the model couldn't write a verifiable check for this slot -- omit it
        out.append({"name": _name_for_block(cleaned, i), "code": cleaned})
    return out


def generate_checks(spec: str, modules: "dict[str, str]", generator_llm,
                     max_checks: int = 4) -> "list[dict]":
    """7B-GENERATE acceptance checks (REQ-31) FROM SCRATCH, from ONLY the visible `spec` +
    built `modules` source -- NEVER any hidden/expected output (NO ORACLE LEAK, Tenet 3;
    same honesty framing as `review_checks`/`REVIEW_PROMPT`). Calls
    ``generator_llm.complete(LlmRequest(prompt=..., params={"temperature": 0.0,
    "max_tokens": 1024})).text`` once with `GENERATE_PROMPT`, asking the (stronger) model to
    WRITE runnable acceptance checks that import the built module(s) and assert behavior
    derivable from the spec's stated rules -- unlike `review_checks`, this is NOT bounded by
    any Gemma-proposed check to correct; the generator writes free-form.

    Returns a list of `{"name": str, "code": str}` dicts (the same shape
    `_compose_acceptance_checklist` entries / `_run_check_verbose` consume), bounded to
    `max_checks`. Parses the response by stripping markdown fences (reusing
    `_clean_reviewed_code`) and splitting multiple fenced blocks into separate checks; a
    whole-response ``DROP``, an unparseable/non-asserting block, or any exception from
    `generator_llm.complete` or parsing is handled CONSERVATIVELY -- that check (or the whole
    call) is simply OMITTED. NEVER raises: this function always returns a list, `[]` at
    worst, never propagating an exception to the caller."""
    try:
        code_blob = "\n\n".join(
            f"# {name}\n{src}" for name, src in (modules or {}).items()
        )[:6000]
        spec_blob = (spec or "")[:1500]
        prompt = GENERATE_PROMPT.format(spec=spec_blob, code=code_blob,
                                         max_checks=max(1, int(max_checks or 1)))
        raw = (generator_llm.complete(
            LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 1024})
        ).text or "")
    except Exception:
        return []
    try:
        return _parse_generated_checks(raw, max_checks)
    except Exception:
        return []
# #EXT-036-REQ-31 End
