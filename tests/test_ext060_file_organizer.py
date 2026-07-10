"""EXT-060 TASK-5: offline tests for the file-organizer-by-extension CLI task's fs_oracle grading
path (REQ-6).

FULLY OFFLINE -- no Jetson/LLM call anywhere. These tests never call
``harness.system_builder.build_system`` with a real model: instead they write a hand-authored
``main.py`` stub (a CORRECT one and, separately, WRONG ones) straight to a temp directory and
drive ``harness.real_systems_suite.grade_real_system_task`` directly -- exactly the ``"fs"``
grading path (already landed for REQ-2/EXT-060) that ``run_real_systems_suite`` would use on an
already-built root, without ever touching the model. Also proves the leaves-OFF assertion holds
for this task's own sentence, exactly like the REQ-2/REQ-3/REQ-4/REQ-5 tasks' tests do.
"""

# #EXT-060-REQ-6 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    FILE_ORGANIZER_TASK,
    REAL_SYSTEMS_TASKS,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


CORRECT_ORGANIZER_STUB = """
    import os
    import sys


    def main():
        target_dir = sys.argv[1]
        for name in os.listdir(target_dir):
            src = os.path.join(target_dir, name)
            if not os.path.isfile(src):
                continue
            dot = name.rfind(".")
            if dot <= 0:
                subdir = "noext"
            else:
                subdir = name[dot + 1:].lower()
            dest_dir = os.path.join(target_dir, subdir)
            os.makedirs(dest_dir, exist_ok=True)
            os.rename(src, os.path.join(dest_dir, name))


    if __name__ == "__main__":
        main()
"""

# WRONG: keeps the leading dot on the destination subdirectory name (e.g. `.txt/a.txt` instead of
# `txt/a.txt`) -- caught by the `indir/txt/a.txt` path_exists check regardless of the host
# filesystem's case sensitivity (unlike an upper/lowercase-only defect, a leading-dot defect
# produces a genuinely different path on every platform).
WRONG_KEEPS_DOT_STUB = """
    import os
    import sys


    def main():
        target_dir = sys.argv[1]
        for name in os.listdir(target_dir):
            src = os.path.join(target_dir, name)
            if not os.path.isfile(src):
                continue
            dot = name.rfind(".")
            if dot <= 0:
                subdir = "noext"
            else:
                subdir = name[dot:].lower()  # BUG: keeps the leading dot (e.g. ".txt")
            dest_dir = os.path.join(target_dir, subdir)
            os.makedirs(dest_dir, exist_ok=True)
            os.rename(src, os.path.join(dest_dir, name))


    if __name__ == "__main__":
        main()
"""

# WRONG: never moves anything at all -- leaves every original file exactly in place, so every
# `path_absent` check on the original path fails.
NOOP_ORGANIZER_STUB = """
    def main():
        pass


    if __name__ == "__main__":
        main()
"""


def test_correct_organizer_stub_passes_the_fs_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_ORGANIZER_STUB)
        accepted, note = grade_real_system_task(FILE_ORGANIZER_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_keeps_dot_organizer_stub_is_caught_by_the_fs_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_KEEPS_DOT_STUB)
        accepted, note = grade_real_system_task(FILE_ORGANIZER_TASK, root, python_exe=PY)
        assert accepted is False
        assert "txt/a.txt" in note


def test_noop_organizer_stub_is_caught_by_the_fs_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", NOOP_ORGANIZER_STUB)
        accepted, note = grade_real_system_task(FILE_ORGANIZER_TASK, root, python_exe=PY)
        assert accepted is False


def test_file_organizer_task_is_declared_correctly():
    assert FILE_ORGANIZER_TASK.oracle_kind == "fs"
    assert FILE_ORGANIZER_TASK.cls == "fs-utility"
    assert "main.py" in FILE_ORGANIZER_TASK.sentence
    assert "noext" in FILE_ORGANIZER_TASK.sentence
    assert FILE_ORGANIZER_TASK.oracle_spec["entrypoint"] == "main.py"
    assert FILE_ORGANIZER_TASK.oracle_spec["argv"] == ["indir"]
    path_exists_checks = {
        c["path"] for c in FILE_ORGANIZER_TASK.oracle_spec["checks"] if c["kind"] == "path_exists"
    }
    assert path_exists_checks == {
        "indir/txt/a.txt", "indir/txt/b.TXT", "indir/md/c.md", "indir/noext/d",
    }


def test_file_organizer_task_itself_is_leaves_off():
    # A sanity check that the suite's own concrete file-organizer task does NOT fingerprint any
    # verified leaf's contract -- otherwise the suite would be measuring the leaf library, not
    # the model.
    assert leaf_for_spec(FILE_ORGANIZER_TASK.sentence) is None


def test_real_systems_tasks_includes_the_file_organizer_task():
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert FILE_ORGANIZER_TASK.name in names
# #EXT-060-REQ-6 End
