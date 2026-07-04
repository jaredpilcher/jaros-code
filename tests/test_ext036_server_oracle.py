"""EXT-036 REQ-22: tests for harness/server_oracle.py -- the REAL server/HTTP acceptance
oracle. Fully OFFLINE (no network beyond 127.0.0.1) and deterministic: fastapi, uvicorn,
and flask ARE installed in this environment, so these tests actually START real localhost
servers on ephemeral ports and hit real endpoints (proving the oracle really checks, not a
trivially-passing stub). Every test tears its server down -- no orphaned processes.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("flask")

from harness.server_oracle import detect_web_service, serve_and_check  # noqa: E402

FASTAPI_MAIN = '''
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/add")
def add(a: int, b: int):
    return {"sum": a + b}
'''

FLASK_MAIN = '''
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/add")
def add():
    a = int(request.args.get("a", 0))
    b = int(request.args.get("b", 0))
    return jsonify({"sum": a + b})
'''

BROKEN_IMPORT_MAIN = '''
from fastapi import FastAPI

raise RuntimeError("boom at import time")

app = FastAPI()
'''

PLAIN_CLI_MAIN = '''
import sys

if __name__ == "__main__":
    data = sys.stdin.read()
    print(len(data))
'''


def _write(root, name, code):
    (root / name).write_text(code, encoding="utf-8")


class TestDetectWebService:
    def test_detects_fastapi(self):
        detected = detect_web_service({"main.py": FASTAPI_MAIN})
        assert detected == {"kind": "asgi", "entry": "main", "app": "app"}

    def test_detects_flask(self):
        detected = detect_web_service({"main.py": FLASK_MAIN})
        assert detected == {"kind": "wsgi", "entry": "main", "app": "app"}

    def test_none_for_plain_cli(self):
        assert detect_web_service({"main.py": PLAIN_CLI_MAIN}) is None

    def test_none_for_empty_or_missing(self):
        assert detect_web_service({}) is None
        assert detect_web_service(None) is None

    def test_never_raises_on_garbage(self):
        assert detect_web_service("not a dict") is None
        assert detect_web_service({"main.py": None}) is None
        assert detect_web_service({None: FASTAPI_MAIN}) is None
        assert detect_web_service(123) is None


class TestServeAndCheckFastAPI:
    def test_serves_and_checks_real_endpoints(self, tmp_path):
        _write(tmp_path, "main.py", FASTAPI_MAIN)
        service = detect_web_service({"main.py": FASTAPI_MAIN})
        assert service is not None

        result = serve_and_check(
            tmp_path,
            service,
            [
                {"method": "GET", "path": "/health", "status": 200,
                 "json_contains": {"status": "ok"}},
                {"method": "GET", "path": "/add?a=2&b=3", "status": 200,
                 "json_contains": {"sum": 5}},
            ],
            startup_timeout=15,
            request_timeout=5,
        )

        assert result["ok"] is True, result["note"]
        assert len(result["results"]) == 2
        assert all(r["passed"] for r in result["results"]), result["results"]
        assert result["results"][0]["status"] == 200
        assert result["results"][1]["status"] == 200

    def test_negative_wrong_expectation_fails_honestly(self, tmp_path):
        """A check demanding a WRONG value must genuinely fail -- proves the oracle really
        inspects the response instead of trivially passing."""
        _write(tmp_path, "main.py", FASTAPI_MAIN)
        service = detect_web_service({"main.py": FASTAPI_MAIN})

        result = serve_and_check(
            tmp_path,
            service,
            [{"method": "GET", "path": "/health", "json_contains": {"status": "nope"}}],
            startup_timeout=15,
            request_timeout=5,
        )

        assert result["ok"] is False
        assert result["results"][0]["passed"] is False


class TestServeAndCheckFlask:
    def test_serves_and_checks_real_endpoint(self, tmp_path):
        _write(tmp_path, "main.py", FLASK_MAIN)
        service = detect_web_service({"main.py": FLASK_MAIN})
        assert service == {"kind": "wsgi", "entry": "main", "app": "app"}

        result = serve_and_check(
            tmp_path,
            service,
            [{"method": "GET", "path": "/health", "status": 200,
              "json_contains": {"status": "ok"}}],
            startup_timeout=15,
            request_timeout=5,
        )

        assert result["ok"] is True, result["note"]
        assert result["results"][0]["passed"] is True


class TestServeAndCheckBrokenApp:
    def test_broken_import_fails_without_hanging(self, tmp_path):
        _write(tmp_path, "main.py", BROKEN_IMPORT_MAIN)
        service = {"kind": "asgi", "entry": "main", "app": "app"}

        result = serve_and_check(
            tmp_path,
            service,
            [{"method": "GET", "path": "/health"}],
            startup_timeout=5,
            request_timeout=3,
        )

        assert result["ok"] is False
        assert result["results"] == []
        assert "note" in result and result["note"]


class TestServeAndCheckRobustness:
    def test_no_service_returns_ok_false(self, tmp_path):
        result = serve_and_check(tmp_path, None, [])
        assert result["ok"] is False
        assert result["results"] == []

    def test_bad_root_never_raises(self):
        result = serve_and_check(object(), {"kind": "asgi", "entry": "main", "app": "app"}, [])
        assert result["ok"] is False

    def test_missing_root_never_raises(self, tmp_path):
        result = serve_and_check(tmp_path / "does_not_exist", {"kind": "asgi", "entry": "main", "app": "app"}, [])
        assert result["ok"] is False

    def test_garbage_service_never_raises(self, tmp_path):
        assert serve_and_check(tmp_path, "not a dict", [])["ok"] is False
        assert serve_and_check(tmp_path, {}, [])["ok"] is False
        assert serve_and_check(tmp_path, 123, None)["ok"] is False

    def test_garbage_checks_never_raise(self, tmp_path):
        _write(tmp_path, "main.py", FASTAPI_MAIN)
        service = detect_web_service({"main.py": FASTAPI_MAIN})
        result = serve_and_check(tmp_path, service, "not a list", startup_timeout=15)
        assert result["ok"] is True, result["note"]  # empty checks after guard -> vacuously ok
        result2 = serve_and_check(tmp_path, service, [123, "bad", {"path": "/health"}], startup_timeout=15)
        assert result2["ok"] is False
        assert len(result2["results"]) == 3
