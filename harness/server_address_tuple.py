"""Deterministic server-address TUPLE repair (EXT-036 TASK-83, REQ-68).

MEASURED ROOT CAUSE (reproduced locally with the exact traceback, canonical-board
`url-shortener-http-service`): gemma writes correct routing/DB logic but the generated ENTRYPOINT
(``main.py``) calls the stdlib server constructor with a BARE-STRING ``server_address`` and THREE
positional args:

    HTTPServer("", port, _RouteHTTPHandler).serve_forever()

The correct signature is ``HTTPServer(server_address, RequestHandlerClass)`` where
``server_address`` is a ``(host, port)`` TUPLE. Passing ``("", port, handler)`` (3 positional,
``args[0]`` a bare string) makes ``socket.bind("")`` raise::

    TypeError: bind(): AF_INET address must be tuple, not str

so the server never binds and every http check fails. ``harness.port_coercion`` (EXT-036 REQ-50)
does NOT fix this: it only int-wraps a port that is ALREADY inside a tuple
(``(("", port), handler)``); here there is no tuple at all. This is the direct analog of the
already-landed deterministic contract repairs (signature-contract REQ-45, filename-contract REQ-46,
endpoint-shape REQ-53, port-coercion REQ-50): a mechanical AST pass over the built modules, never a
model re-call.

Leak-free (Tenet 3): the fix reads nothing but the module's own AST -- no spec text, oracle, test,
or reference implementation is ever consulted. Non-degrading: wrapping the first two positional
args of a recognized server-constructor call into a tuple is a correct-by-construction rewrite of
an otherwise-broken call shape; an already-correct 2-arg (or tuple-first-arg) call is left
completely untouched (idempotent, byte-identical). Never raises: any parse/unparse failure, or a
module with no recognized broken bind site, leaves the code byte-identical.

MUST run BEFORE ``harness.port_coercion.apply_port_coercion`` so a str-typed port ends up
int-wrapped INSIDE the newly-formed tuple, not left dangling as a bare positional argument.
"""
# #EXT-036-REQ-68 Start
import ast


_SERVER_CTORS = {
    "HTTPServer",
    "ThreadingHTTPServer",
    "TCPServer",
    "ThreadingTCPServer",
}


def _callee_name(func: "ast.expr") -> "str | None":
    """Return the simple (rightmost) name of a call target, e.g. ``HTTPServer`` for both a bare
    ``HTTPServer(...)`` and an attribute-qualified ``socketserver.TCPServer(...)`` /
    ``http.server.HTTPServer(...)``. Never raises."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _ServerAddressTupleTransformer(ast.NodeTransformer):
    """Wraps the first two positional args of a recognized stdlib server-constructor call into a
    single ``(host, port)`` tuple when the call is in the broken bare-string/3-positional-arg
    shape.

    Recognizes calls whose rightmost callee name is a server constructor
    (``HTTPServer``/``ThreadingHTTPServer``/``TCPServer``/``ThreadingTCPServer``, bare or
    attribute-qualified, e.g. ``socketserver.TCPServer``) that have THREE OR MORE positional args
    AND whose first positional arg is NOT already an ``ast.Tuple``/``ast.List`` -- the ambiguous
    or already-correct shapes (fewer than 3 positional args, or an already-tuple/list first arg,
    e.g. the correct 2-arg form or the 3-arg form with a trailing ``bind_and_activate=False``) are
    left strictly alone.

    ``self.changed`` records whether any rewrite actually happened, so the caller can skip
    re-serialization when nothing matched (byte-identical no-op)."""

    def __init__(self) -> None:
        self.changed = False

    def visit_Call(self, node: "ast.Call") -> "ast.AST":
        self.generic_visit(node)
        name = _callee_name(node.func)
        if name in _SERVER_CTORS and len(node.args) >= 3:
            first = node.args[0]
            if not isinstance(first, (ast.Tuple, ast.List)):
                host, port = node.args[0], node.args[1]
                new_tuple = ast.Tuple(elts=[host, port], ctx=ast.Load())
                node.args = [new_tuple] + node.args[2:]
                self.changed = True
        return node


def apply_server_address_tuple_to_code(code: "str | None") -> str:
    """Wrap a broken bare-string/3-positional-arg stdlib server-constructor call's first two
    positional args (host, port) into a single tuple. Never raises: any parse or transform failure
    returns ``code`` unchanged. Idempotent + non-degrading: once wrapped, ``args[0]`` is an
    ``ast.Tuple`` so a second pass is a strict no-op; a module with no recognized broken bind site
    is returned BYTE-IDENTICAL (the AST is only re-serialized when a real change was made, so
    formatting elsewhere is preserved for every untouched module)."""
    if not code:
        return code or ""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    transformer = _ServerAddressTupleTransformer()
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


def apply_server_address_tuple(built: "dict[str, str] | None") -> "dict[str, str]":
    """Map ``apply_server_address_tuple_to_code`` across a ``{module_name: code}`` dict. Returns a
    NEW dict (never mutates ``built``); only modules whose bind-site call actually got rewritten
    differ from the input -- every other module is byte-identical to its input value. Never raises:
    a module whose repair fails to apply cleanly is left unchanged in the returned dict."""
    result: "dict[str, str]" = {}
    for name, code in (built or {}).items():
        try:
            result[name] = apply_server_address_tuple_to_code(code)
        except Exception:
            result[name] = code
    return result
# #EXT-036-REQ-68 End
