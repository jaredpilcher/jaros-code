"""EXT-003 REQ-6: scoped (tokenize-based) rename — must not touch comments/docstrings/strings.
Fully deterministic (no model): the rename is tokenize-based and the gate is the real suite."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.refactor import rename_symbol

_TEST_CMD = "python -m pytest -q"


def test_rename_is_scoped_to_identifier_tokens(tmp_path):
    (tmp_path / "shape.py").write_text(
        '"""Docstring mentioning area: the area of a shape."""\n'
        "\n"
        "def area(w, h):\n"
        "    # area of shape\n"
        "    return w * h\n"
        "\n"
        "\n"
        "def areatotal(shapes):\n"
        "    return sum(shapes)\n"
        "\n"
        "\n"
        'DATA = {"area": "area"}\n'
    )
    (tmp_path / "main.py").write_text(
        "from shape import area\n"
        "\n"
        "def total(w, h):\n"
        "    return area(w, h)\n"
    )
    (tmp_path / "test_main.py").write_text(
        "from main import total\n"
        "\n"
        "def test_total():\n"
        "    assert total(2, 3) == 6\n"
    )

    r = rename_symbol(str(tmp_path), "area", "extent", _TEST_CMD)
    assert r["renamed"], r["note"]
    assert r["occurrences"] >= 3     # def area + import area + call area

    shape_src = (tmp_path / "shape.py").read_text()
    main_src = (tmp_path / "main.py").read_text()

    # (a) real identifier occurrences ARE renamed
    assert "def extent(w, h):" in shape_src
    assert "from shape import extent" in main_src
    assert "return extent(w, h)" in main_src

    # (b) comment is UNCHANGED
    assert "# area of shape" in shape_src
    # (c) docstring is UNCHANGED
    assert '"""Docstring mentioning area: the area of a shape."""' in shape_src
    # (d) string/dict-key DATA value is UNCHANGED
    assert 'DATA = {"area": "area"}' in shape_src
    # (e) same-name substring identifier is UNCHANGED (word-token boundary)
    assert "def areatotal(shapes):" in shape_src
    assert "extenttotal" not in shape_src


def test_rename_that_breaks_tests_is_still_reverted(tmp_path):
    # renaming area->extent COLLIDES with the existing extent (two `def extent`; the second
    # shadows), so area's behavior is lost and the suite goes red -> must revert.
    (tmp_path / "mod.py").write_text("def area():\n    return 1\n\n\ndef extent():\n    return 2\n")
    (tmp_path / "test_mod.py").write_text(
        "from mod import area, extent\n\ndef test_both():\n    assert area() == 1\n    assert extent() == 2\n")
    before = (tmp_path / "mod.py").read_text()
    r = rename_symbol(str(tmp_path), "area", "extent", _TEST_CMD)
    assert not r["renamed"] and "reverted" in r["note"]
    assert (tmp_path / "mod.py").read_text() == before    # fully restored
