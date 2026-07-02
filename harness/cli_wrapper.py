"""Deterministic CLI-wrapper synthesizer (EXT-035 REQ-1).

Pure, offline, AST-driven — NO model calls. Productionizes the two-plane
multi-file lever: the deterministic plane synthesizes the mechanical
cross-module wiring (import / arg-marshal / entry-call / print) that a small
model botches free-form, so the model is freed to fill only logic bodies.
"""

from __future__ import annotations

import ast
import os

# #EXT-035-REQ-1 Start

_ARG_MODES = ("ints", "strings", "raw")


def synthesize_cli(module_file: str, entry_func: str, *, arg_mode: str = "ints") -> str:
    """Synthesize a runnable CLI wrapper for `entry_func` defined in `module_file`.

    Parses `module_file` with the `ast` module, confirms `entry_func` is a
    top-level `FunctionDef`, and returns a wrapper string that:
      - imports `entry_func` from the module by name (`from <stem> import <entry_func>`)
      - reads `sys.argv[1:]`
      - marshals the args per `arg_mode` ("ints" -> `[int(a) for a in args]`,
        "strings"/"raw" -> the argv list as-is)
      - calls `entry_func(marshalled)` and prints the result.

    Raises ValueError if `entry_func` is not a top-level function definition
    in `module_file`, or if `arg_mode` is not one of "ints"/"strings"/"raw".
    """
    if arg_mode not in _ARG_MODES:
        raise ValueError(
            f"synthesize_cli: unknown arg_mode {arg_mode!r}; expected one of {_ARG_MODES}"
        )

    with open(module_file, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=module_file)

    found = any(
        isinstance(node, ast.FunctionDef) and node.name == entry_func
        for node in tree.body
    )
    if not found:
        raise ValueError(
            f"synthesize_cli: {entry_func!r} is not a top-level function in {module_file!r}"
        )

    stem = os.path.splitext(os.path.basename(module_file))[0]

    if arg_mode == "ints":
        marshal_lines = (
            "    nums = [int(a) for a in args]\n"
            f"    print({entry_func}(nums))\n"
        )
    else:  # "strings" or "raw" — the argv list as-is
        marshal_lines = f"    print({entry_func}(args))\n"

    wrapper = (
        "import sys\n"
        f"from {stem} import {entry_func}\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    args = sys.argv[1:]\n"
        f"{marshal_lines}"
    )
    return wrapper

# #EXT-035-REQ-1 End
