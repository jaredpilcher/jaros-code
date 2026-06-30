"""Offline tests for harness/swebench_live.py — the productionized SWE-bench solve core.

No Docker / WSL / Jetson: side effects are injected.  The end-to-end test reproduces the
validated django-12125 resolve (__name__ -> __qualname__) with a canned model reply.
"""
from harness.swebench_live import (
    locate_region,
    parse_search_replace,
    apply_search_replace,
    build_solve_prompt,
    solve_instance_live,
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


def test_parse_search_replace_basic():
    txt = "<<<<<<< SEARCH\nold line\n=======\nnew line\n>>>>>>> REPLACE"
    assert parse_search_replace(txt) == ("old line", "new line")


def test_parse_search_replace_strips_think_and_returns_none_when_absent():
    assert parse_search_replace("<think>reasoning here</think>\nno block") is None


def test_apply_search_replace_exact():
    out = apply_search_replace("a\nb\nc\n", "b", "B")
    assert out == "a\nB\nc\n"


def test_apply_search_replace_rstrip_tolerant():
    # SEARCH has trailing spaces the file lacks -> still applies via rstrip-normalised match
    out = apply_search_replace("a\nb\nc\n", "b   ", "B")
    assert out is not None and "B" in out


def test_apply_search_replace_no_match_returns_none():
    assert apply_search_replace("a\nb\nc\n", "zzz", "Z") is None


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


def test_solve_instance_live_returns_empty_when_no_edit_applies():
    diff = solve_instance_live(
        issue="x",
        file_path="f.py",
        original=SERIALIZER,
        hunk_start=BUG_LINE,
        gen_fn=lambda prompt, t: "no search/replace block here",
    )
    assert diff == ""
