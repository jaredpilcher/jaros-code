#!/usr/bin/env python3
"""Jetson model-manager — serve ANY catalog model on :8000 on demand, controlled over HTTP on :8001.

Owner directive (2026-06-28): "make it easy for the model to come up and down depending on what the
client needs rather than having to SSH each time." This daemon OWNS the llama-server process (launches
and kills it as the local user — no sudo, no per-swap SSH). The harness asks it to serve a model via a
single HTTP call; it brings that model up on :8000 (taking the previous one down first, since the
Jetson's ~8 GB only holds one of these at a time) and reports when it is ready.

Control API (on :8001, localhost + LAN):
  GET  /current            -> {"current": <model_id|null>, "serving_ok": bool}
  GET  /catalog            -> the model catalog (ids the manager can serve)
  POST /serve  {"model": <id>}   -> ensure <id> is the model served on :8000 (idempotent); returns
                                    {"ok", "current", "swapped", "ready"}
  GET  /health             -> {"ok": true}

The catalog (models.json next to this file) maps model_id -> {gguf, alias, ctx, ngl, extra_args}.
This file is version-controlled in the jaros-code repo (scripts/) and deployed to
/home/jared/gemma-server/ on the Jetson, run by model-manager.service.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.environ.get("JCODE_MODEL_CATALOG", os.path.join(HERE, "models.json"))
STATE_PATH = os.environ.get("JCODE_MODEL_STATE", os.path.join(HERE, "active_model.txt"))
LLAMA_BIN = os.environ.get("JCODE_LLAMA_BIN", "/home/jared/llama.cpp/build/bin/llama-server")
LOG_PATH = os.environ.get("JCODE_LLAMA_LOG", "/home/jared/gemma-server/llama-server.log")
SERVE_PORT = int(os.environ.get("JCODE_SERVE_PORT", "8000"))
CONTROL_PORT = int(os.environ.get("JCODE_CONTROL_PORT", "8001"))
DEFAULT_MODEL = os.environ.get("JCODE_DEFAULT_MODEL", "gemma-4-e2b")
READY_TIMEOUT_S = int(os.environ.get("JCODE_READY_TIMEOUT_S", "120"))
# llama-server needs the CUDA runtime libs (libcudart.so.13) from the pip cu13 toolkit — the same
# LD_LIBRARY_PATH the original serve.sh exported. Without it llama-server exits rc=127.
LD_LIBRARY_PATH_EXTRA = os.environ.get(
    "JCODE_LD_LIBRARY_PATH",
    "/home/jared/vllm-gemma/.venv/lib/python3.12/site-packages/nvidia/cu13/lib",
)

_proc: subprocess.Popen | None = None
_current: str | None = None


def _load_catalog() -> dict:
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _serving_ok() -> bool:
    # llama.cpp /health returns 200 only when the model is fully LOADED (503 while loading) — unlike
    # /v1/models which 200s during load and would report "ready" prematurely.
    try:
        with urllib.request.urlopen(f"http://localhost:{SERVE_PORT}/health", timeout=2):
            return True
    except Exception:  # noqa: BLE001 — any failure (incl. 503 loading) means "not ready"
        return False


def _kill_llama() -> None:
    """Take the current llama-server down. Kill our child if we own it, else pkill by name
    (adopts a server started by the old gemma.service before we took over)."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _proc.kill()
    subprocess.run(["pkill", "-f", "llama-server"], check=False)
    _proc = None
    # wait for the port to free
    for _ in range(15):
        if not _serving_ok():
            return
        time.sleep(1)


def _build_cmd(spec: dict) -> list[str]:
    cmd = [
        LLAMA_BIN,
        "-m", spec["gguf"],
        "--alias", spec.get("alias", spec.get("gguf")),
        "--host", "0.0.0.0", "--port", str(SERVE_PORT),
        "--n-gpu-layers", str(spec.get("ngl", 99)),
        "--ctx-size", str(spec.get("ctx", 4096)),
        "--flash-attn", "on",
        "--jinja",
    ]
    cmd += list(spec.get("extra_args", []))
    return cmd


def serve_model(model_id: str) -> dict:
    """Ensure `model_id` is the model served on :8000. Idempotent: a no-op if it is already
    serving and healthy. Otherwise brings the previous one down and the requested one up."""
    global _proc, _current
    catalog = _load_catalog()
    if model_id not in catalog:
        return {"ok": False, "error": f"unknown model '{model_id}'", "current": _current,
                "known": sorted(catalog)}
    if model_id == _current and _serving_ok():
        return {"ok": True, "current": _current, "swapped": False, "ready": True}

    _kill_llama()
    spec = catalog[model_id]
    log = open(LOG_PATH, "ab", buffering=0)
    env = dict(os.environ)
    if LD_LIBRARY_PATH_EXTRA:
        prior = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH_EXTRA + (":" + prior if prior else "")
    _proc = subprocess.Popen(_build_cmd(spec), stdout=log, stderr=log, env=env)
    deadline = time.time() + READY_TIMEOUT_S
    while time.time() < deadline:
        if _proc.poll() is not None:
            return {"ok": False, "error": f"llama-server exited rc={_proc.returncode} (see {LOG_PATH})",
                    "current": None, "swapped": True, "ready": False}
        if _serving_ok():
            _current = model_id
            try:
                with open(STATE_PATH, "w", encoding="utf-8") as fh:
                    fh.write(model_id)
            except OSError:
                pass
            return {"ok": True, "current": _current, "swapped": True, "ready": True}
        time.sleep(2)
    return {"ok": False, "error": f"timeout after {READY_TIMEOUT_S}s waiting for {model_id}",
            "current": model_id, "swapped": True, "ready": _serving_ok()}


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):  # quiet default logging
        pass

    def do_GET(self):
        if self.path == "/current":
            self._send(200, {"current": _current, "serving_ok": _serving_ok()})
        elif self.path == "/catalog":
            self._send(200, {"catalog": _load_catalog(), "default": DEFAULT_MODEL})
        elif self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/serve":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            model_id = body["model"]
        except Exception as e:  # noqa: BLE001
            self._send(400, {"ok": False, "error": f"bad request: {e}"})
            return
        result = serve_model(str(model_id))
        self._send(200 if result.get("ok") else 503, result)


def main() -> None:
    # Bring the default model up at boot so the node is immediately usable.
    print(f"[model-manager] starting; serving default '{DEFAULT_MODEL}' on :{SERVE_PORT}", flush=True)
    r = serve_model(DEFAULT_MODEL)
    print(f"[model-manager] default serve: {r}", flush=True)
    srv = HTTPServer(("0.0.0.0", CONTROL_PORT), _Handler)
    print(f"[model-manager] control API on :{CONTROL_PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
