"""EXT-035 REQ-4 — ship-gate heeds module completeness.

Offline, no model calls. Verifies harness.foundry.assemble_and_ship's
optional `module_oracles` kwarg blocks ship when any dependency module
failed its own build_from_intent oracle, even though the CLI ship_cases
themselves pass. Uses tmp_path so nothing pollutes the repo's own
`.jaros-data/foundry/` sandbox.
"""

from harness.foundry import ShipResult, assemble_and_ship

# #EXT-035-REQ-4 Start

CORRECT_STATS_SRC = '''\
def stats(nums):
    return f"count={len(nums)} sum={sum(nums)} mean={round(sum(nums)/len(nums),1)} min={min(nums)} max={max(nums)}"
'''

SHIP_CASES = [
    (["3", "1", "4", "1", "5"], "count=5 sum=14 mean=2.8 min=1 max=5"),
    (["10"], "count=1 sum=10 mean=10.0 min=10 max=10"),
]


def test_all_oracles_pass_ships_with_empty_incomplete(tmp_path):
    result = assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox_ok"),
        project="ext035_req4_all_ok",
        module_oracles={"statslib": True},
    )

    assert isinstance(result, ShipResult)
    assert result.ship is True
    assert result.incomplete_modules == []


def test_failed_dep_oracle_blocks_ship_even_though_cases_pass(tmp_path):
    result = assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox_incomplete"),
        project="ext035_req4_incomplete",
        module_oracles={"statslib": True, "dep": False},
    )

    assert result.ship is False
    assert result.incomplete_modules == ["dep"]
    # the CLI cases still RAN and all passed — it's completeness that blocks, not the run
    assert len(result.cases) == 2
    for case in result.cases:
        assert case["ok"] is True
        assert case["got"] == case["expected"]


def test_module_oracles_none_matches_pre_req4_behavior(tmp_path):
    result_default = assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox_default"),
        project="ext035_req4_default",
    )
    result_explicit_none = assemble_and_ship(
        CORRECT_STATS_SRC,
        "statslib",
        "stats",
        SHIP_CASES,
        arg_mode="ints",
        work_dir=str(tmp_path / "sandbox_explicit_none"),
        project="ext035_req4_explicit_none",
        module_oracles=None,
    )

    for result in (result_default, result_explicit_none):
        assert result.ship is True
        assert result.incomplete_modules == []
        assert len(result.cases) == 2

# #EXT-035-REQ-4 End
