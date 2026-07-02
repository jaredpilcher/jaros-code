"""Deterministic import-resolver (EXT-035 REQ-3).

Pure, offline, AST-driven — NO model calls. Fixes the MEASURED cross-module
import-emission gap: a small model references a dependency symbol without
importing it (NameError) or guesses the wrong module name. The deterministic
plane resolves the correct `from <mod> import <name>` line for each name the
module USES but has not bound, when that name is a known export of a
supplied dependency — the model is left to write only the logic body.
"""

from __future__ import annotations

import ast
import builtins

# #EXT-035-REQ-3 Start

_BUILTIN_NAMES = frozenset(dir(builtins))


def _bound_names(tree: ast.Module) -> set[str]:
    """Names bound at module scope: top-level def/class names, top-level
    assignment targets, and names already imported."""
    bound: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, (ast.Assign,)):
            for target in node.targets:
                bound.update(_assign_target_names(target))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            bound.update(_assign_target_names(node.target))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bound.update(_assign_target_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    bound.update(_assign_target_names(item.optional_vars))
    return bound


def _assign_target_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.update(_assign_target_names(elt))
    elif isinstance(target, ast.Starred):
        names.update(_assign_target_names(target.value))
    return names


def _used_names(tree: ast.Module) -> set[str]:
    """All `ast.Name` nodes in Load context anywhere in the module."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return used


def _qualified_module_stems(tree: ast.Module, bound: set[str], dep_stems: set[str]) -> set[str]:
    """Module stems referenced via the qualified form `<stem>.<attr>`, where
    `<stem>` is an unbound `ast.Name` (not defined/imported/builtin) whose id
    matches a supplied dep's module stem — the `codec.encode(...)` case,
    which the bare-name path (`_used_names`) never sees since `encode` there
    is an attribute string, not a `Name` node."""
    stems: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and isinstance(node.value.ctx, ast.Load)
        ):
            stem = node.value.id
            if stem in dep_stems and stem not in bound and stem not in _BUILTIN_NAMES:
                stems.add(stem)
    return stems


def resolve_imports(module_code: str, dep_exports: dict[str, list[str]]) -> str:
    """Inject import lines for names `module_code` USES but has not bound,
    when that name resolves against a supplied dep in `dep_exports`
    (module-stem -> [exported names]). Handles BOTH forms the model may use:

    - bare-name: `encode(...)` with `encode` an unbound name that is an
      exported name of some dep -> injects `from <stem> import <name>`.
    - qualified: `codec.encode(...)` with `codec` an unbound name that is
      itself a dep's module stem -> injects `import <stem>` (never a
      spurious `from <stem> import <attr>`, since the qualified attribute is
      not a bare-name use).

    Conservative: if `module_code` fails to parse, or a used-unbound name
    doesn't resolve against a known dep, it is left alone (never break
    working code). Deterministic: injected lines are deduped and sorted.
    Idempotent: a name/module already imported or bound is skipped, so
    re-running injects nothing new. Does not touch the model's logic body —
    only prepends import lines. Tag `# #EXT-035-REQ-3`.
    """
    try:
        tree = ast.parse(module_code)
    except SyntaxError:
        return module_code

    bound = _bound_names(tree)
    used = _used_names(tree)
    unbound = used - bound - _BUILTIN_NAMES

    to_inject_from: set[tuple[str, str]] = set()
    for name in unbound:
        for stem, exports in dep_exports.items():
            if name in exports:
                to_inject_from.add((stem, name))
                break

    to_inject_import = _qualified_module_stems(tree, bound, set(dep_exports.keys()))

    import_lines: set[str] = set()
    import_lines.update(f"from {stem} import {name}" for stem, name in to_inject_from)
    import_lines.update(f"import {stem}" for stem in to_inject_import)

    if not import_lines:
        return module_code

    return "\n".join(sorted(import_lines)) + "\n" + module_code

# #EXT-035-REQ-3 End
