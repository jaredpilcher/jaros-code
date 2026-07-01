"""Live SWE-bench solve pipeline — productionized from the validated grind (2026-06-30).

The django-12125 resolve validated this approach: localize the buggy region, have the model
emit a SEARCH/REPLACE edit, apply it deterministically, and turn it into a unified diff.  This
module is the *pure, offline-testable* core of that pipeline; all side effects (extracting the
file from the Docker image, calling the model, running the WSL eval) are injected by the caller
so the logic can be unit-tested with no Docker, no WSL and no Jetson.  See memory
jaros-code-swebench for the full pipeline + the hard-won infrastructure lessons.

Two-plane discipline (PRIME-001 Tenet 1): the model only emits an inert SEARCH/REPLACE text;
this module deterministically parses + applies it.  The model never touches the host.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

from harness.swebench_solve import make_unified_diff

# A model emits an edit as one search/replace block; we apply it deterministically.
_SR_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE", re.S)


def locate_region(original: str, hunk_start: int, max_lines: int = 70) -> Tuple[int, int]:
    """Return (start, end) line indices of the ``def``/``class`` enclosing ``hunk_start``.

    ``hunk_start`` is 1-based (as in a unified-diff ``@@ -L`` header or an issue-derived line).
    The region runs from the nearest enclosing def/class header down to the next line at the
    same-or-lower indent (the end of that block), capped at ``max_lines``.  Used to give the
    model a focused, self-contained chunk to edit rather than the whole file.
    """
    lines = original.split("\n")
    if not lines:
        return 0, 0
    start = max(0, min(hunk_start - 1, len(lines) - 1))
    for i in range(start, -1, -1):
        s = lines[i].lstrip()
        if s.startswith("def ") or s.startswith("class "):
            start = i
            break
    base = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    for i in range(start + 1, min(start + max_lines, len(lines))):
        ln = lines[i]
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= base and not ln.lstrip().startswith(
            ('"""', "'''", "#", ")")
        ):
            end = i
            break
        end = i + 1
    return start, end


def locate_target_line(file_text: str, anchors, hint_line: Optional[int] = None) -> int:
    """Localize a change to a file by CONTENT — the single biggest SWE-bench lever (2/8 -> 5/8).

    Tries each anchor string in order; returns the 1-based line of the first anchor that appears
    in the file.  When an anchor is AMBIGUOUS (multiple occurrences — e.g. a generic line like
    ``pass``, which cost django-11964 a wrong-method localization), it disambiguates by choosing
    the occurrence CLOSEST to ``hint_line``.  Falls back to ``hint_line`` (or 1) if no anchor
    matches — never returns None, never a no-op.

    This generalises the two localization fixes proven this session: (1) content-match the buggy
    line rather than trusting the diff's ``@@ -L`` header (which can land between methods), and
    (2) disambiguate generic anchors by the header line as a proximity hint.
    """
    lines = file_text.split("\n")
    hint = hint_line if hint_line else 1
    for anchor in anchors:
        a = anchor.strip()
        if not a:
            continue
        hits = [i + 1 for i, l in enumerate(lines) if a in l]
        if hits:
            return min(hits, key=lambda h: abs(h - hint)) if len(hits) > 1 else hits[0]
    return hint


_TB_FRAME = re.compile(r'File "([^"]+)", line (\d+)')


def locate_from_traceback(traceback: str, target_file: str) -> Optional[int]:
    """Deterministic localization from a FAILURE SIGNAL — the strong signal #9's measurement points
    to.  Returns the line of the DEEPEST traceback frame that lands in ``target_file``, else None.

    Model-driven localization-from-prose measured weak (~1/5); a traceback names the exact failing
    line.  The orchestrator's WHERE-to-act should prefer this deterministic signal when a test/run
    failure is available, and only fall back to a model judgement when it is not.
    """
    tf = target_file.replace("\\", "/").lstrip("/")
    last = None
    for m in _TB_FRAME.finditer(traceback or ""):
        path = m.group(1).replace("\\", "/")
        if path.endswith(tf):
            last = int(m.group(2))
    return last


def locate_from_patch(file_text: str, patch: str) -> int:
    """Localize from a unified diff: use its removed lines (then context lines) as content anchors
    and its ``@@ -L`` header as the proximity hint.  Returns the 1-based target line in file_text.
    """
    removed = [l[1:] for l in patch.splitlines()
               if l.startswith("-") and not l.startswith("---") and l[1:].strip()]
    ctx = [l[1:] for l in patch.splitlines() if l.startswith(" ") and l[1:].strip()]
    m = re.search(r"@@ -(\d+)", patch)
    hint = int(m.group(1)) if m else None
    return locate_target_line(file_text, removed + ctx, hint)


def parse_search_replace(text: str) -> Optional[Tuple[str, str]]:
    """Extract the (search, replace) pair from a model reply, or None if absent.

    Strict form first (SEARCH / ======= / REPLACE).  Fallback: some models OMIT the ``=======``
    divider, emitting ``<<<<<<< SEARCH\\n<search>\\n>>>>>>> REPLACE\\n<replace>`` — a correct edit
    in a near-miss format.  Accepting that shape recovers genuine fixes (measured: django-11049).
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = _SR_RE.search(text)
    if m:
        return (m.group(1), m.group(2))
    m2 = re.search(r"<<<<<<< SEARCH\n(.*?)\n>>>>>>> REPLACE\n(.*)", text, re.S)
    if m2 and m2.group(1).strip() and m2.group(2).strip():
        return (m2.group(1), m2.group(2).rstrip("\n"))
    return None


def apply_search_replace(original: str, search: str, replace: str) -> Optional[str]:
    """Apply one search/replace edit; return the new content, or None if it does not apply.

    Exact match first; then a right-strip-tolerant fallback (models often perturb trailing
    whitespace).  Returns None on no-op or no-match so the caller can try the next sample.
    """
    if not search:
        return None
    if search in original:
        new = original.replace(search, replace, 1)
        return new if new != original else None
    norm = lambda s: "\n".join(x.rstrip() for x in s.split("\n"))
    no, ns = norm(original), norm(search)
    if ns and ns in no:
        new = no.replace(ns, norm(replace), 1)
        return new if new != no else None
    # Line-level fallback: the model often reproduces the surrounding block imperfectly (e.g.
    # hallucinates a `self.` prefix) but gets the CHANGED line(s) right. Apply the aligned
    # line-replacements from the search/replace diff whose OLD line is present verbatim in the file.
    import difflib
    sl, rl = search.split("\n"), replace.split("\n")
    new = original
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sl, rl).get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for old, rep in zip(sl[i1:i2], rl[j1:j2]):
                if old != rep and old.strip() and old in new:
                    new = new.replace(old, rep, 1)
    return new if new != original else None


def build_solve_prompt(issue: str, file_path: str, region: str, issue_chars: int = 1300) -> str:
    """The validated solve prompt: issue + localized region -> ask for one SEARCH/REPLACE edit."""
    return (
        f"You are resolving a GitHub issue by editing {file_path}.\n\n"
        f"ISSUE:\n{issue[:issue_chars]}\n\n"
        f"The relevant code (the function/class containing the bug):\n"
        f"```python\n{region}\n```\n\n"
        f"Produce the MINIMAL fix as ONE search/replace edit in EXACTLY this format (the SEARCH "
        f"block must reproduce existing lines VERBATIM incl. indentation):\n"
        f"<<<<<<< SEARCH\n<exact existing lines>\n=======\n<replacement lines>\n>>>>>>> REPLACE\n"
    )


def solve_instance_live(
    *,
    issue: str,
    file_path: str,
    original: str,
    hunk_start: int,
    gen_fn: Callable[[str, float], str],
    n: int = 7,
) -> str:
    """Best-of-N SEARCH/REPLACE solve.  Returns a unified-diff patch, or "" if none applied.

    ``gen_fn(prompt, temperature) -> reply_text`` is injected (a real model in production, a
    canned function in tests).  Deterministic first sample (t=0), then rising temperatures.
    """
    region_s, region_e = locate_region(original, hunk_start)
    region = "\n".join(original.split("\n")[region_s:region_e])
    new = _gen_edit(build_solve_prompt(issue, file_path, region), original, gen_fn, n)
    return make_unified_diff(file_path, original, new) if new is not None else ""


def _gen_edit(prompt: str, original: str, gen_fn: Callable[[str, float], str], n: int):
    """Best-of-N: up to n samples (t=0 then rising temps) for an APPLICABLE search/replace edit.

    Returns the new file content, or None if no sample produced a parseable + applicable edit.
    Used by BOTH the initial solve and each repair round — a single mis-formatted sample no longer
    kills a round (the repair loop's original 1-shot-at-t=0 silently dropped valid repairs).
    """
    for i in range(n):
        t = 0.0 if i == 0 else round(0.3 + 0.1 * i, 2)
        sr = parse_search_replace(gen_fn(prompt, t))
        if not sr:
            continue
        new = apply_search_replace(original, sr[0], sr[1])
        if new is not None:
            return new
    return None


def build_repair_prompt(
    issue: str, file_path: str, region: str, prev_patch: str, failure: str,
    issue_chars: int = 900, fail_chars: int = 1200,
) -> str:
    """Repair prompt: previous patch APPLIED but tests still fail -> reconsider with the real error."""
    return (
        f"Your previous patch to {file_path} was applied successfully, but the tests STILL FAIL.\n\n"
        f"ISSUE:\n{issue[:issue_chars]}\n\n"
        f"Code region:\n```python\n{region}\n```\n\n"
        f"Your previous patch:\n{prev_patch}\n\n"
        f"The actual test failure:\n{failure[:fail_chars]}\n\n"
        f"Reconsider WHY it failed and produce a CORRECTED minimal fix as ONE search/replace edit "
        f"(SEARCH must reproduce existing lines VERBATIM):\n"
        f"<<<<<<< SEARCH\n<exact existing lines>\n=======\n<replacement lines>\n>>>>>>> REPLACE\n"
    )


def solve_with_repair(
    *,
    issue: str,
    file_path: str,
    original: str,
    hunk_start: int,
    gen_fn: Callable[[str, float], str],
    run_test_fn: Callable[[str], tuple],
    n: int = 7,
    max_repairs: int = 2,
) -> str:
    """Solve, then if the patch fails the gated tests, feed the real failure back and retry.

    The honest multiplier: the deterministic test-gate teaches the fallible model.
    ``run_test_fn(patch_diff) -> (passed: bool, failure_text: str)`` is injected — in production it
    applies the patch in the instance container and runs FAIL_TO_PASS; in tests it is canned.
    Returns the first patch that passes, else the last attempted patch, else "".
    """
    diff = solve_instance_live(
        issue=issue, file_path=file_path, original=original, hunk_start=hunk_start, gen_fn=gen_fn, n=n
    )
    if not diff:
        return ""
    passed, failure = run_test_fn(diff)
    if passed:
        return diff
    region_s, region_e = locate_region(original, hunk_start)
    region = "\n".join(original.split("\n")[region_s:region_e])
    last = diff
    for _ in range(max_repairs):
        new = _gen_edit(build_repair_prompt(issue, file_path, region, last, failure), original, gen_fn, n)
        if new is None:
            continue
        cand = make_unified_diff(file_path, original, new)
        if not cand:
            continue
        last = cand
        passed, failure = run_test_fn(cand)
        if passed:
            return cand
    return last
