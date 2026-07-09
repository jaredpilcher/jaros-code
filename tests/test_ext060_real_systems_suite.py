"""EXT-060 TASK-1: offline tests for the real-systems suite scaffold (REQ-1) and the CSV->JSON
group-by ETL task's fs_oracle grading path (REQ-2).

FULLY OFFLINE -- no Jetson/LLM call anywhere. These tests never call ``harness.system_builder.
build_system`` with a real model: instead they write a hand-authored ``main.py`` stub (a CORRECT
one and, separately, a WRONG one) straight to a temp directory and drive
``harness.real_systems_suite.grade_real_system_task`` directly -- exactly the ``fs_oracle`` grading
path ``run_real_systems_suite`` would use on an already-built root, without ever touching the model.
The leaves-OFF assertion is exercised via ``run_real_systems_suite`` itself with a substitute task
whose sentence deliberately fingerprints a verified leaf's contract; because that assertion fires
BEFORE any build is attempted, this too never reaches the Jetson.
"""

# #EXT-060-REQ-1 Start
# TASK-1
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from harness.real_systems_suite import (
    CSV_GROUPBY_ETL_TASK,
    RETRY_BACKOFF_LIB_TASK,
    RealSystemTask,
    grade_real_system_task,
    run_real_systems_suite,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# CSV->JSON group-by ETL oracle grading: a CORRECT hand-authored stub passes, a WRONG one fails.
# Neither stub is ever produced by build_system -- both are authored directly in this test file.
# --------------------------------------------------------------------------------------------

CORRECT_ETL_STUB = """
    import sys
    import csv
    import json


    def main():
        input_path, output_path = sys.argv[1], sys.argv[2]
        sums = {}
        with open(input_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                category = row["category"]
                amount = int(row["amount"])
                sums[category] = sums.get(category, 0) + amount
        text = json.dumps(sums, sort_keys=True, separators=(",", ":")) + "\\n"
        with open(output_path, "wb") as f:
            f.write(text.encode("utf-8"))


    if __name__ == "__main__":
        main()
"""

# WRONG grouping/sum: counts rows per category instead of summing the `amount` column -- produces
# a plausible-looking but WRONG JSON output ({"electronics":2,"office":1,"produce":2} instead of
# the correct sums), so it must fail file_bytes_equal specifically (not crash, not fail to run).
WRONG_ETL_STUB = """
    import sys
    import csv
    import json


    def main():
        input_path, output_path = sys.argv[1], sys.argv[2]
        counts = {}
        with open(input_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                category = row["category"]
                counts[category] = counts.get(category, 0) + 1  # BUG: counts rows, never sums
        text = json.dumps(counts, sort_keys=True, separators=(",", ":")) + "\\n"
        with open(output_path, "wb") as f:
            f.write(text.encode("utf-8"))


    if __name__ == "__main__":
        main()
"""

# WRONG output path: computes the correct sums but never writes the output file at all.
NOOP_ETL_STUB = """
    def main():
        print("done")


    if __name__ == "__main__":
        main()
"""


def test_correct_etl_stub_passes_the_fs_oracle():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_ETL_STUB)
        accepted, note = grade_real_system_task(CSV_GROUPBY_ETL_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_wrong_grouping_stub_is_caught_by_the_fs_oracle():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", WRONG_ETL_STUB)
        accepted, note = grade_real_system_task(CSV_GROUPBY_ETL_TASK, root, python_exe=PY)
        assert accepted is False
        assert "file_bytes_equal" in note.lower() or "mismatch" in note.lower()


def test_noop_stub_that_never_writes_output_is_caught():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", NOOP_ETL_STUB)
        accepted, note = grade_real_system_task(CSV_GROUPBY_ETL_TASK, root, python_exe=PY)
        assert accepted is False
        assert "path_exists" in note.lower()


def test_csv_groupby_task_is_declared_correctly():
    assert CSV_GROUPBY_ETL_TASK.oracle_kind == "fs"
    assert "category" in CSV_GROUPBY_ETL_TASK.sentence
    assert "amount" in CSV_GROUPBY_ETL_TASK.sentence
    assert CSV_GROUPBY_ETL_TASK.oracle_spec["entrypoint"] == "main.py"
    assert CSV_GROUPBY_ETL_TASK.oracle_spec["argv"] == ["input.csv", "output.json"]


# --------------------------------------------------------------------------------------------
# Unknown oracle_kind / malformed oracle_spec -- never raises, always an honest failure.
# --------------------------------------------------------------------------------------------

def test_grade_unknown_oracle_kind_is_an_honest_failure(tmp_path):
    bogus = RealSystemTask(name="x", cls="x", sentence="x", oracle_kind="not-a-real-kind",
                            oracle_spec={})
    accepted, note = grade_real_system_task(bogus, tmp_path, python_exe=PY)
    assert accepted is False
    assert "unknown oracle_kind" in note.lower()


def test_grade_never_raises_on_missing_entrypoint(tmp_path):
    task = RealSystemTask(
        name="x", cls="x", sentence="x", oracle_kind="fs",
        oracle_spec={"entrypoint": "does_not_exist.py",
                     "checks": [{"kind": "path_exists", "path": "out.txt"}]},
    )
    accepted, note = grade_real_system_task(task, tmp_path, python_exe=PY)
    assert accepted is False  # never raises, never a fabricated pass


# --------------------------------------------------------------------------------------------
# cli-exact oracle_kind (reuses harness.system_suite's exact_stdout check variant)
# --------------------------------------------------------------------------------------------

CLI_EXACT_CORRECT_STUB = """
    if __name__ == "__main__":
        print("hello", end="")
"""

CLI_EXACT_WRONG_STUB = """
    if __name__ == "__main__":
        print("goodbye", end="")
"""


def test_cli_exact_oracle_passes_and_fails_correctly():
    import tempfile

    task = RealSystemTask(
        name="cli-exact-demo", cls="demo", sentence="x", oracle_kind="cli-exact",
        oracle_spec={"argv": [], "stdin": None, "expected_stdout": "hello"},
    )
    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CLI_EXACT_CORRECT_STUB)
        accepted, note = grade_real_system_task(task, root, python_exe=PY)
        assert accepted is True, note

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CLI_EXACT_WRONG_STUB)
        accepted, note = grade_real_system_task(task, root, python_exe=PY)
        assert accepted is False


# --------------------------------------------------------------------------------------------
# Leaves-OFF assertion (REQ-1): a spec that WOULD fingerprint a verified leaf is rejected/scored
# fail -- and this check fires BEFORE any build is attempted, so it never reaches the Jetson.
# --------------------------------------------------------------------------------------------

def test_leaves_off_assertion_fires_before_any_build_is_attempted():
    # A sentence that deliberately fingerprints the verified ttl-store leaf's contract
    # (harness.graph_dsl.leaf_for_spec matches on the "ttl"/"expire" keywords via the ADT oracle).
    leafy_task = RealSystemTask(
        name="leafy-ttl-store", cls="kv-store",
        sentence=(
            "Write a single-file Python CLI program in a file named main.py, an in-memory "
            "key-value store with TTL (time-to-live) expiry. `set <key> <value> <ttl_seconds>` "
            "stores a value that will expire after ttl_seconds."
        ),
        oracle_kind="fs",
        oracle_spec={"entrypoint": "main.py", "checks": [{"kind": "path_exists", "path": "x"}]},
    )
    report = run_real_systems_suite([leafy_task], llm=object())
    assert report["results"][0]["accepted"] is False
    assert report["results"][0]["leaf_fired"] is True
    assert "leaves-off" in report["results"][0]["note"].lower()
    assert report["aggregate"]["overall"]["pass_rate"] == 0.0


def test_csv_groupby_task_itself_is_leaves_off():
    # A sanity check that the suite's own concrete ETL task does NOT fingerprint any verified
    # leaf's contract -- otherwise the suite would be measuring the leaf library, not the model.
    from harness.graph_dsl import leaf_for_spec

    assert leaf_for_spec(CSV_GROUPBY_ETL_TASK.sentence) is None


# --------------------------------------------------------------------------------------------
# run_real_systems_suite's aggregate shape (per-class pass@1)
# --------------------------------------------------------------------------------------------

def test_run_real_systems_suite_reports_per_class_pass_at_1(monkeypatch):
    """Injects a fake ``build_system`` (via monkeypatch) that writes the CORRECT hand-authored
    stub straight into the build root -- still never calling the real model -- proving the full
    build->leaves-off-check->grade wiring end to end without touching the Jetson."""
    import harness.real_systems_suite as suite_mod

    def _fake_build_system(spec, root, *, llm=None, **kwargs):
        _write(Path(root), "main.py", CORRECT_ETL_STUB)
        return {"shipped": True, "done": True, "build_path": "free-form", "note": "fake build"}

    monkeypatch.setattr(suite_mod, "build_system", _fake_build_system)

    report = run_real_systems_suite([CSV_GROUPBY_ETL_TASK], llm=object())
    assert report["results"][0]["accepted"] is True, report["results"][0]["note"]
    assert report["results"][0]["leaf_fired"] is False
    assert report["aggregate"]["overall"] == {"n": 1, "pass_rate": 1.0}
    assert report["aggregate"]["by_cls"]["etl"] == {"n": 1, "pass_rate": 1.0}


def test_run_real_systems_suite_scores_leaf_adopted_build_result_as_failure(monkeypatch):
    """Even when the pre-build static leaves-off check passes, a build result whose own
    ``build_path`` shows ``build_system``'s internal leaf-repair stage adopted a leaf template is
    STILL scored a failure -- a leaf-produced green must never count as a pass (Tenet 3)."""
    import harness.real_systems_suite as suite_mod

    def _fake_build_system_that_used_a_leaf(spec, root, *, llm=None, **kwargs):
        _write(Path(root), "main.py", CORRECT_ETL_STUB)  # even a CORRECT result must be rejected
        return {"shipped": True, "done": True, "build_path": "leaf:ttl-store", "note": "fake"}

    monkeypatch.setattr(suite_mod, "build_system", _fake_build_system_that_used_a_leaf)

    report = run_real_systems_suite([CSV_GROUPBY_ETL_TASK], llm=object())
    assert report["results"][0]["accepted"] is False
    assert report["results"][0]["leaf_fired"] is True
    assert "leaves-off" in report["results"][0]["note"].lower()


def test_run_real_systems_suite_never_raises_on_a_non_shipping_build(monkeypatch):
    import harness.real_systems_suite as suite_mod

    def _fake_build_system_that_fails(spec, root, *, llm=None, **kwargs):
        return {"shipped": False, "done": False, "build_path": "free-form", "note": "gave up"}

    monkeypatch.setattr(suite_mod, "build_system", _fake_build_system_that_fails)

    report = run_real_systems_suite([CSV_GROUPBY_ETL_TASK], llm=object())
    assert report["results"][0]["accepted"] is False
    assert report["aggregate"]["overall"]["pass_rate"] == 0.0
# #EXT-060-REQ-1 End


# #EXT-060-REQ-3 Start
# TASK-2: offline tests for the retry/backoff decorator library task's import_driver grading path
# (REQ-3). FULLY OFFLINE, exactly like the REQ-2 tests above -- every ``retry.py`` stub below is
# hand-authored straight to a temp directory; ``build_system``/the model is never invoked here.
CORRECT_RETRY_STUB = """
    import time


    def retry(times, exceptions=Exception):
        def decorator(fn):
            def wrapped(*args, **kwargs):
                last_exc = None
                for attempt in range(times):
                    try:
                        return fn(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < times - 1:
                            time.sleep(0.001)
                raise last_exc
            return wrapped
        return decorator
"""

# WRONG: gives up after the FIRST attempt -- never retries at all, so the decorated call raises
# on the very first (still-failing) attempt instead of eventually succeeding.
GIVES_UP_EARLY_RETRY_STUB = """
    def retry(times, exceptions=Exception):
        def decorator(fn):
            def wrapped(*args, **kwargs):
                return fn(*args, **kwargs)
            return wrapped
        return decorator
"""

# WRONG: off-by-one retry count -- attempts `times - 1` times instead of `times`, so against the
# fail-twice-then-succeed spy it exhausts its (too-few) attempts before ever reaching the
# succeeding 3rd call: called only 2 times (not exactly 3) and never returns "success" at all.
WRONG_COUNT_RETRY_STUB = """
    import time


    def retry(times, exceptions=Exception):
        def decorator(fn):
            def wrapped(*args, **kwargs):
                last_exc = None
                for attempt in range(times - 1):  # BUG: one attempt too few
                    try:
                        return fn(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        time.sleep(0.001)
                raise last_exc
            return wrapped
        return decorator
"""

# WRONG: never sleeps between attempts (a busy-loop retry) -- still returns the eventual success
# with the right call count, so only the injected-clock sleep-count check catches this.
NO_SLEEP_BETWEEN_RETRY_STUB = """
    def retry(times, exceptions=Exception):
        def decorator(fn):
            def wrapped(*args, **kwargs):
                last_exc = None
                for attempt in range(times):
                    try:
                        return fn(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc  # BUG: never calls time.sleep between attempts
                raise last_exc
            return wrapped
        return decorator
"""


def test_correct_retry_stub_passes_the_import_driver_oracle():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", CORRECT_RETRY_STUB)
        accepted, note = grade_real_system_task(RETRY_BACKOFF_LIB_TASK, root, python_exe=PY)
        assert accepted is True, note


def test_gives_up_early_retry_stub_is_caught():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", GIVES_UP_EARLY_RETRY_STUB)
        accepted, note = grade_real_system_task(RETRY_BACKOFF_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "returns_equals" in note.lower() or "raised" in note.lower()


def test_wrong_retry_count_stub_is_caught():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", WRONG_COUNT_RETRY_STUB)
        accepted, note = grade_real_system_task(RETRY_BACKOFF_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "call_count" in note.lower() or "returns_equals" in note.lower()


def test_no_sleep_between_attempts_retry_stub_is_caught():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ext060_test_") as tmp:
        root = Path(tmp)
        _write(root, "retry.py", NO_SLEEP_BETWEEN_RETRY_STUB)
        accepted, note = grade_real_system_task(RETRY_BACKOFF_LIB_TASK, root, python_exe=PY)
        assert accepted is False
        assert "sleep" in note.lower()


def test_retry_backoff_task_is_declared_correctly():
    assert RETRY_BACKOFF_LIB_TASK.oracle_kind == "import"
    assert "retry.py" in RETRY_BACKOFF_LIB_TASK.sentence
    assert "retry(times, exceptions=Exception)" in RETRY_BACKOFF_LIB_TASK.sentence
    assert RETRY_BACKOFF_LIB_TASK.oracle_spec["module"] == "retry"
    assert RETRY_BACKOFF_LIB_TASK.oracle_spec["expected_sleep_calls"] == 2


def test_retry_backoff_task_itself_is_leaves_off():
    # A sanity check that the suite's own concrete retry task does NOT fingerprint any verified
    # leaf's contract -- otherwise the suite would be measuring the leaf library, not the model.
    from harness.graph_dsl import leaf_for_spec

    assert leaf_for_spec(RETRY_BACKOFF_LIB_TASK.sentence) is None


def test_retry_backoff_task_leaves_off_via_run_real_systems_suite(monkeypatch):
    """Same end-to-end wiring proof as the ETL task's version above: a fake ``build_system`` writes
    the CORRECT hand-authored ``retry.py`` stub straight into the build root (never the real
    model), proving the full build->leaves-off-check->grade wiring for the import oracle path."""
    import harness.real_systems_suite as suite_mod

    def _fake_build_system(spec, root, *, llm=None, **kwargs):
        _write(Path(root), "retry.py", CORRECT_RETRY_STUB)
        return {"shipped": True, "done": True, "build_path": "free-form", "note": "fake build"}

    monkeypatch.setattr(suite_mod, "build_system", _fake_build_system)

    report = run_real_systems_suite([RETRY_BACKOFF_LIB_TASK], llm=object())
    assert report["results"][0]["accepted"] is True, report["results"][0]["note"]
    assert report["results"][0]["leaf_fired"] is False
    assert report["aggregate"]["overall"] == {"n": 1, "pass_rate": 1.0}
    assert report["aggregate"]["by_cls"]["library"] == {"n": 1, "pass_rate": 1.0}


def test_real_systems_tasks_includes_both_landed_tasks():
    from harness.real_systems_suite import REAL_SYSTEMS_TASKS

    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert CSV_GROUPBY_ETL_TASK.name in names
    assert RETRY_BACKOFF_LIB_TASK.name in names
# #EXT-060-REQ-3 End
