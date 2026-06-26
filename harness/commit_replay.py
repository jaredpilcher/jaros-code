"""EXT-011 — Commit-Replay Evaluation: the real frontier.

Measure how far the LOCAL 2B harness gets on REAL repository commit histories, scored ONLY by the
repo's own tests going red->green (never exact-diff-match). This number is meant to be PUBLISHED, so
everything here is built for honesty: brutal filtering with a logged drop ledger (no silent
truncation), a reproducible Docker test env, and red->green validation of every kept commit.

Stage 1 (this module): mine + STRUCTURALLY filter commits of one repo (more-itertools), then validate
red->green in Docker. Stage 2: baseline pass rate (no jigs). Stage 3: convergence loop (supervisor
authors deterministic test-gated jigs; generalization-gated on held-out commits).

Build-time only uses git/docker on the host (supervisor). Runtime solving stays local-2B-only.
"""
from __future__ import annotations

import ast
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Per-repo config (multi-repo, kept indefinitely expandable). docker img can be shared across
# pure-Python repos (python+pytest). code/test prefixes locate the change vs the tests.
REGISTRY: dict[str, dict] = {
    "more-itertools": {"code": "more_itertools/", "test": "tests/", "img": "mi-test"},
    "toolz": {"code": "toolz/", "test": "toolz/tests/", "img": "mi-test"},
}


def _spec(repo: Path) -> dict:
    return REGISTRY.get(repo.name, {"code": "", "test": "tests/", "img": "mi-test"})


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


@dataclass
class CommitInfo:
    sha: str
    subject: str
    code_files: list[str]
    test_files: list[str]
    parent: str


def _files_changed(repo: Path, sha: str) -> list[str]:
    out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    return [f for f in out.splitlines() if f.strip()]


def structural_filter(repo: Path, n: int = 400, skip: int = 0) -> tuple[list[CommitInfo], dict]:
    """Categorize n commits (optionally skipping the newest `skip`). KEEP only non-merge commits that
    touch CODE and TESTS. Returns (candidates oldest->newest, drop_ledger {reason: count}). `skip`
    carves a DEV window disjoint from the scored set (never tune on the scored commits)."""
    args = ["rev-list", "--skip", str(skip), "-n", str(n), "HEAD"] if skip else ["rev-list", "-n", str(n), "HEAD"]
    shas = _git(repo, *args).split()
    ledger: dict[str, int] = {"merge": 0, "no_code": 0, "no_test": 0, "kept_candidate": 0}
    candidates: list[CommitInfo] = []
    for sha in shas:
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if len(parents) >= 2:
            ledger["merge"] += 1
            continue
        files = _files_changed(repo, sha)
        sp = _spec(repo)
        code = [f for f in files if f.startswith(sp["code"]) and f.endswith(".py")
                and not f.endswith("__init__.py")]
        tests = [f for f in files if f.startswith(sp["test"]) and f.endswith(".py")]
        if not code:
            ledger["no_code"] += 1
            continue
        if not tests:
            ledger["no_test"] += 1
            continue
        subject = _git(repo, "log", "-1", "--format=%s", sha).strip()
        candidates.append(CommitInfo(sha=sha, subject=subject, code_files=code,
                                     test_files=tests, parent=parents[0] if parents else ""))
        ledger["kept_candidate"] += 1
    candidates.reverse()  # oldest -> newest
    return candidates, ledger


# --- Red->green validation (REQ-3): the oracle is the repo's own tests, never diff-match ----------

def _test_nodes(src: str) -> dict[str, str]:
    """{node_id -> source} for test functions/methods. node_id = 'Class::method' or 'func'."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test"):
                    out[f"{node.name}::{m.name}"] = ast.get_source_segment(src, m) or m.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            out[node.name] = ast.get_source_segment(src, node) or node.name
    return out


def _affected_nodes(repo: Path, sha: str, parent: str, test_file: str) -> list[str]:
    """pytest node ids for tests ADDED or whose source CHANGED in `sha` vs `parent`."""
    c_src = _git(repo, "show", f"{sha}:{test_file}")
    p_src = _git(repo, "show", f"{parent}:{test_file}") if parent else ""
    c_nodes, p_nodes = _test_nodes(c_src), _test_nodes(p_src)
    return [f"{test_file}::{k}" for k, v in c_nodes.items() if p_nodes.get(k) != v]


def _run_nodes(repo: Path, nodes: list[str], timeout: int = 180) -> set[str]:
    """Run pytest on `nodes` in the reproducible Docker env. Return the set that did NOT pass
    (failed/errored/uncollected) — i.e. 'red' nodes."""
    if not nodes:
        return set()
    cmd = ["docker", "run", "--rm", "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest", *nodes,
           "-v", "--tb=no", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        text = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return set(nodes)
    passed = set(re.findall(r"^(\S+) PASSED", text, re.M))
    return set(nodes) - passed


def _reset(repo: Path, branch: str) -> None:
    _git(repo, "checkout", "-f", branch)
    _git(repo, "clean", "-fdq")


def validate_redgreen(repo: Path, c: CommitInfo, branch: str, timeout: int = 180) -> tuple[str, list[str]]:
    """Solved-able iff the affected tests FAIL at parent+commit-tests (red) and PASS at the full
    commit (green). Returns (status, redgreen_node_ids). status in
    {valid, no_affected_tests, not_red, not_green}."""
    nodes: list[str] = []
    for tf in c.test_files:
        nodes += _affected_nodes(repo, c.sha, c.parent, tf)
    if not nodes:
        return ("no_affected_tests", [])
    try:
        _git(repo, "checkout", "-f", c.parent)          # parent code
        _git(repo, "checkout", c.sha, "--", "tests/")   # + the commit's tests
        red = _run_nodes(repo, nodes, timeout)
        _git(repo, "checkout", "-f", c.sha)             # full commit
        green_fail = _run_nodes(repo, nodes, timeout)
    finally:
        _reset(repo, branch)
    redgreen = [n for n in nodes if n in red and n not in green_fail]
    if not any(n in red for n in nodes):
        return ("not_red", [])          # tests already pass at parent — don't capture the change
    if not redgreen:
        return ("not_green", [])        # oracle broken — commit doesn't make them pass
    return ("valid", redgreen)


# --- Baseline attempt (REQ-4): the existing local 2B harness tries each commit, scored red->green ---

def _code_funcs(src: str) -> dict[str, str]:
    """{name -> source} for module-level functions."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    return {n.name: (ast.get_source_segment(src, n) or "")
            for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _target_funcs(repo: Path, task: dict) -> list[tuple[str, str, str | None]]:
    """(code_file, func_name, parent_source_or_None) for functions ADDED/CHANGED by the commit."""
    out = []
    for cf in task["code_files"]:
        c_f = _code_funcs(_git(repo, "show", f"{task['sha']}:{cf}"))
        p_f = _code_funcs(_git(repo, "show", f"{task['parent']}:{cf}"))
        for name, csrc in c_f.items():
            if p_f.get(name) != csrc:
                out.append((cf, name, p_f.get(name)))
    return out


def _test_source(repo: Path, task: dict) -> str:
    """Source of the red->green test nodes (the visible spec for the change)."""
    srcs = []
    for tf in task["test_files"]:
        nodes = _test_nodes(_git(repo, "show", f"{task['sha']}:{tf}"))
        for node_id in task["redgreen"]:
            key = node_id.split("::", 1)[1] if "::" in node_id else node_id
            if key in nodes:
                srcs.append(nodes[key])
    return "\n\n".join(srcs)


def _apply_func(src: str, name: str, new_func: str) -> str:
    """Replace function `name` in src with new_func; if new, append it and add to __all__."""
    funcs = _code_funcs(src)
    if funcs.get(name):
        return src.replace(funcs[name], new_func, 1)
    m = re.search(r"__all__\s*=\s*\[", src)
    if m:
        src = src[:m.end()] + f"\n    '{name}'," + src[m.end():]
    return src.rstrip() + "\n\n\n" + new_func + "\n"


def _file_context(src: str, max_chars: int = 900) -> str:
    """Module preamble the 2B is currently blind to: imports + module-level definitions (sentinels,
    constants, __all__) before the first def/class. The 'repo context' the diagnostic points at."""
    keep: list[str] = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("def ", "class ", "@", "async def ")) and keep:
            break
        keep.append(line)
    pre = "\n".join(keep).strip()
    return pre[:max_chars]


def baseline_solve_2b(subject: str, test_src: str, name: str, parent_src: str | None,
                      feedback: str = "", intent_only: bool = False, context: str = "",
                      think: bool = False, fewshot: bool = False, gherkin: bool = False) -> str:
    """Local-2B single-function solve for a real repo function.

    intent_only=True (the STRONG, non-gameable, SWE-bench-style claim): the model gets ONLY the commit
    message + the parent code — NOT the test it is scored on. No leakage, no iteration (feedback from
    the scored test would leak the expected values).
    intent_only=False (TDD framing, gameable-in-principle, label it): the failing test is shown as the
    spec and `feedback` enables fix_loop-style iteration against it. Report this only as an upper bound."""
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm
    ctx = (f"The function currently is:\n\n{parent_src}\n" if parent_src
           else f"There is no `{name}` yet — write it.\n")
    test_block = "" if intent_only else f"\n\nFAILING TEST (it must pass):\n{test_src[:1600]}"
    ctx_block = f"\nMODULE CONTEXT (imports + module-level names available):\n{context}\n" if context else ""
    fb = "" if intent_only else (
        f"\nYour previous attempt FAILED with:\n{feedback[:600]}\nFix the cause.\n" if feedback else "")
    if gherkin:
        think_instr = (f"First, inside <think> </think>, write 2-4 short Given/When/Then behavior "
                       f"scenarios for `{name}` AFTER the change — each capturing exactly the NEW behavior "
                       f"the COMMIT INTENT requires (new parameters, new outputs, edge cases). They state "
                       f"what must become TRUE, so you cannot just copy the current function. Then AFTER "
                       f"</think>, implement `{name}` to satisfy every scenario. ")
    elif think:
        think_instr = ("First, inside <think> </think>, reason about EXACTLY what the COMMIT INTENT requires "
                       "CHANGING in this function (a new parameter? new behavior? a bug fix?) — do NOT just "
                       "copy the current function. Then AFTER </think>, ")
    else:
        think_instr = ""
    demo = ("EXAMPLE of the KIND of edit (note the output MODIFIES the function per the intent — it "
            "does NOT just copy it):\nCURRENT:\ndef total(items):\n    return sum(items)\n"
            "INTENT: allow summing from a starting value.\nCORRECT OUTPUT:\ndef total(items, start=0):\n"
            "    return sum(items, start)\n\n") if fewshot else ""
    prompt = (f"{demo}You are changing a Python library so a failing test passes. Implement/repair the "
              f"function `{name}`.\nCOMMIT INTENT: {subject}{test_block}{ctx_block}\n\n{ctx}{fb}\n"
              f"{think_instr}Output ONLY the complete `def {name}(...):` definition — valid Python, "
              f"correct indentation, no markdown, no prose, no test code.")
    reply = _llm().complete(LlmRequest(prompt=prompt, params={
        "temperature": 0.0, "max_tokens": 1500 if (think or gherkin) else 700})).text
    if (think or gherkin) and "</think>" in reply:
        reply = reply.rsplit("</think>", 1)[1]
    s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    i = s.find(f"def {name}")
    return s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")


def _run_nodes_fb(repo: Path, nodes: list[str], timeout: int = 180) -> tuple[set[str], str]:
    """Like _run_nodes but also returns a short failure traceback (feedback for iteration)."""
    cmd = ["docker", "run", "--rm", "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest", *nodes,
           "-v", "--tb=short", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        text = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return set(nodes), "timeout"
    passed = set(re.findall(r"^(\S+) PASSED", text, re.M))
    fails = set(nodes) - passed
    err = text[-700:] if fails else ""
    return fails, err


# --- EXT-012 Slice 1: full 2B-authored behavioral loop (Gherkin -> self-tests -> code -> fix) -------
# The 2B authors EVERY layer. Self-tests are SCAFFOLDING derived from the intent; the model never sees
# the hidden oracle (task["redgreen"]), which alone scores. No leakage.
def _g_llm(prompt: str, max_tokens: int) -> str:
    from jaros.llm import LlmRequest
    from harness.pass1_eval import _llm
    return _llm().complete(LlmRequest(prompt=prompt, params={
        "temperature": 0.0, "max_tokens": max_tokens})).text


def g_gherkin(subject: str, name: str, parent_src: str | None, context: str) -> str:
    """STEP: the 2B authors the behavior spec for `name` AFTER the change — new behavior the intent
    requires PLUS existing behavior that must be preserved."""
    cur = f"It currently is:\n{parent_src}\n" if parent_src else f"`{name}` does not exist yet.\n"
    ctx = f"Module context:\n{context}\n" if context else ""
    out = _g_llm(
        f"You are changing a Python library function `{name}`.\nCOMMIT INTENT: {subject}\n{ctx}{cur}\n"
        f"Write the behavior specification for `{name}` AFTER the change as 3-6 numbered Given/When/Then "
        f"scenarios. Include BOTH the NEW behavior the intent requires AND existing behavior that must "
        f"stay the same. Output ONLY the numbered scenarios.", 600)
    return out.strip()


def g_selftests(name: str, gherkin: str, pkg: str) -> str:
    """STEP: the 2B writes pytest tests matching every scenario (its OWN alignment tests, from the
    spec — NEVER the hidden oracle)."""
    reply = _g_llm(
        f"Behavior scenarios for `{name}`:\n{gherkin}\n\n"
        f"Write pytest tests checking EACH scenario for `{name}`. Begin with `from {pkg} import {name}`. "
        f"Use plain `def test_...():` functions with assert statements (use `import pytest` + "
        f"`pytest.raises` where a scenario expects an error). Output ONLY runnable Python test code, "
        f"no markdown, no prose.", 700)
    return re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()


def g_code(subject: str, name: str, parent_src: str | None, context: str, gherkin: str,
           feedback: str = "") -> str:
    """STEP: the 2B writes/modifies code to satisfy the scenarios (and fix its own failing tests)."""
    cur = f"Current version:\n{parent_src}\n" if parent_src else ""
    ctx = f"Module context:\n{context}\n" if context else ""
    fb = (f"\nYour previous code FAILED its own tests:\n{feedback[:600]}\nFix the cause.\n"
          if feedback else "")
    reply = _g_llm(
        f"Implement the Python function `{name}` to satisfy these behavior scenarios:\n{gherkin}\n\n"
        f"{ctx}{cur}COMMIT INTENT: {subject}\n{fb}\nOutput ONLY the complete `def {name}(...):` "
        f"definition — valid Python, correct indentation, no markdown, no prose, no test code.", 800)
    s = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    i = s.find(f"def {name}")
    return s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")


# --- Slice 1b: the 2B's alignment REVIEW loops (the heart of the owner's design) ------------------
def g_review_gherkin(subject: str, name: str, parent_src: str | None, gherkin: str) -> str:
    """SELF-REVIEW: the 2B judges its OWN scenarios — do they fully satisfy the intent AND preserve
    existing behavior? Returns the (possibly revised) scenarios."""
    cur = f"Current function:\n{parent_src}\n" if parent_src else ""
    out = _g_llm(
        f"COMMIT INTENT: {subject}\n{cur}Proposed behavior scenarios for `{name}`:\n{gherkin}\n\n"
        f"Review them: do they FULLY capture the new behavior the intent requires AND preserve existing "
        f"behavior that must not change? If complete and correct, output them unchanged; otherwise output "
        f"corrected/expanded numbered scenarios. Output ONLY the numbered scenarios.", 600)
    return out.strip() or gherkin


def g_review_tests(name: str, gherkin: str, tests: str, pkg: str) -> str:
    """SELF-REVIEW: the 2B checks test<->Gherkin alignment — every scenario tested, each test correct."""
    reply = _g_llm(
        f"Behavior scenarios for `{name}`:\n{gherkin}\n\nProposed pytest tests:\n{tests}\n\n"
        f"Review: does each scenario have a matching, correct test? If aligned, output the tests "
        f"unchanged; otherwise output corrected tests. Begin with `from {pkg} import {name}`. Output ONLY "
        f"runnable Python test code, no markdown.", 700)
    out = re.sub(r"```[\w+-]*", "", reply).replace("```", "").strip()
    return out or tests


def g_signoff(name: str, gherkin: str, code: str) -> tuple[bool, str]:
    """SIGN-OFF: final code<->Gherkin review. (signed_off, reason). NO -> one more code revision."""
    out = _g_llm(
        f"Behavior scenarios for `{name}`:\n{gherkin}\n\nImplementation:\n{code}\n\n"
        f"Does the implementation correctly satisfy EVERY scenario? Answer ONLY 'YES' or 'NO: <reason>'.",
        200).strip()
    return out.upper().startswith("YES"), out


def _run_selftests(repo: Path, test_code: str, timeout: int = 120) -> tuple[bool, str]:
    """Run the 2B's OWN tests (scaffolding) in the Docker env. (all_passed, short_feedback).
    returncode 0 == tests ran and all passed (pytest returns 5 for no-tests, 1 for failures)."""
    (repo / "tests" / "test_gherkin_self.py").write_text(test_code, encoding="utf-8", newline="\n")
    cmd = ["docker", "run", "--rm", "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest",
           "tests/test_gherkin_self.py", "--tb=short", "-q", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr)[-700:]
    except subprocess.TimeoutExpired:
        return False, "timeout"


def attempt_gherkin(repo: Path, task: dict, branch: str, timeout: int = 180, max_fix: int = 2,
                    reviews: bool = False) -> str:
    """EXT-012: per changed function the 2B authors Gherkin -> self-tests -> code, then fixes the code
    against its OWN tests; the final code is scored on the HIDDEN oracle (red->green). reviews=True adds
    Slice 1b: the 2B's self-review of the Gherkin, the test<->Gherkin review, and the code<->Gherkin
    sign-off (the alignment heart)."""
    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}
        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]
            gk = g_gherkin(task["subject"], name, parent_src, ctx[cf])
            if reviews:                                  # 1b: self-review the behavior spec
                gk = g_review_gherkin(task["subject"], name, parent_src, gk)
            tests = g_selftests(name, gk, pkg)
            if reviews:                                  # 1b: test<->Gherkin alignment review
                tests = g_review_tests(name, gk, tests, pkg)
            code = g_code(task["subject"], name, parent_src, ctx[cf], gk)
            for _ in range(max_fix + 1):
                if not code:
                    break
                content = orig[cf]                      # clean parent + funcs settled so far + this one
                for n2, c2 in {**final.get(cf, {}), name: code}.items():
                    if c2:
                        content = _apply_func(content, n2, c2)
                (repo / cf).write_text(content, encoding="utf-8", newline="\n")
                ok, fb = _run_selftests(repo, tests, 25)   # 2B unit tests are ~instant; a hang = bad test, fail fast
                if ok:
                    break
                code = g_code(task["subject"], name, parent_src, ctx[cf], gk, fb)
            if reviews and code:                         # 1b: final code<->Gherkin sign-off
                signed, reason = g_signoff(name, gk, code)
                if not signed:
                    revised = g_code(task["subject"], name, parent_src, ctx[cf], gk,
                                     f"sign-off found a gap: {reason}")
                    if revised:                          # KEEP-OR-IMPROVE GUARD: accept the sign-off
                        content = orig[cf]               # revision ONLY if it still passes the self-tests
                        for n2, c2 in {**final.get(cf, {}), name: revised}.items():
                            if c2:
                                content = _apply_func(content, n2, c2)
                        (repo / cf).write_text(content, encoding="utf-8", newline="\n")
                        ok2, _ = _run_selftests(repo, tests, 25)
                        if ok2:                          # else keep the pre-sign-off code (never degrade)
                            code = revised
            final.setdefault(cf, {})[name] = code or ""
        for cf in files:                                # consolidate all settled functions per file
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")
        st = repo / "tests" / "test_gherkin_self.py"    # remove scaffolding before the oracle
        if st.exists():
            st.unlink()
        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


def run_gherkin(repo: Path, branch: str, tasks: list[dict], reviews: bool = False) -> dict:
    """EXT-012 over tasks, scored on the hidden oracle. Honest pass@1 + Wilson CI. reviews -> Slice 1b."""
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin(repo, t, branch, reviews=reviews)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    slice_tag = "Slice 1b (+reviews)" if reviews else "Slice 1a (core loop)"
    print(f">>> RESULT [EXT-012 gherkin-loop {slice_tag} / intent-only / test HIDDEN]: {k}/{n} = "
          f"{k/n*100:.1f}% red->green  [Wilson95 {lo*100:.1f}-{hi*100:.1f}%]\n>>> breakdown: {dict(res)}",
          flush=True)
    return dict(res)


def attempt_task(repo: Path, task: dict, branch: str, solve=baseline_solve_2b,
                 max_iter: int = 1, intent_only: bool = False, use_context: bool = False,
                 use_think: bool = False, use_fewshot: bool = False, use_gherkin: bool = False,
                 timeout: int = 180) -> str:
    """Attempt one commit-replay task. intent_only=True -> message+code only, one-shot, no test
    shown/iterated (the strong non-gameable claim). Else -> failing test shown + iterated up to
    max_iter (TDD upper bound). use_context -> add the file's module preamble (the repo-context jig).
    Returns 'pass'/'fail'/'no_target'/'empty'/'apply_err'."""
    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    test_src = "" if intent_only else _test_source(repo, task)
    iters = 1 if intent_only else max_iter
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}  # clean parent per file
        ctx = {cf: (_file_context(orig[cf]) if use_context else "") for cf in files}
        feedback = ""
        for _ in range(iters):
            edits: dict[str, list] = {}                       # solve EVERY changed function
            for cf, name, parent_src in targets:
                nf = solve(task["subject"], test_src, name, parent_src, feedback, intent_only,
                           ctx[cf], use_think, use_fewshot, use_gherkin)
                if nf:
                    edits.setdefault(cf, []).append((name, nf))
            if not edits:
                return "empty"
            try:
                for cf, funcs in edits.items():               # apply all of them, per file
                    content = orig[cf]
                    for name, nf in funcs:
                        content = _apply_func(content, name, nf)
                    (repo / cf).write_text(content, encoding="utf-8", newline="\n")
            except Exception:
                return "apply_err"
            fails, feedback = _run_nodes_fb(repo, task["redgreen"], timeout)
            if not fails:
                return "pass"
    finally:
        _reset(repo, branch)
    return "fail"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a proportion (honest small-n interval)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run_baseline(repo: Path, branch: str, tasks: list[dict], solve=baseline_solve_2b,
                 max_iter: int = 1, intent_only: bool = False, use_context: bool = False,
                 use_think: bool = False, use_fewshot: bool = False, use_gherkin: bool = False) -> dict:
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_task(repo, t, branch, solve=solve, max_iter=max_iter, intent_only=intent_only,
                             use_context=use_context, use_think=use_think, use_fewshot=use_fewshot,
                             use_gherkin=use_gherkin)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    ctx_tag = (" +ctx" if use_context else "") + (" +think" if use_think else "") \
        + (" +fewshot" if use_fewshot else "") + (" +gherkin" if use_gherkin else "")
    label = ((f"intent-only / 1-shot / test HIDDEN (strong, non-gameable){ctx_tag}" if intent_only
              else f"test-as-spec / iter<={max_iter} (TDD upper bound){ctx_tag}"))
    print(f">>> RESULT [{label}]: {k}/{n} = {k/n*100:.1f}% red->green  "
          f"[Wilson95 {lo*100:.1f}-{hi*100:.1f}%]", flush=True)
    print(f">>> breakdown: {dict(res)}", flush=True)
    return {"pass": k, "n": n, "wilson": (lo, hi), "breakdown": dict(res)}


if __name__ == "__main__":
    import json
    import sys
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".jaros-data/repos/more-itertools")
    if "--gherkin-loop" in sys.argv:
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        tag = "dev" if "--dev" in sys.argv else "valid"
        tj = repo.parent.parent / "artifacts" / f"{repo.name}_{tag}_tasks.json"
        tasks = json.loads(tj.read_text(encoding="utf-8"))
        reviews = "--reviews" in sys.argv
        print(f">>> EXT-012 GHERKIN-LOOP {'1b(+reviews)' if reviews else '1a'} (2B authors Gherkin->"
              f"tests->code) on {len(tasks)} {tag} tasks of {repo.name}", flush=True)
        run_gherkin(repo, branch, tasks, reviews=reviews)
        sys.exit(0)

    if "--baseline" in sys.argv:
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        tag = "dev" if "--dev" in sys.argv else "valid"
        tj = repo.parent.parent / "artifacts" / f"{repo.name}_{tag}_tasks.json"
        tasks = json.loads(tj.read_text(encoding="utf-8"))
        intent_only = "--intent-only" in sys.argv
        use_context = "--context" in sys.argv
        use_think = "--think" in sys.argv
        use_fewshot = "--fewshot" in sys.argv
        use_gherkin = "--gherkin" in sys.argv
        max_iter = int(sys.argv[sys.argv.index("--iters") + 1]) if "--iters" in sys.argv else 1
        mode = ("INTENT-ONLY (test hidden)" if intent_only else f"test-as-spec iter<={max_iter}") \
            + (" +context" if use_context else "") + (" +think" if use_think else "") \
            + (" +fewshot" if use_fewshot else "") + (" +gherkin" if use_gherkin else "")
        print(f">>> {mode} on {len(tasks)} {tag} tasks of {repo.name}", flush=True)
        run_baseline(repo, branch, tasks, max_iter=max_iter, intent_only=intent_only,
                     use_context=use_context, use_think=use_think, use_fewshot=use_fewshot,
                     use_gherkin=use_gherkin)
        sys.exit(0)
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 400
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
    cands, ledger = structural_filter(repo, n, skip=skip)
    tag = "dev" if skip else "valid"
    print(f">>> structural filter on {n} commits (skip {skip}) of {repo.name}", flush=True)
    print(f">>> drop ledger: {json.dumps(ledger)}", flush=True)
    print(f">>> structural candidates (touch code+tests, non-merge): {len(cands)}", flush=True)
    if "--validate" in sys.argv:
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        counts: dict[str, int] = {}
        valid = []
        for i, c in enumerate(cands):
            try:
                status, rg = validate_redgreen(repo, c, branch)
            except Exception as e:  # noqa: BLE001
                status, rg = f"err:{type(e).__name__}", []
            counts[status] = counts.get(status, 0) + 1
            if status == "valid":
                valid.append({"sha": c.sha, "parent": c.parent, "subject": c.subject,
                              "redgreen": rg, "code_files": c.code_files, "test_files": c.test_files})
            print(f"  {i+1}/{len(cands)} {c.sha[:8]} [{status}] rg={len(rg)} | {c.subject[:42]}", flush=True)
        print(f">>> VALIDATION: {json.dumps(counts)}", flush=True)
        print(f">>> VALID red->green tasks: {len(valid)}", flush=True)
        out = repo.parent.parent / "artifacts" / f"{repo.name}_{tag}_tasks.json"
        out.write_text(json.dumps(valid, indent=1), encoding="utf-8")
        print(f">>> saved -> {out}", flush=True)
    else:
        for c in cands[:15]:
            print(f"  {c.sha[:8]} | code={len(c.code_files)} test={len(c.test_files)} | {c.subject[:70]}")
