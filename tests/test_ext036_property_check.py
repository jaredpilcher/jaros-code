"""EXT-036 TASK-46 (REQ-37): a spec-DERIVED behavioral PROPERTY check (PGS-style, arXiv
2506.18315) for build_system acceptance -- catches SEMANTIC/ORDERING false-dones the
crash-based REQ-26 minimum floor misses (a system that never crashes but simply behaves
WRONG, e.g. a priority queue that dequeues in the wrong order).

SACRED-SAFE BY CONSTRUCTION: this ADDS a strictness check to acceptance. It can only ever
flip a build's `done` from True->False (catching a genuine semantic bug the existing checks
missed), NEVER False->True -- so it CANNOT manufacture a false-done. The only risk is an
over-strict FALSE-NEGATIVE, which the tri-state grading rule is specifically designed to
avoid:
  - VIOLATED (the property test ran and its assertion DEFINITIVELY failed) -> check FAILS.
  - INCONCLUSIVE (the CLI couldn't be invoked as the check assumed / any other exception)
    -> treated as a PASS, never a manufactured false-negative.
  - SATISFIED (a clean run) -> PASS.

OFFLINE -- no live model; no Jetson. A stub `llm` (the same `.complete(LlmRequest) -> .text`
convention every other EXT-036 test uses) returns CANNED responses keyed off distinctive
prompt substrings ("ABSTRACT BEHAVIORAL PROPERTIES" for spec->property derivation,
"BEHAVIORAL PROPERTY CHECK" for property->runnable-check derivation -- both chosen to share
no substring with any existing routed prompt-key used across `tests/test_ext036_*.py`'s
canned-llm stubs).
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_builder import (
    build_system,
    _build_property_check,
    _derive_spec_properties,
    _is_subprocess_check,
    _run_check,
    _wrap_property_check,
    MAX_SPEC_PROPERTIES,
    PROPERTY_DERIVATION_PROMPT,
)


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


# ================================================================================================
# fixtures shared by the full build_system integration tests (a)/(b) below
# ================================================================================================

PQ_SPEC = (
    "A priority queue command-line program in main.py. The command enqueue takes a "
    "priority and an item and adds it to the queue. The command dequeue removes and "
    "prints the item with the highest priority first."
)

PQ_PLAN_JSON = """{
  "modules": [
    {"name": "main.py", "responsibility": "priority queue CLI: enqueue <priority> <item>, dequeue removes the highest-priority item first",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": []}
  ],
  "entrypoint": "main.py",
  "acceptance": "dequeue returns the highest-priority item first"
}"""

_PQ_COMMON = (
    "import sys, json, os\n\n"
    "STATE_FILE = 'pq_state.json'\n\n"
    "def _load():\n"
    "    if os.path.exists(STATE_FILE):\n"
    "        with open(STATE_FILE) as f:\n"
    "            return json.load(f)\n"
    "    return []\n\n"
    "def _save(items):\n"
    "    with open(STATE_FILE, 'w') as f:\n"
    "        json.dump(items, f)\n\n"
    "def main():\n"
    "    args = sys.argv[1:]\n"
    "    if not args:\n"
    "        print('usage: main.py enqueue <priority> <item> | dequeue')\n"
    "        return\n"
    "    cmd = args[0]\n"
    "    if cmd == 'enqueue':\n"
    "        if len(args) < 3:\n"
    "            print('usage: enqueue requires a priority and an item')\n"
    "            return\n"
    "        try:\n"
    "            priority = int(args[1])\n"
    "        except ValueError:\n"
    "            print('usage: priority must be an integer')\n"
    "            return\n"
    "        item = args[2]\n"
    "        items = _load()\n"
    "        items.append([priority, item])\n"
    "        _save(items)\n"
    "        print('enqueued')\n"
    "    elif cmd == 'dequeue':\n"
    "        items = _load()\n"
    "        if not items:\n"
    "            print('empty')\n"
    "            return\n"
)

# BUG: FIFO -- pops the FIRST-enqueued item regardless of priority (never crashes, just
# behaves WRONG -- exactly the semantic class REQ-37 exists to catch).
WRONG_PQ_CLI = (
    _PQ_COMMON +
    "        priority, item = items.pop(0)\n"
    "        _save(items)\n"
    "        print(item)\n"
    "    else:\n"
    "        print('usage: unknown command ' + cmd)\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

# CORRECT: dequeues the highest-priority item first.
CORRECT_PQ_CLI = (
    _PQ_COMMON +
    "        items.sort(key=lambda x: -x[0])\n"
    "        priority, item = items.pop(0)\n"
    "        _save(items)\n"
    "        print(item)\n"
    "    else:\n"
    "        print('usage: unknown command ' + cmd)\n\n"
    "if __name__ == '__main__':\n"
    "    main()\n"
)

PROPERTY_LIST_JSON = json.dumps([
    {"property": "an item enqueued with a higher priority is dequeued before an item "
                 "enqueued with a lower priority"},
])

PROPERTY_CHECK_CODE = (
    "import subprocess, sys\n"
    "entry = 'main.py'\n"
    # this check's `build_system` acceptance run may itself be RE-RUN (e.g. by the REQ-5
    # system-repair loop's own re-verification) against the SAME on-disk state -- drain any
    # leftover queue state from a prior invocation of this SAME check first, so the check is
    # idempotent/repeat-safe regardless of how many times the harness re-runs it.
    "for _ in range(50):\n"
    "    drain = subprocess.run([sys.executable, entry, 'dequeue'],\n"
    "                           capture_output=True, text=True, timeout=20, input='')\n"
    "    if 'empty' in drain.stdout:\n"
    "        break\n"
    "subprocess.run([sys.executable, entry, 'enqueue', '1', 'low'],\n"
    "               capture_output=True, text=True, timeout=20, input='')\n"
    "subprocess.run([sys.executable, entry, 'enqueue', '9', 'high'],\n"
    "               capture_output=True, text=True, timeout=20, input='')\n"
    "result = subprocess.run([sys.executable, entry, 'dequeue'],\n"
    "                        capture_output=True, text=True, timeout=20, input='')\n"
    "assert 'high' in result.stdout, "
    "'expected the higher-priority item first, got: ' + result.stdout\n"
)

PROPERTY_CHECK_JSON = json.dumps({
    "name": "higher priority dequeues first",
    "code": PROPERTY_CHECK_CODE,
})


class _CannedPropertyLlm:
    """Routes each `.complete()` call to a canned response based on the prompt's stage,
    mirroring `test_ext036_system_builder.py`'s `_CannedLlm`. Every OTHER stage (the
    model-proposed acceptance checklist tiers, the acceptance-repair prompt) defaults to
    `"[]"`/unparseable, which degrades harmlessly to the deterministic minimum/smoke
    fallback and a no-op repair round respectively -- never affecting this task's own
    property-check wiring."""

    def __init__(self, *, plan, module_code, properties="[]", property_check="{}") -> None:
        self.plan = plan
        self.module_code = module_code
        self.properties = properties
        self.property_check = property_check
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(self.plan)
        if "ABSTRACT BEHAVIORAL PROPERTIES" in prompt:
            return _Resp(self.properties)
        if "BEHAVIORAL PROPERTY CHECK" in prompt:
            return _Resp(self.property_check)
        if "COMPLETE Python module" in prompt or "SYNTAX ERROR" in prompt:
            return _Resp(self.module_code)
        return _Resp("[]")


# ================================================================================================
# (a) a wrong-ordering priority-queue build -> property VIOLATED -> check FAILS (done=False)
# ================================================================================================

def test_a_wrong_ordering_priority_queue_flips_done_false_when_enabled(tmp_path):
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                              properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_wrong"
    result = build_system(PQ_SPEC, root, llm=llm, spec_properties=True)
    assert result["shipped"] is True
    assert result["done"] is False
    assert "property: higher priority dequeues first" in result["unmet"]


def test_a_same_wrong_build_is_done_true_when_the_flag_is_off(tmp_path):
    # SAME wrong (semantically buggy) module, SAME spec, SAME properties/canned llm -- the
    # ONLY difference is `spec_properties` -- proves the property check is what catches the
    # bug, not some other pre-existing check, and that the flag genuinely gates it.
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                              properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    result = build_system(PQ_SPEC, tmp_path / "pq_wrong_off", llm=llm)  # spec_properties defaults False
    assert result["shipped"] is True
    assert result["done"] is True  # the crash-based floor alone never catches this bug


# ================================================================================================
# (b) a correct priority-queue build -> property SATISFIED -> check passes (no new false-negative)
# ================================================================================================

def test_b_correct_priority_queue_stays_done_true_with_property_checks_on(tmp_path):
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=CORRECT_PQ_CLI,
                              properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_correct"
    result = build_system(PQ_SPEC, root, llm=llm, spec_properties=True)
    assert result["shipped"] is True
    assert result["done"] is True
    assert result["unmet"] == []


# ================================================================================================
# (c) an inconclusive/broken property test (CLI can't be invoked as the test assumes) -> PASS
# ================================================================================================

# `check_call` demands rc==0; invoking python against a script that doesn't exist on disk
# raises `subprocess.CalledProcessError` -- a genuine, real exception that is NOT an
# `AssertionError` -- BEFORE the `assert False` below is ever reached. This is exactly the
# "the CLI couldn't be invoked as the check assumed" shape the grading rule must treat as
# INCONCLUSIVE (a pass), never a manufactured false-negative.
INCONCLUSIVE_CHECK_CODE = (
    "import subprocess, sys\n"
    "subprocess.check_call([sys.executable, 'this_file_does_not_exist_xyz.py'], timeout=20)\n"
    "assert False, 'unreachable -- the line above always raises first'\n"
)


def test_c_inconclusive_property_test_is_treated_as_pass_not_a_false_negative(tmp_path):
    assert _is_subprocess_check(INCONCLUSIVE_CHECK_CODE) is True  # sanity: survives the filter
    wrapped = _wrap_property_check(INCONCLUSIVE_CHECK_CODE)
    check = {"name": "inconclusive property test", "code": wrapped}
    root = tmp_path / "inconclusive_root"
    root.mkdir()
    assert _run_check(root, check) is True  # INCONCLUSIVE -> graded as a PASS


def test_c_a_genuine_assertion_failure_still_fails_the_check(tmp_path):
    # the mirror-image control: a property test whose assertion DEFINITIVELY fails (no
    # exotic exception involved) must still be graded VIOLATED (a real fail), proving the
    # tri-state wrapper doesn't accidentally launder every failure into a pass.
    violated_code = "assert 1 == 2, 'a genuine, definitive violation'\n"
    wrapped = _wrap_property_check(violated_code)
    check = {"name": "definitely violated", "code": wrapped}
    root = tmp_path / "violated_root"
    root.mkdir()
    assert _run_check(root, check) is False


def test_c_a_clean_satisfied_run_passes(tmp_path):
    wrapped = _wrap_property_check("assert 1 == 1\n")
    check = {"name": "satisfied", "code": wrapped}
    root = tmp_path / "satisfied_root"
    root.mkdir()
    assert _run_check(root, check) is True


# ================================================================================================
# (d) a task with no derivable property -> no property checks added, behavior unchanged
# ================================================================================================

def test_d_no_derivable_property_adds_no_check_behavior_unchanged(tmp_path):
    # the model honestly reports no clearly-implied property ("[]") -- build_system with
    # spec_properties=True must behave EXACTLY like spec_properties=False on the SAME wrong
    # module (no property check is silently invented to still catch the bug).
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                              properties="[]", property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_no_property"
    result = build_system(PQ_SPEC, root, llm=llm, spec_properties=True)
    assert result["shipped"] is True
    assert result["done"] is True  # nothing new to catch it -- honestly unchanged
    assert not any(u.startswith("property:") for u in result["unmet"])


def test_d_derive_spec_properties_empty_list_response_yields_no_properties():
    class _EmptyLlm:
        def complete(self, request):
            return _Resp("[]")
    assert _derive_spec_properties(PQ_SPEC, _EmptyLlm()) == []


def test_d_derive_spec_properties_malformed_response_yields_no_properties():
    class _JunkLlm:
        def complete(self, request):
            return _Resp("not json at all, just prose")
    assert _derive_spec_properties(PQ_SPEC, _JunkLlm()) == []


def test_d_derive_spec_properties_empty_spec_yields_no_properties_and_never_calls_llm():
    calls = []

    class _RecordingLlm:
        def complete(self, request):
            calls.append(request.prompt)
            return _Resp("[]")
    assert _derive_spec_properties("", _RecordingLlm()) == []
    assert _derive_spec_properties(None, _RecordingLlm()) == []
    assert calls == []


def test_d_derive_spec_properties_bounded_to_max():
    five = json.dumps([{"property": f"property number {i}"} for i in range(5)])

    class _FiveLlm:
        def complete(self, request):
            return _Resp(five)
    out = _derive_spec_properties(PQ_SPEC, _FiveLlm())
    assert len(out) == MAX_SPEC_PROPERTIES == 2


def test_d_build_property_check_none_when_property_unusable():
    class _NeverLlm:
        def complete(self, request):
            raise AssertionError("must never be called")
    assert _build_property_check({}, [{"name": "main.py", "exports": []}], _NeverLlm()) is None
    assert _build_property_check({"property": ""}, [{"name": "main.py", "exports": []}],
                                  _NeverLlm()) is None
    assert _build_property_check(None, [{"name": "main.py", "exports": []}], _NeverLlm()) is None


def test_d_build_property_check_none_when_no_resolvable_entrypoint():
    class _NeverLlm:
        def complete(self, request):
            raise AssertionError("must never be called")
    # no modules at all -> _minimum_entry_filename can't resolve an entry -> None, never
    # even reaching the model call.
    assert _build_property_check({"property": "x"}, [], _NeverLlm()) is None


def test_d_build_property_check_none_on_malformed_model_output():
    class _JunkLlm:
        def complete(self, request):
            return _Resp("not json")
    mods = [{"name": "main.py", "exports": [{"name": "main", "signature": "def main():"}]}]
    assert _build_property_check({"property": "x"}, mods, _JunkLlm()) is None


def test_d_build_property_check_none_when_code_is_not_a_real_subprocess_check():
    # the model returns a well-formed JSON object, but its `code` never actually drives a
    # subprocess (in-process only) -- must be rejected by the SAME `_is_subprocess_check`
    # filter used elsewhere in this module, never silently accepted.
    class _InProcessLlm:
        def complete(self, request):
            return _Resp(json.dumps({"name": "bad", "code": "assert 1 == 1\n"}))
    mods = [{"name": "main.py", "exports": [{"name": "main", "signature": "def main():"}]}]
    assert _build_property_check({"property": "x"}, mods, _InProcessLlm()) is None


# ================================================================================================
# (e) never raises on a misbehaving llm
# ================================================================================================

def test_e_derive_spec_properties_never_raises_when_llm_raises():
    class _RaisingLlm:
        def complete(self, request):
            raise RuntimeError("jetson unreachable")
    assert _derive_spec_properties(PQ_SPEC, _RaisingLlm()) == []


def test_e_build_property_check_never_raises_when_llm_raises():
    class _RaisingLlm:
        def complete(self, request):
            raise RuntimeError("jetson unreachable")
    mods = [{"name": "main.py", "exports": [{"name": "main", "signature": "def main():"}]}]
    assert _build_property_check({"property": "x"}, mods, _RaisingLlm()) is None


def test_e_build_system_never_raises_when_property_llm_calls_raise(tmp_path):
    class _PartlyRaisingLlm(_CannedPropertyLlm):
        def complete(self, request):
            if "ABSTRACT BEHAVIORAL PROPERTIES" in request.prompt:
                raise RuntimeError("jetson unreachable for this stage only")
            return super().complete(request)

    llm = _PartlyRaisingLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                             properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_raising"
    result = build_system(PQ_SPEC, root, llm=llm, spec_properties=True)  # must not raise
    assert result["shipped"] is True
    # no property check could be derived (the stage raised) -- degrades to the pre-existing
    # (crash-only) result, never a manufactured failure from the property mechanism itself.
    assert result["done"] is True


# ================================================================================================
# (f) no-oracle-leak: the derivation prompt receives ONLY the spec text
# ================================================================================================

def test_f_derivation_prompt_contains_only_the_spec_no_module_sources_or_expected_outputs():
    captured = {}

    class _CapturingLlm:
        def complete(self, request):
            captured["prompt"] = request.prompt
            return _Resp("[]")

    _derive_spec_properties(PQ_SPEC, _CapturingLlm())
    assert captured["prompt"] == PROPERTY_DERIVATION_PROMPT.format(spec=PQ_SPEC)
    # the built module's actual source / the deterministic minimum's expected values must
    # never appear -- the prompt is formatted from `spec` alone, structurally incapable of it.
    assert "STATE_FILE" not in captured["prompt"]
    assert WRONG_PQ_CLI not in captured["prompt"]
    assert PROPERTY_CHECK_CODE not in captured["prompt"]


def test_f_build_system_never_sends_module_sources_to_the_property_derivation_stage(tmp_path):
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                              properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_leak_check"
    build_system(PQ_SPEC, root, llm=llm, spec_properties=True)
    derivation_prompts = [p for p in llm.prompts if "ABSTRACT BEHAVIORAL PROPERTIES" in p]
    assert derivation_prompts, "the derivation stage must have actually been invoked"
    for p in derivation_prompts:
        assert "STATE_FILE" not in p            # no built module source
        assert "pq_state.json" not in p         # no built module internals
        assert PQ_PLAN_JSON.strip() not in p    # no plan JSON either


# ================================================================================================
# (g) byte-identical when the flag is off
# ================================================================================================

def test_g_flag_off_never_calls_the_property_derivation_stage(tmp_path, monkeypatch):
    import harness.system_builder as sb

    def _boom(*args, **kwargs):
        raise AssertionError("_derive_spec_properties must never be called when the flag is off")

    monkeypatch.setattr(sb, "_derive_spec_properties", _boom)
    llm = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                              properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    root = tmp_path / "pq_flag_off"
    result = build_system(PQ_SPEC, root, llm=llm)  # spec_properties omitted -> default False
    assert result["shipped"] is True
    assert result["done"] is True


def test_g_flag_off_by_default_matches_flag_explicitly_false(tmp_path):
    llm_default = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                                      properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    llm_explicit = _CannedPropertyLlm(plan=PQ_PLAN_JSON, module_code=WRONG_PQ_CLI,
                                       properties=PROPERTY_LIST_JSON, property_check=PROPERTY_CHECK_JSON)
    r1 = build_system(PQ_SPEC, tmp_path / "default_off", llm=llm_default)
    r2 = build_system(PQ_SPEC, tmp_path / "explicit_off", llm=llm_explicit, spec_properties=False)
    assert r1["shipped"] == r2["shipped"] == True
    assert r1["done"] == r2["done"] == True
    assert r1["unmet"] == r2["unmet"] == []
