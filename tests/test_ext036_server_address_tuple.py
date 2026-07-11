"""Offline tests for EXT-036 REQ-68: deterministic server-address TUPLE repair.

No model/Jetson call anywhere in this file. The exact MEASURED broken shape (reproduced locally
with the exact traceback, canonical-board `url-shortener-http-service`) -- a bare-string
`server_address` passed as THREE positional args, e.g. `HTTPServer("", port,
_RouteHTTPHandler)` -- is reconstructed and proven repaired via AST inspection (never requiring a
live socket bind in this file).
"""

# #EXT-036-REQ-68 Start
import ast

from harness.port_coercion import apply_port_coercion
from harness.server_address_tuple import (
    apply_server_address_tuple,
    apply_server_address_tuple_to_code,
)

# gemma's ACTUAL measured shape: `HTTPServer("", port, Handler)` -- bare-string server_address,
# three positional args -- raises `TypeError: bind(): AF_INET address must be tuple, not str`.
HTTPSERVER_BARE_STRING_MAIN_PY = '''
from http.server import HTTPServer, BaseHTTPRequestHandler


class _RouteHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = 8000
    HTTPServer("", port, _RouteHTTPHandler).serve_forever()
'''

# Composed-with-port-coercion shape: the server_address is bare-string AND the port itself is a
# str pulled from the environment -- both repairs must cooperate to make this genuinely bindable.
HTTPSERVER_BARE_STRING_STR_PORT_PY = '''
import os
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    pass


if __name__ == "__main__":
    port = os.getenv("PORT")
    HTTPServer("", port, Handler).serve_forever()
'''

ATTRIBUTE_QUALIFIED_TCPSERVER_PY = '''
import socketserver


class Handler(socketserver.BaseRequestHandler):
    pass


if __name__ == "__main__":
    port = 9000
    socketserver.TCPServer("", port, Handler).serve_forever()
'''

# --- no-op / already-correct shapes ---

ALREADY_CORRECT_TCPSERVER_PY = '''
import socketserver


class Handler(socketserver.BaseRequestHandler):
    pass


with socketserver.TCPServer(("", 8000), Handler) as httpd:
    httpd.serve_forever()
'''

NON_SERVER_CALL_PY = '''
def foo(a, b, c):
    return a, b, c


foo("", 8000, "bar")
'''

BIND_AND_ACTIVATE_TUPLE_FIRST_PY = '''
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    pass


HTTPServer(("", 8000), Handler, False).serve_forever()
'''

TWO_POSITIONAL_ARG_PY = '''
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    pass


addr = ("", 8000)
HTTPServer(addr, Handler).serve_forever()
'''

NO_BIND_SITE_PY = '''
def add(x, y):
    return x + y
'''


def _server_ctor_call(tree: "ast.AST") -> "ast.Call | None":
    """Find the FIRST server-constructor `ast.Call` node in `tree` (rightmost callee name in the
    recognized set). Helper for AST-shape assertions below."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in {"HTTPServer", "ThreadingHTTPServer", "TCPServer", "ThreadingTCPServer"}:
                return node
    return None


class TestExactReproducedDefect:
    """(1) the EXACT measured broken shape -- HTTPServer("", port, Handler) -- is repaired so the
    first positional arg becomes a 2-tuple and the call has 2 positional args total."""

    def test_bare_string_three_positional_args_repaired(self):
        repaired = apply_server_address_tuple_to_code(HTTPSERVER_BARE_STRING_MAIN_PY)
        assert repaired != HTTPSERVER_BARE_STRING_MAIN_PY
        compile(repaired, "<main.py>", "exec")  # genuinely compiles

        tree = ast.parse(repaired)
        call = _server_ctor_call(tree)
        assert call is not None
        assert len(call.args) == 2
        assert isinstance(call.args[0], ast.Tuple)
        assert len(call.args[0].elts) == 2

    def test_unparsed_text_contains_expected_tuple_wrap(self):
        repaired = apply_server_address_tuple_to_code(HTTPSERVER_BARE_STRING_MAIN_PY)
        assert "HTTPServer(('', port)" in repaired


class TestComposeWithPortCoercion:
    """(2) after apply_server_address_tuple THEN apply_port_coercion, a bare-str server_address
    AND a bare-str env-sourced port both end up correctly repaired -- the port int-wrapped INSIDE
    the newly-formed tuple."""

    def test_composed_repair_wraps_tuple_then_int_coerces_port(self):
        step1 = apply_server_address_tuple_to_code(HTTPSERVER_BARE_STRING_STR_PORT_PY)
        assert step1 != HTTPSERVER_BARE_STRING_STR_PORT_PY

        from harness.port_coercion import coerce_ports_in_code
        step2 = coerce_ports_in_code(step1)
        compile(step2, "<main.py>", "exec")

        tree = ast.parse(step2)
        call = _server_ctor_call(tree)
        assert call is not None
        assert len(call.args) == 2
        assert isinstance(call.args[0], ast.Tuple)
        port_elt = call.args[0].elts[1]
        assert isinstance(port_elt, ast.Call)
        assert isinstance(port_elt.func, ast.Name) and port_elt.func.id == "int"

    def test_apply_functions_compose_over_a_modules_dict(self):
        modules = {"main.py": HTTPSERVER_BARE_STRING_STR_PORT_PY}
        step1 = apply_server_address_tuple(modules)
        step2 = apply_port_coercion(step1)
        assert step2["main.py"] != modules["main.py"]
        compile(step2["main.py"], "<main.py>", "exec")
        assert "int(" in step2["main.py"]


class TestIdempotent:
    """(3) applying twice equals applying once."""

    def test_idempotent_on_the_reproduced_defect(self):
        once = apply_server_address_tuple_to_code(HTTPSERVER_BARE_STRING_MAIN_PY)
        twice = apply_server_address_tuple_to_code(once)
        assert once == twice

    def test_idempotent_on_attribute_qualified_variant(self):
        once = apply_server_address_tuple_to_code(ATTRIBUTE_QUALIFIED_TCPSERVER_PY)
        twice = apply_server_address_tuple_to_code(once)
        assert once == twice


class TestNoOpByteIdentical:
    """(4) already-correct / ambiguous shapes are left strictly alone (byte-identical)."""

    def test_already_correct_tcpserver_is_byte_identical(self):
        assert apply_server_address_tuple_to_code(ALREADY_CORRECT_TCPSERVER_PY) == \
            ALREADY_CORRECT_TCPSERVER_PY

    def test_non_server_call_is_byte_identical(self):
        assert apply_server_address_tuple_to_code(NON_SERVER_CALL_PY) == NON_SERVER_CALL_PY

    def test_bind_and_activate_tuple_first_is_byte_identical(self):
        assert apply_server_address_tuple_to_code(BIND_AND_ACTIVATE_TUPLE_FIRST_PY) == \
            BIND_AND_ACTIVATE_TUPLE_FIRST_PY

    def test_two_positional_args_is_byte_identical(self):
        assert apply_server_address_tuple_to_code(TWO_POSITIONAL_ARG_PY) == TWO_POSITIONAL_ARG_PY

    def test_no_bind_site_is_byte_identical(self):
        assert apply_server_address_tuple_to_code(NO_BIND_SITE_PY) == NO_BIND_SITE_PY


class TestNeverRaises:
    """(5) never raises on unparseable/garbage input."""

    def test_never_raises_on_garbage(self):
        assert apply_server_address_tuple_to_code(None) == ""
        assert apply_server_address_tuple_to_code("") == ""
        assert apply_server_address_tuple_to_code("def f(:\n") == "def f(:\n"
        assert apply_server_address_tuple_to_code("   not python !! @#$") == "   not python !! @#$"

    def test_apply_server_address_tuple_never_raises_on_garbage(self):
        assert apply_server_address_tuple(None) == {}
        assert apply_server_address_tuple({}) == {}
        assert apply_server_address_tuple({"a.py": None}) == {"a.py": ""}
        assert apply_server_address_tuple({"broken.py": "def f(:\n"}) == {"broken.py": "def f(:\n"}


class TestAttributeQualified:
    """(6) attribute-qualified socketserver.TCPServer("", port, H) is also repaired."""

    def test_attribute_qualified_tcpserver_is_repaired(self):
        repaired = apply_server_address_tuple_to_code(ATTRIBUTE_QUALIFIED_TCPSERVER_PY)
        assert repaired != ATTRIBUTE_QUALIFIED_TCPSERVER_PY
        compile(repaired, "<main.py>", "exec")
        tree = ast.parse(repaired)
        call = _server_ctor_call(tree)
        assert call is not None
        assert len(call.args) == 2
        assert isinstance(call.args[0], ast.Tuple)


class TestApplyOverModules:
    """apply_server_address_tuple over a multi-module dict only changes the offending module,
    never mutates the input."""

    def test_only_offending_module_changes(self):
        modules = {
            "main.py": HTTPSERVER_BARE_STRING_MAIN_PY,
            "helpers.py": NO_BIND_SITE_PY,
            "already_ok.py": ALREADY_CORRECT_TCPSERVER_PY,
        }
        result = apply_server_address_tuple(modules)
        assert result["main.py"] != modules["main.py"]
        assert result["helpers.py"] == modules["helpers.py"]
        assert result["already_ok.py"] == modules["already_ok.py"]

    def test_never_mutates_input_dict(self):
        modules = {"main.py": HTTPSERVER_BARE_STRING_MAIN_PY}
        original = dict(modules)
        apply_server_address_tuple(modules)
        assert modules == original
# #EXT-036-REQ-68 End
