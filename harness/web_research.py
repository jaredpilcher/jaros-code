"""Read-only web-research fetch capability (EXT-038 / REQ-2) -- the actual mechanism the

``harness.research_guard`` safety envelope (REQ-1) was built to contain. This module performs the
first REAL network fetch in the research plane; every fetch runs the following non-negotiable
safety contract, in this exact order:

1. **GUARD FIRST** -- :func:`harness.research_guard.assert_research_allowed` is called as the very
   first action, before any transport code runs. A fetch attempted during an active
   ``eval_lock()`` scope (or ``JCODE_EVAL_ACTIVE=1``) raises ``ResearchDisabledError`` -- the
   eval-leak hard-off, now proven against a REAL fetch entrypoint.
2. **EGRESS GATED** -- the caller supplies ``allowed_hosts``; the policy is built via
   :func:`harness.research_guard.research_egress_policy` (fail-closed ``DENY_ALL`` when none are
   given) and a target host not permitted by exact-host match raises :class:`EgressRefused` --
   including a redirect hop off the allow-list, which is refused rather than blindly followed.
3. **READ-ONLY** -- GET only; a non-``http(s)`` scheme or a non-GET method is rejected before any
   connection opens. Response size, timeout, and redirect count are all capped. Nothing in this
   module ever writes to disk.
4. **UNTRUSTED OUTPUT** -- the fetched text is always routed through
   :func:`harness.research_guard.wrap_untrusted` before it is returned; there is no code path that
   hands back raw, unwrapped fetched content.
5. **SSRF HARDENING** -- even an allow-listed host is refused if it resolves to a
   private/loopback/link-local IP address -- the host-based allow-list is not trusted alone to keep
   a fetch off internal services.

**Two-plane discipline:** this module makes zero model/reasoning calls -- it is deterministic
execution-plane code exactly like ``harness.secure_exec``. An ordinary network failure (DNS
failure, connection refused, timeout, an HTTP error status, a decode error) is an honest
``ok=False`` result with a ``note`` -- never raised, mirroring ``secure_exec.py``/
``run_sandboxed``'s never-raise-on-failure discipline. The GUARD and EGRESS-REFUSAL checks are the
deliberate exception: they raise loudly (``ResearchDisabledError`` / :class:`EgressRefused`) so a
misuse of the safety contract can never be silently swallowed.

**Honest scope (Tenet 3):** this module is additive and self-contained. As of EXT-038 REQ-4,
:func:`research_context` (below) IS wired into ``harness.system_builder.build_system``'s PLAN
phase, opt-in via ``enable_research=True`` -- the fetch capability defined here is a real caller's
mechanism, not dormant. Pure stdlib (``urllib.request`` only) plus reuse of
``harness.research_guard`` -- no new dependency (``requests`` etc. are not added).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from harness import research_guard

# #EXT-038-REQ-2 Start


class EgressRefused(RuntimeError):
    """Raised (never swallowed) whenever a fetch target -- or a redirect hop -- is refused by the
    egress allow-list, the scheme/method gate, or the SSRF host-resolution check. This is a loud,
    deliberate misuse signal, the same discipline ``ResearchDisabledError`` follows for the
    guard-first check -- a caller that mis-scopes a fetch must see a hard error, not a silently
    empty/failed result."""


@dataclass
class ResearchResult:
    """The only shape :func:`fetch` returns on the non-raising path. ``text_wrapped`` is ALWAYS
    produced by :func:`harness.research_guard.wrap_untrusted` -- there is no field anywhere on this
    dataclass that carries raw, unwrapped fetched content."""

    ok: bool
    status: "int | None"
    final_url: "str | None"
    content_type: "str | None"
    text_wrapped: str
    truncated: bool
    note: str


_PRIVATE_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)

_DEFAULT_TIMEOUT_S = 15
_DEFAULT_MAX_BYTES = 2_000_000
_MAX_REDIRECTS = 5


def _is_private_ip(ip_str: str) -> bool:
    """Return True iff ``ip_str`` falls in a private/loopback/link-local range -- the SSRF
    backstop, checked independently of (and in addition to) the host-based allow-list."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not a parseable IP at all -- fail-closed: treat as unsafe rather than implicitly safe.
        return True
    if addr.is_loopback or addr.is_link_local or addr.is_private:
        return True
    return any(addr in net for net in _PRIVATE_NETWORKS)


def _resolve_host_ips(host: str) -> list:
    """Resolve ``host`` to its IP address string(s) via stdlib DNS. Raises on failure -- callers
    decide whether a resolution failure should surface as ``EgressRefused`` (fail-closed) or an
    honest ``ok=False`` network-failure result depending on where in the pipeline it occurs."""
    infos = socket.getaddrinfo(host, None)
    ips = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0]:
            ips.append(sockaddr[0])
    return ips


def _assert_host_safe(host: "str | None", policy) -> None:
    """Raise :class:`EgressRefused` unless ``host`` is both allow-listed AND resolves to no
    private/loopback/link-local IP. Fail-closed: an unresolvable host is refused, never treated as
    implicitly safe."""
    if not host or not policy.is_host_allowed(host):
        raise EgressRefused(
            f"egress refused: host {host!r} is not permitted by the supplied allow-list"
        )
    try:
        ips = _resolve_host_ips(host)
    except Exception as exc:
        raise EgressRefused(f"egress refused: could not resolve host {host!r}: {exc}") from exc
    if not ips:
        raise EgressRefused(f"egress refused: host {host!r} resolved to no address")
    for ip in ips:
        if _is_private_ip(ip):
            raise EgressRefused(
                f"egress refused (SSRF): host {host!r} resolves to private/loopback/"
                f"link-local address {ip!r}"
            )


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect hop's host against the SAME allow-list + SSRF checks before
    following it -- a redirect off the allow-list (or into a private IP) is refused immediately,
    never blindly followed. Caps the number of hops followed."""

    def __init__(self, policy) -> None:
        super().__init__()
        self._policy = policy
        self._hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._hops += 1
        if self._hops > _MAX_REDIRECTS:
            raise EgressRefused(f"egress refused: exceeded max redirects ({_MAX_REDIRECTS})")
        parsed = urlparse(newurl)
        if parsed.scheme not in ("http", "https"):
            raise EgressRefused(f"egress refused: redirect to non-http(s) scheme {parsed.scheme!r}")
        _assert_host_safe(parsed.hostname, self._policy)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener(policy) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_AllowlistRedirectHandler(policy))


def _open_url(opener: urllib.request.OpenerDirector, url: str, timeout: float):
    """The one call site that performs the actual transport -- kept as a thin, separately
    monkeypatchable seam so tests never touch a real socket."""
    return opener.open(url, timeout=timeout)


def fetch(
    url: str,
    *,
    allowed_hosts,
    method: str = "GET",
    timeout: float = _DEFAULT_TIMEOUT_S,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> ResearchResult:
    """Read-only GET fetch of ``url``, gated + guarded per the module docstring's 5-point safety
    contract. Never raises on an ordinary network failure (an honest ``ok=False`` result instead) --
    EXCEPT the guard-first check (``ResearchDisabledError``) and any egress/scheme/method/SSRF
    refusal (:class:`EgressRefused`), which are the deliberate, loud exceptions to the
    never-raise rule. ``method`` is accepted only for the sake of an explicit, loud rejection of a
    non-GET verb -- this module never issues anything but GET; it has no write/side-effecting path."""

    # 1. GUARD FIRST -- before ANY transport code runs, before even URL parsing.
    research_guard.assert_research_allowed()

    # 2. EGRESS GATED -- build the policy (fail-closed DENY_ALL with no hosts).
    if isinstance(allowed_hosts, str):
        allowed_hosts = (allowed_hosts,)
    policy = research_guard.research_egress_policy(*(allowed_hosts or ()))

    # 3. READ-ONLY -- scheme + method gate, before any connection opens (and before any DNS
    # resolution is attempted for the host-safety check below).
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EgressRefused(f"egress refused: non-http(s) scheme {parsed.scheme!r}")
    if method != "GET":
        raise EgressRefused(f"egress refused: only GET is permitted, got {method!r}")

    _assert_host_safe(parsed.hostname, policy)  # host allow-list + SSRF (step 2 + step 5)

    final_url = url
    try:
        opener = _build_opener(policy)
        request = urllib.request.Request(url, method="GET")
        with _open_url(opener, request, timeout) as response:
            final_url = getattr(response, "url", url) or url
            status = getattr(response, "status", None)
            headers = getattr(response, "headers", None)
            content_type = headers.get("Content-Type") if headers is not None else None

            raw = response.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            if truncated:
                raw = raw[:max_bytes]

            charset = None
            if headers is not None:
                try:
                    charset = headers.get_content_charset()
                except Exception:
                    charset = None
            text = raw.decode(charset or "utf-8", errors="replace")

        # 4. UNTRUSTED OUTPUT -- ALWAYS wrapped; no unwrapped return path exists.
        wrapped = research_guard.wrap_untrusted(text, source=final_url)
        return ResearchResult(
            ok=True,
            status=status,
            final_url=final_url,
            content_type=content_type,
            text_wrapped=wrapped,
            truncated=truncated,
            note="fetched successfully" + (" (truncated to max_bytes)" if truncated else ""),
        )
    except EgressRefused:
        # Loud, deliberate: egress refusals (including a refused redirect hop raised from inside
        # the opener) must propagate uncaught, never be downgraded into a quiet ok=False result.
        raise
    except research_guard.ResearchDisabledError:
        # Loud, deliberate: mirrors the guard-first contract even if somehow raised mid-fetch.
        raise
    except urllib.error.HTTPError as exc:
        return ResearchResult(
            ok=False,
            status=getattr(exc, "code", None),
            final_url=final_url,
            content_type=None,
            text_wrapped=research_guard.wrap_untrusted("", source=final_url),
            truncated=False,
            note=f"HTTP error: {exc}",
        )
    except Exception as exc:  # ordinary network failure -- honest, never raised
        return ResearchResult(
            ok=False,
            status=None,
            final_url=final_url,
            content_type=None,
            text_wrapped=research_guard.wrap_untrusted("", source=final_url),
            truncated=False,
            note=f"fetch failed: {exc}",
        )


# #EXT-038-REQ-4 Start
# TASK-4: wire the fetch capability into an actual caller (the planner). Deterministic detection
# (never a model judgment) over a small, hand-curated table -- the "real-library systems tier".
KNOWN_LIBRARY_DOCS: "dict[str, tuple[str, str]]" = {
    "flask": ("https://flask.palletsprojects.com/", "flask.palletsprojects.com"),
    "pandas": ("https://pandas.pydata.org/docs/", "pandas.pydata.org"),
    "requests": ("https://requests.readthedocs.io/", "requests.readthedocs.io"),
    "click": ("https://click.palletsprojects.com/", "click.palletsprojects.com"),
    "sqlalchemy": ("https://docs.sqlalchemy.org/", "docs.sqlalchemy.org"),
}

_LIBRARY_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in KNOWN_LIBRARY_DOCS) + r")\b", re.IGNORECASE
)


def research_context(spec: str) -> str:
    """Deterministic, NEVER-RAISE research augmentation for a PLAN prompt: scan ``spec`` for a
    known library name (word-boundary, case-insensitive match against :data:`KNOWN_LIBRARY_DOCS`
    -- never a model guess). On no match, return ``""`` IMMEDIATELY -- zero network activity. On the
    first match, attempt exactly ONE guarded :func:`fetch` call; ANY outcome other than a clean
    ``ok=True`` result (an active ``eval_lock()``, an ``EgressRefused``, an ordinary network
    failure, or any other exception) degrades silently to ``""`` -- the caller can always treat this
    function as a plain string producer, never as something that can fail a build. A successful
    fetch's ALREADY-fenced ``text_wrapped`` (via ``research_guard.wrap_untrusted`` inside
    :func:`fetch`) is embedded verbatim -- never re-wrapped, never stripped."""
    if not isinstance(spec, str) or not spec:
        return ""
    match = _LIBRARY_NAME_RE.search(spec)
    if not match:
        return ""
    name = match.group(1).lower()
    url, host = KNOWN_LIBRARY_DOCS[name]
    try:
        result = fetch(url, allowed_hosts=(host,))
    except Exception:  # ResearchDisabledError, EgressRefused, or anything else -- silent degrade
        return ""
    if not result.ok:
        return ""
    return f"Relevant {name} documentation (untrusted, for reference only):\n{result.text_wrapped}\n\n"
# #EXT-038-REQ-4 End


# #EXT-038-REQ-2 End
