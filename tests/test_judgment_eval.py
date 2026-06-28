"""tests/test_judgment_eval.py — Offline unit tests for the judgment eval (EXT-016 / REQ-3).

All tests run with NO Jetson, NO LLM, NO network.  The live judge is replaced by a stub
injected via run_eval(judge_fn=...).

Run:
    python -m pytest tests/test_judgment_eval.py -q
"""
# #EXT-016-REQ-3 Start
from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_SCENARIOS_PATH = _ROOT / "evals" / "judgment" / "scenarios.json"

# The real action space (must match VALID_ACTIONS in judgment_eval.py and _REV in behavioral_solve.py)
_VALID_ACTIONS = frozenset({"code", "gherkin", "repair", "done"})


# ---------------------------------------------------------------------------
# 1. Schema validation — no LLM needed
# ---------------------------------------------------------------------------

class TestScenariosSchema:
    """Validates evals/judgment/scenarios.json structure without touching the LLM."""

    def test_file_exists(self):
        assert _SCENARIOS_PATH.exists(), f"scenarios.json not found at {_SCENARIOS_PATH}"

    def test_valid_json(self):
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list), "scenarios.json root must be a JSON array"

    def test_minimum_scenario_count(self):
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) >= 8, f"Need at least 8 scenarios, got {len(data)}"

    def test_required_fields_present(self):
        required = {"id", "failure_class", "intent", "name", "feedback", "expected_action", "rationale"}
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for sc in data:
            missing = required - sc.keys()
            assert not missing, f"Scenario {sc.get('id', '?')} missing fields: {missing}"

    def test_expected_action_in_valid_set(self):
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for sc in data:
            assert sc["expected_action"] in _VALID_ACTIONS, (
                f"Scenario '{sc['id']}' has invalid expected_action '{sc['expected_action']}'; "
                f"must be one of {sorted(_VALID_ACTIONS)}"
            )

    def test_required_failure_classes_covered(self):
        required_classes = {"syntax", "logic", "import", "all_pass", "bad_tests"}
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        found = {sc["failure_class"] for sc in data}
        missing = required_classes - found
        assert not missing, f"Missing failure classes: {missing}"

    def test_unique_scenario_ids(self):
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        ids = [sc["id"] for sc in data]
        assert len(ids) == len(set(ids)), f"Duplicate scenario IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_nonempty_string_fields(self):
        str_fields = ["id", "failure_class", "intent", "name", "feedback", "expected_action", "rationale"]
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for sc in data:
            for field in str_fields:
                val = sc.get(field, "")
                assert isinstance(val, str) and val.strip(), (
                    f"Scenario '{sc.get('id', '?')}' has empty/non-string field '{field}'"
                )


# ---------------------------------------------------------------------------
# 2. Module importability (ast.parse + import — no LLM triggered)
# ---------------------------------------------------------------------------

class TestModuleImportability:
    """Verifies judgment_eval.py is syntactically valid and importable."""

    def test_source_parses(self):
        src_path = _ROOT / "harness" / "judgment_eval.py"
        assert src_path.exists(), f"harness/judgment_eval.py not found"
        src = src_path.read_text(encoding="utf-8")
        ast.parse(src)  # raises SyntaxError on failure

    def test_module_imports_cleanly(self):
        """Import harness.judgment_eval — must succeed without touching Jetson."""
        mod = importlib.import_module("harness.judgment_eval")
        assert hasattr(mod, "run_eval"), "run_eval not found in judgment_eval"
        assert hasattr(mod, "VALID_ACTIONS"), "VALID_ACTIONS not found in judgment_eval"

    def test_valid_actions_matches_spec(self):
        mod = importlib.import_module("harness.judgment_eval")
        assert mod.VALID_ACTIONS == _VALID_ACTIONS, (
            f"VALID_ACTIONS mismatch: got {mod.VALID_ACTIONS}, expected {_VALID_ACTIONS}"
        )


# ---------------------------------------------------------------------------
# 3. Scorer correctness — stub judge, no LLM
# ---------------------------------------------------------------------------

class TestScorerWithStubJudge:
    """Uses run_eval(judge_fn=stub) to validate the scoring logic offline."""

    def _load_scenarios(self):
        with open(_SCENARIOS_PATH, encoding="utf-8") as f:
            return json.load(f)

    def _stub_always_code(self, intent: str, name: str, fb: str, temp: float) -> str:
        """Stub that always returns 'code'."""
        return "code"

    def _stub_always_done(self, intent: str, name: str, fb: str, temp: float) -> str:
        return "done"

    def _stub_correct_oracle(self, intent: str, name: str, fb: str, temp: float) -> str:
        """Stub that cheats — returns the correct action by looking it up from scenarios."""
        for sc in self._load_scenarios():
            if sc["name"] == name and sc["intent"] == intent:
                return sc["expected_action"]
        return "code"

    def test_stub_always_code_scores_correctly(self):
        """When stub always returns 'code', only 'code'-expected scenarios should be ok=True."""
        mod = importlib.import_module("harness.judgment_eval")
        scenarios = self._load_scenarios()

        results = mod.run_eval(judge_fn=self._stub_always_code, silent=True)

        assert len(results) == len(scenarios), "Result count must match scenario count"
        for r in results:
            # Find matching scenario
            sc = next(s for s in scenarios if s["id"] == r["id"])
            if sc["expected_action"] == "code":
                assert r["ok"] is True, f"Scenario '{r['id']}' should be ok=True (expected 'code')"
                assert r["got"] == "code"
            else:
                assert r["ok"] is False, f"Scenario '{r['id']}' should be ok=False (expected '{sc['expected_action']}')"

    def test_stub_overall_accuracy_count(self):
        """Overall accuracy = count of 'code'-expected scenarios when stub always says 'code'."""
        mod = importlib.import_module("harness.judgment_eval")
        scenarios = self._load_scenarios()
        expected_ok_count = sum(1 for s in scenarios if s["expected_action"] == "code")

        results = mod.run_eval(judge_fn=self._stub_always_code, silent=True)
        actual_ok = sum(1 for r in results if r["ok"])

        assert actual_ok == expected_ok_count, (
            f"Expected {expected_ok_count} ok results (code-expected scenarios), got {actual_ok}"
        )

    def test_perfect_oracle_stub_scores_100_percent(self):
        """A stub that returns the correct action for every scenario should score 100%."""
        mod = importlib.import_module("harness.judgment_eval")
        scenarios = self._load_scenarios()

        results = mod.run_eval(judge_fn=self._stub_correct_oracle, silent=True)
        n_ok = sum(1 for r in results if r["ok"])

        assert n_ok == len(scenarios), (
            f"Perfect oracle stub should give 100% but got {n_ok}/{len(scenarios)}"
        )

    def test_stub_done_only_scores_all_pass_scenarios(self):
        """Stub always returning 'done' should only match 'all_pass' scenarios."""
        mod = importlib.import_module("harness.judgment_eval")
        scenarios = self._load_scenarios()
        expected_ok_count = sum(1 for s in scenarios if s["expected_action"] == "done")

        results = mod.run_eval(judge_fn=self._stub_always_done, silent=True)
        actual_ok = sum(1 for r in results if r["ok"])

        assert actual_ok == expected_ok_count

    def test_result_dict_has_required_keys(self):
        """Every result dict must have: id, failure_class, expected, got, ok."""
        mod = importlib.import_module("harness.judgment_eval")
        required_keys = {"id", "failure_class", "expected", "got", "ok"}

        results = mod.run_eval(judge_fn=self._stub_always_code, silent=True)
        for r in results:
            missing = required_keys - r.keys()
            assert not missing, f"Result for '{r.get('id', '?')}' missing keys: {missing}"

    def test_got_field_always_valid_action(self):
        """The 'got' field must always be one of the valid actions."""
        mod = importlib.import_module("harness.judgment_eval")
        results = mod.run_eval(judge_fn=self._stub_always_code, silent=True)
        for r in results:
            assert r["got"] in _VALID_ACTIONS, (
                f"Scenario '{r['id']}' has invalid 'got' value: '{r['got']}'"
            )

    def test_parse_action_fallback_to_code(self):
        """_parse_action falls back to 'code' when no known action appears in output."""
        mod = importlib.import_module("harness.judgment_eval")
        # Unknown word -> fallback 'code'
        assert mod._parse_action("unknown-action-xyz") == "code"
        # Empty string -> fallback 'code'
        assert mod._parse_action("") == "code"

    def test_parse_action_detects_all_valid_actions(self):
        """_parse_action correctly recognises each valid action word."""
        mod = importlib.import_module("harness.judgment_eval")
        for action in _VALID_ACTIONS:
            # action as the sole word
            assert mod._parse_action(action) == action
            # action embedded in a sentence
            assert mod._parse_action(f"I think {action} is right") == action
# #EXT-016-REQ-3 End
