"""Deterministic spec-demanded filename/entrypoint normalization (EXT-036 TASK-59, REQ-46).

MEASURED via two validated offline prototypes:

- ``.jaros-data/filename_norm_probe.py`` (memoize-lib case, ``accepted=True``): gemma emits
  CORRECT ``memoize(maxsize=128)`` logic but names the file ``test_memoize.py`` instead of the
  spec-demanded ``memoize.py``; the real-systems import oracle does ``import memoize`` ->
  ``ModuleNotFoundError``. Renaming the sole module to the spec-demanded name greens the full
  import oracle.
- ``.jaros-data/entrypoint_norm_probe.py`` (INI cli-exact case, ``accepted=True``, exact stdout
  matched): gemma emits CORRECT logic split across ``config_parser.py`` + ``cli_handler.py``, but
  there is no ``main.py`` and ``cli_handler.py``'s top-level ``main(args)`` has no
  ``if __name__ == '__main__'`` guard, so the cli-exact grader finds no runnable entrypoint. The
  fix: pick the ROOT module (imports a local sibling, imported by no sibling) and rename it to the
  spec-demanded ``main.py``, injecting a ``__main__`` guard that calls ``main(sys.argv[1:])``.

This is the analog of the already-landed deterministic import-resolver (EXT-035 REQ-3),
guard-index repair (EXT-036 REQ-39), and signature-contract repair (EXT-036 REQ-45) already wired
into ``build_system``: a mechanical pass over the built modules, never a model re-call.

Leak-free (Tenet 3): every demanded target filename originates ONLY in the visible build spec text
handed to ``demanded_filenames`` -- never a hidden oracle, test, or reference implementation.
Non-degrading: a no-op (input dict returned unchanged, plus an explanatory note) whenever the
demanded filename is already present, the entrypoint is ambiguous (zero or more than one candidate
root/single module), or the relevant code fails to parse -- never raises. Renaming is SAFE: only a
module imported by NO local sibling is ever renamed, so no sibling's ``import`` statement breaks.
"""
# #EXT-036-REQ-46 Start
import ast
import re

_FNAME_RE = re.compile(r"file named\s+`?([A-Za-z_][\w./-]*\.py)`?", re.IGNORECASE)


def demanded_filenames(spec_text: "str | None") -> "list[str]":
    """Return the filenames the visible spec explicitly demands (e.g. "a file named
    ``memoize.py``" or "a file named main.py"), deduplicated, order-preserving. Leak-free: reads
    only ``spec_text`` -- never a hidden oracle/test."""
    if not spec_text:
        return []
    return list(dict.fromkeys(_FNAME_RE.findall(spec_text)))


def _local_module_names(modules: "dict[str, str]") -> "set[str]":
    return {k[:-3] for k in modules if k.endswith(".py")}


def _imports_local_sibling(code: str, locals_: "set[str]") -> bool:
    """True if ``code`` imports any name in ``locals_`` (a local sibling module's stem), via a
    top-level ``import x`` or ``from x import ...``. Never raises: an unparseable module is
    treated as importing nothing."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in locals_:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in locals_:
                    return True
    return False


def _uninvoked_main(code: str):
    """Return ``(has_main, has_guard, main_def)`` for the top-level ``main`` function def in
    ``code`` (``main_def`` is ``None`` if absent). ``has_guard`` is True if the module already has
    an ``if __name__ == '__main__':`` block. Never raises: unparseable code reports
    ``(False, False, None)``."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, False, None
    main_def = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None
    )
    has_guard = any(
        isinstance(n, ast.If) and "__main__" in ast.dump(n.test) for n in tree.body
    )
    return main_def is not None, has_guard, main_def


def _main_call(main_def: "ast.FunctionDef | None") -> str:
    """Choose the call injected into the ``__main__`` guard: ``main(sys.argv[1:])`` when ``main``
    declares at least one positional parameter, else ``main()``. Inspected via ``ast`` (the actual
    built function's declared arity), never guessed."""
    if main_def is not None and len(main_def.args.args) >= 1:
        return "main(sys.argv[1:])"
    return "main()"


def _resolve_entrypoint(mods: "dict[str, str]", py: "list[str]") -> "str | None":
    """Pick the unique entrypoint module among ``py`` (keys of ``mods``): the single module when
    there is only one, else the unique module that imports a local sibling AND is imported by no
    sibling (the "root"). Returns ``None`` when zero or more than one candidate exists --
    ambiguous, caller must no-op."""
    if len(py) == 1:
        return py[0]
    locals_ = _local_module_names(mods)
    roots = [
        k for k in py if _imports_local_sibling(mods[k], locals_ - {k[:-3]})
    ]
    candidates = []
    for k in roots:
        stem = k[:-3]
        imported_by_sibling = any(
            other != k and _imports_local_sibling(mods[other], {stem}) for other in py
        )
        if not imported_by_sibling:
            candidates.append(k)
    return candidates[0] if len(candidates) == 1 else None


def normalize_entrypoint(modules: "dict[str, str]", spec_text: "str | None"
                          ) -> "tuple[dict[str, str], list[str]]":
    """Rename the spec-demanded entrypoint module into place and, if it defines an uninvoked
    top-level ``main``, inject an ``if __name__ == '__main__':`` guard calling it with the
    arity-appropriate signature. Covers BOTH measured shapes: a single-module rename (memoize) and
    a multi-module root-entrypoint rename + guard injection (INI cli-exact). Processes each
    spec-demanded filename in order against the current state of the dict.

    Never mutates ``modules``. Never raises. A no-op (unchanged dict + explanatory note) whenever
    the demanded filename is already present, the entrypoint is ambiguous, or the candidate
    entrypoint's code fails to parse. Renaming only ever touches a module imported by no local
    sibling, so no sibling's ``import`` breaks."""
    mods = dict(modules or {})
    notes: "list[str]" = []
    demanded = demanded_filenames(spec_text)
    if not demanded:
        return mods, notes
    for want in demanded:
        base = want.split("/")[-1]
        if any(k == want or k.split("/")[-1] == base for k in mods):
            notes.append(f"{want} already present")
            continue
        py = [k for k in mods if k.endswith(".py")]
        if not py:
            notes.append(f"demanded {want} but no .py modules -- skipped")
            continue
        entry = _resolve_entrypoint(mods, py)
        if entry is None:
            notes.append(f"could not resolve a unique entrypoint among {py} -- skipped")
            continue
        try:
            ast.parse(mods[entry])
        except SyntaxError:
            notes.append(f"{entry} does not parse -- skipped")
            continue
        code = mods.pop(entry)
        has_main, has_guard, main_def = _uninvoked_main(code)
        if has_main and not has_guard:
            call = _main_call(main_def)
            code = code.rstrip() + f"\n\n\nif __name__ == '__main__':\n    import sys\n    {call}\n"
            notes.append(f"injected __main__ guard calling {call}")
        mods[want] = code
        notes.append(f"entrypoint {entry} -> {want} (spec-demanded)")
    return mods, notes


def apply_filename_contract(modules: "dict[str, str]", spec_text: "str | None"
                             ) -> "tuple[dict[str, str], list[str]]":
    """Thin wrapper mapping ``normalize_entrypoint`` over the filenames demanded by
    ``spec_text`` (typically one). Returns a NEW dict (never mutates ``modules``) plus a flat
    list of notes. Never raises: any internal failure leaves ``modules`` unchanged."""
    try:
        return normalize_entrypoint(modules, spec_text)
    except Exception:
        return dict(modules or {}), ["apply_filename_contract failed -- no-op"]
# #EXT-036-REQ-46 End
