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
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CODE_PREFIX = "more_itertools/"
TEST_PREFIX = "tests/"
DOCKER_IMG = "mi-test"


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


def structural_filter(repo: Path, n: int = 400) -> tuple[list[CommitInfo], dict]:
    """Categorize the last n commits. KEEP only non-merge commits that touch CODE and TESTS.
    Returns (candidates oldest->newest, drop_ledger {reason: count})."""
    shas = _git(repo, "rev-list", "-n", str(n), "HEAD").split()
    ledger: dict[str, int] = {"merge": 0, "no_code": 0, "no_test": 0, "kept_candidate": 0}
    candidates: list[CommitInfo] = []
    for sha in shas:
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if len(parents) >= 2:
            ledger["merge"] += 1
            continue
        files = _files_changed(repo, sha)
        code = [f for f in files if f.startswith(CODE_PREFIX) and f.endswith(".py")
                and not f.endswith("__init__.py")]
        tests = [f for f in files if f.startswith(TEST_PREFIX) and f.endswith(".py")]
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
           "-e", "PYTHONPATH=/repo", DOCKER_IMG, "python", "-m", "pytest", *nodes,
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


if __name__ == "__main__":
    import json
    import sys
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".jaros-data/repos/more-itertools")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    cands, ledger = structural_filter(repo, n)
    print(f">>> structural filter on last {n} commits of {repo.name}", flush=True)
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
        out = repo.parent.parent / "artifacts" / f"{repo.name}_valid_tasks.json"
        out.write_text(json.dumps(valid, indent=1), encoding="utf-8")
        print(f">>> saved -> {out}", flush=True)
    else:
        for c in cands[:15]:
            print(f"  {c.sha[:8]} | code={len(c.code_files)} test={len(c.test_files)} | {c.subject[:70]}")
