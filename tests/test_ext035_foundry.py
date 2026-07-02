"""EXT-035 REQ-2 — the Foundry assemble + ship-gate loop.

Offline, no model calls. Verifies harness.foundry.assemble_and_ship wires
REQ-1's synthesize_cli, assembles a sandbox, runs the tool as a real program,
and grades ship/no-ship on exact stdout match. Uses tmp_path so nothing
pollutes the repo's own `.jaros-data/foundry/` sandbox.
"""

import json

from harness.cli_wrapper import synthesize_cli  # noqa: F401 - import path check (REQ-2 step 2)
from harness.foundry import ShipResult, assemble_and_ship

# #EXT-035-REQ-2 Start

CORRECT_STATS_SRC = '''\
def stats(nums):
    return f"count={len(nums)} sum={sum(nums)} mean={round(sum(nums)/len(nums),1)} min={min(nums)} max={max(nums)}"
'''

WRONG_STATS_SRC = '''\
def stats(nums):
    return f"count={len(nums)} sum={sum(nums)+1} mean={round(sum(nums)/len(nums),1)} min={min(nums)} max={max(nums)}"
'''

SHIP_CASES = [
    (["3", "1", "4", "1", "5"], "count=5 sum=14 mean=2.8 min=1 max=5"),
    (["10"], "count=1 sum=10 mean=10.0 min=10 max=10"),
]


def test_assemble_and_ship_correct_lib_ships(tmp_path):
    result = assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox"),
        project="ext035_test_correct",
    )

    assert isinstance(result, ShipResult)
    assert result.ship is True
    assert len(result.cases) == 2
    for case in result.cases:
        assert case["ok"] is True
        assert case["got"] == case["expected"]
    assert "from statslib import stats" in result.cli_code


def test_assemble_and_ship_wrong_lib_does_not_ship(tmp_path):
    result = assemble_and_ship(
        WRONG_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox"),
        project="ext035_test_wrong",
    )

    assert result.ship is False
    failing = [c for c in result.cases if not c["ok"]]
    assert len(failing) >= 1
    for case in failing:
        assert case["got"] != case["expected"]


def test_assemble_and_ship_appends_ship_log(tmp_path, monkeypatch):
    import harness.foundry as foundry_mod

    fake_log = tmp_path / "ship_log.jsonl"
    monkeypatch.setattr(foundry_mod, "SHIP_LOG", fake_log)

    assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox2"),
        project="ext035_test_log",
    )

    assert fake_log.exists()
    lines = fake_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["project"] == "ext035_test_log"
    assert entry["ship"] is True
    assert len(entry["cases"]) == 2

# #EXT-035-REQ-2 End
