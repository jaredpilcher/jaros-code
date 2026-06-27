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
import uuid
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


# #EXT-011-REQ-8 Start
def _run_nodes(repo: Path, nodes: list[str], timeout: int = 180) -> set[str]:
    """Run pytest on `nodes` in the reproducible Docker env. Return the set that did NOT pass
    (failed/errored/uncollected) — i.e. 'red' nodes.

    Container lifecycle is BULLETPROOF (mirrors _run_selftests / EXT-011 REQ-8): every
    invocation gets a unique --name and is force-removed in a try/finally block regardless
    of success, timeout, or exception. An infinite-loop candidate that reaches the oracle
    is killed and removed — never orphaned at 100% CPU."""
    if not nodes:
        return set()
    cname = f"jaros_oracle_{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", cname, "--stop-timeout", "5",
           "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest", *nodes,
           "-v", "--tb=no", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        text = r.stdout + r.stderr
        passed = set(re.findall(r"^(\S+) PASSED", text, re.M))
        return set(nodes) - passed
    except subprocess.TimeoutExpired:
        _docker_force_remove(cname)
        return set(nodes)
    except Exception:  # noqa: BLE001
        _docker_force_remove(cname)
        raise
    finally:
        _docker_force_remove(cname)
# #EXT-011-REQ-8 End


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


# #EXT-011-REQ-8 Start
def _run_nodes_fb(repo: Path, nodes: list[str], timeout: int = 180) -> tuple[set[str], str]:
    """Like _run_nodes but also returns a short failure traceback (feedback for iteration).

    Container lifecycle mirrors _run_nodes (EXT-011 REQ-8): unique --name + force-remove
    in try/finally so an infinite-loop candidate never orphans a container."""
    cname = f"jaros_oracle_{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", cname, "--stop-timeout", "5",
           "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest", *nodes,
           "-v", "--tb=short", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        text = r.stdout + r.stderr
        passed = set(re.findall(r"^(\S+) PASSED", text, re.M))
        fails = set(nodes) - passed
        err = text[-700:] if fails else ""
        return fails, err
    except subprocess.TimeoutExpired:
        _docker_force_remove(cname)
        return set(nodes), "timeout"
    except Exception:  # noqa: BLE001
        _docker_force_remove(cname)
        raise
    finally:
        _docker_force_remove(cname)
# #EXT-011-REQ-8 End


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
        f"stay the same. Output ONLY the numbered scenarios.", 600)   # comprehension step PRUNED (regressed
    return out.strip()                                                # held-out 37: lost Reject-by-ID, exactly_n still failed)


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
    code = s[i:] if i >= 0 else (s if s.lstrip().startswith("def ") else "")
    if code:                                   # STACK the proven parse-gated syntax-repair (pass1 lineage,
        try:                                   # +12% on HumanEval) — fires only if the code doesn't parse,
            from harness.pass1_eval import _bc, _llm   # so behavioral-solve gens inherit ALL proven layers
            code = _bc.repair_indentation(_llm(), code)   # in BOTH the /build product path and the eval.
        except Exception:                      # noqa: BLE001 — repair is best-effort, never block the solve
            pass
    return code


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


# #EXT-011-REQ-7 Start
def _docker_force_remove(name: str) -> None:
    """Best-effort force-kill + remove a named Docker container. Never raises."""
    try:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001
        pass
    try:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001
        pass


def _run_selftests(repo: Path, test_code: str, timeout: int = 120) -> tuple[bool, str]:
    """Run the 2B's OWN tests (scaffolding) in the Docker env. (all_passed, short_feedback).
    returncode 0 == tests ran and all passed (pytest returns 5 for no-tests, 1 for failures).

    Container lifecycle is BULLETPROOF: every container gets a unique --name and is
    force-removed in a try/finally block regardless of success, timeout, or exception.
    --rm is kept as a belt-and-suspenders defense, but the real guarantee is the
    explicit `docker rm -f <name>` in the finally clause."""
    tnode = _spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py"   # repo's real test dir (toolz/tests, tests, ...)
    (repo / tnode).write_text(test_code, encoding="utf-8", newline="\n")
    cname = f"jaros_selftest_{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", cname, "--stop-timeout", "5",
           "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest",
           tnode, "--tb=short", "-q", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr)[-700:]
    except subprocess.TimeoutExpired:
        _docker_force_remove(cname)
        return False, "timeout"
    except Exception:  # noqa: BLE001
        _docker_force_remove(cname)
        raise
    finally:
        # Belt-and-suspenders: runs even if the process already exited cleanly
        # (docker rm -f on a nonexistent container is a no-op exit 1, which we ignore).
        _docker_force_remove(cname)
# #EXT-011-REQ-7 End


def attempt_gherkin(repo: Path, task: dict, branch: str, timeout: int = 180, max_fix: int = 2,
                    reviews: bool = False, ensemble: bool = False, agentic: bool = False) -> str:
    """EXT-012: per changed function the 2B authors Gherkin -> self-tests -> code, then fixes the code
    against its OWN tests; the final code is scored on the HIDDEN oracle (red->green). reviews=True adds
    Slice 1b: the 2B's self-review of the Gherkin, the test<->Gherkin review, and the code<->Gherkin
    sign-off (the alignment heart)."""
    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    if len(targets) > 4:               # the 2B can't nail >4 functions in one pass; ~25min to inevitably
        return "capped"                # fail. Cap fail-fast (still counts as not-solved, reported separately).
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}
        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]
            if agentic:                                  # ORCHESTRATOR: the 2B judges which tool to use
                from harness.behavioral_solve import behavioral_solve_agentic

                def _rt(code: str, test_code: str, _cf=cf, _name=name) -> tuple[bool, str]:
                    content = orig[_cf]
                    for n2, c2 in {**final.get(_cf, {}), _name: code}.items():
                        if c2:
                            content = _apply_func(content, n2, c2)
                    (repo / _cf).write_text(content, encoding="utf-8", newline="\n")
                    return _run_selftests(repo, test_code, 25)
                res = behavioral_solve_agentic(task["subject"], name, parent_src, ctx[cf], pkg, _rt)
                final.setdefault(cf, {})[name] = res["code"] or ""
                continue
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
            if ensemble:                                 # HONEST ENSEMBLE: also try the plain baseline solve;
                def _passes_selftests(c: str) -> bool:   # pick whichever satisfies the gherkin SELF-tests
                    if not c:
                        return False
                    content = orig[cf]
                    for n2, c2 in {**final.get(cf, {}), name: c}.items():
                        if c2:
                            content = _apply_func(content, n2, c2)
                    (repo / cf).write_text(content, encoding="utf-8", newline="\n")
                    return _run_selftests(repo, tests, 25)[0]
                code_b = baseline_solve_2b(task["subject"], "", name, parent_src,
                                           intent_only=True, context=ctx[cf])
                if not _passes_selftests(code) and _passes_selftests(code_b):
                    code = code_b                        # baseline meets the spec where gherkin couldn't
            final.setdefault(cf, {})[name] = code or ""
        for cf in files:                                # consolidate all settled functions per file
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")
        st = repo / (_spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py")   # remove scaffolding before the oracle
        if st.exists():
            st.unlink()
        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


# #EXT-013-REQ-5 Start
def attempt_gherkin_jaros(repo: Path, task: dict, branch: str, timeout: int = 180,
                          max_fix: int = 2) -> str:
    """EXT-013 / REQ-5: per-function solve via the Jaros-native ``behavioral_solve_jaros``
    (Runtime gate -> executor -> DecisionLog), scored on the hidden oracle (red->green).

    The test-run op mirrors ``_run_selftests`` exactly — same Docker image, same container
    lifecycle (unique --name + force-remove in finally) — but the shell command is issued
    via ``Runtime.apply(shell.exec Decision)`` so it is gated + logged.  File writes
    (gherkin spec, self-tests, code artefacts) go through ``Runtime.apply(code.write_file
    Decision)``.  The comparison with the Python path is therefore apples-to-apples.
    """
    from harness.behavioral_solve import behavioral_solve_jaros
    from harness.coding_loop import Runtime

    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    if len(targets) > 4:
        return "capped"
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}

        # One Runtime per task — all per-function solves share the same DecisionLog.
        rt = Runtime()

        # Self-test file: same location as _run_selftests uses.
        tnode = _spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py"
        abs_test_path = str((repo / tnode).resolve())

        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]
            # Artefact paths for this function (written via Runtime through code.write_file).
            spec_path = str((repo / f".jcode/{name}.gherkin").resolve())
            code_path = str((repo / f".jcode/{name}.py").resolve())

            # Build the Docker test command (mirrors _run_selftests).
            cname = f"jaros_selftest_{uuid.uuid4().hex[:12]}"
            docker_cmd = (
                f"docker run --rm --name {cname} --stop-timeout 5 "
                f"-v {repo.resolve().as_posix()}:/repo -w /repo "
                f"-e PYTHONPATH=/repo {_spec(repo)['img']} "
                f"python -m pytest {tnode} --tb=short -q -p no:cacheprovider"
            )

            def _make_pre_test_hook(cf_=cf, name_=name):
                """Return a hook that applies the current code to the repo file BEFORE the
                Docker test run.  Called with (code, tests) by ``behavioral_solve_jaros``
                at each test iteration; the test file is already written by the test-writer
                agent's ``code.write_file`` Decision before this hook runs.

                The repo source file is written DIRECTLY (bypassing the code.write_file
                safety gate) because it is NOT generated content — it is a controlled
                _apply_func merge of the parent repo source + the candidate function.
                The repo file may contain legitimate constructs (e.g. ``__import__``) that
                the gate refuses as unsafe in model-generated code.  The agent-generated
                artefacts (gherkin spec, self-tests, code snippet) continue to go through
                the Runtime gate.  The Docker test-run Decision (shell.exec) is always
                gated + logged."""
                def hook(code: str, tests: str) -> None:
                    # Apply the generated code into the full repo source file.
                    content = orig[cf_]
                    for n2, c2 in {**final.get(cf_, {}), name_: code}.items():
                        if c2:
                            content = _apply_func(content, n2, c2)
                    # Direct write: repo source file merge is deterministic, not generated code.
                    (repo / cf_).write_text(content, encoding="utf-8", newline="\n")
                return hook

            pre_test_hook = _make_pre_test_hook()

            try:
                result = behavioral_solve_jaros(
                    intent=task["subject"],
                    name=name,
                    current_src=parent_src,
                    context=ctx[cf],
                    pkg=pkg,
                    runtime=rt,
                    spec_path=spec_path,
                    test_path=abs_test_path,
                    code_path=code_path,
                    test_command=docker_cmd,
                    max_fix=max_fix,
                    pre_test_hook=pre_test_hook,
                )
            finally:
                # Belt-and-suspenders: force-remove the container even on exception/timeout.
                _docker_force_remove(cname)

            final.setdefault(cf, {})[name] = result.get("code") or ""

        # Consolidate all settled functions per file.
        for cf in files:
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # Remove scaffolding before the oracle.
        st = repo / tnode
        if st.exists():
            st.unlink()

        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


def run_gherkin_jaros(repo: Path, branch: str, tasks: list[dict]) -> dict:
    """Run ``attempt_gherkin_jaros`` over all tasks, scored on the hidden oracle.
    Prints per-task results and a Wilson CI summary — same format as ``run_gherkin``."""
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin_jaros(repo, t, branch)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    print(f">>> RESULT [EXT-013 jaros-native gherkin-loop / intent-only / test HIDDEN]: "
          f"{k}/{n} = {k/n*100:.1f}% red->green  [Wilson95 {lo*100:.1f}-{hi*100:.1f}%]\n"
          f">>> breakdown: {dict(res)}", flush=True)
    return dict(res)
# #EXT-013-REQ-5 End


# #EXT-012-REQ-13 Start
def _apply_augmenter(name: str, source: str, self_tests: str) -> str:
    """Augment *self_tests* with doctest-derived assertions from *source*.

    Uses the ``code.augment_selftests`` execution-plane tool (deterministic, no LLM).
    Falls back to the original *self_tests* unchanged if the tool cannot parse
    the docstring or finds no examples (graceful no-op).

    HONESTY: *source* is the VISIBLE function/module source from the parent repo
    checkout.  The hidden oracle (``task["redgreen"]`` / ``test_more.py``) is
    never passed here — see SelftestAugmenterTool docstring.
    """
    import importlib.util as _ilu
    import os as _os
    from pathlib import Path as _Path
    from types import SimpleNamespace

    _tools_dir = _Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"
    tool_path = str(_tools_dir / "selftest_augmenter_tool.py")
    spec = _ilu.spec_from_file_location("_sat_tool", tool_path)
    mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)       # type: ignore[union-attr]
    tool = mod.SelftestAugmenterTool()

    decision = SimpleNamespace(
        payload={"name": name, "source": source, "self_tests": self_tests},
        type="code.augment_selftests",
    )
    v = tool.validate(decision)
    if not v.ok:
        return self_tests   # validation failed — leave tests unchanged
    result = tool.execute(decision)
    return result.get("self_tests", self_tests)


def attempt_gherkin_jaros_augment(repo: Path, task: dict, branch: str,
                                  timeout: int = 180, max_fix: int = 2) -> str:
    """EXT-012 / REQ-13: per-function solve via the Jaros-native fix-loop with
    STRONGER ORACLE self-tests.

    Mirrors ``attempt_gherkin_jaros`` exactly, except that after the model's
    ``g_selftests`` grain produces the initial self-tests, they are augmented via
    the deterministic ``code.augment_selftests`` tool: doctest ``>>> `` examples
    from the target function's VISIBLE docstring (parent repo source) are parsed
    and appended as concrete ``assert`` statements.

    HONESTY: augmentation reads ONLY the visible docstring from the parent source
    checkout — NEVER the hidden oracle (``task["redgreen"]`` / ``test_more.py``).
    The hidden oracle is used only at the final scoring step (same as every other
    path).  Augmented tests remain SCAFFOLDING; they are removed before the oracle
    run (same as ``_run_selftests`` in the non-augmented path).

    Default behavior is NOT changed: ``attempt_gherkin_jaros`` is unmodified.
    This function is a separate additive path, active only when ``--augment`` is
    passed on the CLI.
    """
    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    if len(targets) > 4:
        return "capped"
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}
        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]

            # Step 1: Gherkin spec (same Python-path grain as attempt_gherkin).
            gk = g_gherkin(task["subject"], name, parent_src, ctx[cf])

            # Step 2: Model's self-tests from the spec.
            tests = g_selftests(name, gk, pkg)

            # Step 3: AUGMENT with doctest-derived assertions from the VISIBLE source.
            # HONESTY: orig[cf] is the parent repo source (visible); NOT the hidden oracle.
            tests = _apply_augmenter(name, orig[cf], tests)

            # Step 4: Deterministic fix-loop (code -> run augmented tests -> revise).
            code = g_code(task["subject"], name, parent_src, ctx[cf], gk)
            for _ in range(max_fix + 1):
                if not code:
                    break
                content = orig[cf]
                for n2, c2 in {**final.get(cf, {}), name: code}.items():
                    if c2:
                        content = _apply_func(content, n2, c2)
                (repo / cf).write_text(content, encoding="utf-8", newline="\n")
                ok, fb = _run_selftests(repo, tests, 25)
                if ok:
                    break
                code = g_code(task["subject"], name, parent_src, ctx[cf], gk, fb)
            final.setdefault(cf, {})[name] = code or ""

        # Consolidate all settled functions per file.
        for cf in files:
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # Remove scaffolding before the oracle (mirrors attempt_gherkin).
        st = repo / (_spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py")
        if st.exists():
            st.unlink()

        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


def run_gherkin_jaros_augment(repo: Path, branch: str, tasks: list[dict]) -> dict:
    """Run ``attempt_gherkin_jaros_augment`` over all tasks, scored on the hidden oracle.
    Prints per-task results and a Wilson CI summary (same format as ``run_gherkin_jaros``).

    This is the measurement harness for EXT-012 REQ-13 (stronger-oracle).  The
    full 37-task run is launched with::

        python -m harness.commit_replay <repo> --gherkin-loop --jaros --augment --n 37
    """
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin_jaros_augment(repo, t, branch)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    print(f">>> RESULT [EXT-012 REQ-13 stronger-oracle augment / intent-only / test HIDDEN]: "
          f"{k}/{n} = {k/n*100:.1f}% red->green  [Wilson95 {lo*100:.1f}-{hi*100:.1f}%]\n"
          f">>> breakdown: {dict(res)}", flush=True)
    return dict(res)
# #EXT-012-REQ-13 End


# #EXT-012-REQ-12 Start
def _run_selftests_count(repo: Path, test_code: str, timeout: int = 120) -> tuple[int, str]:
    """Run the 2B's self-tests in Docker and return (pass_count, feedback).

    Mirrors ``_run_selftests`` exactly (same Docker image, same container lifecycle:
    unique --name + force-remove in finally) but returns an INTEGER pass count instead
    of a bool, so it can be used as the ``run_selftests`` callable for
    ``generate_and_test_solve``.

    HONESTY: the test_code MUST be derived from the model's own spec (visible intent),
    NEVER from the hidden oracle.  This invariant is the caller's responsibility and is
    documented at each call site.
    """
    tnode = _spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py"
    (repo / tnode).write_text(test_code, encoding="utf-8", newline="\n")
    cname = f"jaros_gentest_{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", cname, "--stop-timeout", "5",
           "-v", f"{repo.resolve().as_posix()}:/repo", "-w", "/repo",
           "-e", "PYTHONPATH=/repo", _spec(repo)["img"], "python", "-m", "pytest",
           tnode, "--tb=no", "-q", "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        text = r.stdout + r.stderr
        # Count passed tests from pytest -q summary ("X passed" line).
        import re as _re
        m = _re.search(r"(\d+) passed", text)
        count = int(m.group(1)) if m else 0
        return count, text[-500:]
    except subprocess.TimeoutExpired:
        _docker_force_remove(cname)
        return 0, "timeout"
    except Exception:  # noqa: BLE001
        _docker_force_remove(cname)
        raise
    finally:
        _docker_force_remove(cname)


def attempt_gherkin_jaros_gen(repo: Path, task: dict, branch: str, timeout: int = 180,
                              n_gen: int = 4) -> str:
    """EXT-012 / REQ-12: per-function solve via generate-and-test (best-of-N by self-tests),
    scored on the hidden oracle (red->green).

    For each changed function the 2B authors Gherkin -> self-tests (same as
    ``attempt_gherkin``), then ``generate_and_test_solve`` generates ``n_gen`` candidate
    implementations at varied seeds and selects the best by the self-test pass count.

    SELECTION HONESTY: the ``run_selftests`` callable passed to ``generate_and_test_solve``
    uses ONLY the model's own spec-derived tests (``_run_selftests_count``).  The hidden
    oracle (``task["redgreen"]``) is NEVER exposed to the solve or to the selection step —
    it is only used at the very end to score the chosen candidate (same as every other path).

    Container lifecycle mirrors ``attempt_gherkin_jaros`` and ``_run_selftests`` exactly:
    each Docker run gets a unique ``--name`` and is force-removed in a try/finally block
    regardless of success, timeout, or exception (EXT-011 REQ-7 / #14-safe).
    """
    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    if len(targets) > 4:
        return "capped"
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}

        # One minimal Runtime per task (for the generate_and_test_solve Decision log).
        from harness.coding_loop import Runtime
        rt = Runtime()

        # Self-test file: same location as _run_selftests / attempt_gherkin_jaros use.
        tnode = _spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py"

        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]

            # Step 1: author Gherkin + self-tests (same Python-path grains as attempt_gherkin).
            gk = g_gherkin(task["subject"], name, parent_src, ctx[cf])
            tests = g_selftests(name, gk, pkg)

            # Step 2: build the run_selftests callable.
            # HONESTY: `tests` is derived from the model's OWN Gherkin spec (visible intent).
            # The hidden oracle is NEVER touched here — selection is purely by self-tests.
            def _make_run_selftests(cf_=cf, name_=name, tests_=tests):
                """Return a callable (code: str) -> int that applies code and runs Docker.

                The test file has already been written to disk with the model's own
                spec-derived tests.  Each call applies the candidate code to the repo
                source file, re-writes the test file (idempotent), runs pytest in Docker,
                and returns the integer pass count.  Container cleanup is guaranteed by
                ``_run_selftests_count``'s try/finally block.
                """
                def _run(code: str) -> int:
                    # Apply the candidate into the full repo source file.
                    content = orig[cf_]
                    for n2, c2 in {**final.get(cf_, {}), name_: code}.items():
                        if c2:
                            content = _apply_func(content, n2, c2)
                    # Direct write: deterministic merge, not generated content.
                    (repo / cf_).write_text(content, encoding="utf-8", newline="\n")
                    # Run Docker self-tests and return pass count (not bool).
                    # HONESTY: tests_ was derived from visible spec only — never the oracle.
                    count, _ = _run_selftests_count(repo, tests_, 25)
                    return count
                return _run

            run_selftests = _make_run_selftests()

            # Step 3: generate N candidates and select best by self-test pass count.
            # generate_and_test_solve internally uses varied seeds and the code-writer agent.
            from harness.generate_test_solve import generate_and_test_solve
            from harness.pass1_eval import _llm

            gen_result = generate_and_test_solve(
                intent=task["subject"],
                name=name,
                current_src=parent_src,
                context=ctx[cf],
                pkg=pkg,
                runtime=rt,
                run_selftests=run_selftests,
                n=n_gen,
                base_seed=0,
                llm=_llm(),
                gherkin=gk,
            )

            final.setdefault(cf, {})[name] = gen_result.get("chosen") or ""

        # Consolidate all settled functions per file.
        for cf in files:
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        # Remove scaffolding before the oracle.
        st = repo / tnode
        if st.exists():
            st.unlink()

        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


# #EXT-015-REQ-3 Start
def attempt_gherkin_jaros_plan(repo: Path, task: dict, branch: str,
                               timeout: int = 180, max_fix: int = 2) -> str:
    """EXT-015: per-function solve via ``behavioral_solve_jaros(plan=True)``.

    Mirrors ``attempt_gherkin_jaros`` exactly, but passes ``plan=True`` to
    ``behavioral_solve_jaros`` so the plan_agent -> strategy_filter grain runs
    before code generation.  The filtered strategy is included in the code-writer
    prompt.  Scored on the hidden oracle (red->green), identical to all other paths.

    HONESTY: no hidden-oracle access at any point; the plan is derived from the
    visible commit intent only (same constraint as Gherkin and self-tests).
    """
    from harness.behavioral_solve import behavioral_solve_jaros
    from harness.coding_loop import Runtime

    targets = _target_funcs(repo, task)
    if not targets:
        return "no_target"
    if len(targets) > 4:
        return "capped"
    files = sorted({cf for cf, _, _ in targets})
    try:
        _git(repo, "checkout", "-f", task["parent"])
        _git(repo, "checkout", task["sha"], "--", "tests/")
        orig = {cf: (repo / cf).read_text(encoding="utf-8") for cf in files}
        ctx = {cf: _file_context(orig[cf]) for cf in files}
        final: dict[str, dict] = {}
        rt = Runtime()
        tnode = _spec(repo)["test"].rstrip("/") + "/test_gherkin_self.py"
        abs_test_path = str((repo / tnode).resolve())

        for cf, name, parent_src in targets:
            pkg = cf.split("/")[0]
            spec_path = str((repo / f".jcode/{name}.gherkin").resolve())
            code_path = str((repo / f".jcode/{name}.py").resolve())
            cname = f"jaros_selftest_{uuid.uuid4().hex[:12]}"
            docker_cmd = (
                f"docker run --rm --name {cname} --stop-timeout 5 "
                f"-v {repo.resolve().as_posix()}:/repo -w /repo "
                f"-e PYTHONPATH=/repo {_spec(repo)['img']} "
                f"python -m pytest {tnode} --tb=short -q -p no:cacheprovider"
            )

            def _make_pre_test_hook(cf_=cf, name_=name):
                def hook(code: str, tests: str) -> None:
                    content = orig[cf_]
                    for n2, c2 in {**final.get(cf_, {}), name_: code}.items():
                        if c2:
                            content = _apply_func(content, n2, c2)
                    (repo / cf_).write_text(content, encoding="utf-8", newline="\n")
                return hook

            pre_test_hook = _make_pre_test_hook()
            try:
                result = behavioral_solve_jaros(
                    intent=task["subject"],
                    name=name,
                    current_src=parent_src,
                    context=ctx[cf],
                    pkg=pkg,
                    runtime=rt,
                    spec_path=spec_path,
                    test_path=abs_test_path,
                    code_path=code_path,
                    test_command=docker_cmd,
                    max_fix=max_fix,
                    pre_test_hook=pre_test_hook,
                    plan=True,          # EXT-015: plan-then-code path
                )
            finally:
                _docker_force_remove(cname)

            final.setdefault(cf, {})[name] = result.get("code") or ""

        for cf in files:
            content = orig[cf]
            for n2, c2 in final.get(cf, {}).items():
                if c2:
                    content = _apply_func(content, n2, c2)
            (repo / cf).write_text(content, encoding="utf-8", newline="\n")

        st = repo / tnode
        if st.exists():
            st.unlink()

        return "pass" if not _run_nodes(repo, task["redgreen"], timeout) else "fail"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"
    finally:
        _reset(repo, branch)


def run_gherkin_jaros_plan(repo: Path, branch: str, tasks: list[dict]) -> dict:
    """Run ``attempt_gherkin_jaros_plan`` over all tasks, scored on the hidden oracle.

    Prints per-task results and a Wilson CI summary — same format as
    ``run_gherkin_jaros``.  Use to measure EXT-015 plan-then-code vs the default
    jaros-native baseline.

    Exact measurement command::

        python -m harness.commit_replay <repo> --gherkin-loop --jaros --plan --n 37
    """
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin_jaros_plan(repo, t, branch)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    print(f">>> RESULT [EXT-015 plan-then-code / intent-only / test HIDDEN]: "
          f"{k}/{n} = {k/n*100:.1f}% red->green  [Wilson95 {lo*100:.1f}-{hi*100:.1f}%]\n"
          f">>> breakdown: {dict(res)}", flush=True)
    return dict(res)
# #EXT-015-REQ-3 End


def run_gherkin_jaros_gen(repo: Path, branch: str, tasks: list[dict], n_gen: int = 4) -> dict:
    """Run ``attempt_gherkin_jaros_gen`` over all tasks, scored on the hidden oracle.
    Prints per-task results and a Wilson CI summary — same format as ``run_gherkin_jaros``.

    n_gen candidates are generated per function per task; the best by self-test pass count
    is selected (NEVER by the hidden oracle — honesty invariant inherited from
    ``generate_and_test_solve`` and ``_run_selftests_count``).
    """
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin_jaros_gen(repo, t, branch, n_gen=n_gen)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    print(f">>> RESULT [EXT-012 REQ-12 generate-and-test N={n_gen} / intent-only / test HIDDEN]: "
          f"{k}/{n} = {k/n*100:.1f}% red->green  [Wilson95 {lo*100:.1f}-{hi*100:.1f}%]\n"
          f">>> breakdown: {dict(res)}", flush=True)
    return dict(res)
# #EXT-012-REQ-12 End


def run_gherkin(repo: Path, branch: str, tasks: list[dict], reviews: bool = False,
                ensemble: bool = False, agentic: bool = False) -> dict:
    """EXT-012 over tasks, scored on the hidden oracle. Honest pass@1 + Wilson CI. reviews -> Slice 1b;
    ensemble -> baseline+gherkin selected by self-tests; agentic -> 2B-orchestrated tool use."""
    from collections import Counter
    res: Counter = Counter()
    for i, t in enumerate(tasks):
        try:
            r = attempt_gherkin(repo, t, branch, reviews=reviews, ensemble=ensemble, agentic=agentic)
        except Exception as e:  # noqa: BLE001
            r = f"err:{type(e).__name__}"
        res[r] += 1
        print(f"  {i+1}/{len(tasks)} {t['sha'][:8]} [{r}] | {t['subject'][:42]}", flush=True)
    k, n = res["pass"], len(tasks)
    lo, hi = wilson(k, n)
    slice_tag = ("AGENTIC (2B orchestrates the tools)" if agentic
                 else "ENSEMBLE (gherkin+baseline by self-tests)" if ensemble
                 else "Slice 1b (+reviews)" if reviews else "Slice 1a (core loop)")
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
        ensemble = "--ensemble" in sys.argv
        agentic = "--agentic" in sys.argv
        jaros = "--jaros" in sys.argv
        # --gen N: generate-and-test best-of-N (EXT-012 REQ-12); default N=4.
        # Only active when combined with --jaros.  Default behaviour is unchanged.
        gen_n = int(sys.argv[sys.argv.index("--gen") + 1]) if "--gen" in sys.argv else 0
        augment = "--augment" in sys.argv   # EXT-012 REQ-13: stronger-oracle self-test augmenter
        # #EXT-015-REQ-3 Start
        plan = "--plan" in sys.argv         # EXT-015: plan-then-code (plan_agent -> filter -> code)
        # #EXT-015-REQ-3 End
        if jaros:
            n_tasks = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else len(tasks)
            tasks = tasks[:n_tasks]
            if gen_n > 0:
                # EXT-012 REQ-12: generate-and-test path — N candidates selected by self-tests.
                # HONESTY: selection is ONLY by the model's own spec-derived self-tests;
                # the hidden oracle is never touched until the final oracle score at the end.
                print(f">>> EXT-012 REQ-12 GENERATE-AND-TEST N={gen_n} on {len(tasks)} "
                      f"{tag} tasks of {repo.name}", flush=True)
                run_gherkin_jaros_gen(repo, branch, tasks, n_gen=gen_n)
            elif augment:
                # EXT-012 REQ-13: stronger-oracle path — self-tests augmented with doctest
                # examples from the VISIBLE docstring.  HONESTY: never reads the hidden oracle.
                print(f">>> EXT-012 REQ-13 STRONGER-ORACLE AUGMENT on {len(tasks)} "
                      f"{tag} tasks of {repo.name}", flush=True)
                run_gherkin_jaros_augment(repo, branch, tasks)
            # #EXT-015-REQ-3 Start
            elif plan:
                # EXT-015: plan-then-code decomposition — plan_agent -> strategy_filter -> code.
                # Honest: no hidden-oracle access; strategy is derived from visible intent only.
                print(f">>> EXT-015 PLAN-THEN-CODE on {len(tasks)} {tag} tasks of {repo.name}",
                      flush=True)
                run_gherkin_jaros_plan(repo, branch, tasks)
            # #EXT-015-REQ-3 End
            else:
                print(f">>> EXT-013 JAROS-NATIVE GHERKIN-LOOP on {len(tasks)} {tag} tasks of {repo.name}", flush=True)
                run_gherkin_jaros(repo, branch, tasks)
        else:
            mode = "AGENTIC" if agentic else "ENSEMBLE" if ensemble else ("1b(+reviews)" if reviews else "1a")
            print(f">>> EXT-012 GHERKIN-LOOP {mode} on {len(tasks)} {tag} tasks of {repo.name}", flush=True)
            run_gherkin(repo, branch, tasks, reviews=reviews, ensemble=ensemble, agentic=agentic)
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
