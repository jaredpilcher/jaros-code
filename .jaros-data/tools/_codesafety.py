"""Shared generated-code safety scanner (EXT-001 / REQ-11).

The agents generate code with Gemma 4 2B (`e2b`); that code is written to disk and then
EXECUTED by the test command. So the model's output must be gated too — not just
shell.exec. This deterministic scanner refuses code containing dangerous operations
(network egress, process/shell execution, destructive filesystem ops, dynamic
eval/exec/import) before it is ever written. Underscore-prefixed so the tool loader
skips it as a tool; imported by the write tools.

Scope note: the current workload is pure-function coding tasks + harness self-edits,
which never legitimately need these operations, so refusing them is safe. Override
the policy deliberately via JCODE_ALLOW_UNSAFE_CODE=1 only if a task truly needs it.
"""

from __future__ import annotations

import os
import re

# Dangerous operations a generated solution must not contain (unattended safety).
_UNSAFE_PATTERNS = [
    # process / shell execution
    r"\bos\.system\b", r"\bos\.popen\b", r"\bos\.exec[lv]\w*", r"\bos\.spawn\w*",
    r"\bsubprocess\b", r"\bpty\b", r"\bcommands\b",
    # network egress
    r"\bsocket\b", r"\bsocketserver\b", r"\burllib\b", r"\brequests\b",
    r"\bhttp\.client\b", r"\bhttplib\b", r"\bftplib\b", r"\bsmtplib\b",
    r"\bparamiko\b", r"\btelnetlib\b", r"\bxmlrpc\b", r"\basyncio\.open_connection\b",
    # destructive filesystem
    r"\bshutil\.rmtree\b", r"\bos\.remove\b", r"\bos\.unlink\b",
    r"\bos\.rmdir\b", r"\bos\.removedirs\b", r"\brm\s+-rf\b",
    # dynamic execution / unsafe deserialization / FFI
    r"\beval\s*\(", r"\bexec\s*\(", r"\b__import__\s*\(", r"\bcompile\s*\(",
    r"\bctypes\b", r"\bcffi\b", r"\bmarshal\b", r"\bpickle\.loads\b",
    # opening absolute/UNC paths for writing outside the workdir
    r"open\s*\(\s*['\"](?:/|[A-Za-z]:\\\\|\\\\\\\\)",
]
_UNSAFE_RE = re.compile("|".join(_UNSAFE_PATTERNS))


def unsafe_reason(code: str) -> str | None:
    """Return the matched dangerous token if ``code`` is unsafe, else None.

    Bypassable only by the explicit JCODE_ALLOW_UNSAFE_CODE=1 escape hatch.
    """
    if os.environ.get("JCODE_ALLOW_UNSAFE_CODE") == "1":
        return None
    if not isinstance(code, str):
        return None
    m = _UNSAFE_RE.search(code)
    return m.group(0) if m else None
