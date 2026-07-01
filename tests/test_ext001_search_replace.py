"""EXT-001 / REQ-13 -- code.search_replace: resilient SEARCH/REPLACE execution-plane
tool. Offline, deterministic, no network/Jetson/Docker (real tmp files on disk).

Mirrors the ``_load_tool`` / ``_decision`` conventions of ``test_ext001_tools.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from jaros.core import create_decision

TOOLS_DIR = Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"


def _load_tool(filename: str, classname: str):
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, classname)()


def _decision(dtype: str, payload):
    return create_decision(id=f"t-{dtype}", source="test", type=dtype, payload=payload)


def _tool():
    return _load_tool("search_replace_tool.py", "SearchReplaceTool")


# (a) exact-match tier ------------------------------------------------------

def test_search_replace_exact_tier(tmp_path):
    tool = _tool()
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    before_bytes = len(f.read_text(encoding="utf-8").encode("utf-8"))
    out = tool.execute(_decision("code.search_replace", {
        "path": str(f), "search": "    return 1", "replace": "    return 2",
    }))
    assert out["applied"] is True
    assert out["matchedBy"] == "exact"
    assert out["bytesBefore"] == before_bytes
    assert out["bytesAfter"] == len(f.read_text(encoding="utf-8").encode("utf-8"))
    assert f.read_text(encoding="utf-8") == "def foo():\n    return 2\n"


# (b) rstrip-tolerant tier (trailing-whitespace drift) -----------------------

def test_search_replace_rstrip_tolerant_tier(tmp_path):
    tool = _tool()
    f = tmp_path / "b.py"
    # file has trailing whitespace on the "x = 1" line the model's SEARCH block
    # doesn't reproduce -- the multi-line block prevents an exact substring match
    # so this can only apply via the rstrip-tolerant tier.
    f.write_text("def foo():\n    x = 1  \n    return x\n", encoding="utf-8")
    out = tool.execute(_decision("code.search_replace", {
        "path": str(f),
        "search": "    x = 1\n    return x",
        "replace": "    x = 1\n    return x * 2",
    }))
    assert out["applied"] is True
    assert out["matchedBy"] == "rstrip"
    assert f.read_text(encoding="utf-8") == "def foo():\n    x = 1\n    return x * 2\n"


# (c) difflib line-level fallback (hallucinated surrounding lines) ----------

def test_search_replace_difflib_tier(tmp_path):
    tool = _tool()
    f = tmp_path / "c.py"
    f.write_text(
        "def foo(x):\n"
        "    y = x + 1\n"
        "    return y\n",
        encoding="utf-8",
    )
    # SEARCH hallucinates the def-line prefix ("self.") but the CHANGED line
    # ("    return y" -> "    return y * 2") is present verbatim in the file.
    search = "def foo(self, x):\n    y = x + 1\n    return y"
    replace = "def foo(self, x):\n    y = x + 1\n    return y * 2"
    out = tool.execute(_decision("code.search_replace", {
        "path": str(f), "search": search, "replace": replace,
    }))
    assert out["applied"] is True
    assert out["matchedBy"] == "difflib"
    assert "return y * 2" in f.read_text(encoding="utf-8")


# (d) validate rejects a payload missing search/replace ----------------------

def test_search_replace_validate_rejects_missing_fields():
    tool = _tool()
    assert tool.validate(_decision("code.search_replace", {"path": "x.py"})).ok is False
    assert tool.validate(_decision("code.search_replace", {"path": "x.py", "search": "a"})).ok is False
    assert tool.validate(_decision("code.search_replace", {"search": "a", "replace": "b"})).ok is False


# (e) unmatchable edit raises (no silent no-op) -------------------------------

def test_search_replace_unmatchable_raises(tmp_path):
    tool = _tool()
    f = tmp_path / "e.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        tool.execute(_decision("code.search_replace", {
            "path": str(f), "search": "nonexistent block entirely", "replace": "x",
        }))


# --- safety gate ------------------------------------------------------------

def test_search_replace_refuses_unsafe_replace(tmp_path):
    tool = _tool()
    d = _decision("code.search_replace", {
        "path": "s.py", "search": "x", "replace": "import os\nos.system('rm -rf /')",
    })
    assert tool.validate(d).ok is False
