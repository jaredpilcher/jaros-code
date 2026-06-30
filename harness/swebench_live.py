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


def parse_search_replace(text: str) -> Optional[Tuple[str, str]]:
    """Extract the (search, replace) pair from a model reply, or None if absent."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = _SR_RE.search(text)
    return (m.group(1), m.group(2)) if m else None


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
    return None


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
    prompt = build_solve_prompt(issue, file_path, region)
    for i in range(n):
        t = 0.0 if i == 0 else round(0.3 + 0.1 * i, 2)
        sr = parse_search_replace(gen_fn(prompt, t))
        if not sr:
            continue
        new = apply_search_replace(original, sr[0], sr[1])
        if new is not None:
            return make_unified_diff(file_path, original, new)
    return ""
