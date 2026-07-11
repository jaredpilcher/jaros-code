"""EXT-036 TASK-84 (REQ-69): sweep model-REGENERATED code through the deterministic-repair chain
at every regeneration site.

MEASURED WIRING GAP (canonical-board `url-shortener-http-service`): `_apply_deterministic_repairs`
(the signature-contract / endpoint-shape / server-address-tuple[REQ-68] / port-coercion /
http-service-scaffold / agent-scaffold chain) is proven correct against the exact shipped module
set, but `_repair_system` (the acceptance-driven REQ-5 loop `build_system` calls) regenerates a
module body via the model and writes/re-checks it WITHOUT ever routing it back through that chain
-- so a repair round could reintroduce (or leave standing) the exact mechanical protocol bug the
initial deterministic pass had already fixed. The REQ-43 single-file-retry fallback has the same
gap for its `single_code` candidate.

OFFLINE -- no live model. These tests use two complementary techniques:
  (1) a DIRECT WIRING PROOF: monkeypatch `harness.system_builder._apply_deterministic_repairs`
      with a recording spy (that still performs the REAL, narrow `apply_server_address_tuple`
      transform) so we can assert exactly WHAT subset of modules reaches it, without the rest of
      the (already independently tested) deterministic-repair chain as a confound.
  (2) an END-TO-END REPAIR PROOF via `build_system` + a canned llm (same `.complete()` convention
      as `test_ext036_system_repair.py`), proving the actual reproduced defect
      (`HTTPServer("", port, H)`) gets repaired to a tuple-first-arg call, checked via `ast`
      (never brittle string/formatting matching).
"""

# #EXT-036-REQ-69 Start
from __future__ import annotations

import ast
import os
import re

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.system_builder as sb
from harness.system_builder import build_system, syntax_ok
from harness.server_address_tuple import apply_server_address_tuple


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


def _json_str(s: str) -> str:
    import json
    return json.dumps(s)


def _server_call_first_arg_is_tuple(code: str, ctor: str = "HTTPServer") -> bool:
    """True iff `code` contains a call to `ctor` whose first positional arg is an `ast.Tuple`.
    Robust to `ast.unparse` formatting (quote style / whitespace), unlike a string match."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if name == ctor and node.args:
                return isinstance(node.args[0], ast.Tuple)
    return False


# ============================================================================================
# (1) DIRECT WIRING PROOF -- _repair_system sweeps its round's regenerated module
# ============================================================================================

SPEC = "A tiny calculator module with add(a, b)."

PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "define add(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"}],
     "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "add computes correctly"
}"""

CHECKLIST_ONE = """[
  {"name": "adds correctly", "code": "from main import add\\nassert add(1, 2) == 3\\n"}
]"""

_FAILING_CHECK_RE = re.compile(r"FAILING CHECK: (.+)")
_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")

MAIN_BROKEN = "def add(a, b):\n    return a * b\n"

# the targeted-repair "fix": correct add() PLUS an unrelated, never-invoked bare-string
# HTTPServer bind site -- the exact reproduced defect shape (REQ-68).
MAIN_FIXED_WITH_SERVER_BUG = (
    "from http.server import HTTPServer, BaseHTTPRequestHandler\n\n\n"
    "def add(a, b):\n    return a + b\n\n\n"
    "class _H(BaseHTTPRequestHandler):\n    pass\n\n\n"
    "def serve(port):\n"
    "    HTTPServer('', port, _H).serve_forever()\n"
)

# the SAME fix, but the server call is ALREADY in the correct tuple form -- idempotency control.
MAIN_FIXED_ALREADY_TUPLE = (
    "from http.server import HTTPServer, BaseHTTPRequestHandler\n\n\n"
    "def add(a, b):\n    return a + b\n\n\n"
    "class _H(BaseHTTPRequestHandler):\n    pass\n\n\n"
    "def serve(port):\n"
    "    HTTPServer(('', port), _H).serve_forever()\n"
)


class _CannedRepairLlm:
    """Same convention as `test_ext036_system_repair.py`'s `_CannedRepairLlm`."""

    def __init__(self, *, plan=PLAN_JSON, module_first=None, checklist=CHECKLIST_ONE,
                 repair_fixes: "dict[str, str] | None" = None) -> None:
        self.plan = plan
        self.module_first = module_first or {"main.py": MAIN_BROKEN}
        self.checklist = checklist
        self.repair_fixes = repair_fixes or {}
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(self.checklist)
        if "SYSTEM ACCEPTANCE REPAIR" in prompt:
            m = _FAILING_CHECK_RE.search(prompt)
            check_name = m.group(1).strip() if m else None
            code = self.repair_fixes.get(check_name)
            if code is None:
                return _Resp("not json at all")
            return _Resp('{"module": "main.py", "code": %s}' % _json_str(code))
        if "SYNTAX ERROR" in prompt:
            return _Resp("")
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp(self.module_first.get(name, ""))
        return _Resp("")


def _spy_apply_deterministic_repairs(monkeypatch, calls: list):
    """Replace `sb._apply_deterministic_repairs` with a spy that RECORDS the exact module subset
    it is called with, then performs only the narrow, already-independently-tested
    `apply_server_address_tuple` transform -- isolating the WIRING under test from the rest of
    the (unrelated, unrelated-gated) deterministic-repair chain."""

    def spy(modules, spec_text, *, llm=None):
        calls.append(dict(modules))
        return apply_server_address_tuple(modules)

    monkeypatch.setattr(sb, "_apply_deterministic_repairs", spy)


def test_repair_system_sweeps_only_the_regenerated_module_through_the_repair_chain(tmp_path, monkeypatch):
    """WIRING proof: `_repair_system`'s round hands EXACTLY its own regenerated module (never the
    whole `built` dict, never an untouched sibling) to `_apply_deterministic_repairs`."""
    calls: list = []
    _spy_apply_deterministic_repairs(monkeypatch, calls)

    llm = _CannedRepairLlm(repair_fixes={"adds correctly": MAIN_FIXED_WITH_SERVER_BUG})
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert calls, "the repair round's regenerated module must reach _apply_deterministic_repairs"
    # exactly the ONE regenerated module, nothing else
    assert calls[-1] == {"main.py": MAIN_FIXED_WITH_SERVER_BUG}
    assert result["shipped"] is True


def test_repair_system_repairs_the_reproduced_server_bind_defect_end_to_end(tmp_path):
    """END-TO-END proof (real, unmocked `_apply_deterministic_repairs`): a repair round whose
    targeted fix embeds the exact reproduced `HTTPServer("", port, H)` defect ships with the
    server-constructor call's first positional arg repaired to a tuple -- both in the returned
    `modules` dict and on disk -- while the check the round targets ("adds correctly") is
    unaffected by the unrelated, never-invoked server code."""
    llm = _CannedRepairLlm(repair_fixes={"adds correctly": MAIN_FIXED_WITH_SERVER_BUG})
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []

    code = result["modules"]["main.py"]
    assert syntax_ok(code)[0] is True
    assert _server_call_first_arg_is_tuple(code)

    on_disk = (tmp_path / "built" / "main.py").read_text(encoding="utf-8")
    assert _server_call_first_arg_is_tuple(on_disk)

    # the behavior the round was actually repairing genuinely holds
    ns: dict = {}
    exec(compile(code, "main.py", "exec"), ns)
    assert ns["add"](1, 2) == 3


def test_repair_system_sweep_is_idempotent_no_op_on_already_correct_code(tmp_path, monkeypatch):
    """Non-degrading: a regenerated module that is ALREADY in the correct tuple form passes
    through the sweep byte-identical (no spurious rewrite, no accidental double-wrap)."""
    calls: list = []
    _spy_apply_deterministic_repairs(monkeypatch, calls)

    llm = _CannedRepairLlm(repair_fixes={"adds correctly": MAIN_FIXED_ALREADY_TUPLE})
    result = build_system(SPEC, tmp_path / "built", llm=llm)

    assert result["done"] is True
    assert result["modules"]["main.py"].strip() == MAIN_FIXED_ALREADY_TUPLE.strip()


def test_repair_system_never_raises_when_deterministic_repairs_blows_up(tmp_path, monkeypatch):
    """A misbehaving `_apply_deterministic_repairs` (raises internally) must never crash the
    repair loop -- the loop stays exactly as fault-tolerant as before this task."""

    def blowup(modules, spec_text, *, llm=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(sb, "_apply_deterministic_repairs", blowup)

    llm = _CannedRepairLlm(repair_fixes={"adds correctly": MAIN_FIXED_WITH_SERVER_BUG})
    # build_system's own outer guards must absorb this -- never propagate.
    result = build_system(SPEC, tmp_path / "built", llm=llm)
    assert isinstance(result, dict)


# ============================================================================================
# (2) SINGLE-FILE-RETRY path (REQ-43) -- single_code swept before adopt
# ============================================================================================

_SF_SPEC = "A tiny CLI that prints the sum of two numbers given as command-line arguments."

_SF_PLAN_JSON = """{
  "modules": [
    {"name": "helper.py", "responsibility": "define add(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []},
    {"name": "main.py", "responsibility": "CLI entrypoint: print the sum of two argv ints",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["helper.py"]}
  ],
  "entrypoint": "main.py",
  "acceptance": "python main.py 1 2 prints 3"
}"""

_SF_HELPER_OK = "def add(a, b):\n    return a + b\n"

# a genuine cross-module logic bug -- the stubbed targeted repair below offers no fix, so
# `_repair_system` cannot recover it and the single-file retry fires (mirrors
# test_ext036_system_builder.py's TASK-55/56 fixture exactly).
_SF_MAIN_BROKEN = (
    "import sys\n"
    "from helper import add\n\n\n"
    "def main():\n"
    "    a, b = int(sys.argv[1]), int(sys.argv[2])\n"
    "    print(add(a, b) + 1)\n\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

_SF_CHECK_CODE = (
    "import subprocess, sys\n"
    "result = subprocess.run([sys.executable, 'main.py', '1', '2'], capture_output=True,\n"
    "                        text=True, timeout=20)\n"
    "assert result.stdout.strip() == '3', result.stdout + result.stderr\n"
)
_SF_CHECKS = [{"name": "prints the sum", "code": _SF_CHECK_CODE}]

# the single-file retry's candidate: correct sum-printing behavior PLUS the same reproduced
# bare-string HTTPServer defect, never invoked by the check above.
_SF_MAIN_OK_WITH_SERVER_BUG = (
    "import sys\n"
    "from http.server import HTTPServer, BaseHTTPRequestHandler\n\n\n"
    "def add(a, b):\n    return a + b\n\n\n"
    "class _H(BaseHTTPRequestHandler):\n    pass\n\n\n"
    "def main():\n"
    "    a, b = int(sys.argv[1]), int(sys.argv[2])\n"
    "    print(add(a, b))\n\n\n"
    "def serve(port):\n"
    "    HTTPServer('', port, _H).serve_forever()\n\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)


class _PlanOnlyLlm:
    """Handles only the PLAN prompt; every other stage is mocked directly (mirrors
    `test_ext036_system_builder.py`'s TASK-55/56 fixture)."""

    def __init__(self, plan: str) -> None:
        self.plan = plan
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        if "build PLAN" in request.prompt:
            return _Resp(self.plan)
        return _Resp("")


def _sf_fake_build_module(spec, m, built, llm, *, max_repair=None, plan=None):
    name = m.get("name")
    if name == "helper.py":
        return _SF_HELPER_OK, True
    if name == "main.py":
        return _SF_MAIN_BROKEN, True
    return "", False


def test_single_file_retry_sweeps_candidate_before_adopt(tmp_path, monkeypatch):
    """WIRING + END-TO-END proof for the REQ-43 single-file-retry path: the candidate
    `single_code` (containing the reproduced server-bind defect) is repaired -- BOTH in
    `result["modules"]` and on disk -- before it is adopted onto root."""
    monkeypatch.setattr(sb, "_build_module", _sf_fake_build_module)
    monkeypatch.setattr(sb, "_build_single_file",
                         lambda spec, llm: (_SF_MAIN_OK_WITH_SERVER_BUG, True))
    monkeypatch.setattr(sb, "_compose_acceptance_checklist",
                         lambda spec, mods, llm, plan=None: list(_SF_CHECKS))
    monkeypatch.setattr(sb, "_minimum_acceptance", lambda spec, mods, plan=None: [])

    calls: list = []
    _spy_apply_deterministic_repairs(monkeypatch, calls)

    root = tmp_path / "built"
    llm = _PlanOnlyLlm(_SF_PLAN_JSON)
    result = sb.build_system(_SF_SPEC, root, llm=llm)

    assert result["build_path"] == "single-file-retry"
    assert result["done"] is True
    # the WIRING: the single-file candidate (only) reached _apply_deterministic_repairs
    assert {"main.py": _SF_MAIN_OK_WITH_SERVER_BUG} in calls

    code = result["modules"]["main.py"]
    assert _server_call_first_arg_is_tuple(code)
    on_disk = (root / "main.py").read_text(encoding="utf-8")
    assert _server_call_first_arg_is_tuple(on_disk)


def test_single_file_retry_sweep_is_idempotent_no_op_when_already_correct(tmp_path, monkeypatch):
    """Non-degrading: a single-file candidate with no defect shape (no server call at all) is
    completely unaffected by the sweep -- byte-identical to the raw model output (after the
    existing `_strip_fences`)."""
    clean_code = (
        "import sys\n\n\n"
        "def add(a, b):\n    return a + b\n\n\n"
        "def main():\n"
        "    a, b = int(sys.argv[1]), int(sys.argv[2])\n"
        "    print(add(a, b))\n\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    monkeypatch.setattr(sb, "_build_module", _sf_fake_build_module)
    monkeypatch.setattr(sb, "_build_single_file", lambda spec, llm: (clean_code, True))
    monkeypatch.setattr(sb, "_compose_acceptance_checklist",
                         lambda spec, mods, llm, plan=None: list(_SF_CHECKS))
    monkeypatch.setattr(sb, "_minimum_acceptance", lambda spec, mods, plan=None: [])

    root = tmp_path / "built"
    llm = _PlanOnlyLlm(_SF_PLAN_JSON)
    result = sb.build_system(_SF_SPEC, root, llm=llm)

    assert result["build_path"] == "single-file-retry"
    assert result["modules"] == {"main.py": clean_code}
# #EXT-036-REQ-69 End
