"""Offline tests for the deterministic import-resolver (EXT-035 REQ-3).

NO model calls — pure AST. Covers the three acceptance-criteria cases plus
the build_from_intent wiring helper that derives dep_exports from deps.
"""

# #EXT-035-REQ-3 Start

from harness.import_wiring import resolve_imports
from harness.intent_loop import _derive_dep_exports


def test_injects_missing_import_and_is_idempotent():
    code = "def pack(items):\n    return '|'.join(encode(i) for i in items)\n"
    dep_exports = {"codec": ["encode"]}

    out = resolve_imports(code, dep_exports)

    assert "from codec import encode" in out
    assert "def pack" in out

    # Idempotent: running it again with the same deps injects nothing new.
    out2 = resolve_imports(out, dep_exports)
    assert out2 == out


def test_already_correct_import_is_unchanged():
    code = (
        "from codec import encode\n"
        "def pack(items):\n"
        "    return '|'.join(encode(i) for i in items)\n"
    )
    dep_exports = {"codec": ["encode"]}

    out = resolve_imports(code, dep_exports)

    assert out == code
    # No duplicate import line injected.
    assert out.count("from codec import encode") == 1


def test_unrelated_undefined_name_not_injected():
    code = "def pack(items):\n    return frobnicate(items)\n"
    dep_exports = {"codec": ["encode"]}

    out = resolve_imports(code, dep_exports)

    assert out == code
    assert "import" not in out


def test_derive_dep_exports_from_ast():
    deps = {
        "codec.py": "def encode(x):\n    return x\n\n\ndef decode(x):\n    return x\n",
        "helpers.py": "class Thing:\n    pass\n",
    }

    exports = _derive_dep_exports(deps)

    assert exports == {"codec": ["encode", "decode"], "helpers": ["Thing"]}


def test_injects_import_for_qualified_module_reference():
    code = "def pack(items):\n    return '|'.join(codec.encode(i) for i in items)\n"
    dep_exports = {"codec": ["encode"]}

    out = resolve_imports(code, dep_exports)

    assert "import codec" in out
    assert "def pack" in out
    # Only the module import is needed for the qualified form — no spurious
    # bare-name import, since `encode` itself is never used as a bare name.
    assert "from codec import" not in out

    # Idempotent: running it again with the same deps injects nothing new.
    out2 = resolve_imports(out, dep_exports)
    assert out2 == out


def test_derive_dep_exports_wires_into_resolve_imports():
    # Simulates the build_from_intent wiring point: derive dep_exports from
    # deps sources, then use it to resolve a missing cross-module import.
    deps = {"codec.py": "def encode(x):\n    return x\n"}
    generated_code = "def pack(items):\n    return [encode(i) for i in items]\n"

    fixed = resolve_imports(generated_code, _derive_dep_exports(deps))

    assert "from codec import encode" in fixed
    assert "def pack" in fixed

# #EXT-035-REQ-3 End
