"""EXT-060 TASK-6: offline tests for the MODIFY half (REQ-7) -- RealSystemModifyTask +
run_real_systems_modify_suite, graded by the SAME independent oracles the CREATE half already
uses (grade_real_system_task -- no new oracle code for either check kind).

FULLY OFFLINE -- no Jetson/LLM call anywhere except the ONE end-to-end test that drives
``run_real_systems_modify_suite`` with a canned stub llm (same ``.complete(LlmRequest)->.text``
convention ``tests/test_ext036_modify.py``'s ``_CannedModifyLlm`` already uses). The direct
oracle-wiring tests never call ``harness.system_builder.modify_system`` at all: they write a
hand-authored POST-MODIFICATION module straight to a temp directory and drive
``grade_real_system_task`` directly, exactly the grading step ``run_real_systems_modify_suite``
performs after a successful ``applied=True`` modification, without ever touching the model.
"""

# #EXT-060-REQ-7 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    INI_DEFAULT_FLAG_MODIFY_TASK,
    REAL_SYSTEMS_MODIFY_TASKS,
    RETRY_BASE_DELAY_MODIFY_TASK,
    RealSystemModifyTask,
    grade_real_system_task,
    run_real_systems_modify_suite,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# --- (a) retry-backoff base_delay modify task ------------------------------------------------

CORRECT_RETRY_BASE_DELAY = """
    import time


    def retry(times, exceptions=Exception, base_delay=0.1):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        return fn(*args, **kwargs)
                    except exceptions:
                        if attempt >= times:
                            raise
                        time.sleep(base_delay)
            return wrapper
        return decorator
"""

# WRONG: never adopted the new optional `base_delay` keyword at all -- the oracle's api_call
# explicitly passes `base_delay=0.05`, so this raises TypeError on the very first call.
WRONG_RETRY_IGNORES_BASE_DELAY = """
    import time


    def retry(times, exceptions=Exception):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        return fn(*args, **kwargs)
                    except exceptions:
                        if attempt >= times:
                            raise
                        time.sleep(0.1)
            return wrapper
        return decorator
"""


def test_correct_retry_base_delay_modification_passes_the_import_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_modtest_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", CORRECT_RETRY_BASE_DELAY)
        accepted, note = grade_real_system_task(RETRY_BASE_DELAY_MODIFY_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_retry_module_that_never_adopted_base_delay_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_modtest_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", WRONG_RETRY_IGNORES_BASE_DELAY)
        accepted, note = grade_real_system_task(RETRY_BASE_DELAY_MODIFY_TASK, root, python_exe=PY)
        assert accepted is False


def test_retry_base_delay_modify_task_is_declared_correctly():
    assert RETRY_BASE_DELAY_MODIFY_TASK.oracle_kind == "import"
    assert RETRY_BASE_DELAY_MODIFY_TASK.cls == "library-modify"
    assert "retry.py" in RETRY_BASE_DELAY_MODIFY_TASK.start_system
    assert "base_delay" in RETRY_BASE_DELAY_MODIFY_TASK.mod_sentence
    assert RETRY_BASE_DELAY_MODIFY_TASK.oracle_spec["module"] == "retry"


def test_retry_base_delay_modify_task_itself_is_leaves_off():
    assert leaf_for_spec(RETRY_BASE_DELAY_MODIFY_TASK.mod_sentence) is None


# --- (b) INI --default fallback modify task --------------------------------------------------

CORRECT_INI_DEFAULT_FLAG = """
    import sys


    def parse_ini(text):
        sections = {}
        current = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                current = line[1:-1]
                sections.setdefault(current, {})
                continue
            if current is not None and '=' in line:
                key, _, value = line.partition('=')
                sections[current][key.strip()] = value.strip()
        return sections


    def main():
        args = sys.argv[1:]
        have_default = False
        default = None
        if len(args) == 2:
            section, key = args
        elif len(args) == 4 and args[2] == '--default':
            section, key, _, default = args
            have_default = True
        else:
            sys.exit(1)
            return
        sections = parse_ini(sys.stdin.read())
        if section in sections and key in sections[section]:
            print(sections[section][key])
            return
        if have_default:
            print(default)
            return
        sys.exit(1)


    if __name__ == '__main__':
        main()
"""

# WRONG: never implemented the --default fallback -- still rejects the 4-argument form.
WRONG_INI_IGNORES_DEFAULT_FLAG = """
    import sys


    def parse_ini(text):
        sections = {}
        current = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                current = line[1:-1]
                sections.setdefault(current, {})
                continue
            if current is not None and '=' in line:
                key, _, value = line.partition('=')
                sections[current][key.strip()] = value.strip()
        return sections


    def main():
        if len(sys.argv) != 3:
            sys.exit(1)
        section, key = sys.argv[1], sys.argv[2]
        sections = parse_ini(sys.stdin.read())
        if section in sections and key in sections[section]:
            print(sections[section][key])
            return
        sys.exit(1)


    if __name__ == '__main__':
        main()
"""


def test_correct_ini_default_flag_modification_passes_the_cli_exact_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_modtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_INI_DEFAULT_FLAG)
        accepted, note = grade_real_system_task(INI_DEFAULT_FLAG_MODIFY_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_ini_module_that_never_adopted_default_flag_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_modtest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_INI_IGNORES_DEFAULT_FLAG)
        accepted, note = grade_real_system_task(INI_DEFAULT_FLAG_MODIFY_TASK, root, python_exe=PY)
        assert accepted is False


def test_ini_default_flag_modify_task_is_declared_correctly():
    assert INI_DEFAULT_FLAG_MODIFY_TASK.oracle_kind == "cli-exact"
    assert INI_DEFAULT_FLAG_MODIFY_TASK.cls == "config-cli-modify"
    assert "main.py" in INI_DEFAULT_FLAG_MODIFY_TASK.start_system
    assert "--default" in INI_DEFAULT_FLAG_MODIFY_TASK.mod_sentence
    assert INI_DEFAULT_FLAG_MODIFY_TASK.oracle_spec["expected_stdout"] == "fallback\n"


def test_ini_default_flag_modify_task_itself_is_leaves_off():
    assert leaf_for_spec(INI_DEFAULT_FLAG_MODIFY_TASK.mod_sentence) is None


def test_real_systems_modify_tasks_includes_both_tasks():
    # #EXT-060-REQ-10 Start
    # TASK-8: the modify roster GREW by one (REST_SQLITE_ADD_UPDATE_MODIFY, REQ-10) -- this test
    # now asserts membership + a minimum size rather than an exact count, so future roster growth
    # (the design doc's explicit "roster only ever GROWS" direction) does not require touching
    # this unrelated test again.
    names = {t.name for t in REAL_SYSTEMS_MODIFY_TASKS}
    assert RETRY_BASE_DELAY_MODIFY_TASK.name in names
    assert INI_DEFAULT_FLAG_MODIFY_TASK.name in names
    assert len(REAL_SYSTEMS_MODIFY_TASKS) >= 3
    # #EXT-060-REQ-10 End


# --- run_real_systems_modify_suite: end-to-end with a canned stub llm ------------------------

class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedModifyLlm:
    """Same prompt-substring routing convention as tests/test_ext036_modify.py's
    _CannedModifyLlm: identify target / apply modification (regenerated body) / syntax repair
    / the two ACCEPTANCE-CHECKS derivations (baseline vs. best-effort new-behavior)."""

    def __init__(self, *, target, modified, mod_sentence, baseline_checklist) -> None:
        self.target = target
        self.modified = modified
        self.mod_sentence = mod_sentence
        self.baseline_checklist = baseline_checklist
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp(self.target)
        if "APPLY MODIFICATION" in prompt:
            return _Resp(self.modified)
        if "SYNTAX ERROR" in prompt:
            return _Resp("")
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")
        if "ACCEPTANCE CHECKS" in prompt:
            if self.mod_sentence in prompt:
                return _Resp("[]")  # best-effort new-behavior checklist not needed here
            return _Resp(self.baseline_checklist)
        return _Resp("")


# A baseline check that stays true both before AND after a correct base_delay modification
# (retry stays importable and callable either way) -- exactly the non-regressing shape a real
# modify_system run needs to report applied=True.
_RETRY_BASELINE_CHECKLIST = (
    '[{"name": "retry is callable", '
    '"code": "from retry import retry\\nassert callable(retry)\\n"}]'
)


def test_run_real_systems_modify_suite_accepts_a_correct_modification_end_to_end():
    llm = _CannedModifyLlm(
        target='["retry.py"]',
        modified=textwrap.dedent(CORRECT_RETRY_BASE_DELAY),
        mod_sentence=RETRY_BASE_DELAY_MODIFY_TASK.mod_sentence,
        baseline_checklist=_RETRY_BASELINE_CHECKLIST,
    )
    out = run_real_systems_modify_suite([RETRY_BASE_DELAY_MODIFY_TASK], llm=llm, python_exe=PY)
    assert out["results"], out
    rec = out["results"][0]
    assert rec["applied"] is True, rec["note"]
    assert rec["accepted"] is True, rec["note"]
    assert out["aggregate"]["overall"]["pass_rate"] == 1.0


def test_run_real_systems_modify_suite_never_raises_on_unparseable_target():
    llm = _CannedModifyLlm(
        target="not json at all",
        modified=textwrap.dedent(CORRECT_RETRY_BASE_DELAY),
        mod_sentence=RETRY_BASE_DELAY_MODIFY_TASK.mod_sentence,
        baseline_checklist=_RETRY_BASELINE_CHECKLIST,
    )
    out = run_real_systems_modify_suite([RETRY_BASE_DELAY_MODIFY_TASK], llm=llm, python_exe=PY)
    rec = out["results"][0]
    assert rec["applied"] is False
    assert rec["accepted"] is False


def test_run_real_systems_modify_suite_defaults_to_the_module_task_list(monkeypatch):
    """Never touches the model -- an unreachable/None llm on an empty override still returns
    the standard shape without raising (mirrors the CREATE half's own default-list contract)."""
    class _BrokenLlm:
        def complete(self, request):
            raise RuntimeError("no model available in this offline test")

    out = run_real_systems_modify_suite([RETRY_BASE_DELAY_MODIFY_TASK], llm=_BrokenLlm(), python_exe=PY)
    assert out["results"][0]["accepted"] is False
    assert "results" in out and "aggregate" in out
# #EXT-060-REQ-7 End
