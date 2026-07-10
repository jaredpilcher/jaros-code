"""Offline tests for EXT-036 REQ-50: deterministic PORT int-coercion repair.

No model/Jetson call anywhere in this file. The exact MEASURED broken shape (diagnosed via
code-dump, `scratchpad/saas_crud_diag.out`) is reconstructed and proven END-TO-END against a REAL
running stdlib server via `harness.server_oracle.serve_and_check_stdlib` -- the same oracle
`harness.real_systems_suite` uses to grade the "service" oracle_kind -- so a green here is a
genuine offline proof the repaired code actually binds a str-typed `PORT` env var and serves real
HTTP.
"""

# #EXT-036-REQ-50 Start
from pathlib import Path

from harness.port_coercion import apply_port_coercion, coerce_ports_in_code
from harness.server_oracle import serve_and_check_stdlib

_HEALTH_CHECKS = [
    {"method": "GET", "path": "/health", "status": 200, "body_contains": "ok"},
]

# gemma's ACTUAL measured shape: `os.getenv("PORT")` returns a str, passed un-coerced into the
# TCPServer bind-site tuple -- raises `TypeError: 'str' object cannot be interpreted as an
# integer` at bind time.
TCPSERVER_STR_PORT_MAIN_PY = '''
import os
import socketserver
from http.server import BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = os.getenv("PORT")
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
'''

HTTPSERVER_STR_PORT_MAIN_PY = '''
import os
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = os.getenv("PORT")
    HTTPServer(("", port), Handler).serve_forever()
'''

RAW_SOCKET_STR_PORT_PY = '''
import os
import socket

port = os.getenv("PORT")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("", port))
sock.listen(1)
'''

ALREADY_INT_CALL_PY = '''
import os
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    pass


if __name__ == "__main__":
    port = os.environ.get("PORT", "8000")
    HTTPServer(("", int(port)), Handler).serve_forever()
'''

ALREADY_INT_LITERAL_PY = '''
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    pass


HTTPServer(("", 8000), Handler).serve_forever()
'''

NO_BIND_SITE_PY = '''
def add(x, y):
    return x + y
'''


class TestCoerceEndToEnd:
    """(1) the EXACT measured broken shape -- os.getenv("PORT") then
    socketserver.TCPServer(("", port), handler) -- coerces to int(port), compiles, and actually
    binds+serves for real when PORT is a str env var."""

    def test_tcpserver_str_port_is_coerced_and_serves_for_real(self, tmp_path: Path):
        repaired = coerce_ports_in_code(TCPSERVER_STR_PORT_MAIN_PY)
        assert repaired != TCPSERVER_STR_PORT_MAIN_PY
        assert "int(port)" in repaired
        compile(repaired, "<main.py>", "exec")  # genuinely compiles

        (tmp_path / "main.py").write_text(repaired, encoding="utf-8")
        result = serve_and_check_stdlib(tmp_path, "main.py", _HEALTH_CHECKS)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r

    def test_unrepaired_tcpserver_str_port_genuinely_fails_to_bind(self, tmp_path: Path):
        # Control: WITHOUT the repair, the exact measured defect really does fail to serve --
        # proves the fix above is doing real work, not a fabricated pass.
        (tmp_path / "main.py").write_text(TCPSERVER_STR_PORT_MAIN_PY, encoding="utf-8")
        result = serve_and_check_stdlib(tmp_path, "main.py", _HEALTH_CHECKS)
        assert result["ok"] is False


class TestCoerceVariants:
    """(2) HTTPServer(("", port), Handler) variant."""

    def test_httpserver_variant_is_coerced(self):
        repaired = coerce_ports_in_code(HTTPSERVER_STR_PORT_MAIN_PY)
        assert "int(port)" in repaired
        compile(repaired, "<main.py>", "exec")

    # (3) raw sock.bind(("", port)) variant.
    def test_raw_socket_bind_variant_is_coerced(self):
        repaired = coerce_ports_in_code(RAW_SOCKET_STR_PORT_PY)
        assert repaired != RAW_SOCKET_STR_PORT_PY
        assert "int(port)" in repaired
        compile(repaired, "<sock.py>", "exec")


class TestIdempotentAndSafe:
    """(4) IDEMPOTENT: already int(port) and already an int literal 8000 are left unchanged
    (byte-identical)."""

    def test_already_int_call_is_byte_identical(self):
        assert coerce_ports_in_code(ALREADY_INT_CALL_PY) == ALREADY_INT_CALL_PY

    def test_already_int_literal_is_byte_identical(self):
        assert coerce_ports_in_code(ALREADY_INT_LITERAL_PY) == ALREADY_INT_LITERAL_PY

    def test_no_bind_site_is_byte_identical(self):
        assert coerce_ports_in_code(NO_BIND_SITE_PY) == NO_BIND_SITE_PY

    # (5) never-raises on unparseable/garbage input.
    def test_never_raises_on_garbage(self):
        assert coerce_ports_in_code(None) == ""
        assert coerce_ports_in_code("") == ""
        assert coerce_ports_in_code("def f(:\n") == "def f(:\n"
        assert coerce_ports_in_code("   not python !! @#$") == "   not python !! @#$"

    def test_apply_port_coercion_never_raises_on_garbage(self):
        assert apply_port_coercion(None) == {}
        assert apply_port_coercion({}) == {}
        assert apply_port_coercion({"a.py": None}) == {"a.py": ""}
        assert apply_port_coercion({"broken.py": "def f(:\n"}) == {"broken.py": "def f(:\n"}


class TestApplyPortCoercionOverModules:
    """(6) apply_port_coercion over a multi-module dict only changes the offending module."""

    def test_only_offending_module_changes(self):
        modules = {
            "main.py": TCPSERVER_STR_PORT_MAIN_PY,
            "helpers.py": NO_BIND_SITE_PY,
            "already_ok.py": ALREADY_INT_LITERAL_PY,
        }
        result = apply_port_coercion(modules)
        assert result["main.py"] != modules["main.py"]
        assert "int(port)" in result["main.py"]
        assert result["helpers.py"] == modules["helpers.py"]
        assert result["already_ok.py"] == modules["already_ok.py"]

    def test_never_mutates_input_dict(self):
        modules = {"main.py": TCPSERVER_STR_PORT_MAIN_PY}
        original = dict(modules)
        apply_port_coercion(modules)
        assert modules == original
# #EXT-036-REQ-50 End
