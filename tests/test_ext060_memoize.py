"""EXT-060 TASK-4: offline tests for the memoize/cache decorator library task's import_driver
grading path (REQ-5).

FULLY OFFLINE -- no Jetson/LLM call anywhere. These tests never call
``harness.system_builder.build_system`` with a real model: instead they write a hand-authored
``memoize.py`` stub (a CORRECT one and, separately, WRONG ones) straight to a temp directory and
drive ``harness.real_systems_suite.grade_real_system_task`` directly -- exactly the ``"import"``
grading path (already landed for REQ-3/EXT-060) that ``run_real_systems_suite`` would use on an
already-built root, without ever touching the model. Also proves the leaves-OFF assertion holds
for this task's own sentence, exactly like the REQ-2/REQ-3/REQ-4 tasks' tests do.
"""

# #EXT-060-REQ-5 Start
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    MEMOIZE_LIB_TASK,
    REAL_SYSTEMS_TASKS,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


CORRECT_MEMOIZE_STUB = """
    def memoize(maxsize=128):
        def decorator(fn):
            cache = {}

            def wrapped(*args):
                if args in cache:
                    return cache[args]
                result = fn(*args)
                cache[args] = result
                return result

            return wrapped
        return decorator
"""

# WRONG: never caches at all -- always calls through to the wrapped callable, so the underlying
# spy is invoked on EVERY call (4 times: call_x1, call_x2, call_y1, call_x3) instead of exactly 2.
WRONG_NEVER_CACHES_STUB = """
    def memoize(maxsize=128):
        def decorator(fn):
            def wrapped(*args):
                return fn(*args)
            return wrapped
        return decorator
"""

# WRONG: only remembers the SINGLE most-recently-seen call (a size-1 cache), not a real
# arg-keyed cache -- so after the intervening call with a DIFFERENT argument (7), the final
# repeat of the original argument (5) is a cache miss and re-invokes the spy a 3rd time.
WRONG_LAST_CALL_ONLY_STUB = """
    def memoize(maxsize=128):
        def decorator(fn):
            state = {"args": None, "value": None}

            def wrapped(*args):
                if state["args"] == args:
                    return state["value"]
                result = fn(*args)
                state["args"] = args
                state["value"] = result
                return result

            return wrapped
        return decorator
"""

# WRONG: drops the documented default entirely -- makes `maxsize` a REQUIRED positional
# parameter, so the oracle's own zero-argument `memoize()` call raises a TypeError instead of
# returning a decorator (the exact signature-contract defect shape EXT-036 REQ-45 targets).
WRONG_DROPS_DEFAULT_STUB = """
    def memoize(maxsize):
        def decorator(fn):
            cache = {}

            def wrapped(*args):
                if args in cache:
                    return cache[args]
                result = fn(*args)
                cache[args] = result
                return result

            return wrapped
        return decorator
"""


def test_correct_memoize_stub_passes_the_import_driver_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "memoize.py", CORRECT_MEMOIZE_STUB)
        accepted, note = grade_real_system_task(MEMOIZE_LIB_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_never_caches_memoize_stub_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "memoize.py", WRONG_NEVER_CACHES_STUB)
        accepted, note = grade_real_system_task(MEMOIZE_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "call_count" in note.lower()


def test_last_call_only_memoize_stub_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "memoize.py", WRONG_LAST_CALL_ONLY_STUB)
        accepted, note = grade_real_system_task(MEMOIZE_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "call_count" in note.lower()


def test_dropped_default_memoize_stub_is_caught():
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "memoize.py", WRONG_DROPS_DEFAULT_STUB)
        accepted, note = grade_real_system_task(MEMOIZE_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "raised" in note.lower() or "returns_equals" in note.lower()


def test_memoize_task_is_declared_correctly():
    assert MEMOIZE_LIB_TASK.oracle_kind == "import"
    assert MEMOIZE_LIB_TASK.cls == "library"
    assert "memoize.py" in MEMOIZE_LIB_TASK.sentence
    assert "memoize(maxsize=128)" in MEMOIZE_LIB_TASK.sentence
    assert MEMOIZE_LIB_TASK.oracle_spec["module"] == "memoize"
    call_count_checks = [c for c in MEMOIZE_LIB_TASK.oracle_spec["checks"] if c["kind"] == "call_count"]
    assert call_count_checks == [{"kind": "call_count", "spy": "counter", "expected": 2}]


def test_memoize_task_itself_is_leaves_off():
    # A sanity check that the suite's own concrete memoize task does NOT fingerprint any verified
    # leaf's contract -- otherwise the suite would be measuring the leaf library, not the model.
    assert leaf_for_spec(MEMOIZE_LIB_TASK.sentence) is None


def test_real_systems_tasks_includes_the_memoize_task():
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert MEMOIZE_LIB_TASK.name in names
# #EXT-060-REQ-5 End
