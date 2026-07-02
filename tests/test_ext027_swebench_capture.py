"""EXT-027 REQ-4 -- offline tests for the swebench_live ``on_verified`` capture callback.

No live model / Docker / WSL: ``gen_fn`` and ``run_test_fn`` are canned, mirroring the fixture
style in ``tests/test_swebench_live.py``.  Proves the hook fires ONLY at the real-test-verified
moment (never on the self-consistency fallback or the give-up return), is best-effort (a raising
callback never changes the returned diff), and is fully backward-compatible (default ``None``).
"""
# #EXT-027-REQ-4 Start
from harness.swebench_live import solve_gated, solve_with_repair

_ORIG = "class Choices:\n    pass\n"
_WRONG = ("<<<<<<< SEARCH\n    pass\n=======\n"
          "    def __str__(self):\n        return self.value\n>>>>>>> REPLACE\n")
_CORRECT = ("<<<<<<< SEARCH\n    pass\n=======\n"
            "    def __str__(self):\n        return str(self.value)\n>>>>>>> REPLACE\n")


# ---------------------------------------------------------------------------
# solve_gated
# ---------------------------------------------------------------------------


def test_solve_gated_on_verified_fires_with_passing_diff():
    spy = []

    def gen_fn(prompt, t):
        return _WRONG if t == 0.0 else _CORRECT

    def run_test_fn(diff):
        return ("str(self.value)" in diff, "" if "str(self.value)" in diff else "wrong")

    diff = solve_gated(
        issue="cast enum to str", file_path="m.py", original=_ORIG,
        hunk_start=2, gen_fn=gen_fn, run_test_fn=run_test_fn, n=4,
        on_verified=spy.append,
    )
    assert "str(self.value)" in diff
    assert spy == [diff]  # fired exactly once, with the winning (passing) diff


def test_solve_gated_on_verified_does_not_fire_on_self_consistency_fallback():
    spy = []

    def run_test_fn(diff):
        return (False, "still failing")  # no candidate ever passes

    diff = solve_gated(
        issue="x", file_path="m.py", original=_ORIG, hunk_start=2,
        gen_fn=lambda p, t: _WRONG, run_test_fn=run_test_fn, n=4,
        on_verified=spy.append,
    )
    assert diff  # the self-consistency fallback still returns a (unverified) diff
    assert spy == []  # but on_verified must NOT have fired for it


def test_solve_gated_on_verified_does_not_fire_when_nothing_applies():
    spy = []
    diff = solve_gated(
        issue="x", file_path="m.py", original=_ORIG, hunk_start=2,
        gen_fn=lambda p, t: "no search/replace block here",
        run_test_fn=lambda d: (True, ""), n=4,
        on_verified=spy.append,
    )
    assert diff == ""
    assert spy == []


def test_solve_gated_on_verified_raising_does_not_change_returned_diff():
    def gen_fn(prompt, t):
        return _WRONG if t == 0.0 else _CORRECT

    def run_test_fn(diff):
        return ("str(self.value)" in diff, "" if "str(self.value)" in diff else "wrong")

    def boom(diff):
        raise RuntimeError("callback exploded")

    diff = solve_gated(
        issue="cast enum to str", file_path="m.py", original=_ORIG,
        hunk_start=2, gen_fn=gen_fn, run_test_fn=run_test_fn, n=4,
        on_verified=boom,
    )
    assert "str(self.value)" in diff  # raising callback did not break/alter the solve


def test_solve_gated_default_on_verified_none_unaffected():
    def gen_fn(prompt, t):
        return _WRONG if t == 0.0 else _CORRECT

    def run_test_fn(diff):
        return ("str(self.value)" in diff, "" if "str(self.value)" in diff else "wrong")

    with_default = solve_gated(
        issue="cast enum to str", file_path="m.py", original=_ORIG,
        hunk_start=2, gen_fn=gen_fn, run_test_fn=run_test_fn, n=4,
    )
    with_none = solve_gated(
        issue="cast enum to str", file_path="m.py", original=_ORIG,
        hunk_start=2, gen_fn=gen_fn, run_test_fn=run_test_fn, n=4, on_verified=None,
    )
    assert with_default == with_none
    assert "str(self.value)" in with_default


# ---------------------------------------------------------------------------
# solve_with_repair
# ---------------------------------------------------------------------------

_SR_ORIG = (
    "class TypeSerializer:\n"
    "    def serialize(self):\n"
    "        if hasattr(self.value, \"__module__\"):\n"
    "            module = self.value.__module__\n"
    "            return \"%s.%s\" % (module, self.value.__name__), {\"import %s\" % module}\n"
)
_SR_BUG_LINE = 5


def _sr(attr):
    buggy = '            return "%s.%s" % (module, self.value.__name__), {"import %s" % module}'
    return (
        "<<<<<<< SEARCH\n" + buggy + "\n=======\n"
        + buggy.replace("__name__", attr) + "\n>>>>>>> REPLACE\n"
    )


def test_solve_with_repair_on_verified_fires_on_first_try_pass():
    spy = []

    def gen_fn(prompt, t):
        return _sr("__qualname__")

    diff = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=_SR_ORIG,
        hunk_start=_SR_BUG_LINE, gen_fn=gen_fn, run_test_fn=lambda d: (True, ""),
        on_verified=spy.append,
    )
    assert "__qualname__" in diff
    assert spy == [diff]


def test_solve_with_repair_on_verified_fires_after_repair_round_passes():
    spy = []

    def gen_fn(prompt, t):
        return _sr("__qualname__") if "STILL FAIL" in prompt else _sr("__module__")

    def run_test_fn(diff):
        return (True, "") if "__qualname__" in diff else (False, "AssertionError: mismatch")

    diff = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=_SR_ORIG,
        hunk_start=_SR_BUG_LINE, gen_fn=gen_fn, run_test_fn=run_test_fn,
        on_verified=spy.append,
    )
    assert "__qualname__" in diff
    assert spy == [diff]  # fired once, at the repair round that actually passed


def test_solve_with_repair_on_verified_does_not_fire_on_give_up_return():
    spy = []

    def gen_fn(prompt, t):
        return _sr("__module__")  # always the wrong-but-applies edit

    diff = solve_with_repair(
        issue="x", file_path="serializer.py", original=_SR_ORIG, hunk_start=_SR_BUG_LINE,
        gen_fn=gen_fn, run_test_fn=lambda d: (False, "still failing"), max_repairs=2,
        on_verified=spy.append,
    )
    assert diff  # returns the last attempted (unverified) patch
    assert spy == []  # never fired -- nothing ever passed


def test_solve_with_repair_on_verified_raising_does_not_change_returned_diff():
    def gen_fn(prompt, t):
        return _sr("__qualname__")

    def boom(diff):
        raise RuntimeError("callback exploded")

    diff = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=_SR_ORIG,
        hunk_start=_SR_BUG_LINE, gen_fn=gen_fn, run_test_fn=lambda d: (True, ""),
        on_verified=boom,
    )
    assert "__qualname__" in diff  # raising callback did not break/alter the solve


def test_solve_with_repair_default_on_verified_none_unaffected():
    def gen_fn(prompt, t):
        return _sr("__qualname__")

    with_default = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=_SR_ORIG,
        hunk_start=_SR_BUG_LINE, gen_fn=gen_fn, run_test_fn=lambda d: (True, ""),
    )
    with_none = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=_SR_ORIG,
        hunk_start=_SR_BUG_LINE, gen_fn=gen_fn, run_test_fn=lambda d: (True, ""), on_verified=None,
    )
    assert with_default == with_none
    assert "__qualname__" in with_default
# #EXT-027-REQ-4 End
