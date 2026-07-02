"""From-intent build loop (EXT-008): the generative spine.

This is the capability the repair loop (EXT-003) does NOT exercise: turn a
natural-language *intent* into a working system with NO test handed to us. The harness
writes its own tests (test-writer grain), implements against them (the EXT-003 fix_loop),
and is then scored against a HIDDEN oracle test it never sees.

Two honest metrics per task:
  * self_pass    — did the implementation pass the tests the system wrote itself?
  * oracle_pass  — did it pass the held-out oracle (the real "did it meet intent")?

The gap between them is un-gameable: the system cannot see the oracle, so it cannot
write its code (or its tests) to satisfy it. self_pass without oracle_pass means the
system convinced itself but misread the intent — exactly what we need to measure.
"""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from harness.coding_loop import Runtime, build_llm, fix_loop, _load_agent
from jaros.core import create_decision

# #EXT-035-REQ-3 Start
import ast as _ast


def _derive_dep_exports(deps: dict) -> dict:
    """AST-derive {dep-stem: [top-level def/class names]} from dep sources,
    for resolve_imports to inject the correct cross-module import lines."""
    exports: dict = {}
    for fname, src in deps.items():
        stem = Path(fname).stem
        names: list = []
        try:
            tree = _ast.parse(src)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                names.append(node.name)
        exports[stem] = names
    return exports
# #EXT-035-REQ-3 End


@dataclass
class IntentResult:
    id: str
    self_pass: bool
    oracle_pass: bool
    attempts: int
    note: str = ""
    # #EXT-027-REQ-3 Start
    code: str = ""  # the final built module content (for daily_driver auto-capture)
    # #EXT-027-REQ-3 End


def _stub(signature: str, func: str) -> str:
    sig = signature.strip().rstrip(":")
    if not sig.startswith("def "):
        sig = f"def {func}(*args, **kwargs)"
    return f"{sig}:\n    raise NotImplementedError\n"


def build_from_intent(task: dict, *, max_iters: int = 3, verbose: bool = False,
                      deps: dict | None = None) -> IntentResult:
    intent = task["intent"]
    target = task["target"]                       # e.g. "csv_parse.py"
    module = Path(target).stem                     # "csv_parse"
    func = task.get("func", module)
    signature = task.get("signature", f"def {func}(...):")
    test_cmd = task.get("test_cmd", "python -m pytest -q")

    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        target_path = dp / target
        target_path.write_text(_stub(signature, func), encoding="utf-8", newline="\n")
        # #EXT-008-REQ-4 Start
        # Write caller-supplied dependency modules into the build dir so a module
        # can import an already-built sibling (multi-module Foundry builds).
        if deps:
            for fname, src in deps.items():
                (dp / fname).write_text(src, encoding="utf-8", newline="\n")
        # #EXT-008-REQ-4 End

        # 1) GENERATIVE grain: the system writes its own tests from intent.
        rt = Runtime()
        writer = _load_agent("test_writer_agent.py", build_llm())
        [tw] = writer.decide({"intent": intent, "module": module, "func": func,
                              "signature": signature, "test_path": str(dp / f"test_{module}.py"),
                              "seed": 1})
        if tw.type != "code.write_file":
            return IntentResult(task["id"], False, False, 0, "test-writer produced no tests")
        rt.apply(tw)
        if verbose:
            print(f"  [test-writer] wrote {Path(tw.payload['path']).name} "
                  f"({len(tw.payload['content'])} chars)")

        # 2) Implement against the SELF-WRITTEN tests (reuse the EXT-003 fix_loop).
        res = fix_loop(str(target_path), intent, test_cmd, max_iters=max_iters,
                       cwd=str(dp), verbose=verbose)
        self_pass = res.success
        final_impl = target_path.read_text(encoding="utf-8")

        # #EXT-035-REQ-3 Start
        # Deterministic fix for the MEASURED cross-module import-emission gap: the model
        # may reference a dep symbol without importing it (or guess the wrong module name).
        # Resolve the correct `from <stem> import <name>` lines before the oracle scores it.
        if deps:
            from harness.import_wiring import resolve_imports
            final_impl = resolve_imports(final_impl, _derive_dep_exports(deps))
        # #EXT-035-REQ-3 End

        # 3) Score against the HIDDEN oracle in a fresh dir (system never saw this test).
        # #EXT-008-REQ-4 Start
        oracle_pass = _run_oracle(module, target, final_impl, task["oracle_test"], test_cmd, deps=deps)
        # #EXT-008-REQ-4 End

    return IntentResult(task["id"], self_pass, oracle_pass, res.attempts,
                        "self+oracle" if (self_pass and oracle_pass) else
                        ("self-only (misread intent)" if self_pass else "unsolved"),
                        # #EXT-027-REQ-3 Start
                        code=final_impl)
                        # #EXT-027-REQ-3 End


def build_in_dir(cwd: str, intent: str, target: str, func: str | None = None,
                 signature: str | None = None, *, max_iters: int = 3, verbose: bool = False) -> dict:
    """CLI-facing generative build (EXT-008): turn an intent into a working function + its tests,
    written into a REAL directory (no hidden oracle, unlike build_from_intent). Reuses the same
    grains: the test-writer writes tests from the intent, then fix_loop implements against them.
    Returns {self_pass, files, note}. The generative spine exposed for interactive use."""
    # Powered by the canonical BEHAVIORAL SOLVE (EXT-012 system): the 2B writes a Gherkin behavior spec
    # for the intent (comprehension step pins the exact case), derives its OWN tests, implements, and
    # fixes against them — the same system proven on held-out real commits. The eval and this product
    # path now share ONE solve; here the env adapter is local pytest.
    from harness.behavioral_solve import behavioral_solve
    module = Path(target).stem
    func = func or module
    tp = Path(cwd) / target
    current = tp.read_text(encoding="utf-8") if tp.exists() else None
    test_name = f"test_{module}.py"
    testp = Path(cwd) / test_name

    def run_tests(code: str, test_code: str) -> tuple[bool, str]:
        tp.write_text(code, encoding="utf-8", newline="\n")
        testp.write_text(test_code, encoding="utf-8", newline="\n")
        # #EXT-005-REQ-12 Start
        from harness.proc_treekill import run_with_treekill
        ok, output = run_with_treekill(f"python -m pytest -q {test_name}", cwd, timeout=60, capture=True)
        return ok, (output[-700:] if output else "timeout")
        # #EXT-005-REQ-12 End

    r = behavioral_solve(intent, func, current, "", module, run_tests, max_fix=max_iters)
    tp.write_text(r["code"] or (current or _stub(signature or "", func)), encoding="utf-8", newline="\n")
    testp.write_text(r["tests"], encoding="utf-8", newline="\n")
    return {"self_pass": r["self_pass"], "files": [target, test_name],
            "note": ("built via behavioral solve — passes its own Gherkin-derived tests" if r["self_pass"]
                     else "implemented via behavioral solve; did not pass its self-tests")}


def _run_oracle(module: str, target: str, impl: str, oracle_test: str, test_cmd: str,
                deps: dict | None = None) -> bool:
    with tempfile.TemporaryDirectory() as od:
        odp = Path(od)
        (odp / target).write_text(impl, encoding="utf-8", newline="\n")
        (odp / f"test_oracle_{module}.py").write_text(oracle_test, encoding="utf-8", newline="\n")
        # #EXT-008-REQ-4 Start
        # Write the same dependency modules into the oracle dir so an implementation
        # that imports a dep does not ImportError. The oracle TEST itself stays hidden.
        if deps:
            for fname, src in deps.items():
                (odp / fname).write_text(src, encoding="utf-8", newline="\n")
        # #EXT-008-REQ-4 End
        rt = Runtime()
        res = rt.apply(create_decision(id=f"orc-{uuid.uuid4().hex}", source="oracle",
                       type="shell.exec", payload={"command": test_cmd, "timeout_s": 15, "cwd": str(odp)}))
        return isinstance(res, dict) and res.get("exitCode") == 0
