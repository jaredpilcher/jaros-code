"""EXT-008 from-intent generative spine: deterministic tests of the mechanics that
do NOT need the model (test-writer parsing, oracle scoring, stub generation). The
model-driven build_from_intent is exercised by the eval suite, not here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.intent_loop import _run_oracle, _stub  # noqa: E402


def _load_agent(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".jaros-data" / "agents" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_parse_tests_strips_fences_and_guarantees_import():
    mod = _load_agent("test_writer_agent.py")
    reply = "Here are tests:\n```python\ndef test_it():\n    assert add(1, 2) == 3\n```"
    code = mod.parse_tests(reply, "adder", "add")
    assert "```" not in code
    assert "from adder import add" in code
    assert "def test_it" in code


def test_parse_tests_empty_when_no_test_fn():
    mod = _load_agent("test_writer_agent.py")
    assert mod.parse_tests("I cannot write tests, sorry.", "adder", "add") == ""


def test_stub_raises_not_implemented():
    s = _stub("def parse_csv(text):", "parse_csv")
    assert "def parse_csv(text):" in s
    assert "NotImplementedError" in s


def test_extract_examples_pulls_user_ground_truth():
    mod = _load_agent("test_writer_agent.py")
    intent = ("Build running_total(nums): a running cumulative sum. "
              "running_total([1, 2, 3]) returns [1, 3, 6]. Empty list returns empty list.")
    ex = mod.extract_examples(intent, "running_total")
    assert ("running_total([1, 2, 3])", "[1, 3, 6]") in ex
    tests = mod.build_tests_from_examples("running_total", "running_total", ex)
    assert "assert running_total([1, 2, 3]) == [1, 3, 6]" in tests
    assert "from running_total import running_total" in tests


def test_extract_examples_handles_dicts_and_strings():
    mod = _load_agent("test_writer_agent.py")
    intent = "parse_csv('a,b\\n1,2') returns [{'a': '1', 'b': '2'}]."
    ex = mod.extract_examples(intent, "parse_csv")
    assert len(ex) == 1
    call, lit = ex[0]
    assert lit == "[{'a': '1', 'b': '2'}]"


def test_extract_examples_empty_when_no_example():
    mod = _load_agent("test_writer_agent.py")
    assert mod.extract_examples("Build a function that sorts a list.", "mysort") == []


def test_oracle_passes_correct_impl_fails_wrong():
    good = "def running_total(nums):\n    out, s = [], 0\n    for n in nums:\n        s += n\n        out.append(s)\n    return out\n"
    bad = "def running_total(nums):\n    return list(nums)\n"
    oracle = ("from running_total import running_total\n\n\n"
              "def test_oracle():\n    assert running_total([1, 2, 3]) == [1, 3, 6]\n")
    assert _run_oracle("running_total", "running_total.py", good, oracle, "python -m pytest -q") is True
    assert _run_oracle("running_total", "running_total.py", bad, oracle, "python -m pytest -q") is False
