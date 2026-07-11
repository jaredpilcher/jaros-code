"""EXT-036 REQ-70: deterministic DB/state-INIT-CALL repair for a stdlib ``http.server`` build
that kept its OWN real serve loop.

MEASURED ROOT CAUSE (reproduced locally with the exact traceback, canonical-board
``url-shortener-http-service``): after the REQ-68/REQ-69 server-address-tuple levers, the
built server now BINDS, but on a FRESH database (the oracle's condition --
``serve_and_check_stdlib`` runs in a clean tempdir) the first request crashes::

    File "server.py", do_POST -> self.handler.route('POST', ...)
    File "api.py", route -> self.create_link(url)
    File "database.py", create_link -> cursor.execute("INSERT INTO links ...")
    sqlite3.OperationalError: no such table: links

gemma's ``database.py`` defines a correct ZERO-ARG instance-method init
(``DatabaseManager.initialize_db(self)``) that does ``CREATE TABLE IF NOT EXISTS links (...)``,
but NOTHING ever CALLS it before serving: ``main.py`` -> ``start_server(port)`` (in
``server.py``) -> ``with socketserver.TCPServer(('', int(port)), Handler) as httpd:
httpd.serve_forever()`` -- no init call anywhere on the path to the bind.

``harness.http_service_scaffold`` (REQ-65) already solves the analogous problem for the
SCAFFOLD path -- ``find_init_functions``/``generate_skeleton``/``generate_route_skeleton``
recognize a confident zero-arg TOP-LEVEL init/create-table export and CALL it once before the
generated main binds. But that path only fires when the scaffold actually GENERATES the entry
module; here gemma kept its OWN real serve loop (``has_real_serve_loop`` is true), so the
scaffold correctly NO-OPs and REQ-65's carry-forward logic never runs. This module fills that
gap for the case the scaffold deliberately leaves untouched: it detects a confident zero-arg
DB-init/create-table export -- either a TOP-LEVEL function (reusing
:func:`harness.http_service_scaffold.find_init_functions` unmodified) or a zero-arg-callable
INSTANCE METHOD on a zero-arg-constructible class (the measured shape,
``DatabaseManager().initialize_db()``) -- that is NOT already called anywhere in the built
system, and INJECTS a single call to it as the FIRST statement of the function/block that
contains the server-constructor call, before the server binds.

Guard (correct-by-construction, NON-DEGRADING -- fires ONLY when ALL hold):
  (a) the spec demands a stdlib ``http.server`` service AND a real serve loop already exists
      (:func:`harness.http_service_scaffold.spec_demands_stdlib_http_service` /
      :func:`harness.http_service_scaffold.has_real_serve_loop`) AND no Flask/FastAPI/Starlette
      service was detected (:func:`harness.server_oracle.detect_web_service`) -- an already-
      broken-in-a-DIFFERENT-way build, or one the scaffold repair (REQ-48/65) still owns, is left
      to that other repair.
  (b) EXACTLY ONE confident zero-arg init candidate exists across the whole build (top-level OR
      instance-method) -- more than one, or zero, is ambiguous and a strict no-op.
  (c) EXACTLY ONE recognizable "serve site" exists -- a top-level function, or a top-level
      ``if __name__ == "__main__":`` block, whose body contains BOTH a recognized server-
      constructor call (``HTTPServer``/``ThreadingHTTPServer``/``TCPServer``/
      ``ThreadingTCPServer``, bare or attribute-qualified) and a ``.serve_forever(`` call.
  (d) the candidate's name (the class, for an instance method; the function itself, for a
      top-level candidate) is already resolvable in the serve-site module's own scope (defined
      there, or already imported via ``from <module> import <name>``) -- NO import is ever
      added; an unresolvable name is a strict no-op.
  (e) the candidate is NOT already called ANYWHERE in the built module set (idempotent -- if
      gemma already calls it, this is a no-op).

Any ambiguity in (b)/(c), or a failed guard in (d)/(e), or no real serve loop, or a framework
service, or a non-web spec -> byte-identical NO-OP. Never raises: any parse/transform/unparse
failure leaves the module set unmodified.

Leak-free (Tenet 3): reads only the built modules' own AST plus the spec-driven detection
already proven in ``http_service_scaffold`` -- never an oracle/test/reference implementation.
"""
# #EXT-036-REQ-70 Start
from __future__ import annotations

import ast

from harness.http_service_scaffold import (
    _INIT_FUNC_NAME_RE,
    _init_all_defaulted,
    _is_main_guard_if,
    find_init_functions,
    has_real_serve_loop,
    spec_demands_stdlib_http_service,
)
from harness.server_address_tuple import _SERVER_CTORS, _callee_name
from harness.server_oracle import detect_web_service


def _zero_required_method_args(func_node: "ast.FunctionDef") -> bool:
    """True when ``func_node`` (an instance method, ``self`` at ``args.args[0]``) can be called
    with zero arguments beyond ``self`` -- mirrors
    :func:`harness.http_service_scaffold._init_all_defaulted`'s logic. Never raises (assumes a
    well-formed ``ast.FunctionDef``, guarded by the caller)."""
    n_params = len(func_node.args.args) - 1  # drop `self`
    n_defaults = len(func_node.args.defaults)
    required = max(0, n_params - n_defaults)
    kwonly_required = sum(1 for d in (func_node.args.kw_defaults or []) if d is None)
    return required == 0 and kwonly_required == 0


def find_instance_init_methods(modules: "dict[str, str] | None") -> "list[dict]":
    """Best-effort, NEVER-RAISE AST scan of ``{filename: source}`` module SOURCES for a
    confident, zero-arg-callable INSTANCE METHOD (name matching
    :data:`harness.http_service_scaffold._INIT_FUNC_NAME_RE`) defined on a class whose own
    ``__init__`` is zero-arg-constructible
    (:func:`harness.http_service_scaffold._init_all_defaulted`) -- the measured
    ``DatabaseManager.initialize_db(self)`` shape. Only TOP-LEVEL classes are scanned (a nested
    class is ignored, matching the sibling finders' top-level-only discipline).

    Returns candidates in MODULE ORDER, then top-to-bottom source order, as
    ``{"module": <stem>, "class": <name>, "callable": <name>}`` dicts. Empty list on no match or
    any malformed input. Never raises."""
    candidates: "list[dict]" = []
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return candidates
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            tree = ast.parse(str(code))
        except (SyntaxError, TypeError, ValueError):
            continue
        stem = str(name)[:-3]
        try:
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or not _init_all_defaulted(node):
                    continue
                for meth in node.body:
                    if isinstance(meth, ast.FunctionDef) and _INIT_FUNC_NAME_RE.match(meth.name):
                        if meth.args.args and _zero_required_method_args(meth):
                            candidates.append(
                                {"module": stem, "class": node.name, "callable": meth.name}
                            )
        except Exception:
            continue
    return candidates


def _contains_call(node: "ast.AST", predicate) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and predicate(n):
            return True
    return False


def _is_server_ctor_call(call: "ast.Call") -> bool:
    return _callee_name(call.func) in _SERVER_CTORS


def _is_serve_forever_call(call: "ast.Call") -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == "serve_forever"


def find_serve_sites(modules: "dict[str, str] | None") -> "list[dict]":
    """Best-effort, NEVER-RAISE AST scan for the "serve site" -- a TOP-LEVEL function, or a
    top-level ``if __name__ == "__main__":`` block, whose body contains BOTH a recognized
    server-constructor call and a ``.serve_forever(`` call (the block a DB/state-init call must
    run before, REQ-70). A nested function/if is not scanned (top-level-only, matching the
    sibling finders' discipline -- the measured shape, ``def start_server(port): ...``, is
    already top-level).

    Returns candidates in MODULE ORDER as ``{"module": <stem>, "kind": "function"|"if_main",
    "name": <func name>|None}`` dicts. Empty list on no match or any malformed input. Never
    raises."""
    sites: "list[dict]" = []
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return sites
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            tree = ast.parse(str(code))
        except (SyntaxError, TypeError, ValueError):
            continue
        stem = str(name)[:-3]
        try:
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    if _contains_call(node, _is_server_ctor_call) and _contains_call(node, _is_serve_forever_call):
                        sites.append({"module": stem, "kind": "function", "name": node.name})
                elif isinstance(node, ast.If) and _is_main_guard_if(node):
                    if _contains_call(node, _is_server_ctor_call) and _contains_call(node, _is_serve_forever_call):
                        sites.append({"module": stem, "kind": "if_main", "name": None})
        except Exception:
            continue
    return sites


def _name_available(code: "str | None", target: "str | None") -> bool:
    """True when ``target`` is a genuine top-level name already in scope in module source
    ``code``: a top-level ``class``/``def`` with that name, or a name brought in via a top-level
    ``from <module> import <target>[ as <target>]``. NEVER adds an import -- only reports
    whether one is already present. Never raises."""
    if not code or not target:
        return False
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    try:
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == target:
                return True
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if (alias.asname or alias.name) == target:
                        return True
    except Exception:
        return False
    return False


def _already_called_anywhere(modules: "dict[str, str] | None", callable_name: "str | None") -> bool:
    """True when ANY module in ``modules`` already contains a call to ``callable_name`` -- either
    a bare call (``callable_name()``) or an attribute call (``<anything>.callable_name()``).
    Deliberately over-inclusive (any match anywhere counts, not just on the serve path) --
    idempotency must never risk a double-init; a false-positive here only ever means "leave a
    build we're not sure about untouched," never a wrong action. Never raises."""
    if not callable_name:
        return False
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return False
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            tree = ast.parse(str(code))
        except (SyntaxError, TypeError, ValueError):
            continue
        try:
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                func = n.func
                if isinstance(func, ast.Name) and func.id == callable_name:
                    return True
                if isinstance(func, ast.Attribute) and func.attr == callable_name:
                    return True
        except Exception:
            continue
    return False


class _InitCallInjector(ast.NodeTransformer):
    """Prepends a single deterministic init-call statement to the FIRST recognized serve site
    (function body, or top-level ``if __name__ == "__main__":`` body) matching ``site``.
    ``self.changed`` records whether the injection actually happened. Only the FIRST matching
    site is ever touched (there is exactly one by the caller's own uniqueness guard)."""

    def __init__(self, site: dict, call_stmt: "ast.stmt") -> None:
        self.site = site
        self.call_stmt = call_stmt
        self.changed = False

    def visit_FunctionDef(self, node: "ast.FunctionDef") -> "ast.AST":
        self.generic_visit(node)
        if not self.changed and self.site.get("kind") == "function" and node.name == self.site.get("name"):
            node.body = [self.call_stmt] + list(node.body)
            self.changed = True
        return node

    def visit_If(self, node: "ast.If") -> "ast.AST":
        self.generic_visit(node)
        if not self.changed and self.site.get("kind") == "if_main" and _is_main_guard_if(node):
            node.body = [self.call_stmt] + list(node.body)
            self.changed = True
        return node


def _build_call_stmt(candidate: dict) -> "ast.stmt":
    """Build the AST for the injected init call: ``ClassName().method()`` for an instance-method
    candidate (``candidate["class"]`` set), or ``function_name()`` for a top-level-function
    candidate (``candidate["class"]`` is ``None``)."""
    callable_name = candidate["callable"]
    class_name = candidate.get("class")
    if class_name:
        func = ast.Attribute(
            value=ast.Call(func=ast.Name(id=class_name, ctx=ast.Load()), args=[], keywords=[]),
            attr=callable_name,
            ctx=ast.Load(),
        )
    else:
        func = ast.Name(id=callable_name, ctx=ast.Load())
    call = ast.Call(func=func, args=[], keywords=[])
    return ast.Expr(value=call)


def _candidate_label(candidate: dict) -> str:
    if candidate.get("class"):
        return f"{candidate['class']}().{candidate['callable']}()"
    return f"{candidate['callable']}()"


def apply_db_init_call(modules: "dict[str, str]", spec_text: "str | None",
                        *, llm=None) -> "tuple[dict[str, str], list[str]]":
    """The public, never-raising repair (REQ-70): fires ONLY when ``spec_text`` demands a stdlib
    ``http.server`` service AND a real serve loop already exists (the case
    ``harness.http_service_scaffold.apply_http_service_scaffold`` deliberately leaves as a no-op)
    AND no Flask/FastAPI/Starlette service was detected.

    Detects a SINGLE confident zero-arg DB/state-init export (top-level function OR
    zero-arg-callable instance method on a zero-arg-constructible class) not already called
    anywhere, and a SINGLE recognizable serve site (a function or top-level ``if __name__ ==
    "__main__":`` block containing both a server-constructor call and ``.serve_forever(``), and
    -- only when the candidate's name is already resolvable (no import ever added) in the serve
    site's own module -- injects one call to it as that site's FIRST statement, before the bind.

    Returns a NEW dict (never mutates ``modules``) plus a list of explanatory notes. Never
    raises -- any internal failure leaves ``modules`` unchanged. ``llm`` is accepted for call-site
    parity with the sibling repairs in the deterministic-repair chain but is unused -- this repair
    is purely mechanical (no model re-call)."""
    try:
        mods = dict(modules or {})
        notes: "list[str]" = []

        if not spec_demands_stdlib_http_service(spec_text):
            return mods, notes
        if not mods:
            return mods, notes

        try:
            if detect_web_service(mods):
                notes.append("a Flask/FastAPI/Starlette service was detected -- db-init-call repair not applicable")
                return mods, notes
        except Exception:
            pass

        if not has_real_serve_loop(mods):
            notes.append("no real serve loop -- not applicable (handled by the http-service scaffold repair)")
            return mods, notes

        instance_candidates = [
            {"module": c["module"], "class": c["class"], "callable": c["callable"]}
            for c in find_instance_init_methods(mods)
        ]
        toplevel_candidates = [
            {"module": c["module"], "class": None, "callable": c["callable"]}
            for c in find_init_functions(mods)
        ]
        all_candidates = instance_candidates + toplevel_candidates
        if len(all_candidates) != 1:
            notes.append(f"{len(all_candidates)} init candidate(s) found -- ambiguous, no-op")
            return mods, notes
        candidate = all_candidates[0]

        sites = find_serve_sites(mods)
        if len(sites) != 1:
            notes.append(f"{len(sites)} serve site(s) found -- ambiguous, no-op")
            return mods, notes
        site = sites[0]

        serve_name = f"{site['module']}.py"
        serve_code = mods.get(serve_name)
        if not serve_code:
            notes.append(f"serve module {serve_name} not found -- no-op")
            return mods, notes

        if _already_called_anywhere(mods, candidate["callable"]):
            notes.append(f"{_candidate_label(candidate)} already called somewhere -- idempotent no-op")
            return mods, notes

        target_name = candidate["class"] or candidate["callable"]
        if not _name_available(serve_code, target_name):
            notes.append(f"{target_name!r} not resolvable in {serve_name} without adding an import -- no-op")
            return mods, notes

        try:
            tree = ast.parse(serve_code)
        except SyntaxError as exc:
            notes.append(f"{serve_name} failed to parse -- no-op: {exc}")
            return mods, notes

        call_stmt = _build_call_stmt(candidate)
        injector = _InitCallInjector(site, call_stmt)
        try:
            new_tree = injector.visit(tree)
        except Exception:
            notes.append("injection transform failed -- no-op")
            return mods, notes
        if not injector.changed:
            notes.append("serve site not found for injection -- no-op")
            return mods, notes
        try:
            ast.fix_missing_locations(new_tree)
            new_code = ast.unparse(new_tree)
        except Exception:
            notes.append("re-serialization failed -- no-op")
            return mods, notes

        mods[serve_name] = new_code
        notes.append(f"injected {_candidate_label(candidate)} before the server bind in {serve_name}")
        return mods, notes
    except Exception as exc:
        try:
            fallback = dict(modules or {})
        except (TypeError, ValueError):
            fallback = {}
        return fallback, [f"apply_db_init_call failed -- no-op: {exc}"]
# #EXT-036-REQ-70 End
