"""harness/dependency_structure.py — EXT-028: Method dependency structure for decomposition.

Deterministic AST analysis of a Python module that maps a target function's
dependencies, guiding decomposition of hard multi-step-repo changes.

Two-plane discipline (Tenet 1): this module is entirely deterministic — no LLM,
no network, no file I/O.  The model consumes the output of `dependency_brief` to
reason about WHERE a change must propagate and in what order, turning a hard
whole-task into a dependency-ordered decomposition.
"""
from __future__ import annotations

import ast
from pathlib import Path

__all__ = ["method_dependencies", "dependency_brief", "cross_file_callers"]

# ── internal helpers ─────────────────────────────────────────────────────────


def _sig(node: ast.FunctionDef | ast.AsyncFunctionDef, src: str) -> str:
    """Return the first (``def …:``) line of a function from its source segment."""
    seg = ast.get_source_segment(src, node)
    if seg:
        return seg.splitlines()[0].strip()
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}(...):"


def _module_state_names(tree: ast.Module) -> set[str]:
    """Names assigned at module level (not inside any function or class)."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _param_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """All parameter names for ``func_node``."""
    a = func_node.args
    names = {arg.arg for arg in a.args + a.posonlyargs + a.kwonlyargs}
    if a.vararg:
        names.add(a.vararg.arg)
    if a.kwarg:
        names.add(a.kwarg.arg)
    return names


def _called_plain_names(node: ast.AST) -> set[str]:
    """Bare (non-method) function names called anywhere within ``node``."""
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            names.add(n.func.id)
    return names


def _state_used(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    mod_state: set[str],
) -> set[str]:
    """Module-level state names actually referenced inside ``func_node``.

    Authoritative: explicit ``global`` declarations.
    Heuristic: bare ``Name`` references to module-level vars that are not
    parameter names (conservative — over-reports rather than under-reports).
    """
    params = _param_names(func_node)
    used: set[str] = set()

    # Explicit global declarations are definitive.
    for n in ast.walk(func_node):
        if isinstance(n, ast.Global):
            for name in n.names:
                if name in mod_state:
                    used.add(name)

    # Bare Name references not shadowed by params.
    for n in ast.walk(func_node):
        if isinstance(n, ast.Name) and n.id in mod_state and n.id not in params:
            used.add(n.id)

    return used


# ── public API ────────────────────────────────────────────────────────────────

# #EXT-028-REQ-1 Start
def method_dependencies(source: str, target_name: str) -> dict:
    """Deterministic AST analysis of a Python MODULE source for ``target_name``.

    Returns:
        {
          "target":                   str,
          "callees":                  [{"name": str, "signature": str}, ...],
          "callers":                  [str, ...],
          "module_state_used":        [str, ...],
          "siblings_sharing_state":   [str, ...],
        }

    ``callees`` — module-level functions the target CALLS (with their ``def``
    signatures).
    ``callers`` — other module-level functions that CALL the target.
    ``module_state_used`` — module-level variable names the target reads or
    writes (including via ``global`` statements).
    ``siblings_sharing_state`` — other functions that touch at least one of the
    same module-level state names and therefore need coordinated change.

    Returns a partial result (all lists empty) on parse errors or when
    ``target_name`` is not found.  Never raises.
    """
    base: dict = {
        "target": target_name,
        "callees": [],
        "callers": [],
        "module_state_used": [],
        "siblings_sharing_state": [],
    }
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return base

    # Collect module-level functions.
    mod_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        n.name: n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    target_node = mod_funcs.get(target_name)
    if target_node is None:
        return base

    mod_state = _module_state_names(tree)

    # Callees: module-level functions the target calls (excluding itself).
    called = _called_plain_names(target_node)
    callees = [
        {"name": name, "signature": _sig(mod_funcs[name], source)}
        for name in sorted(called)
        if name in mod_funcs and name != target_name
    ]

    # Callers: other module-level functions that call the target.
    callers = sorted(
        name
        for name, fn in mod_funcs.items()
        if name != target_name and target_name in _called_plain_names(fn)
    )

    # Module-level state referenced by the target.
    target_state = _state_used(target_node, mod_state)

    # Siblings that share any of the same module-level state.
    siblings_sharing = sorted(
        name
        for name, fn in mod_funcs.items()
        if name != target_name and _state_used(fn, mod_state) & target_state
    )

    return {
        "target": target_name,
        "callees": callees,
        "callers": callers,
        "module_state_used": sorted(target_state),
        "siblings_sharing_state": siblings_sharing,
    }
# #EXT-028-REQ-1 End


# #EXT-028-REQ-2 Start
def dependency_brief(deps: dict) -> str:
    """Render a ``method_dependencies`` result as a decomposition-oriented brief.

    The brief is the artefact that the decomposition / solve step consumes:
    "To change ``{target}``, you may need to coordinate …  Suggested order: …"

    Pure function — no LLM, no I/O, no network.
    """
    target = deps.get("target", "?")
    callees = deps.get("callees", [])
    callers = deps.get("callers", [])
    state = deps.get("module_state_used", [])
    siblings = deps.get("siblings_sharing_state", [])

    callee_names = [c["name"] if isinstance(c, dict) else str(c) for c in callees]
    caller_names = [str(c) for c in callers]

    lines: list[str] = [f"To change `{target}`, you may need to coordinate:"]

    if caller_names:
        lines.append(
            f"  - Callers [{', '.join(caller_names)}] depend on its behavior"
            f" — update them if the interface changes."
        )
    else:
        lines.append("  - Callers: none in this module.")

    if callee_names:
        lines.append(
            f"  - Helpers it uses [{', '.join(callee_names)}]"
            f" — their interface changes propagate into `{target}`."
        )
    else:
        lines.append("  - Helpers: none in this module.")

    if state:
        lines.append(
            f"  - Shared module-level state [{', '.join(state)}]"
            f" — reads/writes shared with other functions."
        )

    if siblings:
        lines.append(
            f"  - Functions sharing the same state [{', '.join(siblings)}]"
            f" — coordinate to avoid diverging assumptions."
        )

    lines.append("")
    lines.append("Suggested change order:")
    step = 1
    if callee_names:
        lines.append(
            f"  {step}. Update helpers first if their interface needs to change:"
            f" {', '.join(callee_names)}."
        )
        step += 1
    lines.append(f"  {step}. Modify `{target}` itself.")
    step += 1
    if caller_names:
        lines.append(
            f"  {step}. Update callers if `{target}`'s interface changed:"
            f" {', '.join(caller_names)}."
        )
        step += 1
    if siblings:
        lines.append(
            f"  {step}. Check siblings sharing state: {', '.join(siblings)}."
        )

    return "\n".join(lines)
# #EXT-028-REQ-2 End


def cross_file_callers(
    repo_root: str, target_module: str, target_name: str
) -> list[dict]:
    """Find callers of ``target_name`` in modules OTHER than ``target_module``.

    Bounded search: scans ``.py`` files under ``repo_root``, skipping standard
    dirs.  Pre-filters by string occurrence before full AST parse (cheap).

    Returns ``[{"caller": func_name, "file": relative_path}, ...]``.
    """
    _SKIP = {".git", "__pycache__", ".venv", "node_modules", ".jaros-data", "datasets"}
    root = Path(repo_root)

    try:
        target_path = Path(target_module)
        if not target_path.is_absolute():
            target_path = root / target_module
        target_path = target_path.resolve()
    except OSError:
        return []

    result: list[dict] = []
    for py_file in root.rglob("*.py"):
        if any(part in _SKIP for part in py_file.parts):
            continue
        try:
            if py_file.resolve() == target_path:
                continue
        except OSError:
            continue
        try:
            src = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Pre-filter: target name must appear as a token somewhere in the file.
        if target_name not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if target_name in _called_plain_names(node):
                try:
                    rel = py_file.relative_to(root).as_posix()
                except ValueError:
                    rel = str(py_file)
                result.append({"caller": node.name, "file": rel})
    return result
