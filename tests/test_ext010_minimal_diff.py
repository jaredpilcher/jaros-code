"""EXT-010 REQ-6 regression: multi_file_fix's cumulative candidate loop keeps ANY edit that
strictly reduces the failing-test count, and returns the moment the suite goes all-green. So
a partial-progress "symptom patch" kept early can become REDUNDANT once a later root-cause fix
turns everything green -- both edits stay applied, a non-minimal diff. `_minimize_edits` is the
deterministic, test-gated delta-debugging pass that removes any kept edit not actually necessary
to keep the suite green. This test is offline/no-model: it drives `_minimize_edits` directly
against a real temp-dir repo + real pytest, with the redundant/necessary edits pre-applied (the
exact state multi_file_fix's cumulative loop would leave behind)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.multi_file import _minimize_edits, _snapshot, _run


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def test_minimize_edits_drops_redundant_caller_patch_keeps_root_fix(tmp_path):
    # core.py has the real bug (add subtracts instead of adds).
    core = tmp_path / "core.py"
    _write(core, "def add(a, b):\n    return a - b  # bug: should be a + b\n")

    # helper.py is a CALLER of core.add.
    helper = tmp_path / "helper.py"
    _write(helper, "from core import add\n\n\ndef combine(a, b):\n    return add(a, b)\n")

    test_file = tmp_path / "test_combine.py"
    _write(
        test_file,
        "from helper import combine\n\n\n"
        "def test_combine():\n    assert combine(3, 4) == 7\n",
    )

    # Snapshot the ORIGINAL (buggy) state -- this is what multi_file_fix captures at the very
    # start, before any candidate edit is tried.
    orig = _snapshot(str(tmp_path))

    # Simulate the cumulative loop's history: first a candidate pass on helper.py was tried and
    # KEPT (it left an extra, harmless hunk behind -- an unused helper function -- that does NOT
    # change combine()'s behavior at all; this is the realistic "caller patch that turns out to
    # add nothing of value" case). combine() itself is untouched, so the suite is still RED with
    # only this edit applied (core's real bug is still there) -- this file's "keep" only matters
    # for the diff, not for making the suite pass on its own.
    _write(
        helper,
        "from core import add\n\n\ndef combine(a, b):\n    return add(a, b)\n\n\n"
        "def _unused_helper():\n    return None\n",
    )

    # ...then a LATER pass fixed the real root cause in core.py. Now BOTH edits are applied and
    # the suite is green, but the helper.py hunk is redundant on top of the real fix.
    _write(core, "def add(a, b):\n    return a + b\n")
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok  # green with both edits applied

    kept_paths = [str(helper), str(core)]  # kept in the order multi_file_fix would have kept them
    kept_min, dropped = _minimize_edits(str(tmp_path), "pytest -q", orig, kept_paths)

    assert dropped == ["helper.py"]
    assert [Path(p).name for p in kept_min] == ["core.py"]

    # helper.py must have been reverted to its ORIGINAL (pre-edit) content.
    assert helper.read_text(encoding="utf-8") == orig[str(helper)]
    # core.py (the necessary fix) must still hold the fixed content, not the original buggy one.
    assert "a + b" in core.read_text(encoding="utf-8")

    # Invariant: the repo is still all-green after minimization.
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok


def test_minimize_edits_single_kept_edit_is_a_no_op(tmp_path):
    # Only ONE edit was ever kept -- the common case. Reverting it must fail the suite, so
    # minimization restores it and reports nothing dropped.
    core = tmp_path / "core.py"
    _write(core, "def add(a, b):\n    return a - b  # bug\n")

    test_file = tmp_path / "test_core.py"
    _write(
        test_file,
        "from core import add\n\n\ndef test_add():\n    assert add(3, 4) == 7\n",
    )

    orig = _snapshot(str(tmp_path))

    _write(core, "def add(a, b):\n    return a + b\n")
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok

    kept_min, dropped = _minimize_edits(str(tmp_path), "pytest -q", orig, [str(core)])

    assert dropped == []
    assert kept_min == [str(core)]
    assert "a + b" in core.read_text(encoding="utf-8")

    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok


def test_minimize_edits_never_drops_a_necessary_edit(tmp_path):
    # Two files BOTH genuinely needed: core.py provides the base value, helper.py applies a
    # required transform. Neither is redundant on its own.
    core = tmp_path / "core.py"
    _write(core, "def base(x):\n    return x  # bug: should double\n")

    helper = tmp_path / "helper.py"
    _write(helper, "from core import base\n\n\ndef total(x):\n    return base(x)  # bug: should add 1\n")

    test_file = tmp_path / "test_total.py"
    _write(
        test_file,
        "from helper import total\n\n\ndef test_total():\n    assert total(3) == 7\n",
    )

    orig = _snapshot(str(tmp_path))

    _write(core, "def base(x):\n    return x * 2\n")
    _write(helper, "from core import base\n\n\ndef total(x):\n    return base(x) + 1\n")
    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok

    kept_paths = [str(core), str(helper)]
    kept_min, dropped = _minimize_edits(str(tmp_path), "pytest -q", orig, kept_paths)

    assert dropped == []
    assert sorted(Path(p).name for p in kept_min) == ["core.py", "helper.py"]

    ok, _ = _run(str(tmp_path), "pytest -q")
    assert ok
