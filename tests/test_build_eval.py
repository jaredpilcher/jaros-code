"""Build eval (EXT-009 / REQ-6 build variant) — deterministic harness checks (no model)."""
from harness.build_eval import SCENARIOS, _oracle_pass


def test_scenarios_wellformed():
    for sc in SCENARIOS:
        assert sc["intent"] and "solution import" in sc["oracle"]


def test_oracle_pass_deterministic():
    oracle = "from solution import add\n\ndef test():\n    assert add(2, 3) == 5\n"
    assert _oracle_pass("def add(a, b):\n    return a + b\n", oracle) is True
    assert _oracle_pass("def add(a, b):\n    return a - b\n", oracle) is False
    assert _oracle_pass("", oracle) is False
