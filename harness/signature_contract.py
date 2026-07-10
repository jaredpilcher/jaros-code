"""Deterministic signature-contract repair (EXT-036 TASK-58, REQ-45).

MEASURED (`.jaros-data/sigcontract_probe.py`, 2026-07-08/09) on the retry/backoff-lib real-system
task, pass@1 0/3: gemma writes a library function with CORRECT LOGIC but DROPS a documented default
parameter -- it emits ``def retry(times, exceptions):`` while the visible build spec documents the
signature in backticks as ``retry(times, exceptions=Exception)``, and the spec's own primary usage
``@retry(times=3)`` then raises ``TypeError: retry() missing 1 required positional argument:
'exceptions'``. This module is the deterministic, AST-only fix for that specific, provably-safe
defect shape -- the analog of the existing import-resolver (EXT-035 REQ-3) / entrypoint-not-listed
(EXT-036 REQ-1) / guard-index (EXT-036 REQ-39) repairs already wired into ``build_system``: a
mechanical pass over the built modules, never a model re-call.

Leak-free (Tenet 3): every default value text originates ONLY in the visible build spec sentence
handed to ``documented_defaults`` -- never a hidden oracle, test, or reference implementation.
Non-degrading: any parse failure, or any transform that would produce an illegal signature (a bare
parameter following a defaulted one), leaves the code BYTE-IDENTICAL -- never raises, never guesses.
"""
# #EXT-036-REQ-45 Start
import ast
import re

_SIG_RE = re.compile(r"`([A-Za-z_]\w*)\(([^`]*?)\)`")


def documented_defaults(spec_text: "str | None") -> "dict[str, dict[str, str]]":
    """Return ``{func_name: {param_name: default_src}}`` for every backtick-quoted
    ``name(params)`` signature in ``spec_text`` that includes at least one ``param=default``.
    Parses the param list with ``ast`` for safety; a signature that doesn't parse as a valid
    Python parameter list is skipped, never raises. Positional AND keyword-only defaults are
    both captured."""
    out: "dict[str, dict[str, str]]" = {}
    if not spec_text:
        return out
    for m in _SIG_RE.finditer(spec_text):
        name, params = m.group(1), m.group(2).strip()
        if "=" not in params:
            continue
        try:
            tree = ast.parse(f"def _f({params}): pass")
        except SyntaxError:
            continue
        if not tree.body or not isinstance(tree.body[0], ast.FunctionDef):
            continue
        fn = tree.body[0]
        defaults: "dict[str, str]" = {}
        args = fn.args.args
        pad = len(args) - len(fn.args.defaults)
        for i, d in enumerate(fn.args.defaults):
            try:
                defaults[args[pad + i].arg] = ast.unparse(d)
            except Exception:
                continue
        for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
            if d is not None:
                try:
                    defaults[a.arg] = ast.unparse(d)
                except Exception:
                    continue
        if defaults:
            out.setdefault(name, {}).update(defaults)
    return out


def repair_signature_defaults(code: "str | None", documented: "dict[str, dict[str, str]]"
                               ) -> "tuple[str, bool, list[str]]":
    """For each top-level ``FunctionDef`` in ``code`` whose name is a key of ``documented``, add
    any documented default the built def is MISSING, ONLY when every parameter positionally
    AFTER it already has (or is also being given, in this same pass) a default -- Python's
    no-non-default-after-default rule. Never removes or alters an existing default. Returns
    ``(new_code, changed, notes)``; on a parse failure (or no documented functions), returns
    ``code`` unchanged with an explanatory note, never raising."""
    if not documented:
        return code or "", False, []
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return code or "", False, ["build code does not parse"]

    changed = False
    notes: "list[str]" = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in documented:
            continue
        want = documented[node.name]
        args = node.args.args
        n_have_default = len(node.args.defaults)
        with_default = set(a.arg for a in args[len(args) - n_have_default:])
        for idx, a in enumerate(args):
            if a.arg not in want or a.arg in with_default:
                continue
            trailing = args[idx + 1:]
            if not all(t.arg in with_default or t.arg in want for t in trailing):
                # inserting this default would leave (or create) a bare parameter after a
                # defaulted one -- an illegal Python signature. Skip, never guess.
                continue
            try:
                default_node = ast.parse(want[a.arg], mode="eval").body
            except SyntaxError:
                continue
            node.args.defaults.append(default_node)
            with_default.add(a.arg)
            changed = True
            notes.append(f"added default {a.arg}={want[a.arg]} to {node.name}()")

    if not changed:
        return code or "", False, notes
    ast.fix_missing_locations(tree)
    try:
        new_code = ast.unparse(tree)
    except Exception:
        return code or "", False, ["repaired AST failed to unparse -- reverted"]
    return new_code, True, notes


def apply_signature_contract(modules: "dict[str, str]", spec_text: "str | None"
                              ) -> "tuple[dict[str, str], list[str]]":
    """Map ``repair_signature_defaults`` across a ``{module_name: code}`` dict using
    signatures documented in ``spec_text``. Returns a NEW dict (never mutates ``modules``)
    plus a flat list of per-module notes. Never raises: any module whose repair fails to
    apply cleanly is left unchanged in the returned dict."""
    result = dict(modules or {})
    notes: "list[str]" = []
    documented = documented_defaults(spec_text)
    if not documented:
        return result, notes
    for name, code in (modules or {}).items():
        try:
            new_code, changed, mod_notes = repair_signature_defaults(code, documented)
        except Exception:
            continue
        if changed:
            result[name] = new_code
            notes.extend(f"{name}: {n}" for n in mod_notes)
    return result, notes
# #EXT-036-REQ-45 End
