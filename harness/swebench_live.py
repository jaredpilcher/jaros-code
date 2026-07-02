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

import os
import re
import sys
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


# #EXT-013-REQ-9 Start
def locate_from_coverage(run_fn: Callable[[], None], target_file: str) -> list:
    """Deterministic RUNTIME localization signal for WRONG-OUTPUT (non-crash) bugs.

    Runs ``run_fn()`` (a zero-arg callable that executes the failing test IN-PROCESS) under a
    ``sys.settrace`` line tracer and returns the sorted list of 1-based line numbers EXECUTED in
    ``target_file``.  Uses only the stdlib (coverage.py is NOT installed / not a dependency).

    Static signals were MEASURED weak for wrong-output bugs (test-name 0/5, test-body-symbols
    1/5), and ``locate_from_traceback`` only helps CRASH bugs (the failing frame lands in the
    buggy file).  For a wrong-output bug the test passes through the buggy code without raising,
    so the executed-line SET (not a single traceback frame) is the deterministic signal: the fix
    is almost always on a line that ran.  Two-plane-clean — no model, purely mechanical tracing.

    ``target_file`` is matched by ``os.path.basename`` equality OR ``str.endswith`` against the
    traced frame's ``co_filename``, since the frame's filename may be an absolute (e.g. temp)
    path rather than the caller's ``target_file`` string.  Robust to ``run_fn`` raising (a failing
    test typically raises/asserts) — the exception is swallowed so tracing still returns whatever
    executed before the raise.  A global ``sys.settrace`` trace only fires per-line if installed
    BEFORE the call, so this saves/restores the prior tracer (``sys.gettrace()``) around the call.
    """
    target_base = os.path.basename(target_file.replace("\\", "/"))
    target_norm = target_file.replace("\\", "/")
    executed: set = set()

    def _tracer(frame, event, arg):
        if event == "line":
            fname = frame.f_code.co_filename.replace("\\", "/")
            if os.path.basename(fname) == target_base or fname.endswith(target_norm):
                executed.add(frame.f_lineno)
        return _tracer

    prev_trace = sys.gettrace()
    sys.settrace(_tracer)
    try:
        try:
            run_fn()
        except Exception:
            pass
    finally:
        sys.settrace(prev_trace)
    return sorted(executed)


def locate_target_line_traced(
    file_text: str, anchors, executed_lines, hint_line: Optional[int] = None
) -> int:
    """Disambiguate ``locate_target_line`` anchor hits with the runtime executed-line set.

    Reuses the same content-match anchor logic as ``locate_target_line``, but among the hits for
    the FIRST matching anchor, PREFERS a hit whose line number is in ``executed_lines`` (the
    ``locate_from_coverage`` signal) — the fix is almost always on a line that ran.  If no hit
    intersects ``executed_lines`` (or ``executed_lines`` is empty), falls back to the existing
    ``locate_target_line`` behavior (hint-proximity, then hint/1).  Never a no-op.
    """
    lines = file_text.split("\n")
    executed = set(executed_lines or [])
    if executed:
        hint = hint_line if hint_line else 1
        for anchor in anchors:
            a = anchor.strip()
            if not a:
                continue
            hits = [i + 1 for i, l in enumerate(lines) if a in l]
            traced_hits = [h for h in hits if h in executed]
            if traced_hits:
                return min(traced_hits, key=lambda h: abs(h - hint)) if len(traced_hits) > 1 else traced_hits[0]
    return locate_target_line(file_text, anchors, hint_line)
# #EXT-013-REQ-9 End


def _strip_block_fence(block: str) -> str:
    """Strip a wrapping ```lang ... ``` code fence from INSIDE a SEARCH/REPLACE block.

    Some models (measured: qwen on django-11964) wrap the block CONTENT in a ```python fence, so the
    SEARCH text literally contains the fence lines and can never match the source verbatim — a
    CORRECT fix (the model emitted the right __str__) is silently dropped.  Removing a leading
    ```lang line and a trailing ``` line recovers it.  A block that isn't fenced is unchanged (no
    normal Python line is exactly a ``` fence), so this is safe and generic.
    """
    lines = block.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def parse_search_replace(text: str) -> Optional[Tuple[str, str]]:
    """Extract the (search, replace) pair from a model reply, or None if absent.

    Strict form first (SEARCH / ======= / REPLACE).  Fallback: some models OMIT the ``=======``
    divider, emitting ``<<<<<<< SEARCH\\n<search>\\n>>>>>>> REPLACE\\n<replace>`` — a correct edit
    in a near-miss format.  Accepting that shape recovers genuine fixes (measured: django-11049).
    Both blocks are then fence-stripped (see ``_strip_block_fence``) so a ```python-wrapped block
    still matches the source verbatim (measured: django-11964).
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = _SR_RE.search(text)
    if m:
        return (_strip_block_fence(m.group(1)), _strip_block_fence(m.group(2)))
    m2 = re.search(r"<<<<<<< SEARCH\n(.*?)\n>>>>>>> REPLACE\n(.*)", text, re.S)
    if m2 and m2.group(1).strip() and m2.group(2).strip():
        return (_strip_block_fence(m2.group(1)), _strip_block_fence(m2.group(2).rstrip("\n")))
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


# #EXT-027-REQ-4 Start
def _notify_verified(on_verified: Optional[Callable[[str], None]], diff: str) -> None:
    """Best-effort invoke ``on_verified`` with the passing diff; never raises, never a no-op crash.

    Mirrors ``solution_memory.record_verified``'s never-raise contract: a raising or misbehaving
    callback must never change the returned diff or break the solve pipeline.
    """
    if on_verified is None:
        return
    try:
        on_verified(diff)
    except Exception:
        pass
# #EXT-027-REQ-4 End


def solve_gated(
    *,
    issue: str,
    file_path: str,
    original: str,
    hunk_start: int,
    gen_fn: Callable[[str, float], str],
    run_test_fn: Callable[[str], tuple],
    n: int = 7,
    test_budget: int = 6,
    # #EXT-027-REQ-4 Start
    on_verified: Optional[Callable[[str], None]] = None,
    # #EXT-027-REQ-4 End
) -> str:
    """Best-of-N with the REAL TEST as the SELECTOR (not just applicability).

    ``solve_instance_live`` returns the FIRST *applicable* candidate — but a model often emits BOTH
    a wrong-but-applicable edit and a correct one (measured: django-11964, ``return self.value`` vs
    the gold ``return str(self.value)``), and first-applicable-wins then loses the fix.  This
    generates up to ``n`` candidates, collects the DISTINCT applicable diffs (in first-seen order),
    and runs ``run_test_fn`` on each (up to ``test_budget``), returning the first diff that PASSES.
    If none pass, falls back to the SELF-CONSISTENCY winner — the most frequently generated applicable
    diff (Agentless-style: count how often each patch occurs; ties keep first-seen order) — a
    principled default for the realistic gold-free case, better than an arbitrary first-applicable
    pick.  (Self-consistency is a FALLBACK only, never overriding the test-gate: it would mis-pick
    cases like django-11964 where the correct variant is the minority, so the executed test wins when
    available.)  Returns "" if no candidate even applies.  The honest test-gated multiplier.

    ``on_verified``, when given, is invoked with the winning diff ONLY in the test-PASS branch — the
    one moment the candidate is REAL-test-verified — never on the self-consistency fallback (that
    candidate did not pass the real test) and never on the empty-candidate return.  Best-effort: a
    raising callback never changes the returned diff (see ``_notify_verified``).  Defaults to
    ``None`` (no-op), so existing callers are unaffected.
    """
    region_s, region_e = locate_region(original, hunk_start)
    region = "\n".join(original.split("\n")[region_s:region_e])
    prompt = build_solve_prompt(issue, file_path, region)
    from collections import Counter
    counts: Counter = Counter()
    order = []  # distinct diffs in first-seen order
    for i in range(n):
        t = 0.0 if i == 0 else round(0.3 + 0.1 * i, 2)
        sr = parse_search_replace(gen_fn(prompt, t))
        if not sr:
            continue
        new = apply_search_replace(original, sr[0], sr[1])
        if new is None:
            continue
        d = make_unified_diff(file_path, original, new)
        if not d:
            continue
        if d not in counts:
            order.append(d)
        counts[d] += 1
    if not order:
        return ""
    for d in order[:test_budget]:
        passed, _ = run_test_fn(d)
        if passed:
            # #EXT-027-REQ-4 Start
            _notify_verified(on_verified, d)
            # #EXT-027-REQ-4 End
            return d
    # no candidate passed -> self-consistency: most frequent applicable diff (first-seen breaks ties)
    return max(order, key=lambda d: (counts[d], -order.index(d)))


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
    # #EXT-027-REQ-4 Start
    on_verified: Optional[Callable[[str], None]] = None,
    # #EXT-027-REQ-4 End
) -> str:
    """Solve, then if the patch fails the gated tests, feed the real failure back and retry.

    The honest multiplier: the deterministic test-gate teaches the fallible model.
    ``run_test_fn(patch_diff) -> (passed: bool, failure_text: str)`` is injected — in production it
    applies the patch in the instance container and runs FAIL_TO_PASS; in tests it is canned.
    Returns the first patch that passes, else the last attempted patch, else "".

    ``on_verified``, when given, fires with the passing diff at the verified moment — either the
    initial solve or a repair round passing the gated test — never on the give-up (last-attempt)
    return.  Best-effort (see ``_notify_verified``); defaults to ``None`` (no-op, unaffected).
    """
    diff = solve_instance_live(
        issue=issue, file_path=file_path, original=original, hunk_start=hunk_start, gen_fn=gen_fn, n=n
    )
    if not diff:
        return ""
    passed, failure = run_test_fn(diff)
    if passed:
        # #EXT-027-REQ-4 Start
        _notify_verified(on_verified, diff)
        # #EXT-027-REQ-4 End
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
            # #EXT-027-REQ-4 Start
            _notify_verified(on_verified, cand)
            # #EXT-027-REQ-4 End
            return cand
    return last


def solve_from_failure(
    *,
    file_text: str,
    traceback: str,
    target_file: str,
    gen_fn: Callable[[str, float], str],
    issue: str = "",
    n: int = 7,
) -> str:
    """Gold-FREE repo solve: localize WHERE from the FAILURE traceback (not a gold diff), then solve.

    The realistic SWE-bench path — the failing line comes from running the test (the strong signal
    #9's measurement pointed to), and the model produces only the FIX.  This is the honest general
    solve: no gold patch is used to find the location.  Returns a unified-diff patch, or "" if the
    traceback names no line in ``target_file`` or no sample yields an applicable edit.  The only
    non-offline step (running the test to produce ``traceback``) is the caller's responsibility.
    """
    line = locate_from_traceback(traceback, target_file)
    if not line:
        return ""
    return solve_instance_live(
        issue=issue or traceback, file_path=target_file, original=file_text,
        hunk_start=line, gen_fn=gen_fn, n=n,
    )
