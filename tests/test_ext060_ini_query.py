"""EXT-060 TASK-3: offline tests for the INI-section config-query CLI task's cli-exact grading
path (REQ-4).

FULLY OFFLINE -- no Jetson/LLM call anywhere. These tests never call ``harness.system_builder.
build_system`` with a real model: instead they write a hand-authored ``main.py`` stub (a CORRECT
one and, separately, WRONG ones) straight to a temp directory and drive
``harness.real_systems_suite.grade_real_system_task`` directly -- exactly the cli-exact grading
path (already landed for REQ-1/EXT-059) that ``run_real_systems_suite`` would use on an
already-built root, without ever touching the model. Also proves the leaves-OFF assertion holds
for this task's own sentence, exactly like the REQ-2/REQ-3 tasks' tests do.
"""

# #EXT-060-REQ-4 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    INI_SECTION_QUERY_TASK,
    REAL_SYSTEMS_TASKS,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


CORRECT_INI_QUERY_STUB = """
    import configparser
    import sys


    def main():
        section, key = sys.argv[1], sys.argv[2]
        parser = configparser.ConfigParser()
        parser.read_string(sys.stdin.read())
        if not parser.has_section(section) or not parser.has_option(section, key):
            sys.exit(1)
        print(parser.get(section, key).strip())


    if __name__ == "__main__":
        main()
"""

# WRONG: ignores section scoping -- returns whatever `port` value it encounters LAST across the
# whole file, regardless of which section was requested (5432 from `[db]` instead of 8080 from
# the requested `[server]` section).
WRONG_IGNORES_SECTION_STUB = """
    import sys


    def main():
        section, key = sys.argv[1], sys.argv[2]
        value = None
        for line in sys.stdin:
            line = line.strip()
            if "=" in line and not line.startswith("["):
                k, _, v = line.partition("=")
                if k.strip() == key:
                    value = v.strip()
        if value is None:
            sys.exit(1)
        print(value)


    if __name__ == "__main__":
        main()
"""

# WRONG: prints an extra trailing line (extra output) even though the value itself is correct.
WRONG_EXTRA_OUTPUT_STUB = """
    import configparser
    import sys


    def main():
        section, key = sys.argv[1], sys.argv[2]
        parser = configparser.ConfigParser()
        parser.read_string(sys.stdin.read())
        if not parser.has_section(section) or not parser.has_option(section, key):
            sys.exit(1)
        print(parser.get(section, key).strip())
        print("done")


    if __name__ == "__main__":
        main()
"""


def test_correct_ini_query_stub_passes_the_cli_exact_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_INI_QUERY_STUB)
        accepted, note = grade_real_system_task(INI_SECTION_QUERY_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_ini_query_stub_that_ignores_section_scoping_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_IGNORES_SECTION_STUB)
        accepted, note = grade_real_system_task(INI_SECTION_QUERY_TASK, root, python_exe=PY)
        assert accepted is False


def test_ini_query_stub_with_extra_output_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_EXTRA_OUTPUT_STUB)
        accepted, note = grade_real_system_task(INI_SECTION_QUERY_TASK, root, python_exe=PY)
        assert accepted is False


def test_ini_section_query_task_is_declared_correctly():
    assert INI_SECTION_QUERY_TASK.oracle_kind == "cli-exact"
    assert INI_SECTION_QUERY_TASK.cls == "config-cli"
    assert "section" in INI_SECTION_QUERY_TASK.sentence.lower()
    assert INI_SECTION_QUERY_TASK.oracle_spec["argv"] == ["server", "port"]
    assert INI_SECTION_QUERY_TASK.oracle_spec["expected_stdout"] == "8080\n"


def test_ini_section_query_task_itself_is_leaves_off():
    # A sanity check that the suite's own concrete INI-query task does NOT fingerprint any
    # verified leaf's contract -- otherwise the suite would be measuring the leaf library, not
    # the model.
    assert leaf_for_spec(INI_SECTION_QUERY_TASK.sentence) is None


def test_real_systems_tasks_includes_the_ini_query_task():
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert INI_SECTION_QUERY_TASK.name in names
# #EXT-060-REQ-4 End
