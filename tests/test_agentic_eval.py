"""Agentic eval (EXT-009 / REQ-6) — deterministic harness checks (NO model).

The real `run_agentic_eval` drives the 2B and is run on demand (not in CI). Here we only verify
the eval HARNESS: scenarios are well-formed and the runner returns a correct scorecard shape when
driven by an injected (model-free) planner.
"""
from harness.agentic_eval import SCENARIOS, run_agentic_eval


def test_scenarios_wellformed():
    for sc in SCENARIOS:
        assert sc["request"] and sc["files"]
        assert any(n.startswith("test") for n in sc["files"]), sc["name"]


def test_harness_scorecard_shape_deterministic():
    # empty injected plan -> the loop does nothing (no model) -> faulty repos stay red.
    # We assert the scorecard SHAPE, not a solve. persist=False so the trend isn't polluted.
    sc = run_agentic_eval(planner=lambda req: [], persist=False)
    assert sc["suite"] == "agentic"
    assert sc["total"] == len(SCENARIOS)
    assert isinstance(sc["solved"], int) and 0 <= sc["solved"] <= sc["total"]
    assert len(sc["perTask"]) == len(SCENARIOS)
