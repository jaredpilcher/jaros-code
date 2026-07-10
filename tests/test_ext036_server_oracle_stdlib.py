"""EXT-036 REQ-47: tests for harness/server_oracle.py's stdlib http.server launch+drive mode
(``serve_and_check_stdlib`` / ``detect_stdlib_http_service``). Fully OFFLINE (no network beyond
127.0.0.1, no model/Jetson calls) and deterministic: these tests write HAND-WRITTEN fixture
scripts that use only the Python STANDARD LIBRARY (``http.server``), launch them as real
subprocesses on ephemeral localhost ports, and drive real HTTP requests -- proving the oracle
really checks a plain stdlib REST service, not a framework-shaped one. Every test tears its
server down -- no orphaned processes, proven by re-checking the port is free afterward.
"""

from __future__ import annotations

import socket

import harness.server_oracle as server_oracle
from harness.server_oracle import detect_stdlib_http_service, serve_and_check_stdlib

# A correct fixture: reads PORT from the environment (the 12-factor contract this module's
# launch mode guarantees), serves GET /health, and round-trips POST/GET /items via an in-memory
# store.
GOOD_MAIN = '''
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

ITEMS = []


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
        elif self.path == "/items":
            self._send_json(200, {"items": ITEMS})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/items":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
            ITEMS.append(data)
            self._send_json(201, {"created": data})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''

# A broken fixture: binds the port fine but every endpoint 500s (wrong body / wrong status).
BROKEN_MAIN = '''
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{\\"error\\": \\"boom\\"}")

    def do_POST(self):
        self.do_GET()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''

# A fixture that never binds (crashes before serve_forever).
NEVER_BINDS_MAIN = '''
import sys

print("crashing before bind", file=sys.stderr)
raise RuntimeError("boom before bind")
'''

FLASK_LIKE_MAIN = '''
from flask import Flask

app = Flask(__name__)
'''


def _write(root, name, code):
    (root / name).write_text(code, encoding="utf-8")


def _port_is_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class TestDetectStdlibHttpService:
    def test_detects_http_server(self):
        assert detect_stdlib_http_service({"main.py": GOOD_MAIN}) == "main.py"

    def test_none_when_flask_present(self):
        assert detect_stdlib_http_service({"main.py": FLASK_LIKE_MAIN}) is None

    def test_none_for_plain_script(self):
        assert detect_stdlib_http_service({"main.py": "print('hi')"}) is None

    def test_never_raises_on_garbage(self):
        assert detect_stdlib_http_service("not a dict") is None
        assert detect_stdlib_http_service({"main.py": None}) is None
        assert detect_stdlib_http_service({None: GOOD_MAIN}) is None
        assert detect_stdlib_http_service(123) is None
        assert detect_stdlib_http_service({}) is None
        assert detect_stdlib_http_service(None) is None


class TestServeAndCheckStdlibGood:
    def test_health_and_items_roundtrip(self, tmp_path):
        _write(tmp_path, "main.py", GOOD_MAIN)

        result = serve_and_check_stdlib(
            tmp_path,
            "main.py",
            [
                {"method": "GET", "path": "/health", "status": 200,
                 "json_contains": {"ok": True}},
                {"method": "POST", "path": "/items", "status": 201,
                 "json_contains": {"created": {}}},
                {"method": "GET", "path": "/items", "status": 200,
                 "body_contains": "items"},
            ],
            startup_timeout=15,
            request_timeout=5,
        )

        assert result["ok"] is True, result["note"]
        assert len(result["results"]) == 3
        assert all(r["passed"] for r in result["results"]), result["results"]

    def test_no_orphan_process_left_after_success(self, tmp_path, monkeypatch):
        """Capture the EXACT port `serve_and_check_stdlib` allocated (by wrapping `_free_port`)
        and assert that specific port is bindable again immediately after teardown -- a
        precise no-orphan proof, not a generic sampling."""
        _write(tmp_path, "main.py", GOOD_MAIN)

        used_ports = []
        real_free_port = server_oracle._free_port

        def _spy_free_port():
            port = real_free_port()
            used_ports.append(port)
            return port

        monkeypatch.setattr(server_oracle, "_free_port", _spy_free_port)

        result = serve_and_check_stdlib(
            tmp_path, "main.py",
            [{"method": "GET", "path": "/health", "status": 200}],
            startup_timeout=15, request_timeout=5,
        )
        assert result["ok"] is True, result["note"]
        assert len(used_ports) == 1
        assert _port_is_free(used_ports[0])


class TestServeAndCheckStdlibBroken:
    def test_wrong_status_and_body_fails_honestly(self, tmp_path):
        _write(tmp_path, "main.py", BROKEN_MAIN)

        result = serve_and_check_stdlib(
            tmp_path,
            "main.py",
            [{"method": "GET", "path": "/health", "status": 200, "json_contains": {"ok": True}}],
            startup_timeout=15,
            request_timeout=5,
        )

        assert result["ok"] is False
        assert result["results"][0]["passed"] is False
        assert result["results"][0]["status"] == 500

    def test_never_binds_fails_with_note_and_no_orphan(self, tmp_path, monkeypatch):
        _write(tmp_path, "main.py", NEVER_BINDS_MAIN)

        used_ports = []
        real_free_port = server_oracle._free_port

        def _spy_free_port():
            port = real_free_port()
            used_ports.append(port)
            return port

        monkeypatch.setattr(server_oracle, "_free_port", _spy_free_port)

        result = serve_and_check_stdlib(
            tmp_path,
            "main.py",
            [{"method": "GET", "path": "/health"}],
            startup_timeout=5,
            request_timeout=3,
        )

        assert result["ok"] is False
        assert result["results"] == []
        assert "note" in result and result["note"]
        assert len(used_ports) == 1
        assert _port_is_free(used_ports[0])


class TestServeAndCheckStdlibRobustness:
    def test_missing_entry_never_raises(self, tmp_path):
        result = serve_and_check_stdlib(tmp_path, None, [])
        assert result["ok"] is False
        assert result["results"] == []

    def test_entry_not_on_disk_never_raises(self, tmp_path):
        result = serve_and_check_stdlib(tmp_path, "does_not_exist.py", [])
        assert result["ok"] is False

    def test_bad_root_never_raises(self):
        result = serve_and_check_stdlib(object(), "main.py", [])
        assert result["ok"] is False

    def test_missing_root_never_raises(self, tmp_path):
        result = serve_and_check_stdlib(tmp_path / "does_not_exist", "main.py", [])
        assert result["ok"] is False

    def test_garbage_entry_types_never_raise(self, tmp_path):
        assert serve_and_check_stdlib(tmp_path, 123, [])["ok"] is False
        assert serve_and_check_stdlib(tmp_path, "", [])["ok"] is False
        assert serve_and_check_stdlib(tmp_path, [], [])["ok"] is False

    def test_garbage_checks_never_raise(self, tmp_path):
        _write(tmp_path, "main.py", GOOD_MAIN)
        result = serve_and_check_stdlib(tmp_path, "main.py", "not a list", startup_timeout=15)
        assert result["ok"] is True, result["note"]  # empty checks after guard -> vacuously ok
        result2 = serve_and_check_stdlib(
            tmp_path, "main.py", [123, "bad", {"path": "/health"}], startup_timeout=15,
        )
        assert result2["ok"] is False
        assert len(result2["results"]) == 3
