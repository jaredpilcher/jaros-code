"""Tests for the observability heartbeat (EXT-040 REQ-1). No real sleeps: stall logic is
exercised by writing a current.json with an old timestamp."""
import json
import time

import pytest

from harness import heartbeat as hb


@pytest.fixture(autouse=True)
def _tmp_hb(tmp_path, monkeypatch):
    monkeypatch.setenv("JCODE_HEARTBEAT_DIR", str(tmp_path / "heartbeat"))
    return tmp_path


def _read_current():
    d = hb._hb_dir()
    return json.loads((d / hb._CURRENT).read_text(encoding="utf-8"))


def test_beat_writes_current_and_run_log():
    hb.beat("build_system", "PLAN", run_id="r1")
    cur = _read_current()
    assert cur["activity"] == "build_system"
    assert cur["detail"] == "PLAN"
    assert cur["run_id"] == "r1"
    # per-run log appended
    log = (hb._hb_dir() / "r1.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 1
    hb.beat("build_system", "ASSEMBLE", run_id="r1")
    log = (hb._hb_dir() / "r1.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 2  # appends, does not truncate


def test_status_idle_when_no_activity():
    st = hb.status()
    assert st["idle"] is True
    assert st["stalled"] is False


def test_status_after_beat_is_live_not_stalled():
    hb.beat("suite", "running", run_id="r2")
    st = hb.status(stall_after_s=300)
    assert st["idle"] is False
    assert st["activity"] == "suite"
    assert st["stalled"] is False
    assert st["since_last_beat_s"] < 5


def test_status_detects_stall_from_old_beat():
    # write a current.json whose last beat is 10 minutes old -> stalled under a 5-min threshold
    d = hb._hb_dir()
    old = time.time() - 600
    (d / hb._CURRENT).write_text(json.dumps({
        "ts": old, "activity": "wedged_op", "detail": "PYTEST",
        "pid": 123, "run_id": "r3", "started_at": old,
    }), encoding="utf-8")
    st = hb.status(stall_after_s=300)
    assert st["stalled"] is True
    assert st["since_last_beat_s"] >= 600
    assert st["elapsed_s"] >= 600


def test_heartbeat_context_beats_start_and_end():
    with hb.heartbeat("op", run_id="ctx1") as h:
        h.beat("PHASE_A")
        mid = _read_current()
        assert "PHASE_A" in mid["detail"]
    end = _read_current()
    assert end["detail"].startswith("END")


def test_heartbeat_context_beats_error_and_reraises():
    with pytest.raises(ValueError):
        with hb.heartbeat("op", run_id="ctx2"):
            raise ValueError("boom")
    end = _read_current()
    assert end["detail"].startswith("ERROR")
    assert "ValueError" in end["detail"]


def test_format_status_strings():
    assert "idle" in hb.format_status(hb.status()).lower()
    hb.beat("build_system", "ACCEPTANCE 2/5", run_id="r4")
    line = hb.format_status(hb.status())
    assert "build_system" in line and "ACCEPTANCE" in line
    # a stalled status renders the flag
    stalled = {"idle": False, "activity": "x", "detail": "", "pid": 1,
               "elapsed_s": 600, "since_last_beat_s": 600, "stalled": True}
    assert "STALLED" in hb.format_status(stalled)


def test_never_raises_on_bad_input():
    # non-str activity / weird detail must not raise
    hb.beat(None, {"not": "a str"}, run_id=None)  # type: ignore[arg-type]
    assert isinstance(hb.status(), dict)
    assert isinstance(hb.format_status(None), str)


def test_run_with_heartbeat_runs_command_and_records_result():
    import sys as _sys

    from harness.run_with_heartbeat import run_with_heartbeat
    res = run_with_heartbeat(
        [_sys.executable, "-c", "print('hi')"], label="unit-ok", interval=0.05)
    assert res["ok"] is True
    assert res["exit_code"] == 0
    assert "hi" in res["tail"]
    # a final beat was recorded for this run
    st = hb.status()
    assert st["activity"] == "unit-ok"
    assert "done exit=0" in st["detail"]


def test_run_with_heartbeat_reports_nonzero_exit():
    import sys as _sys

    from harness.run_with_heartbeat import run_with_heartbeat
    res = run_with_heartbeat(
        [_sys.executable, "-c", "import sys; sys.exit(3)"], label="unit-fail", interval=0.05)
    assert res["ok"] is False
    assert res["exit_code"] == 3


def test_run_with_heartbeat_spawn_failure_is_honest_not_raised():
    from harness.run_with_heartbeat import run_with_heartbeat
    res = run_with_heartbeat(["this_binary_does_not_exist_xyz"], label="unit-spawn")
    assert res["ok"] is False
    assert "spawn failed" in res["tail"]
