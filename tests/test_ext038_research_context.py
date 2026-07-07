"""EXT-038 REQ-4 (TASK-4) -- ``harness.web_research.research_context``: deterministic library-name

detection + guarded fetch, offline (the same ``_open_url``/``_resolve_host_ips`` monkeypatch seams
``tests/test_ext038_web_research.py`` uses -- no real network access anywhere in this file).
"""

from __future__ import annotations

import email.message
import os

import pytest

from harness import research_guard, web_research
from harness.web_research import KNOWN_LIBRARY_DOCS, research_context

# #EXT-038-REQ-4 Start


class _FakeResponse:
    def __init__(self, body: bytes, *, status=200, url="https://flask.palletsprojects.com/"):
        self._body = body
        self.status = status
        self.url = url
        self.headers = email.message.Message()
        self.headers["Content-Type"] = "text/plain; charset=utf-8"

    def read(self, n=-1):
        if n is None or n < 0:
            data, self._body = self._body, b""
        else:
            data, self._body = self._body[:n], self._body[n:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _fake_public_ips(host):
    return ["93.184.216.34"]


@pytest.fixture(autouse=True)
def _clean_eval_env():
    prior = os.environ.pop("JCODE_EVAL_ACTIVE", None)
    yield
    if prior is not None:
        os.environ["JCODE_EVAL_ACTIVE"] = prior
    else:
        os.environ.pop("JCODE_EVAL_ACTIVE", None)


def test_known_library_triggers_exactly_one_fetch_to_the_right_url(monkeypatch):
    calls = []

    def _tracked_open(opener, request, timeout):
        calls.append(request.full_url)
        return _FakeResponse(b"Flask docs body")

    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(web_research, "_open_url", _tracked_open)

    ctx = research_context("Build a small web app using Flask that serves a JSON API.")

    assert len(calls) == 1
    assert calls[0] == KNOWN_LIBRARY_DOCS["flask"][0]
    assert "flask" in ctx.lower()
    assert "Flask docs body" in ctx


def test_no_known_library_triggers_zero_fetches(monkeypatch):
    calls = []
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(web_research, "_open_url",
                        lambda opener, request, timeout: calls.append(1) or _FakeResponse(b""))

    ctx = research_context("Build a CLI that reverses lines of a text file.")

    assert calls == []
    assert ctx == ""


def test_fetch_failure_degrades_to_empty_string_never_raises(monkeypatch):
    def _boom_open(opener, request, timeout):
        raise ConnectionRefusedError("simulated network failure")

    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(web_research, "_open_url", _boom_open)

    ctx = research_context("Build a data pipeline using pandas to clean a CSV.")

    assert ctx == ""  # never raises out of research_context


def test_active_eval_lock_degrades_to_empty_string_never_raises(monkeypatch):
    called = {"open": False}

    def _boom_open(opener, request, timeout):
        called["open"] = True
        raise AssertionError("transport must never be attempted during an eval lock")

    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(web_research, "_open_url", _boom_open)

    with research_guard.eval_lock():
        ctx = research_context("Build a CLI using Click for argument parsing.")

    assert ctx == ""
    assert called["open"] is False


def test_empty_spec_never_raises():
    assert research_context("") == ""
    assert research_context(None) == ""  # type: ignore[arg-type]
# #EXT-038-REQ-4 End
