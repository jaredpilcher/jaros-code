"""Deterministic code-quality ADVISORY signal for model-generated systems (EXT-037 / REQ-8).

**What this answers (owner's open question, 2026-07-04):** "are we checking the actual code
it's writing for quality?" — before this module, honestly NO. ``harness.secure_exec.scan_code``
(REQ-7) already gates DANGEROUS operations (subprocess/dynamic-exec/destructive-fs/egress) and
correctly REFUSES a build on a real violation. This module is the complementary, much softer
signal: ordinary code-QUALITY smells (bare excepts, swallowed exceptions, mutable default args,
star imports, overly-long/overly-complex/deeply-nested functions) that are never dangerous
enough to refuse a build over, but are worth surfacing to a caller/reader.

**PURE STDLIB.** Uses only :mod:`ast` — no ``ruff``/``radon``/``pyflakes`` or any other
third-party dependency (none of those are installed in this environment; this module is
deliberately self-contained so the quality signal is always available, deterministic, and
two-plane-pure, exactly like ``harness.secure_exec.scan_code`` before it). The AST-walk style
(never raise, unparseable source becomes a note not a crash, ``{filename: code}`` or a bare
code string both accepted) deliberately mirrors ``harness/secure_exec.py``'s house pattern.

**ADVISORY ONLY — this NEVER gates a build.** :class:`QualityReport`'s ``ok`` field is
informational: ``True`` unless a *critical* smell fires (today: a bare ``except:`` or an
``except Exception: pass`` swallow — the two patterns that actively HIDE bugs/errors, as
opposed to the merely-stylistic smells below). No caller may use ``ok``/this report to
change ``done``, refuse a build, or alter behavior for anyone who ignores the field — a
working-but-smelly generated system stays exactly as done/shipped as before this module
existed. See ``harness/system_builder.py::build_system`` for the (additive-only) wiring.

Detectors are intentionally CONSERVATIVE (no false-positive storms): unused-import detection
is skipped entirely, since it cannot be done reliably from a single module's own AST (a name
may be re-exported, used only via ``globals()``/``getattr``, etc.) — better to omit a detector
than to false-positive on it.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

# #EXT-037-REQ-8 Start

# Smell categories whose presence flips QualityReport.ok to False -- the two patterns that
# actively HIDE a bug/error rather than merely being a style smell. Every other category is
# purely informational (never affects `ok`).
CRITICAL_SMELL_CATEGORIES = {"bare_except", "swallowed_exception"}

LONG_FUNCTION_LINES = 80
HIGH_COMPLEXITY_THRESHOLD = 15
DEEP_NESTING_THRESHOLD = 5


@dataclass
class QualityReport:
    """Advisory-only code-quality signal. See module docstring: ``ok`` MUST NOT gate a build."""

    ok: bool
    max_complexity: int = 0
    worst_function: "str | None" = None
    smells: list = field(default_factory=list)
    per_file: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Per-function metrics: McCabe cyclomatic complexity, line length, max nesting depth.
# --------------------------------------------------------------------------------------------

_SCOPE_BOUNDARY_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_MATCH_CASE_TYPE = getattr(ast, "match_case", None)  # ast.match_case only exists on 3.10+


def _walk_own_scope(node):
    """Yield every descendant of ``node``, never descending into a nested function/lambda's OWN
    body -- that nested function's complexity/nesting is measured independently when the outer
    module-level scan reaches its own ``FunctionDef``/``AsyncFunctionDef`` node, so counting it
    again here would double-count its decision points into the OUTER function's score."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_BOUNDARY_TYPES):
            continue
        yield child
        yield from _walk_own_scope(child)


def _function_complexity(node) -> int:
    """McCabe cyclomatic complexity = 1 + count of decision points in the function's OWN scope:
    If/For/AsyncFor/While/ExceptHandler/With-items/BoolOp-extra-values/IfExp/comprehension-if/
    assert/match-case (nested function/lambda bodies excluded -- see :func:`_walk_own_scope`)."""
    complexity = 1
    for child in _walk_own_scope(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)):
            complexity += 1
        elif isinstance(child, ast.withitem):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # a BoolOp with N values has N-1 "extra" branch points (a and b and c == 2 extra).
            complexity += max(len(child.values) - 1, 0)
        elif isinstance(child, ast.comprehension):
            complexity += len(child.ifs)
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif _MATCH_CASE_TYPE is not None and isinstance(child, _MATCH_CASE_TYPE):
            complexity += 1
    return complexity


def _function_length(node) -> int:
    """Line count of the function, inclusive of its ``def`` line."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return 0
    return max(end - start + 1, 0)


_NESTING_NODE_TYPES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


def _max_nesting_depth(node) -> int:
    """Max nesting depth of compound blocks (If/For/While/Try/With, including elif chains, which
    the parser represents as a nested ``If`` inside the ``orelse``) within this function's own
    scope -- 0 means no nested control-flow block at all. Never descends into a nested
    function/lambda's own body (its depth is measured independently)."""

    def _depth(n, cur):
        best = cur
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPE_BOUNDARY_TYPES):
                continue
            nxt = cur + 1 if isinstance(child, _NESTING_NODE_TYPES) else cur
            best = max(best, _depth(child, nxt))
        return best

    return _depth(node, 0)


# --------------------------------------------------------------------------------------------
# Structural smells: conservative, no false-positive storms.
# --------------------------------------------------------------------------------------------


def _is_mutable_literal(node) -> bool:
    return isinstance(node, (ast.List, ast.Dict, ast.Set))


def _scan_smells(tree: ast.AST, filename: str, smells: list) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                smells.append({
                    "category": "bare_except",
                    "detail": "bare `except:` catches everything, including KeyboardInterrupt/SystemExit",
                    "lineno": getattr(node, "lineno", None), "file": filename,
                })
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                body = node.body or []
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    smells.append({
                        "category": "swallowed_exception",
                        "detail": "`except Exception: pass` silently swallows every error",
                        "lineno": getattr(node, "lineno", None), "file": filename,
                    })
        elif isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                smells.append({
                    "category": "star_import",
                    "detail": f"from {node.module or '?'} import * pollutes the namespace",
                    "lineno": getattr(node, "lineno", None), "file": filename,
                })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + list(node.args.kw_defaults)
            for d in defaults:
                if d is not None and _is_mutable_literal(d):
                    smells.append({
                        "category": "mutable_default_arg",
                        "detail": f"mutable default argument in `{node.name}` (shared across calls)",
                        "lineno": getattr(node, "lineno", None), "file": filename,
                    })


def assess_quality(sources) -> QualityReport:
    """AST-scan ``sources`` (a single code string, or ``{filename: code}``) and compute a
    deterministic, ADVISORY code-quality signal. Never raises -- unparseable source is recorded
    as a note and simply skipped, never a crash.

    ``ok`` is advisory only (see module docstring): it is ``True`` unless a *critical* smell
    (``bare_except``/``swallowed_exception``) fires. It MUST NOT be used to gate a build.
    """
    smells: list = []
    per_file: dict = {}
    notes: list = []
    max_complexity = 0
    worst_function: "str | None" = None

    try:
        if isinstance(sources, str):
            file_map = {"<string>": sources}
        elif isinstance(sources, dict):
            file_map = sources
        else:
            return QualityReport(
                ok=True,
                notes=[f"assess_quality requires a str or dict, got {type(sources)!r}"],
            )

        for filename, code in file_map.items():
            file_functions: list = []
            if not isinstance(code, str):
                notes.append(f"{filename}: skipped non-string source")
                continue
            try:
                tree = ast.parse(code, filename=filename)
            except SyntaxError as exc:
                notes.append(f"{filename}: unparseable source, skipped ({exc})")
                continue
            except Exception as exc:  # pragma: no cover - never raise on garbage input
                notes.append(f"{filename}: scan failed, skipped ({exc})")
                continue

            _scan_smells(tree, filename, smells)

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                cc = _function_complexity(node)
                length = _function_length(node)
                depth = _max_nesting_depth(node)
                file_functions.append({
                    "name": node.name, "complexity": cc, "length": length,
                    "max_nesting": depth, "lineno": getattr(node, "lineno", None),
                })
                qualified = f"{filename}:{node.name}"
                if cc > max_complexity:
                    max_complexity = cc
                    worst_function = qualified
                if length > LONG_FUNCTION_LINES:
                    smells.append({
                        "category": "long_function",
                        "detail": f"`{node.name}` is {length} lines (> {LONG_FUNCTION_LINES})",
                        "lineno": node.lineno, "file": filename,
                    })
                if cc > HIGH_COMPLEXITY_THRESHOLD:
                    smells.append({
                        "category": "high_complexity",
                        "detail": f"`{node.name}` has cyclomatic complexity {cc} (> {HIGH_COMPLEXITY_THRESHOLD})",
                        "lineno": node.lineno, "file": filename,
                    })
                if depth > DEEP_NESTING_THRESHOLD:
                    smells.append({
                        "category": "deep_nesting",
                        "detail": f"`{node.name}` nests {depth} levels deep (> {DEEP_NESTING_THRESHOLD})",
                        "lineno": node.lineno, "file": filename,
                    })

            per_file[filename] = {"functions": file_functions}

        critical = [s for s in smells if s.get("category") in CRITICAL_SMELL_CATEGORIES]
        ok = len(critical) == 0
        return QualityReport(
            ok=ok, max_complexity=max_complexity, worst_function=worst_function,
            smells=smells, per_file=per_file, notes=notes,
        )
    except Exception as exc:  # never raise -- advisory signal, not a gate
        return QualityReport(ok=True, notes=[f"assess_quality failed unexpectedly: {exc}"])
# #EXT-037-REQ-8 End
