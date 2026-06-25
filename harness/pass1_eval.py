"""Deterministic pass@1 evaluation (no-ceiling pursuit, 2026-06-24).

ONE greedy (temperature=0) body completion per stub Task, scored on the hidden test. Greedy ->
DETERMINISTIC -> reproducible -> the honest, low-noise metric for A/B-ing generic harness
mechanisms. (best-of-6 resampling is far too noisy: it swung 35/40 vs 49/50 on overlapping problems
run-to-run, which made a NET-NEGATIVE prompt change look like a +6% win. See body_completer_agent.)

Fast: skips the 6-strategy cascade entirely (~5x faster than fix_loop), so mechanism A/Bs take
minutes, not hours. Reusable for any stub Task (HumanEval, MBPP, ...).
"""
from __future__ import annotations

import ast
import doctest
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.coding_loop import build_llm
from harness.eval_runner import setup_task
from jaros.llm import LlmRequest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_body_completer", _ROOT / ".jaros-data" / "agents" / "body_completer_agent.py")
_bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bc)
_LLM = None


def _llm():
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM


def solve_pass1(task, *, edge: bool = False) -> str:
    """One greedy body completion for a stub Task -> the spliced solution source (deterministic)."""
    with tempfile.TemporaryDirectory() as d:
        target = setup_task(task, Path(d))
        stub = Path(target).read_text(encoding="utf-8")
    sig_doc = _bc.signature_and_docstring(stub)
    edge_txt = _bc._EDGECASE if edge else ""
    prompt = _bc._PROMPT.format(edge=edge_txt, instruction=task.instruction, feedback="", sig_doc=sig_doc)
    reply = _llm().complete(LlmRequest(prompt=prompt, params={"temperature": 0.0})).text
    return _bc.repair_indentation(_llm(), _bc.splice(sig_doc, reply))


def run_pass1(tasks, *, edge: bool = False) -> tuple[int, list[str]]:
    """Deterministic pass@1 over stub Tasks. Returns (passed, failing_ids)."""
    passed, fails = 0, []
    for t in tasks:
        with tempfile.TemporaryDirectory() as d:
            setup_task(t, Path(d))
            Path(d, "solution.py").write_text(solve_pass1(t, edge=edge), encoding="utf-8", newline="\n")
            try:
                r = subprocess.run(t.test_cmd, cwd=d, shell=True, capture_output=True, text=True, timeout=60)
                ok = r.returncode == 0
            except subprocess.TimeoutExpired:
                ok = False
        passed += ok
        if not ok:
            fails.append(t.id)
    return passed, fails


# --- Self-gated reasoning ("thinking" only when needed) — owner's idea, 2026-06-25 -----------------
# The 2B is not a thinking model; for the diffuse LOGIC failures (wrong reasoning, not malformed
# output) a one-shot body is often wrong. Mechanism: solve direct; ONLY when direct fails the
# function's OWN visible docstring examples (the model effectively self-detects it's wrong) spend a
# reasoning pass (<think>..</think> then the body). CLEAN paired full-HumanEval verdict (direct
# computed once, gate reuses it -> no re-run noise): 116 -> 119 deterministic pass@1 (+3; fixed
# HumanEval 9/54/100; ZERO breakage; thought on only 9/164 ~5%). Honest (visible spec gates it,
# hidden tests only score) and efficient. Was a clean win ONLY after removing two confounds: a flaky
# gate (timeouts mis-firing) and best-of-6 / re-run non-determinism. See [[jaros-code-deterministic-pass1]].
_THINK = (
    "Solve this Python function. First, inside <think> </think>, reason about the algorithm: the "
    "goal, the docstring examples, the exact steps and edge cases. Then AFTER </think> output ONLY "
    "the function body (indented statements after the signature+docstring; no signature/docstring/"
    "markdown).\n\nTASK: {instruction}\nFUNCTION:\n{sig_doc}\n<think>"
)


def _doctest_asserts(stub: str) -> list:
    """(call, want) pairs from the LAST function's docstring >>> examples. Robust to malformed docs."""
    try:
        funcs = [n for n in ast.walk(ast.parse(stub)) if isinstance(n, ast.FunctionDef)]
    except SyntaxError:
        return []
    if not funcs:
        return []
    doc = ast.get_docstring(funcs[-1]) or ""
    try:
        exs = doctest.DocTestParser().get_examples(doc)
    except Exception:
        return []
    return [(e.source.strip(), e.want.strip()) for e in exs
            if e.source.strip() and e.want.strip()
            and e.source.split("(")[0].strip() not in ("import", "from", "print")]


def _visible_ok(src: str, asserts: list) -> bool:
    """True if src passes the docstring's own examples. Gate-think ONLY on a genuine AssertionError
    (logic provably wrong); any other error/timeout -> True (don't think — the check is unreliable)."""
    if not asserts:
        return True
    test = src + "\n" + "\n".join(f"assert ({s}) == ({w})" for s, w in asserts)
    with tempfile.TemporaryDirectory() as d:
        Path(d, "v.py").write_text(test, encoding="utf-8", newline="\n")
        try:
            r = subprocess.run([sys.executable, str(Path(d, "v.py"))],
                               capture_output=True, text=True, timeout=30)
        except Exception:
            return True
    return r.returncode == 0 or "AssertionError" not in (r.stderr or "")


def solve_think(task) -> str:
    """One reasoning pass then the body (deterministic, temp=0). For logic the one-shot body misses."""
    with tempfile.TemporaryDirectory() as d:
        stub = Path(setup_task(task, Path(d))).read_text(encoding="utf-8")
    sig_doc = _bc.signature_and_docstring(stub)
    reply = _llm().complete(LlmRequest(
        prompt=_THINK.format(instruction=task.instruction, sig_doc=sig_doc),
        params={"temperature": 0.0, "max_tokens": 512})).text
    body = reply.rsplit("</think>", 1)[1] if "</think>" in reply else reply
    return _bc.repair_indentation(_llm(), _bc.splice(sig_doc, body))


def solve_gated(task) -> str:
    """Self-gated reasoning. Reason when EITHER (a) the docstring has NO examples to anchor on —
    direct flounders most there and reasoning helps a lot (no-ex A/B: 58->73 = +15/95); or (b) direct
    fails the visible examples (self-detected wrong). Where examples EXIST and direct passes them, keep
    direct (reasoning just adds noise). The effect is heterogeneous, hence the gate."""
    direct = solve_pass1(task)
    with tempfile.TemporaryDirectory() as d:
        stub = Path(setup_task(task, Path(d))).read_text(encoding="utf-8")
    asserts = _doctest_asserts(stub)
    if asserts and _visible_ok(direct, asserts):
        return direct
    try:
        return solve_think(task)
    except Exception:
        return direct


def run_gated(tasks) -> tuple[int, list[str]]:
    """Deterministic pass@1 with self-gated reasoning. Returns (passed, failing_ids)."""
    passed, fails = 0, []
    for t in tasks:
        with tempfile.TemporaryDirectory() as d:
            setup_task(t, Path(d))
            Path(d, "solution.py").write_text(solve_gated(t), encoding="utf-8", newline="\n")
            try:
                ok = subprocess.run(t.test_cmd, cwd=d, shell=True, capture_output=True,
                                    text=True, timeout=60).returncode == 0
            except subprocess.TimeoutExpired:
                ok = False
        passed += ok
        if not ok:
            fails.append(t.id)
    return passed, fails
