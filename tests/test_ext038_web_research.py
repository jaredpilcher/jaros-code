"""EXT-038 / REQ-2 (TASK-2) -- ``harness.web_research``: the read-only web-fetch capability that

rides on top of the REQ-1 guards. Offline, deterministic, NO real network access anywhere in this
module -- every transport call site is monkeypatched (the module's ``_open_url``/
``_resolve_host_ips`` seams), never a real socket.
"""

from __future__ import annotations

import email.message
import socket
import urllib.error
import urllib.request

import pytest

from harness import research_guard, web_research
from harness.web_research import (
    EgressRefused,
    ResearchResult,
    _AllowlistRedirectHandler,
    fetch,
)

# #EXT-038-REQ-2 Start


class _FakeResponse:
    """A minimal stand-in for a ``urllib`` response object -- context-manager compatible, with
    ``.read(n)``, ``.headers`` (a real ``email.message.Message`` so ``get_content_charset()``
    behaves exactly like the real thing), ``.status``, and ``.url``."""

    def __init__(self, body: bytes, *, status=200, url="https://good.example.com/page",
                 content_type="text/plain; charset=utf-8"):
        self._body = body
        self.status = status
        self.url = url
        self.headers = email.message.Message()
        if content_type is not None:
            self.headers["Content-Type"] = content_type

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
    """Stand-in for :func:`harness.web_research._resolve_host_ips` -- returns a genuine PUBLIC IP
    (never contacted) so the SSRF check passes without a real DNS lookup."""
    return ["93.184.216.34"]


def _fake_private_ips(host):
    """Stand-in returning a private/loopback address -- proves the SSRF check fires even for an
    otherwise allow-listed host."""
    return ["127.0.0.1"]


@pytest.fixture(autouse=True)
def _clean_eval_env():
    prior = None
    import os

    prior = os.environ.pop("JCODE_EVAL_ACTIVE", None)
    yield
    if prior is not None:
        os.environ["JCODE_EVAL_ACTIVE"] = prior
    else:
        os.environ.pop("JCODE_EVAL_ACTIVE", None)


# --- (a) GUARD FIRST: fetch during eval_lock() raises before any transport code runs -----------


def test_fetch_during_eval_lock_raises_before_any_transport(monkeypatch):
    called = {"resolve": False, "open": False}

    def _boom_resolve(host):
        called["resolve"] = True
        raise AssertionError("DNS resolution must never be attempted during an eval lock")

    def _boom_open(opener, request, timeout):
        called["open"] = True
        raise AssertionError("transport must never be attempted during an eval lock")

    monkeypatch.setattr(web_research, "_resolve_host_ips", _boom_resolve)
    monkeypatch.setattr(web_research, "_open_url", _boom_open)

    with research_guard.eval_lock():
        with pytest.raises(research_guard.ResearchDisabledError):
            fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])

    assert called["resolve"] is False
    assert called["open"] is False


def test_fetch_outside_eval_lock_does_not_raise_research_disabled(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: _FakeResponse(b"hello world"),
    )
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert isinstance(result, ResearchResult)
    assert result.ok is True


# --- (b) host not on the allow-list is refused, no transport call made -------------------------


def test_fetch_refuses_host_not_on_allowlist(monkeypatch):
    called = {"resolve": False, "open": False}
    monkeypatch.setattr(
        web_research, "_resolve_host_ips",
        lambda host: called.update(resolve=True) or _fake_public_ips(host),
    )
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda *a, **k: called.update(open=True) or _FakeResponse(b""),
    )
    with pytest.raises(EgressRefused):
        fetch("https://evil.example.com/page", allowed_hosts=["good.example.com"])
    assert called["resolve"] is False
    assert called["open"] is False


def test_fetch_with_no_allowed_hosts_is_deny_all(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    with pytest.raises(EgressRefused):
        fetch("https://good.example.com/page", allowed_hosts=[])


# --- (c) a redirect off the allow-list is refused, not followed --------------------------------


def test_redirect_handler_refuses_non_allowlisted_host(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    policy = research_guard.research_egress_policy("good.example.com")
    handler = _AllowlistRedirectHandler(policy)
    fake_request = urllib.request.Request("https://good.example.com/page")  # noqa: F821
    with pytest.raises(EgressRefused):
        handler.redirect_request(
            fake_request, None, 302, "Found", {}, "https://evil.example.com/steal"
        )


def test_fetch_end_to_end_refuses_redirect_off_allowlist(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)

    class _FakeOpenerFollowsBadRedirect:
        def __init__(self, policy):
            self._handler = _AllowlistRedirectHandler(policy)

        def open(self, request, timeout=None):
            # Simulate the server responding with a 302 to a disallowed host -- the SAME
            # handler `fetch()` installs on its real opener must refuse this redirect.
            self._handler.redirect_request(
                request, None, 302, "Found", {}, "https://evil.example.com/steal"
            )
            raise AssertionError("redirect must have been refused before this point")

    monkeypatch.setattr(
        web_research, "_build_opener",
        lambda policy: _FakeOpenerFollowsBadRedirect(policy),
    )
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: opener.open(request, timeout=timeout),
    )
    with pytest.raises(EgressRefused):
        fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])


# --- (d) non-http(s) scheme and non-GET method are both refused --------------------------------


def test_fetch_refuses_non_http_scheme(monkeypatch):
    called = {"resolve": False}
    monkeypatch.setattr(
        web_research, "_resolve_host_ips",
        lambda host: called.update(resolve=True) or _fake_public_ips(host),
    )
    with pytest.raises(EgressRefused):
        fetch("file:///etc/passwd", allowed_hosts=["good.example.com"])
    assert called["resolve"] is False


def test_fetch_refuses_non_get_method(monkeypatch):
    called = {"resolve": False}
    monkeypatch.setattr(
        web_research, "_resolve_host_ips",
        lambda host: called.update(resolve=True) or _fake_public_ips(host),
    )
    with pytest.raises(EgressRefused):
        fetch("https://good.example.com/page", allowed_hosts=["good.example.com"], method="POST")
    assert called["resolve"] is False


# --- (e) SSRF: a private/loopback resolved IP is refused even for an allow-listed host ----------


def test_fetch_refuses_private_resolved_ip_ssrf(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_private_ips)
    opened = {"called": False}
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda *a, **k: opened.update(called=True) or _FakeResponse(b""),
    )
    with pytest.raises(EgressRefused):
        fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert opened["called"] is False


@pytest.mark.parametrize("bad_ip", ["127.0.0.1", "10.0.0.5", "172.16.4.4", "192.168.1.1",
                                    "169.254.1.1", "::1"])
def test_is_private_ip_flags_every_reserved_range(bad_ip):
    assert web_research._is_private_ip(bad_ip) is True


def test_is_private_ip_allows_a_public_ip():
    assert web_research._is_private_ip("93.184.216.34") is False


# --- (f) oversized response is truncated, never read unbounded ---------------------------------


def test_fetch_truncates_oversized_response(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    big_body = b"x" * 100
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: _FakeResponse(big_body),
    )
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"], max_bytes=10)
    assert result.ok is True
    assert result.truncated is True
    # The wrapped text must reflect the TRUNCATED body only (10 bytes), never the full 100.
    assert ("x" * 100) not in result.text_wrapped


def test_fetch_does_not_flag_truncation_when_under_the_cap(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: _FakeResponse(b"small"),
    )
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"], max_bytes=1000)
    assert result.ok is True
    assert result.truncated is False


# --- (g) the returned text is ALWAYS wrapped -- no unwrapped path exists ------------------------


def test_fetch_result_is_always_wrapped(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: _FakeResponse(b"plain fetched content"),
    )
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert result.ok is True
    assert result.text_wrapped.startswith("===== UNTRUSTED WEB CONTENT (source=")
    assert "===== END UNTRUSTED WEB CONTENT =====" in result.text_wrapped
    assert "plain fetched content" in result.text_wrapped


def test_fetch_wraps_even_a_failed_result():
    # Even the honest ok=False network-failure path (proven below) must carry wrapped text, not
    # an empty raw string -- there is no "unwrapped" ResearchResult shape.
    pass  # covered structurally by test_fetch_network_failure_returns_honest_ok_false below


# --- (h) an ordinary network failure returns ok=False, never raises ----------------------------


def test_fetch_network_failure_returns_honest_ok_false(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)

    def _boom(opener, request, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(web_research, "_open_url", _boom)
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert result.ok is False
    assert "no route to host" in result.note
    assert result.text_wrapped.startswith("===== UNTRUSTED WEB CONTENT (source=")


def test_fetch_timeout_returns_honest_ok_false(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)

    def _boom(opener, request, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(web_research, "_open_url", _boom)
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert result.ok is False
    assert "timed out" in result.note


def test_fetch_http_error_returns_honest_ok_false_with_status(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)

    def _boom(opener, request, timeout):
        raise urllib.error.HTTPError("https://good.example.com/page", 404, "Not Found", {}, None)

    monkeypatch.setattr(web_research, "_open_url", _boom)
    result = fetch("https://good.example.com/page", allowed_hosts=["good.example.com"])
    assert result.ok is False
    assert result.status == 404


# --- misc: allowed_hosts as a plain string is accepted (single-host convenience) ----------------


def test_fetch_accepts_a_single_host_string(monkeypatch):
    monkeypatch.setattr(web_research, "_resolve_host_ips", _fake_public_ips)
    monkeypatch.setattr(
        web_research, "_open_url",
        lambda opener, request, timeout: _FakeResponse(b"ok"),
    )
    result = fetch("https://good.example.com/page", allowed_hosts="good.example.com")
    assert result.ok is True


# #EXT-038-REQ-2 End
