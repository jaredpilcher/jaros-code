"""Deterministic PORT int-coercion repair (EXT-036 TASK-63, REQ-50).

MEASURED ROOT CAUSE (diagnosed via code-dump, `scratchpad/saas_crud_diag.out`): the canonical-board
SaaS HTTP-service classes (rest-sqlite-crud CREATE and rest-put MODIFY) both measure 0/3 because
gemma writes FULLY CORRECT service logic -- a real SQLite layer, real routing, a REAL serve loop
(so `harness.http_service_scaffold.has_real_serve_loop` correctly no-ops) -- but reads the port
from the environment as a STRING and passes it UN-COERCED to the server bind site:

    port = os.getenv("PORT")
    with socketserver.TCPServer(("", port), handler) as httpd:   # port is a str

``socketserver``/``http.server`` require an ``int`` port; the un-coerced ``str`` raises
``TypeError: 'str' object cannot be interpreted as an integer`` at bind time, so the service never
binds and every http check fails before a single request is sent -- a build-time gap, not a
request-handling gap. This is the direct analog of the already-landed deterministic
signature-contract (EXT-036 REQ-45), filename-contract (EXT-036 REQ-46), and http.server-scaffold
(EXT-036 REQ-48) repairs: a mechanical AST pass over the built modules, never a model re-call.

Leak-free (Tenet 3): the fix reads nothing but the module's own AST -- no spec text, oracle, test,
or reference implementation is ever consulted. Non-degrading: a port is always numeric, so
``int(<expr>)`` is a no-op on an already-int expression and a correct coercion on a numeric
string -- wrapping is always safe; an already-int-literal or already-``int(...)``-wrapped port
element is left untouched (idempotent, byte-identical). Never raises: any parse/unparse failure, or
a module with no recognized bind site, leaves the code byte-identical.
"""
# #EXT-036-REQ-50 Start
import ast


_SERVER_CTORS = {
    "HTTPServer",
    "ThreadingHTTPServer",
    "TCPServer",
    "ThreadingTCPServer",
}


def _callee_name(func: "ast.expr") -> "str | None":
    """Return the simple (rightmost) name of a call target, e.g. ``TCPServer`` for both a bare
    ``TCPServer(...)`` and an attribute-qualified ``socketserver.TCPServer(...)`` /
    ``http.server.HTTPServer(...)``. Never raises."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_already_int(node: "ast.expr | None") -> bool:
    """True if ``node`` is already an int literal (an ``ast.Constant`` holding an ``int``, never
    a ``bool``) or already an ``int(...)`` call -- the idempotency guard that keeps an
    already-coerced or naturally-int bind site byte-identical."""
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return True
    if isinstance(node, ast.Call) and _callee_name(node.func) == "int":
        return True
    return False


class _PortCoercionTransformer(ast.NodeTransformer):
    """Wraps the PORT element of a recognized stdlib server bind-site tuple in ``int(...)``.

    Recognizes exactly two shapes:
      1. A server constructor call (``HTTPServer``/``ThreadingHTTPServer``/``TCPServer``/
         ``ThreadingTCPServer``, bare or attribute-qualified e.g. ``socketserver.TCPServer``)
         whose FIRST positional arg is a 2-tuple ``(host, port)`` -- wraps the tuple's second
         element.
      2. A ``<sock>.bind((host, port))`` call -- wraps the tuple's second element.

    Never touches anything but the recognized tuple's port element. ``self.changed`` records
    whether any wrap actually happened, so the caller can skip re-serialization when nothing
    matched (byte-identical no-op)."""

    def __init__(self) -> None:
        self.changed = False

    def _maybe_wrap_bind_tuple(self, call: "ast.Call") -> None:
        if not call.args:
            return
        first = call.args[0]
        if not isinstance(first, ast.Tuple) or len(first.elts) != 2:
            return
        port_elt = first.elts[1]
        if _is_already_int(port_elt):
            return
        first.elts[1] = ast.Call(
            func=ast.Name(id="int", ctx=ast.Load()),
            args=[port_elt],
            keywords=[],
        )
        self.changed = True

    def visit_Call(self, node: "ast.Call") -> "ast.AST":
        self.generic_visit(node)
        name = _callee_name(node.func)
        if name in _SERVER_CTORS:
            self._maybe_wrap_bind_tuple(node)
        elif name == "bind" and isinstance(node.func, ast.Attribute):
            self._maybe_wrap_bind_tuple(node)
        return node


def coerce_ports_in_code(code: "str | None") -> str:
    """Wrap the PORT element of any recognized stdlib server bind-site tuple in ``int(...)`` if it
    isn't already an int literal or an ``int(...)`` call. Never raises: any parse or transform
    failure returns ``code`` unchanged. Idempotent + non-degrading: a module with no recognized
    bind site, or one whose port is already coerced/an int literal, is returned BYTE-IDENTICAL
    (the AST is only re-serialized when a real change was made, so formatting elsewhere is
    preserved for every untouched module)."""
    if not code:
        return code or ""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    transformer = _PortCoercionTransformer()
    try:
        new_tree = transformer.visit(tree)
    except Exception:
        return code
    if not transformer.changed:
        return code
    try:
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
    except Exception:
        return code


def apply_port_coercion(modules: "dict[str, str] | None") -> "dict[str, str]":
    """Map ``coerce_ports_in_code`` across a ``{module_name: code}`` dict. Returns a NEW dict
    (never mutates ``modules``); only modules whose bind-site port actually got wrapped differ
    from the input -- every other module is byte-identical to its input value. Never raises: a
    module whose repair fails to apply cleanly is left unchanged in the returned dict."""
    result: "dict[str, str]" = {}
    for name, code in (modules or {}).items():
        try:
            result[name] = coerce_ports_in_code(code)
        except Exception:
            result[name] = code
    return result
# #EXT-036-REQ-50 End
