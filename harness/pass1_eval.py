"""Deterministic pass@1 evaluation (no-ceiling pursuit, 2026-06-24).

ONE greedy (temperature=0) body completion per stub Task, scored on the hidden test. Greedy ->
DETERMINISTIC -> reproducible -> the honest, low-noise metric for A/B-ing generic harness
mechanisms. (best-of-6 resampling is far too noisy: it swung 35/40 vs 49/50 on overlapping problems
run-to-run, which made a NET-NEGATIVE prompt change look like a +6% win. See body_completer_agent.)

Fast: skips the 6-strategy cascade entirely (~5x faster than fix_loop), so mechanism A/Bs take
minutes, not hours. Reusable for any stub Task (HumanEval, MBPP, ...).
"""
from __future__ import annotations

import importlib.util
import subprocess
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
    return _bc.splice(sig_doc, reply)


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
