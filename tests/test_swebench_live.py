"""Offline tests for harness/swebench_live.py — the productionized SWE-bench solve core.

No Docker / WSL / Jetson: side effects are injected.  The end-to-end test reproduces the
validated django-12125 resolve (__name__ -> __qualname__) with a canned model reply.
"""
import importlib.util
import os
import sys

from harness.swebench_live import (
    locate_region,
    locate_target_line,
    locate_from_patch,
    locate_from_traceback,
    locate_from_coverage,
    locate_target_line_traced,
    parse_search_replace,
    apply_search_replace,
    build_solve_prompt,
    solve_instance_live,
    build_repair_prompt,
    solve_with_repair,
    solve_gated,
    solve_from_failure,
)

# django-11964-shaped: three `pass` lines, the target is the middle one (the Choices class).
_MULTIPASS = (
    "class Meta:\n"          # 1
    "    pass\n"             # 2  pass #1 (wrong)
    "\n"                     # 3
    "class Choices:\n"       # 4
    "    '''docs'''\n"       # 5
    "    pass\n"             # 6  pass #2 — the TARGET
    "\n"                     # 7
    "class Other:\n"         # 8
    "    pass\n"             # 9  pass #3
)

_BUGGY = '                return "%s.%s" % (module, self.value.__name__), {"import %s" % module}'
def _sr(replacement_attr):
    return (
        "<<<<<<< SEARCH\n" + _BUGGY + "\n=======\n"
        + _BUGGY.replace("__name__", replacement_attr) + "\n>>>>>>> REPLACE\n"
    )

# A django-12125-shaped fixture: TypeSerializer.serialize with the buggy __name__ line.
SERIALIZER = (
    "import builtins\n"
    "\n"
    "class TypeSerializer:\n"
    "    def serialize(self):\n"
    "        special_cases = []\n"
    "        for case, string, imports in special_cases:\n"
    "            if case is self.value:\n"
    "                return string, set(imports)\n"
    "        if hasattr(self.value, \"__module__\"):\n"
    "            module = self.value.__module__\n"
    "            if module == builtins.__name__:\n"
    "                return self.value.__name__, set()\n"
    "            else:\n"
    "                return \"%s.%s\" % (module, self.value.__name__), {\"import %s\" % module}\n"
    "\n"
    "def other():\n"
    "    return 1\n"
)

BUG_LINE = 14  # 1-based line of the `return "%s.%s" % (module, self.value.__name__)` statement


def test_locate_region_finds_enclosing_method():
    start, end = locate_region(SERIALIZER, BUG_LINE)
    region = "\n".join(SERIALIZER.split("\n")[start:end])
    assert "def serialize(self):" in region
    assert "self.value.__name__" in region
    # must stop before the next top-level def
    assert "def other()" not in region


def test_locate_target_line_unique_anchor():
    assert locate_target_line(_MULTIPASS, ["class Choices:"]) == 4


def test_locate_target_line_ambiguous_uses_hint():
    # generic anchor `pass` occurs 3x; hint near the Choices class -> pick line 6, not line 2
    assert locate_target_line(_MULTIPASS, ["pass"], hint_line=6) == 6
    # without a hint, the ambiguous anchor takes the first occurrence
    assert locate_target_line(_MULTIPASS, ["pass"]) == 2


def test_locate_target_line_fallback_to_hint_when_no_match():
    assert locate_target_line(_MULTIPASS, ["nonexistent line"], hint_line=5) == 5
    assert locate_target_line(_MULTIPASS, ["nonexistent"]) == 1  # no hint -> 1, never None


def test_locate_target_line_prefers_earlier_anchors():
    # a unique later anchor is only used if the earlier ones miss
    assert locate_target_line(_MULTIPASS, ["nope", "class Other:"]) == 8


def test_locate_from_patch_disambiguates_generic_anchor():
    # a unified diff replacing the Choices class's `pass`; @@ -5 hint disambiguates the 3 `pass`
    patch = (
        "--- a/enums.py\n+++ b/enums.py\n@@ -5,2 +5,3 @@ class Choices:\n"
        "     '''docs'''\n-    pass\n+    def __str__(self):\n+        return str(self.value)\n"
    )
    assert locate_from_patch(_MULTIPASS, patch) == 6


_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/testbed/tests/runtests.py", line 20, in run\n'
    "    result = suite()\n"
    '  File "/testbed/django/db/models/query.py", line 1044, in distinct\n'
    "    clone.query.add_distinct_fields(*field_names)\n"
    '  File "/testbed/django/db/models/query.py", line 1138, in add_distinct_fields\n'
    "    raise TypeError(...)\n"
    "TypeError: boom\n"
)


def test_locate_from_traceback_deepest_frame_in_target():
    # two frames in query.py -> return the DEEPEST (last) one, where the error actually is
    assert locate_from_traceback(_TRACEBACK, "django/db/models/query.py") == 1138


def test_locate_from_traceback_other_file():
    assert locate_from_traceback(_TRACEBACK, "tests/runtests.py") == 20


def test_locate_from_traceback_none_when_file_absent():
    assert locate_from_traceback(_TRACEBACK, "django/db/models/fields.py") is None
    assert locate_from_traceback("", "x.py") is None


# #EXT-013-REQ-9 Start
_COVERAGE_MODULE_SRC = (
    "def buggy(x):\n"        # 1
    "    y = x + 1\n"        # 2  executed
    "    z = y * 2\n"        # 3  executed
    "    return z\n"         # 4  executed
    "\n"                     # 5
    "\n"                     # 6
    "def unrelated(x):\n"    # 7
    "    a = x - 1\n"        # 8  NOT executed
    "    return a\n"         # 9  NOT executed
)


def _write_and_import(tmp_path, name, src):
    path = os.path.join(str(tmp_path), name + ".py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, path


def test_locate_from_coverage_executed_lines_in_buggy_not_unrelated(tmp_path):
    mod, path = _write_and_import(tmp_path, "cov_target_mod", _COVERAGE_MODULE_SRC)

    def run_fn():
        mod.buggy(3)

    executed = locate_from_coverage(run_fn, path)
    # lines 2,3,4 (inside buggy) executed; lines 7,8,9 (inside unrelated) never called
    assert {2, 3, 4}.issubset(set(executed))
    assert not ({8, 9} & set(executed))


def test_locate_from_coverage_matches_by_basename_and_survives_raise(tmp_path):
    mod, path = _write_and_import(tmp_path, "cov_target_mod2", _COVERAGE_MODULE_SRC)

    def run_fn():
        mod.buggy(3)
        raise AssertionError("simulated failing test")

    # target_file passed as just the basename -> still matches the absolute temp path frame
    executed = locate_from_coverage(run_fn, os.path.basename(path))
    assert {2, 3, 4}.issubset(set(executed))


def test_locate_from_coverage_restores_prior_trace(tmp_path):
    mod, path = _write_and_import(tmp_path, "cov_target_mod3", _COVERAGE_MODULE_SRC)
    prev = sys.gettrace()
    locate_from_coverage(lambda: mod.buggy(1), path)
    assert sys.gettrace() is prev


_TRACED_FILE = (
    "class A:\n"       # 1
    "    pass\n"       # 2  identical anchor text, NOT executed
    "\n"
    "class B:\n"       # 4
    "    pass\n"       # 5  identical anchor text, executed -> should win
)


def test_locate_target_line_traced_prefers_executed_anchor():
    line = locate_target_line_traced(_TRACED_FILE, ["pass"], executed_lines=[5])
    assert line == 5


def test_locate_target_line_traced_falls_back_when_no_intersection():
    # executed_lines has no overlap with any anchor hit -> behaves like locate_target_line
    line = locate_target_line_traced(_TRACED_FILE, ["pass"], executed_lines=[99], hint_line=4)
    assert line == locate_target_line(_TRACED_FILE, ["pass"], hint_line=4)


def test_locate_target_line_traced_empty_executed_falls_back_to_content_match():
    line = locate_target_line_traced(_TRACED_FILE, ["class B"], executed_lines=[])
    assert line == locate_target_line(_TRACED_FILE, ["class B"])
    assert line == 4
# #EXT-013-REQ-9 End


def test_parse_search_replace_basic():
    txt = "<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE"
    assert parse_search_replace(txt) == ("old line", "new line")


def test_parse_search_replace_strips_think_and_returns_none_when_absent():
    assert parse_search_replace("<think>reasoning here</think>\nno block") is None


def test_parse_search_replace_fallback_missing_divider():
    # some models omit the ======= divider (measured: django-11049) — still recover the edit
    txt = "<<<<<<< SEARCH\nold line\n>>>>>>> REPLACE\nnew line"
    assert parse_search_replace(txt) == ("old line", "new line")


def test_parse_search_replace_strips_wrapping_code_fence():
    # measured (django-11964): qwen wraps the SEARCH/REPLACE block CONTENT in a ```python fence,
    # so the search text can never match the source verbatim and a CORRECT fix is dropped.
    # The parser must strip a leading ```lang line and trailing ``` line from each block.
    txt = (
        "<<<<<<< SEARCH\n```python\n    pass\n```\n=======\n"
        "```python\n    def __str__(self):\n        return str(self.value)\n```\n>>>>>>> REPLACE"
    )
    search, replace = parse_search_replace(txt)
    assert search == "    pass"
    assert replace == "    def __str__(self):\n        return str(self.value)"


def test_parse_search_replace_unfenced_block_unchanged():
    # a normal (unfenced) block must be untouched by the fence-strip
    txt = "<<<<<<< SEARCH\n    x = 1\n=======\n    x = 2\n>>>>>>> REPLACE"
    assert parse_search_replace(txt) == ("    x = 1", "    x = 2")


def test_apply_search_replace_exact():
    out = apply_search_replace("a\nb\nc\n", "b", "B")
    assert out == "a\nB\nc\n"


def test_apply_search_replace_rstrip_tolerant():
    # SEARCH has trailing spaces the file lacks -> still applies via rstrip-normalised match
    out = apply_search_replace("a\nb\nc\n", "b   ", "B")
    assert out is not None and "B" in out


def test_apply_search_replace_no_match_returns_none():
    assert apply_search_replace("a\nb\nc\n", "zzz", "Z") is None


def test_apply_search_replace_line_level_fallback():
    # block doesn't match (model hallucinated a `self.` prefix) but the CHANGED line is right
    # and present verbatim in the file -> line-level fallback applies just that edit.
    orig = "class F:\n    default_error_messages = {\n        'x': 'old format str',\n    }\n"
    search = "    self.default_error_messages = {\n        'x': 'old format str',\n    }"
    replace = "    self.default_error_messages = {\n        'x': 'new format str',\n    }"
    out = apply_search_replace(orig, search, replace)
    assert out is not None and "new format str" in out and "old format str" not in out


def test_apply_search_replace_noop_returns_none():
    assert apply_search_replace("a\nb\n", "b", "b") is None


def test_build_solve_prompt_contains_issue_and_format():
    p = build_solve_prompt("the bug", "x/y.py", "def f(): pass")
    assert "the bug" in p and "x/y.py" in p and "<<<<<<< SEARCH" in p


def test_solve_instance_live_resolves_django12125_shape():
    # Canned model: emit the correct __name__ -> __qualname__ search/replace edit.
    sr = (
        "<<<<<<< SEARCH\n"
        "                return \"%s.%s\" % (module, self.value.__name__), {\"import %s\" % module}\n"
        "=======\n"
        "                return \"%s.%s\" % (module, self.value.__qualname__), {\"import %s\" % module}\n"
        ">>>>>>> REPLACE\n"
    )
    diff = solve_instance_live(
        issue="makemigrations produces incorrect path for inner classes",
        file_path="django/db/migrations/serializer.py",
        original=SERIALIZER,
        hunk_start=BUG_LINE,
        gen_fn=lambda prompt, t: sr,
    )
    assert diff, "expected a non-empty patch"
    assert "-                return \"%s.%s\" % (module, self.value.__name__)" in diff
    assert "+                return \"%s.%s\" % (module, self.value.__qualname__)" in diff
    # clean diff: no doubled blank lines (the make_unified_diff bug we fixed)
    assert "\n\n\n" not in diff


def test_solve_gated_test_selects_correct_over_wrong_applicable():
    # django-11964 shape: the model emits BOTH a wrong-but-applicable edit (return self.value) and
    # the correct one (return str(self.value)); first-applicable would pick the wrong one, but the
    # test-gate must select the candidate that PASSES.
    orig = "class Choices:\n    pass\n"
    wrong = ("<<<<<<< SEARCH\n    pass\n=======\n"
             "    def __str__(self):\n        return self.value\n>>>>>>> REPLACE\n")
    correct = ("<<<<<<< SEARCH\n    pass\n=======\n"
               "    def __str__(self):\n        return str(self.value)\n>>>>>>> REPLACE\n")

    def gen_fn(prompt, t):
        return wrong if t == 0.0 else correct

    def run_test_fn(diff):
        return ("str(self.value)" in diff, "" if "str(self.value)" in diff else "wrong")

    diff = solve_gated(issue="cast enum to str", file_path="m.py", original=orig,
                       hunk_start=2, gen_fn=gen_fn, run_test_fn=run_test_fn, n=4)
    assert "str(self.value)" in diff, "test-gate should have selected the correct variant"


def test_solve_gated_falls_back_to_first_applicable_when_none_pass():
    orig = "class Choices:\n    pass\n"
    edit = ("<<<<<<< SEARCH\n    pass\n=======\n"
            "    def __str__(self):\n        return self.value\n>>>>>>> REPLACE\n")
    calls = {"n": 0}

    def run_test_fn(diff):
        calls["n"] += 1
        return (False, "still failing")

    diff = solve_gated(issue="x", file_path="m.py", original=orig, hunk_start=2,
                       gen_fn=lambda p, t: edit, run_test_fn=run_test_fn, n=4)
    assert diff and "return self.value" in diff  # fell back to the (only) applicable diff
    assert calls["n"] >= 1  # it did try the test-gate


def test_solve_instance_live_returns_empty_when_no_edit_applies():
    diff = solve_instance_live(
        issue="x",
        file_path="f.py",
        original=SERIALIZER,
        hunk_start=BUG_LINE,
        gen_fn=lambda prompt, t: "no search/replace block here",
    )
    assert diff == ""


def test_build_repair_prompt_includes_failure_and_prev():
    p = build_repair_prompt("issue", "f.py", "region", "PREV_PATCH_TEXT", "AssertionError: boom")
    assert "STILL FAIL" in p and "PREV_PATCH_TEXT" in p and "AssertionError: boom" in p


def test_solve_with_repair_passes_first_try_no_repair():
    calls = {"n": 0}
    def gen_fn(prompt, t):
        calls["n"] += 1
        return _sr("__qualname__")
    diff = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=SERIALIZER,
        hunk_start=BUG_LINE, gen_fn=gen_fn, run_test_fn=lambda d: (True, ""),
    )
    assert "__qualname__" in diff
    assert calls["n"] == 1  # solved on first try, no repair calls


def test_solve_with_repair_fixes_after_test_failure():
    # solve emits a WRONG edit (__module__) that applies but fails tests; repair emits the right one.
    def gen_fn(prompt, t):
        return _sr("__qualname__") if "STILL FAIL" in prompt else _sr("__module__")
    def run_test_fn(diff):
        return (True, "") if "__qualname__" in diff else (False, "AssertionError: got Inner want Outer.Inner")
    diff = solve_with_repair(
        issue="inner class path", file_path="serializer.py", original=SERIALIZER,
        hunk_start=BUG_LINE, gen_fn=gen_fn, run_test_fn=run_test_fn,
    )
    assert "__qualname__" in diff  # the repair round corrected it
    assert "__module__" not in diff


def test_solve_from_failure_localizes_from_traceback_and_solves():
    # gold-free: WHERE comes from the traceback (line 14 of the serializer), FIX from the model
    tb = ('Traceback:\n  File "django/db/migrations/serializer.py", line 14, in serialize\n'
          "    return ...\n")
    sr = (
        "<<<<<<< SEARCH\n"
        "                return \"%s.%s\" % (module, self.value.__name__), {\"import %s\" % module}\n"
        "=======\n"
        "                return \"%s.%s\" % (module, self.value.__qualname__), {\"import %s\" % module}\n"
        ">>>>>>> REPLACE\n"
    )
    diff = solve_from_failure(
        file_text=SERIALIZER, traceback=tb,
        target_file="django/db/migrations/serializer.py", gen_fn=lambda p, t: sr,
    )
    assert diff and "__qualname__" in diff and "-" in diff


def test_solve_from_failure_empty_when_traceback_misses_file():
    diff = solve_from_failure(
        file_text=SERIALIZER, traceback='Traceback:\n  File "other.py", line 3, in x\n',
        target_file="serializer.py", gen_fn=lambda p, t: "irrelevant",
    )
    assert diff == ""


def test_solve_with_repair_returns_last_when_never_passes():
    def gen_fn(prompt, t):
        return _sr("__module__")  # always the wrong-but-applies edit
    diff = solve_with_repair(
        issue="x", file_path="serializer.py", original=SERIALIZER, hunk_start=BUG_LINE,
        gen_fn=gen_fn, run_test_fn=lambda d: (False, "still failing"), max_repairs=2,
    )
    assert diff  # returns the last attempted patch (non-empty), not a false success
    assert "__module__" in diff
