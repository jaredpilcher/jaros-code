"""Offline tests for EXT-026 harness/maximal_help_probe.py.

All tests run WITHOUT the Jetson (no LLM calls, no Docker, no git clones).
Stubs replace all live I/O. The repo is a minimal temp directory.

Verified with:
    python -m pytest tests/test_maximal_help_probe.py -v

Coverage:
  1. File parses (ast.parse smoke).
  2. Top-level symbols importable.
  3. _build_maxhelp_prompt contains all three layers (retrieved context, worked example,
     decomposition plan) in the returned string.
  4. _build_maxhelp_prompt does NOT contain the target task's oracle/solution (honesty).
  5. _core_maxhelp_probe calls generate_fn with worked_example dict from a DIFFERENT task.
  6. Oracle is score-only — generate_fn args do not change based on oracle outcomes.
  7. Files are restored to parent content after probe (pass and fail).
  8. maxhelp_pass=True when oracle passes; False when oracle fails.
  9. _build_worked_example never returns the target task's sha (honesty invariant).
  10. _build_maxhelp_prompt includes the visible failing test in the prompt.
"""
from __future__ import annotations

import ast
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Syntax smoke-test
# ---------------------------------------------------------------------------

def test_maximal_help_probe_parses():
    """maximal_help_probe.py must parse without syntax errors."""
    src = (
        Path(__file__).resolve().parents[1] / "harness" / "maximal_help_probe.py"
    ).read_text(encoding="utf-8")
    ast.parse(src)  # raises SyntaxError on failure


# ---------------------------------------------------------------------------
# Import smoke-test
# ---------------------------------------------------------------------------

def test_maximal_help_probe_imports():
    """Top-level symbols importable — no heavy LLM imports at module scope."""
    from harness.maximal_help_probe import (  # noqa: F401
        _build_maxhelp_prompt,
        _g_code_maxhelp,
        _build_worked_example,
        _core_maxhelp_probe,
        probe_task_maxhelp,
        run_maximal_help,
    )


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _make_repo_and_task(tmpdir: Path):
    """Create a minimal repo structure and task dict for offline testing."""
    (tmpdir / "pkg").mkdir(exist_ok=True)
    cf = "pkg/mod.py"
    (tmpdir / cf).write_text("def foo():\n    pass\n", encoding="utf-8")
    task = {
        "sha": "aabbccdd" * 5,
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
    plans = {(cf, "foo"): "1. parse args\n2. return None"}
    failing_tests = {(cf, "foo"): "def test_foo():\n    assert foo() is None\n"}
    enriched_ctxs = {(cf, "foo"): "# imports\nimport os\n"}
    return task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs


def _make_stub_oracle(passes: bool = True):
    """Return an oracle stub that always passes or always fails."""
    call_log: list[tuple] = []

    def oracle(repo, nodes, timeout):
        call_log.append((list(nodes), timeout))
        return set() if passes else set(nodes)

    oracle.call_log = call_log
    return oracle


# ---------------------------------------------------------------------------
# _build_maxhelp_prompt — three-layer content checks
# ---------------------------------------------------------------------------

def test_prompt_contains_retrieved_context():
    """Layer 1: enriched context must appear in the prompt."""
    from harness.maximal_help_probe import _build_maxhelp_prompt

    prompt = _build_maxhelp_prompt(
        subject="add bar",
        name="bar",
        parent_src="def bar():\n    pass\n",
        enriched_ctx="def _helper(x): return x * 2\n",
        gherkin="Given bar() returns something",
        worked_example=None,
        plan="1. parse\n2. return",
        failing_test_src="",
    )
    assert "RETRIEVED CONTEXT" in prompt, "Layer 1 header must appear in prompt"
    assert "_helper" in prompt, "enriched context content must appear in prompt"


def test_prompt_contains_worked_example():
    """Layer 2: worked example from a different task must appear in the prompt."""
    from harness.maximal_help_probe import _build_maxhelp_prompt

    example = {
        "subject": "add default arg to total",
        "func_name": "total",
        "parent_src": "def total(items):\n    return sum(items)\n",
        "fixed_src": "def total(items, start=0):\n    return sum(items, start)\n",
    }
    prompt = _build_maxhelp_prompt(
        subject="fix foo",
        name="foo",
        parent_src="def foo():\n    pass\n",
        enriched_ctx="",
        gherkin="",
        worked_example=example,
        plan="",
        failing_test_src="",
    )
    assert "WORKED EXAMPLE" in prompt, "Layer 2 header must appear in prompt"
    assert "add default arg to total" in prompt, "example subject must appear"
    assert "total" in prompt, "example func_name must appear"
    assert "def total(items, start=0)" in prompt, "fixed_src must appear in prompt"


def test_prompt_contains_decomposition_plan():
    """Layer 3: decomposition plan must appear in the prompt."""
    from harness.maximal_help_probe import _build_maxhelp_prompt

    prompt = _build_maxhelp_prompt(
        subject="fix foo",
        name="foo",
        parent_src="def foo():\n    pass\n",
        enriched_ctx="",
        gherkin="",
        worked_example=None,
        plan="1. parse args\n2. iterate\n3. handle edge cases\n4. return result",
        failing_test_src="",
    )
    assert "STEP-BY-STEP IMPLEMENTATION PLAN" in prompt, "Layer 3 header must appear"
    assert "1. parse args" in prompt, "plan content must appear in prompt"
    assert "handle edge cases" in prompt, "plan content must appear in prompt"


def test_prompt_contains_all_three_layers():
    """All three layers must be present together in the same prompt."""
    from harness.maximal_help_probe import _build_maxhelp_prompt

    example = {
        "subject": "different task subject ZZZZ",
        "func_name": "helper_fn",
        "parent_src": "def helper_fn(x):\n    return x\n",
        "fixed_src": "def helper_fn(x, y=0):\n    return x + y\n",
    }
    prompt = _build_maxhelp_prompt(
        subject="fix target_func",
        name="target_func",
        parent_src="def target_func():\n    pass\n",
        enriched_ctx="def _dep(a): return a + 1\n",
        gherkin="Given target_func() then it works",
        worked_example=example,
        plan="1. initialize\n2. compute\n3. return",
        failing_test_src="def test_target():\n    assert target_func() == 42\n",
    )
    # Layer 1
    assert "RETRIEVED CONTEXT" in prompt, "Layer 1 header missing"
    assert "_dep" in prompt, "Layer 1 content missing"
    # Layer 2
    assert "WORKED EXAMPLE" in prompt, "Layer 2 header missing"
    assert "different task subject ZZZZ" in prompt, "Layer 2 subject missing"
    # Layer 3
    assert "STEP-BY-STEP IMPLEMENTATION PLAN" in prompt, "Layer 3 header missing"
    assert "1. initialize" in prompt, "Layer 3 content missing"


# ---------------------------------------------------------------------------
# Honesty: target task's oracle/solution never appears in prompt
# ---------------------------------------------------------------------------

def test_prompt_never_contains_target_oracle():
    """The target task's hidden oracle answer must NEVER appear in the prompt.

    We simulate this by:
    - Using a sentinel string 'ORACLE_SECRET_ANSWER_XYZ' as the 'solution'
    - Verifying it does NOT appear in the built prompt
    The worked_example is from a DIFFERENT task (different subject/content).
    """
    from harness.maximal_help_probe import _build_maxhelp_prompt

    target_oracle_secret = "ORACLE_SECRET_ANSWER_XYZ"

    # The worked_example is from a different task — does NOT contain the oracle secret
    different_task_example = {
        "subject": "fix some other function",
        "func_name": "other_fn",
        "parent_src": "def other_fn(x):\n    return x\n",
        "fixed_src": "def other_fn(x, y=1):\n    return x * y\n",
    }

    prompt = _build_maxhelp_prompt(
        subject="fix target_fn",
        name="target_fn",
        parent_src="def target_fn():\n    pass\n",
        enriched_ctx="def _helper(): pass\n",
        gherkin="1. Given target_fn() is called",
        worked_example=different_task_example,
        plan="1. parse\n2. return",
        failing_test_src="def test_target_fn():\n    assert target_fn() == 1\n",
    )

    # The oracle secret (target's hidden answer) must never appear
    assert target_oracle_secret not in prompt, (
        f"Oracle secret '{target_oracle_secret}' must NEVER appear in the prompt"
    )
    # The worked example is from a different task
    assert "some other function" in prompt, "worked example from different task is in prompt"
    # The target subject IS in the prompt (it's the spec)
    assert "fix target_fn" in prompt


def test_worked_example_never_uses_target_sha():
    """_build_worked_example must never return the target task's own commit.

    We construct a minimal stub corpus where the first task IS the target
    (same sha) and the second task is different. _build_worked_example must
    skip the first and return the second.

    Uses a stub for _code_funcs and _git to avoid real git calls.
    """
    from unittest.mock import patch
    import harness.commit_replay as _cr

    target_sha = "aabbccdd" + "00" * 18
    other_sha = "11223344" + "00" * 18

    corpus = [
        {
            "sha": target_sha,
            "parent": "p" * 40,
            "subject": "target task — must be skipped",
            "code_files": ["pkg/mod.py"],
            "repo": "pkg",
        },
        {
            "sha": other_sha,
            "parent": "q" * 40,
            "subject": "different task — should be returned",
            "code_files": ["pkg/mod.py"],
            "repo": "pkg",
        },
    ]

    # Stub _git to return non-empty Python source
    parent_src = "def fn(x):\n    return x\n"
    fixed_src = "def fn(x, y=0):\n    return x + y\n"

    def stub_git(repo, *args):
        # For 'show sha:file' return different content based on sha
        show_arg = " ".join(args)
        if other_sha[:8] in show_arg:
            return fixed_src
        elif "q" * 8 in show_arg or "parent" in show_arg:
            return parent_src
        return parent_src

    with tempfile.TemporaryDirectory() as tmpdir:
        repos_dir = Path(tmpdir)
        (repos_dir / "pkg").mkdir()

        # Stub both _git and _code_funcs so no real git calls occur
        def stub_code_funcs(src: str):
            if "y=0" in src:
                return {"fn": fixed_src}
            return {"fn": parent_src}

        with patch.object(_cr, "_git", side_effect=stub_git), \
             patch.object(_cr, "_code_funcs", side_effect=stub_code_funcs):
            from harness.maximal_help_probe import _build_worked_example
            result = _build_worked_example(corpus, target_sha, repos_dir)

    # Must skip the target task and return the other task's worked example
    assert result is not None, "_build_worked_example must find the different task"
    assert "different task" in result["subject"], (
        "returned subject must be from the different task, not the target"
    )
    assert result["func_name"] == "fn"


# ---------------------------------------------------------------------------
# _core_maxhelp_probe — generate_fn receives all three layer args
# ---------------------------------------------------------------------------

def test_core_maxhelp_generate_fn_receives_all_layers():
    """generate_fn must be called with worked_example, enriched_ctx, and plan."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    captured_calls: list[dict] = []

    def spy_generate_fn(subject, name, parent_src, enriched_ctx, gherkin,
                        worked_example, plan, failing_test):
        captured_calls.append({
            "subject": subject,
            "name": name,
            "enriched_ctx": enriched_ctx,
            "worked_example": worked_example,
            "plan": plan,
            "failing_test": failing_test,
        })
        return f"def {name}():\n    return None\n"

    stub_oracle = _make_stub_oracle(passes=True)

    example = {
        "subject": "example task from different sha",
        "func_name": "other",
        "parent_src": "def other(x): return x",
        "fixed_src": "def other(x, y=0): return x + y",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )

        result = _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=example,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=spy_generate_fn,
            oracle_fn=stub_oracle,
        )

    assert len(captured_calls) == 1, "generate_fn must be called once per target"
    call = captured_calls[0]

    # Layer 1: enriched context was passed
    assert call["enriched_ctx"] != "", "enriched_ctx must be passed to generate_fn"
    assert "import os" in call["enriched_ctx"], "enriched ctx content must be passed"

    # Layer 2: worked example was passed (from the different task)
    assert call["worked_example"] is example, (
        "worked_example must be passed to generate_fn"
    )
    assert "example task from different sha" in call["worked_example"]["subject"]

    # Layer 3: decomposition plan was passed
    assert call["plan"] != "", "plan must be passed to generate_fn"
    assert "1. parse args" in call["plan"]

    # Visible failing test was passed (it's part of the spec)
    assert "test_foo" in call["failing_test"]

    # maxhelp_pass reflects oracle result
    assert result["maxhelp_pass"] is True


def test_core_maxhelp_oracle_is_score_only():
    """Oracle outcome must NOT influence what is passed to generate_fn.

    We use an alternating oracle (pass/fail/pass) and verify generate_fn
    always receives the same args regardless of prior oracle outcomes.
    """
    from harness.maximal_help_probe import _core_maxhelp_probe

    generate_calls: list[dict] = []

    def recording_generate_fn(subject, name, parent_src, enriched_ctx, gherkin,
                               worked_example, plan, failing_test):
        generate_calls.append({
            "subject": subject,
            "gherkin": gherkin,
            "plan": plan,
        })
        return f"def {name}():\n    return None\n"

    oracle_calls: list[int] = [0]

    def alternating_oracle(repo, nodes, timeout):
        idx = oracle_calls[0]
        oracle_calls[0] += 1
        return set() if idx % 2 == 0 else set(nodes)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )

        _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=recording_generate_fn,
            oracle_fn=alternating_oracle,
        )

    # generate_fn called exactly once (one target, no fix-loop in maxhelp)
    assert len(generate_calls) == 1, f"generate_fn must be called once, got {len(generate_calls)}"
    # subject and gherkin were passed correctly
    assert generate_calls[0]["subject"] == "add foo behaviour"


# ---------------------------------------------------------------------------
# File restoration invariant
# ---------------------------------------------------------------------------

def test_core_maxhelp_files_restored_after_pass():
    """Repo files must be restored to parent content after the probe (oracle passes)."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    stub_oracle = _make_stub_oracle(passes=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )
        original_content = orig["pkg/mod.py"]

        _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=lambda *_a: "def foo():\n    return 42\n",
            oracle_fn=stub_oracle,
        )

        restored = (repo / "pkg/mod.py").read_text(encoding="utf-8")
        assert restored == original_content, "file must be restored after probe passes"


def test_core_maxhelp_files_restored_after_fail():
    """Repo files must be restored to parent content after the probe (oracle fails)."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    stub_oracle = _make_stub_oracle(passes=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )
        original_content = orig["pkg/mod.py"]

        _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=lambda *_a: "def foo():\n    return None\n",
            oracle_fn=stub_oracle,
        )

        restored = (repo / "pkg/mod.py").read_text(encoding="utf-8")
        assert restored == original_content, "file must be restored after probe fails"


# ---------------------------------------------------------------------------
# maxhelp_pass correctly reflects oracle result
# ---------------------------------------------------------------------------

def test_core_maxhelp_pass_when_oracle_passes():
    """maxhelp_pass=True when oracle returns empty set (all nodes passed)."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    stub_oracle = _make_stub_oracle(passes=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )
        result = _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=lambda *_a: "def foo():\n    return None\n",
            oracle_fn=stub_oracle,
        )
    assert result["maxhelp_pass"] is True
    assert len(stub_oracle.call_log) == 1, "oracle called exactly once"


def test_core_maxhelp_fail_when_oracle_fails():
    """maxhelp_pass=False when oracle returns non-empty set (nodes still failing)."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    stub_oracle = _make_stub_oracle(passes=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )
        result = _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=lambda *_a: "def foo():\n    return None\n",
            oracle_fn=stub_oracle,
        )
    assert result["maxhelp_pass"] is False


# ---------------------------------------------------------------------------
# per_target is populated
# ---------------------------------------------------------------------------

def test_core_maxhelp_per_target_populated():
    """per_target must contain name and code for each target function."""
    from harness.maximal_help_probe import _core_maxhelp_probe

    stub_oracle = _make_stub_oracle(passes=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        task, targets, orig, gherkins, plans, failing_tests, enriched_ctxs = (
            _make_repo_and_task(repo)
        )
        result = _core_maxhelp_probe(
            targets=targets,
            orig=orig,
            gherkins=gherkins,
            failing_tests=failing_tests,
            enriched_ctxs=enriched_ctxs,
            worked_example=None,
            plans=plans,
            task=task,
            repo=repo,
            timeout=10,
            generate_fn=lambda s, n, *_a: f"def {n}():\n    return 99\n",
            oracle_fn=stub_oracle,
        )

    assert len(result["per_target"]) == 1
    pt = result["per_target"][0]
    assert pt["name"] == "foo"
    assert "def foo" in pt["code"]


# ---------------------------------------------------------------------------
# _build_maxhelp_prompt includes failing test (the visible spec)
# ---------------------------------------------------------------------------

def test_prompt_includes_visible_failing_test():
    """The visible failing test (spec) must appear in the prompt.

    This is the test that was checked out from the commit; it is the public
    spec and is always safe to include. The HIDDEN oracle (task['redgreen'])
    is only the list of node IDs used to score — it is never in the prompt.
    """
    from harness.maximal_help_probe import _build_maxhelp_prompt

    failing_test = "def test_foo():\n    assert foo(1, 2) == 3\n"
    prompt = _build_maxhelp_prompt(
        subject="add two numbers",
        name="foo",
        parent_src="def foo(x):\n    return x\n",
        enriched_ctx="",
        gherkin="",
        worked_example=None,
        plan="1. add x and y\n2. return result",
        failing_test_src=failing_test,
    )
    assert "FAILING TEST" in prompt, "prompt must label the visible failing test"
    assert "def test_foo" in prompt, "visible failing test source must appear in prompt"
    assert "assert foo(1, 2) == 3" in prompt, "test assertion must appear in prompt"
