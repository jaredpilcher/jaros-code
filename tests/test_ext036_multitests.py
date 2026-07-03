"""EXT-036 TASK-10: multi-level tests -- integration + performance (REQ-6).

OFFLINE -- no live model required for the core assertions. `integration_check`'s
best-effort flow-derivation path is exercised with a canned stub `llm` (same
`.complete(LlmRequest) -> .text` convention used across `test_ext036_*`), never a live
model. `perf_check` needs no model at all -- it is proven with real, fast/slow
`entry_cmd` subprocess runs (a REAL measured wall-clock time, never faked).

Proves the three required properties:
  (a) an integration flow across 2 cooperating modules PASSES; it FAILS for real when one
      of the modules is broken (a genuine cross-module run, not a stub).
  (b) `perf_check` PASSES a fast entry and genuinely FAILS a deliberately slow one against
      a tight threshold -- the failure is a REAL measured elapsed time over the bar, not a
      fabricated verdict.
  (c) both functions NEVER raise on bad/missing input (None modules, missing flow/entry,
      an unusable root) -- they return an honest non-passing result instead.
"""

from __future__ import annotations

from harness.multi_tests import integration_check, perf_check, _assemble, _derive_flow_code

# --- fixtures: two cooperating modules -----------------------------------------------------

MOD_A_WORKING = "def add(a, b):\n    return a + b\n"
MOD_A_BROKEN = "def add(a, b):\n    return a - b\n"   # syntactically fine, semantically wrong

MOD_B = (
    "from mod_a import add\n\n\n"
    "def combine(x, y):\n"
    "    return add(x, y) * 2\n"
)

FLOW_CODE = (
    "from mod_a import add\n"
    "from mod_b import combine\n\n"
    "assert add(2, 3) == 5\n"
    "assert combine(2, 3) == 10\n"
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """Returns a canned integration-flow script whenever asked; records every prompt."""

    def __init__(self, flow: str = FLOW_CODE) -> None:
        self.flow = flow
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp(self.flow)


# --- (a) integration flow across 2 cooperating modules ---------------------------------

def test_integration_check_passes_when_modules_cooperate(tmp_path):
    modules = {"mod_a.py": MOD_A_WORKING, "mod_b.py": MOD_B}
    result = integration_check(modules, tmp_path / "sys_ok", flow_code=FLOW_CODE)
    assert result["passed"] is True
    assert "output" in result


def test_integration_check_fails_when_a_module_is_broken(tmp_path):
    modules = {"mod_a.py": MOD_A_BROKEN, "mod_b.py": MOD_B}
    result = integration_check(modules, tmp_path / "sys_broken", flow_code=FLOW_CODE)
    assert result["passed"] is False
    assert result["output"]   # the real assertion-failure output is surfaced, not swallowed


def test_integration_check_derives_flow_via_model_when_not_supplied(tmp_path):
    modules = {"mod_a.py": MOD_A_WORKING, "mod_b.py": MOD_B}
    llm = _CannedLlm(flow=FLOW_CODE)
    result = integration_check(modules, tmp_path / "sys_derived", flow_code=None, llm=llm)
    assert result["passed"] is True
    assert llm.prompts   # the model was actually consulted to derive the flow


def test_integration_check_honest_failure_when_no_flow_and_no_llm(tmp_path):
    modules = {"mod_a.py": MOD_A_WORKING, "mod_b.py": MOD_B}
    result = integration_check(modules, tmp_path / "sys_noflow", flow_code=None, llm=None)
    assert result["passed"] is False
    assert "no flow_code" in result["output"] or "no integration flow" in result["output"]


# --- (b) perf_check: REAL measured wall-clock time, honest pass/fail -----------------------

def test_perf_check_passes_a_fast_entry(tmp_path):
    result = perf_check({}, tmp_path / "perf_fast", 'python -c "pass"', threshold_s=10.0)
    assert result["passed"] is True
    assert result["elapsed"] is not None
    assert result["elapsed"] < 10.0


def test_perf_check_fails_a_deliberately_slow_entry_real_measured_time(tmp_path):
    result = perf_check(
        {}, tmp_path / "perf_slow",
        'python -c "import time;time.sleep(2)"',
        threshold_s=0.5,
    )
    assert result["passed"] is False
    # a REAL measurement over the bar -- not a fabricated verdict
    assert result["elapsed"] is not None
    assert result["elapsed"] > 0.5


def test_perf_check_assembles_modules_before_running(tmp_path):
    modules = {"mod_a.py": MOD_A_WORKING}
    root = tmp_path / "perf_modules"
    result = perf_check(modules, root, 'python -c "import mod_a; assert mod_a.add(1, 1) == 2"',
                         threshold_s=10.0)
    assert result["passed"] is True
    assert (root / "mod_a.py").exists()


def test_perf_check_fails_honestly_when_entry_cmd_itself_fails(tmp_path):
    result = perf_check({}, tmp_path / "perf_bad_cmd", 'python -c "import sys; sys.exit(1)"',
                         threshold_s=10.0)
    assert result["passed"] is False   # a real non-zero exit is a real failure, not a pass


# --- (c) never raises on bad / missing input ------------------------------------------------

def test_integration_check_never_raises_on_bad_input(tmp_path):
    assert integration_check(None, tmp_path / "none_mods", flow_code=None, llm=None)["passed"] is False
    assert integration_check({}, tmp_path / "empty_mods", flow_code="", llm=None)["passed"] is False
    assert integration_check("not a dict", tmp_path / "bad_mods", flow_code=None, llm=None)["passed"] is False


def test_perf_check_never_raises_on_bad_input(tmp_path):
    assert perf_check(None, tmp_path / "none_mods", None, 1.0)["passed"] is False
    assert perf_check({}, tmp_path / "no_cmd", "", 1.0)["passed"] is False
    assert perf_check("not a dict", tmp_path / "bad_mods", 'python -c "pass"', 1.0)["passed"] is False


# --- (unit) helpers --------------------------------------------------------------------------

def test_assemble_writes_modules_to_root(tmp_path):
    root = tmp_path / "assembled"
    assert _assemble({"a.py": "x = 1\n"}, root) is True
    assert (root / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_assemble_guards_bad_input(tmp_path):
    assert _assemble(None, tmp_path / "noop") is True   # nothing to write, still succeeds
    assert _assemble("not a dict", tmp_path / "bad") is False


def test_derive_flow_code_returns_stripped_model_text():
    llm = _CannedLlm(flow="```python\nprint('hi')\n```")
    code = _derive_flow_code({"a.py": "x = 1\n"}, llm)
    assert code == "print('hi')"


def test_derive_flow_code_guards_model_failure():
    class _BoomLlm:
        def complete(self, request):
            raise RuntimeError("boom")

    assert _derive_flow_code({"a.py": "x = 1\n"}, _BoomLlm()) == ""
