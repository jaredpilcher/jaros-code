"""Spec-driven (jarify-flow) loop (EXT-009) — deterministic check of the structured flow."""


def test_spec_driven_already_green(tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_m.py").write_text(
        "from m import f\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8")
    from harness.spec_loop import spec_driven_loop
    r = spec_driven_loop("make sure it works", str(tmp_path))
    assert r["solved"] is True and r["flow"] == "already-green"


def test_parse_reqs():
    from harness.spec_loop import _parse_reqs
    reply = ("add: adds two numbers\n"
             "- subtract: subtracts the second from the first\n"
             "1. multiply(a, b): multiplies two numbers\n"
             "this line is prose, no colon-name\n")
    reqs = _parse_reqs(reply)
    names = [n for n, _ in reqs]
    assert names == ["add", "subtract", "multiply"]      # bullet/number/paren stripped to identifiers
    assert ("add", "adds two numbers") in reqs
    assert all(n.isidentifier() for n in names)


def test_extract_signatures():
    from harness.spec_loop import _extract_signatures
    sigs = _extract_signatures("a list module with largest(xs) returning the max, "
                               "smallest(xs) returning the min, and total(xs) returning the sum")
    assert sigs == [("largest", "xs"), ("smallest", "xs"), ("total", "xs")]  # no spurious list_module
    sigs2 = _extract_signatures("add(a, b) that adds and subtract(a, b) that subtracts")
    assert sigs2 == [("add", "a, b"), ("subtract", "a, b")]


def test_plan_preview_build(tmp_path):
    from harness.spec_loop import plan_preview
    out = plan_preview("a module with add(a, b) and subtract(a, b)", str(tmp_path))
    assert "BUILD" in out and "add(a, b)" in out and "subtract(a, b)" in out


def test_plan_preview_fix(tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    (tmp_path / "test_m.py").write_text(
        "from m import f\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8")
    from harness.spec_loop import plan_preview
    assert "FIX flow" in plan_preview("fix it", str(tmp_path))


def test_sanitize_source_strips_stray_brackets():
    """build-hard finding: a correct module + a trailing model artifact ('}}}') failed to parse.
    _sanitize_source repairs it deterministically; no-op on already-valid source."""
    from harness.spec_loop import _sanitize_source
    import ast
    dirty = "def f(x):\n    return x + 1\n}}}\n"
    clean = _sanitize_source(dirty)
    ast.parse(clean)                       # parses now (no exception)
    assert "}}}" not in clean and "return x + 1" in clean
    ok = "def g():\n    return 1\n"
    assert _sanitize_source(ok) == ok      # untouched when already valid


def test_sanitize_source_strips_repl_marker_and_duplicate():
    """class-build finding: a CORRECT class followed by a '>>>FILE' marker + a duplicated body
    failed to parse. _sanitize_source cuts at the first '>>>' artifact, keeping the valid prefix."""
    from harness.spec_loop import _sanitize_source
    import ast
    dirty = ("class Stack:\n    def __init__(self):\n        self.items = []\n"
             "    def push(self, x):\n        self.items.append(x)\n"
             ">>>FILE\n>>>class Stack:\n    def __init__(self):\n        self.items = []\n")
    clean = _sanitize_source(dirty)
    ast.parse(clean)
    assert ">>>" not in clean and "class Stack:" in clean and "def push" in clean


def test_detect_class_routing():
    """OOP: class intents route to the whole-class build; function intents do not (no regression)."""
    from harness.spec_loop import _detect_class
    assert _detect_class("a Stack class with push(x), pop()") == "Stack"
    assert _detect_class("a BankAccount class starting at balance 0") == "BankAccount"
    assert _detect_class("a Rectangle class created with width and height") == "Rectangle"
    assert _detect_class("a math module with add(a, b) and subtract(a, b)") is None
    assert _detect_class("largest(xs) returning the max, total(xs) the sum") is None
