#!/usr/bin/env python3
"""Focus-independent phone notify via ntfy (owner directive 2026-07-01).

The harness PushNotification tool is auto-suppressed while the terminal has OS focus.
ntfy is a real phone push that arrives regardless of focus. This sender reads the
owner's private topic from a GITIGNORED config (never in the repo) and POSTs the
message to https://ntfy.sh/<topic> (or a self-hosted base URL). Stdlib only.

Setup (one-time, owner):
  1. Install the free "ntfy" app (iOS/Android) and subscribe to a hard-to-guess topic,
     e.g.  jcode-<something-random>.
  2. Put it in a gitignored file OUTSIDE the repo (NEVER commit):
       C:/Users/jared/.claude/ntfy.env   with a line:  NTFY_TOPIC=jcode-<random>
     (optional: NTFY_BASE=https://ntfy.sh  — override for a self-hosted server)
     — or just set the env var NTFY_TOPIC.

Usage:
  python scripts/notify.py "message body" ["optional title"]
  echo "body" | python scripts/notify.py
Exit 0 on delivery, 2 if unconfigured (prints how to configure), 1 on send error.
"""
import os
import sys
import urllib.request

ENV_FILE = os.path.expanduser(r"~/.claude/ntfy.env")


def _load_topic():
    topic = os.environ.get("NTFY_TOPIC")
    base = os.environ.get("NTFY_BASE")
    if (not topic) and os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "NTFY_TOPIC" and not topic:
                topic = v
            elif k == "NTFY_BASE" and not base:
                base = v
    return topic, (base or "https://ntfy.sh").rstrip("/")


def send(message: str, title: str | None = None) -> int:
    topic, base = _load_topic()
    if not topic:
        print(
            "notify: NO TOPIC configured. Install the ntfy app, pick a topic, and put\n"
            f"  NTFY_TOPIC=<your-topic>\nin {ENV_FILE} (gitignored) or the NTFY_TOPIC env var.",
            file=sys.stderr,
        )
        return 2
    # HTTP headers must be latin-1-encodable; titles often carry em-dashes/unicode from commit
    # subjects, so sanitize the Title to ASCII (the utf-8 BODY is unaffected) rather than 500 on send.
    safe_title = (title or "jaros-code").encode("ascii", "replace").decode("ascii")
    req = urllib.request.Request(
        f"{base}/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": safe_title, "Priority": "default"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
        print(f"notify: sent to {base}/{topic}" if ok else f"notify: HTTP {resp.status}")
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        print(f"notify: send failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    msg = args[0] if args else sys.stdin.read().strip()
    ttl = args[1] if len(args) > 1 else None
    if not msg:
        print("notify: empty message", file=sys.stderr)
        sys.exit(1)
    sys.exit(send(msg, ttl))
