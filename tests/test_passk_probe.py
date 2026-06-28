"""Offline tests for EXT-019 harness/passk_probe.py.

All tests run without the Jetson (no LLM, no Docker). The code-generation function
and the hidden oracle are replaced by stubs. The repo is a minimal temp directory.

Verified with:
    python -m pytest tests/test_passk_probe.py -v
"""
from __future__ import annotations

import ast
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Syntax + import smoke-test
# ---------------------------------------------------------------------------

def test_passk_probe_parses():
    """passk_probe.py must parse without syntax errors."""
    src = (Path(__file__).resolve().parents[1] / "harness" / "passk_probe.py").read_text(
        encoding="utf-8"
    )
    ast.parse(src)  # raises SyntaxError on failure


def test_passk_probe_imports():
    """Top-level symbols are importable (no heavy LLM imports at module scope)."""
    from harness.passk_probe import (  # noqa: F401
        _parse_fail_shas,
        _resolve_tasks,
        _core_probe,
        probe_task,
        run_probe,
    )


# ---------------------------------------------------------------------------
# _parse_fail_shas — pure function
# ---------------------------------------------------------------------------

_SAMPLE_BIGBAR = """\
>>> big-bar corpus loaded: 101 tasks total  (more-itertools:91, toolz:10)
  1/101 [more-itertools] e39ae39c [pass] | Reject by ID
  2/101 [more-itertools] cca32949 [fail] | fix last() when __reversed__ is None
  3/101 [more-itertools] 6887a7bd [pass] | Add running_median
  4/101 [more-itertools] 5c8336c5 [capped] | Draft of running_median
  5/101 [more-itertools] f8ccab22 [fail] | Various small improvments
  6/101 [more-itertools] 7f21fb14 [fail] | Add interleave_randomly
  7/101 [more-itertools] 5bd5c263 [fail] | Working draft
  8/101 [more-itertools] 21d3d883 [fail] | Issue 1003: Multidimensional reshape
  9/101 [more-itertools] 120ee0a5 [pass] | Issue 900: Replace iequals fillvalue
 10/101 [more-itertools] ccf96ac6 [fail] | Issue 1070: Add random derangements
"""


def test_parse_fail_shas_basic():
    """Extract exactly n [fail] sha prefixes in order."""
    from harness.passk_probe import _parse_fail_shas

    shas = _parse_fail_shas(_SAMPLE_BIGBAR, n=3)
    assert shas == ["cca32949", "f8ccab22", "7f21fb14"], f"got {shas}"


def test_parse_fail_shas_caps_at_n():
    """Never returns more than n shas even if more [fail] lines exist."""
    from harness.passk_probe import _parse_fail_shas

    shas = _parse_fail_shas(_SAMPLE_BIGBAR, n=2)
    assert len(shas) == 2


def test_parse_fail_shas_empty():
    """Returns [] when no [fail] lines are present."""
    from harness.passk_probe import _parse_fail_shas

    shas = _parse_fail_shas("no fail lines here", n=5)
    assert shas == []


def test_parse_fail_shas_skip_pass_capped():
    """Does NOT include [pass] or [capped] lines."""
    from harness.passk_probe import _parse_fail_shas

    shas = _parse_fail_shas(_SAMPLE_BIGBAR, n=100)
    # pass lines: e39ae39c, 6887a7bd, 120ee0a5 — must NOT appear
    # capped: 5c8336c5 — must NOT appear
    assert "e39ae39c" not in shas
    assert "6887a7bd" not in shas
    assert "5c8336c5" not in shas
    assert "120ee0a5" not in shas


# ---------------------------------------------------------------------------
# _resolve_tasks — pure function
# ---------------------------------------------------------------------------

_SAMPLE_CORPUS = [
    {"sha": "cca32949abcdef1234567890abcdef12", "parent": "p1", "subject": "fix last()",
     "redgreen": ["tests/test_more.py::test_last"], "code_files": ["more_itertools/more.py"],
     "test_files": ["tests/test_more.py"], "repo": "more-itertools"},
    {"sha": "f8ccab22abcdef1234567890abcdef12", "parent": "p2", "subject": "Various small",
     "redgreen": ["tests/test_more.py::test_small"], "code_files": ["more_itertools/more.py"],
     "test_files": ["tests/test_more.py"], "repo": "more-itertools"},
    {"sha": "deadbeefabcdef1234567890abcdef12", "parent": "p3", "subject": "some other",
     "redgreen": ["tests/test_more.py::test_other"], "code_files": ["more_itertools/more.py"],
     "test_files": ["tests/test_more.py"], "repo": "more-itertools"},
]


def test_resolve_tasks_basic():
    """Match sha prefixes to corpus tasks."""
    from harness.passk_probe import _resolve_tasks

    tasks = _resolve_tasks(["cca32949", "f8ccab22"], _SAMPLE_CORPUS)
    assert len(tasks) == 2
    assert tasks[0]["sha"].startswith("cca32949")
    assert tasks[1]["sha"].startswith("f8ccab22")


def test_resolve_tasks_unknown_sha_skipped():
    """Unknown shas (not in corpus) are silently skipped."""
    from harness.passk_probe import _resolve_tasks

    tasks = _resolve_tasks(["00000000", "cca32949"], _SAMPLE_CORPUS)
    assert len(tasks) == 1
    assert tasks[0]["sha"].startswith("cca32949")


def test_resolve_tasks_no_duplicates():
    """Same sha prefix twice does not produce duplicate tasks."""
    from harness.passk_probe import _resolve_tasks

    tasks = _resolve_tasks(["cca32949", "cca32949"], _SAMPLE_CORPUS)
    assert len(tasks) == 1


# ---------------------------------------------------------------------------
# _core_probe — sampling loop with stubs (no Jetson, no Docker)
# ---------------------------------------------------------------------------

def _make_stub_oracle(passing_sample_indices: set[int]):
    """Return a stub oracle that passes on specific SAMPLE indices (0-based).

    The oracle is called: once for greedy (index 0), then k times for samples
    (indices 1..k). The caller decides which sample-indices (1-based within
    the k-loop) should pass; index 0 (greedy) always fails in these stubs
    unless -1 is in passing_sample_indices.

    For simplicity: the oracle just counts total calls and passes when the
    call number (0 = greedy, 1..k = samples) is in ``passing_call_indices``.
    """
    call_count: list[int] = [0]

    def oracle(repo, nodes, timeout):
        idx = call_count[0]
        call_count[0] += 1
        if idx in passing_sample_indices:
            return set()        # pass
        return set(nodes)       # fail

    oracle.call_count = call_count
    return oracle


def test_core_probe_passk_three_of_twenty():
    """Stub oracle passes on sample calls 1, 8, 15 (3 out of 20). Assert n_passed=3, passk=True."""
    from harness.passk_probe import _core_probe

    # Stub oracle: call 0 = greedy (fail), calls 1, 8, 15 = pass (sample idx 0, 7, 14)
    stub_oracle = _make_stub_oracle({1, 8, 15})

    def stub_generate(subject, name, parent_src, context, gherkin, temp):
        return f"def {name}():\n    pass\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / "pkg").mkdir()
        cf = "pkg/mod.py"
        (repo / cf).write_text("def foo():\n    pass\n", encoding="utf-8")

        task = {
            "sha": "abc12345" * 5,
            "parent": "p" * 40,
            "subject": "add foo behaviour",
            "redgreen": ["tests/test_mod.py::test_foo"],
            "code_files": [cf],
            "test_files": ["tests/test_mod.py"],
            "repo": "pkg",
        }
        targets = [(cf, "foo", "def foo():\n    pass\n")]
        orig = {cf: "def foo():\n    pass\n"}
        gherkins = {(cf, "foo"): "Given foo called\nThen it returns None"}

        result = _core_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            k=20,
            temp=0.8,
            timeout=10,
            generate_fn=stub_generate,
            oracle_fn=stub_oracle,
        )

    assert result["n_passed"] == 3, f"expected 3, got {result['n_passed']}"
    assert result["passk"] is True, "passk should be True when n_passed > 0"
    assert result["greedy_pass"] is False, "greedy call (index 0) should fail"
    assert result["k"] == 20


def test_core_probe_greedy_passes():
    """Stub oracle passes only on the greedy call (index 0)."""
    from harness.passk_probe import _core_probe

    stub_oracle = _make_stub_oracle({0})  # only greedy passes

    def stub_generate(subject, name, parent_src, context, gherkin, temp):
        return f"def {name}():\n    pass\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / "pkg").mkdir()
        cf = "pkg/mod.py"
        (repo / cf).write_text("def foo():\n    pass\n", encoding="utf-8")

        task = {
            "sha": "abc12345" * 5,
            "parent": "p" * 40,
            "subject": "test subject",
            "redgreen": ["tests/test_mod.py::test_foo"],
            "code_files": [cf],
            "test_files": ["tests/test_mod.py"],
            "repo": "pkg",
        }
        targets = [(cf, "foo", None)]
        orig = {cf: "def foo():\n    pass\n"}
        gherkins = {(cf, "foo"): "some scenarios"}

        result = _core_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            k=5,
            temp=0.8,
            timeout=10,
            generate_fn=stub_generate,
            oracle_fn=stub_oracle,
        )

    assert result["greedy_pass"] is True
    assert result["n_passed"] == 0, "no sample calls should pass"
    assert result["passk"] is False


def test_core_probe_none_pass():
    """When oracle never passes, n_passed=0 and passk=False."""
    from harness.passk_probe import _core_probe

    stub_oracle = _make_stub_oracle(set())  # nothing passes

    def stub_generate(subject, name, parent_src, context, gherkin, temp):
        return f"def {name}():\n    pass\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / "pkg").mkdir()
        cf = "pkg/mod.py"
        (repo / cf).write_text("def foo():\n    pass\n", encoding="utf-8")

        task = {
            "sha": "abc12345" * 5,
            "parent": "p" * 40,
            "subject": "test subject",
            "redgreen": ["tests/test_mod.py::test_foo"],
            "code_files": [cf],
            "test_files": ["tests/test_mod.py"],
            "repo": "pkg",
        }
        targets = [(cf, "foo", None)]
        orig = {cf: "def foo():\n    pass\n"}
        gherkins = {(cf, "foo"): "scenarios"}

        result = _core_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            k=10,
            temp=0.8,
            timeout=10,
            generate_fn=stub_generate,
            oracle_fn=stub_oracle,
        )

    assert result["n_passed"] == 0
    assert result["passk"] is False
    assert result["greedy_pass"] is False


def test_core_probe_oracle_is_score_only():
    """Oracle output is NEVER fed back to generate_fn (honest probe invariant).

    The generate_fn should always receive the same (subject, name, parent_src,
    context, gherkin, temp) regardless of oracle outcomes — oracle output must
    not influence generation.  We verify this by recording all generate_fn args
    and confirming they are identical across all k calls.
    """
    from harness.passk_probe import _core_probe

    # Oracle that alternates pass/fail — if generate_fn reacted to oracle it would
    # produce different outputs on different calls
    call_count: list[int] = [0]

    def alternating_oracle(repo, nodes, timeout):
        idx = call_count[0]
        call_count[0] += 1
        return set() if idx % 2 == 0 else set(nodes)

    generate_calls: list[tuple] = []

    def recording_generate(subject, name, parent_src, context, gherkin, temp):
        generate_calls.append((subject, name, parent_src, context, gherkin, temp))
        return f"def {name}():\n    pass\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / "pkg").mkdir()
        cf = "pkg/mod.py"
        (repo / cf).write_text("def foo():\n    pass\n", encoding="utf-8")

        task = {
            "sha": "abc12345" * 5,
            "parent": "p" * 40,
            "subject": "test subject",
            "redgreen": ["tests/test_mod.py::test_foo"],
            "code_files": [cf],
            "test_files": ["tests/test_mod.py"],
            "repo": "pkg",
        }
        targets = [(cf, "foo", None)]
        orig = {cf: "def foo():\n    pass\n"}
        gherkins = {(cf, "foo"): "scenarios"}

        _core_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            task=task,
            repo=repo,
            k=4,
            temp=0.8,
            timeout=10,
            generate_fn=recording_generate,
            oracle_fn=alternating_oracle,
        )

    # 1 greedy + 4 samples = 5 generate calls
    assert len(generate_calls) == 5

    # All k-sample calls (indices 1..4) must have the SAME args — oracle output
    # must not have influenced the generate_fn inputs
    sample_calls = generate_calls[1:]  # skip greedy
    subjects = [c[0] for c in sample_calls]
    gherkin_args = [c[4] for c in sample_calls]
    assert len(set(subjects)) == 1, "subject must be identical across samples"
    assert len(set(gherkin_args)) == 1, "gherkin must be identical across samples (oracle must not feed back)"
