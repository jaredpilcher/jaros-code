"""EXT-044: Durable conversation sessions -- continue / resume / fork / name.

OFFLINE -- no live model. Store-level behavior is exercised directly against
`harness.session` (isolated to a tmp `SESSIONS_DIR`, mirroring
tests/test_ext036_cli_session.py). CLI-level flag routing (`-c`/`-r`/`--fork`) is exercised via
`harness.cli.main()` with `JcodeCli` monkeypatched to a stub class (mirrors
tests/test_ext043_headless.py's stubbing approach) so no live Runtime/LLM/agent is constructed.
The "resumed prior turns appear in context" plumbing is exercised with a REAL (unstubbed)
`JcodeCli` + a stub orchestrator, mirroring tests/test_ext036_cli_session.py.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.cli as cli_mod
import harness.session as sess_mod
from harness.cli import JcodeCli, _parse_session_flags, _resolve_session_target, main
from harness.session import (
    Session,
    fork_session,
    load_session,
    most_recent_session_id,
    resolve_session_ref,
    save_session,
    set_session_name,
)


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Every test in this file persists sessions under a throwaway tmp dir, never the real
    .jaros-data/sessions/ (mirrors the other EXT-036/043 session test files)."""
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path)
    yield tmp_path


# =====================================================================================
# (1) durable session store: create -> persist -> list (REQ-1)
# =====================================================================================

def test_create_persist_list_roundtrip(tmp_path):
    s = Session(name="my-feature")
    s.append("user", "hello")
    save_session(s)

    assert (tmp_path / f"{s.id}.json").is_file()
    assert (tmp_path / "index.json").is_file()

    rows = sess_mod.list_sessions(limit=10)
    ids = [r["id"] for r in rows]
    assert s.id in ids
    row = next(r for r in rows if r["id"] == s.id)
    assert row["name"] == "my-feature"
    assert row["turns"] == 1


def test_session_without_name_or_timestamps_round_trips_unchanged():
    """A Session constructed with no new EXT-044 fields behaves exactly as before this spec."""
    s = Session()
    assert s.name is None
    assert isinstance(s.created, float) and isinstance(s.last_active, float)


def test_pre_ext044_session_file_loads_cleanly(tmp_path):
    """A session file saved WITHOUT name/created/last_active (pre-EXT-044 shape) still loads."""
    sid = "legacy1234"
    (tmp_path / f"{sid}.json").write_text(
        json.dumps({"id": sid, "turns": [{"role": "user", "text": "hi", "ts": 1.0}]}),
        encoding="utf-8",
    )
    s = load_session(sid)
    assert s is not None
    assert s.name is None
    assert s.turns[0]["text"] == "hi"


# =====================================================================================
# (2) `-c` resumes the most recent session (REQ-2)
# =====================================================================================

def test_most_recent_session_id_picks_the_latest():
    older = Session()
    older.last_active = 100.0
    save_session(older)

    newer = Session()
    newer.last_active = 200.0
    save_session(newer)

    assert most_recent_session_id() == newer.id


def test_most_recent_session_id_none_when_store_empty():
    assert most_recent_session_id() is None


def test_resolve_target_continue_flag_picks_most_recent():
    older = Session()
    older.last_active = 1.0
    save_session(older)
    newer = Session()
    newer.last_active = 2.0
    save_session(newer)

    sid, err = _resolve_session_target(True, None, None, None)
    assert err is None
    assert sid == newer.id


def test_resolve_target_continue_flag_errors_on_empty_store():
    sid, err = _resolve_session_target(True, None, None, None)
    assert sid is None
    assert err and "no saved sessions" in err.lower()


# =====================================================================================
# (3) `-r <id>` and `-r <name>` resume the right one (REQ-3)
# =====================================================================================

def test_resolve_session_ref_by_id():
    s = Session()
    save_session(s)
    assert resolve_session_ref(s.id) == s.id


def test_resolve_session_ref_by_name():
    s = Session()
    save_session(s)
    set_session_name(s, "widget-fix")
    assert resolve_session_ref("widget-fix") == s.id


def test_resolve_session_ref_unknown_returns_none():
    assert resolve_session_ref("no-such-ref") is None


def test_resolve_target_dash_r_by_id():
    s = Session()
    save_session(s)
    sid, err = _resolve_session_target(False, s.id, None, None)
    assert err is None
    assert sid == s.id


def test_resolve_target_dash_r_by_name():
    s = Session()
    save_session(s)
    set_session_name(s, "my-session")
    sid, err = _resolve_session_target(False, "my-session", None, None)
    assert err is None
    assert sid == s.id


def test_resolve_target_dash_r_unknown_is_honest_error():
    sid, err = _resolve_session_target(False, "totally-unknown", None, None)
    assert sid is None
    assert err and "totally-unknown" in err


def test_legacy_resume_flag_unchanged_no_error_on_unknown_id():
    """The OLD --resume <id> flag (no -c/-r/--fork) keeps its exact pre-EXT-044 semantics: an
    unknown id is passed through unchanged (JcodeCli creates a fresh session under it), never an
    error."""
    sid, err = _resolve_session_target(False, None, None, "brand-new-id-never-seen")
    assert err is None
    assert sid == "brand-new-id-never-seen"


def test_no_flags_at_all_resolves_to_none_fresh_session():
    sid, err = _resolve_session_target(False, None, None, None)
    assert sid is None
    assert err is None


# =====================================================================================
# (4) `--fork` creates a NEW id with a COPY, original unchanged (REQ-4)
# =====================================================================================

def test_fork_session_copies_transcript_into_a_new_id():
    src = Session()
    src.append("user", "original topic")
    src.append("assistant", "ok")
    save_session(src)

    forked = fork_session(src.id)
    assert forked is not None
    assert forked.id != src.id
    assert forked.turns == src.turns


def test_fork_session_leaves_original_untouched():
    src = Session()
    src.append("user", "original topic")
    save_session(src)
    original_turns = list(load_session(src.id).turns)

    forked = fork_session(src.id)
    forked.append("user", "a new branch-only message")
    save_session(forked)

    reloaded_src = load_session(src.id)
    assert reloaded_src.turns == original_turns
    assert not any("branch-only" in t.get("text", "") for t in reloaded_src.turns)


def test_fork_session_by_name():
    src = Session()
    src.append("user", "hi")
    save_session(src)
    set_session_name(src, "base-session")

    forked = fork_session("base-session")
    assert forked is not None
    assert forked.id != src.id
    assert forked.turns == src.turns


def test_fork_session_unknown_ref_returns_none():
    assert fork_session("no-such-session") is None


def test_resolve_target_fork_with_explicit_ref():
    src = Session()
    src.append("user", "x")
    save_session(src)

    sid, err = _resolve_session_target(False, None, src.id, None)
    assert err is None
    assert sid != src.id   # a NEW session id
    assert load_session(sid).turns == src.turns


def test_resolve_target_fork_defaults_to_most_recent_when_no_ref():
    older = Session()
    older.last_active = 1.0
    save_session(older)
    newer = Session()
    newer.append("user", "the recent one")
    newer.last_active = 2.0
    save_session(newer)

    sid, err = _resolve_session_target(False, None, "", None)
    assert err is None
    assert sid not in (older.id, newer.id)
    assert load_session(sid).turns == newer.turns


def test_resolve_target_fork_unknown_ref_is_honest_error():
    sid, err = _resolve_session_target(False, None, "no-such-ref", None)
    assert sid is None
    assert err and "no-such-ref" in err


def test_resolve_target_fork_empty_store_is_honest_error():
    sid, err = _resolve_session_target(False, None, "", None)
    assert sid is None
    assert err and "fork" in err.lower()


# =====================================================================================
# (5) resumed prior turns appear in the assembled context (REQ-5)
# =====================================================================================

class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
    def __init__(self, action: str = "help", arg: str = "") -> None:
        self.calls: list[dict] = []
        self._action = action
        self._arg = arg

    def decide(self, context):
        self.calls.append(context)
        return [_FakeDecision(self._action, self._arg)]


def _stub_cli(session_id=None) -> tuple[JcodeCli, _StubOrchestrator]:
    cli = JcodeCli(session_id=session_id)
    stub = _StubOrchestrator()
    cli._load_agent = lambda filename, llm: stub
    return cli, stub


def test_continue_resumed_session_context_includes_prior_turns():
    original, _ = _stub_cli()
    original.handle("original topic discussed earlier")
    sid = original.session.id

    resolved_id, err = _resolve_session_target(True, None, None, None)
    assert err is None
    assert resolved_id == sid

    resumed, stub = _stub_cli(session_id=resolved_id)
    resumed.handle("a follow-up question")
    ctx = stub.calls[0]
    assert any("original topic discussed earlier" in h["text"] for h in ctx["history"])


def test_resume_by_name_context_includes_prior_turns():
    original, _ = _stub_cli()
    original.handle("the deploy target is staging-west")
    set_session_name(original.session, "deploy-chat")

    resolved_id, err = _resolve_session_target(False, "deploy-chat", None, None)
    assert err is None

    resumed, stub = _stub_cli(session_id=resolved_id)
    resumed.handle("what did we decide?")
    ctx = stub.calls[0]
    assert any("staging-west" in h["text"] for h in ctx["history"])


def test_forked_session_context_includes_source_prior_turns_independently():
    original, _ = _stub_cli()
    original.handle("shared context from the original")
    sid = original.session.id

    resolved_id, err = _resolve_session_target(False, None, sid, None)
    assert err is None
    assert resolved_id != sid

    forked_cli, stub = _stub_cli(session_id=resolved_id)
    forked_cli.handle("continuing in the fork")
    ctx = stub.calls[0]
    assert any("shared context from the original" in h["text"] for h in ctx["history"])

    # the original session's own context is unaffected by what happens in the fork
    original.handle("only in the original now")
    assert any("only in the original now" in t.get("text", "") for t in load_session(sid).turns)
    assert not any(
        "only in the original now" in t.get("text", "")
        for t in load_session(resolved_id).turns
    )  # never leaked into the fork


# =====================================================================================
# CLI-level flag routing via main() (JcodeCli stubbed -- mirrors test_ext043_headless.py)
# =====================================================================================

class _StubCliCls:
    response = "stub response text"
    model = "stub-model"
    raise_on_handle = False
    raise_on_init = False
    last_request = None
    last_session_id = None
    constructed = False

    def __init__(self, session_id=None, stream=False):  # stream: EXT-045-REQ-1
        _StubCliCls.constructed = True
        if _StubCliCls.raise_on_init:
            raise RuntimeError("stub init failure")
        _StubCliCls.last_session_id = session_id
        self.session = Session(id=session_id)

    def handle(self, request):
        _StubCliCls.last_request = request
        if _StubCliCls.raise_on_handle:
            raise RuntimeError("stub handle failure")
        return _StubCliCls.response


@pytest.fixture(autouse=True)
def _reset_stub_cli():
    _StubCliCls.raise_on_handle = False
    _StubCliCls.raise_on_init = False
    _StubCliCls.last_request = None
    _StubCliCls.last_session_id = None
    _StubCliCls.constructed = False
    yield


@pytest.fixture()
def stub_jcode_cli(monkeypatch):
    monkeypatch.setattr(cli_mod, "JcodeCli", _StubCliCls)
    return _StubCliCls


def test_cli_continue_resumes_most_recent(monkeypatch, stub_jcode_cli):
    older = Session()
    older.last_active = 1.0
    save_session(older)
    newer = Session()
    newer.last_active = 2.0
    save_session(newer)

    monkeypatch.setattr("sys.argv", ["harness.cli", "-c", "keep", "going"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id == newer.id
    assert _StubCliCls.last_request == "keep going"


def test_cli_dash_r_resumes_by_id(monkeypatch, stub_jcode_cli):
    s = Session()
    save_session(s)
    monkeypatch.setattr("sys.argv", ["harness.cli", "-r", s.id, "hello"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id == s.id


def test_cli_dash_r_resumes_by_name(monkeypatch, stub_jcode_cli):
    s = Session()
    save_session(s)
    set_session_name(s, "my-named-session")
    monkeypatch.setattr("sys.argv", ["harness.cli", "-r", "my-named-session", "hello"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id == s.id


def test_cli_fork_creates_new_session_id(monkeypatch, stub_jcode_cli):
    s = Session()
    s.append("user", "original")
    save_session(s)
    monkeypatch.setattr("sys.argv", ["harness.cli", "--fork", s.id, "continue in fork"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id is not None
    assert _StubCliCls.last_session_id != s.id
    assert _StubCliCls.last_request == "continue in fork"
    # original untouched
    orig = load_session(s.id)
    assert len(orig.turns) == 1
    assert orig.turns[0]["text"] == "original"


def test_cli_unknown_ref_is_honest_error_no_crash(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "-r", "no-such-session-xyz", "hello"])
    code = main()
    assert code != 0
    assert _StubCliCls.constructed is False   # JcodeCli was NEVER constructed
    out = capsys.readouterr().out
    assert "error" in out.lower()


def test_cli_unknown_fork_ref_is_honest_error_no_crash(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "--fork", "no-such-session-xyz", "hi"])
    code = main()
    assert code != 0
    assert _StubCliCls.constructed is False
    out = capsys.readouterr().out
    assert "error" in out.lower()


def test_cli_continue_empty_store_is_honest_error(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "-c", "hello"])
    code = main()
    assert code != 0
    assert _StubCliCls.constructed is False
    out = capsys.readouterr().out
    assert "error" in out.lower()


def test_cli_unknown_ref_json_format_is_honest_error(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv",
                         ["harness.cli", "--output-format", "json", "-r", "nope", "hi"])
    code = main()
    assert code != 0
    obj = json.loads(capsys.readouterr().out.strip())
    assert obj["ok"] is False
    assert "error" in obj


# =====================================================================================
# backward-compat: fresh run (no flags) is byte-unchanged
# =====================================================================================

def test_fresh_run_no_flags_unchanged(monkeypatch, stub_jcode_cli, capsys):
    monkeypatch.setattr("sys.argv", ["harness.cli", "plain", "request"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id is None
    out = capsys.readouterr().out
    assert out.strip() == "stub response text"


def test_legacy_resume_flag_still_works_unchanged(monkeypatch, stub_jcode_cli):
    """--resume <id> (pre-EXT-044) is untouched: passes straight through, no existence check."""
    monkeypatch.setattr("sys.argv", ["harness.cli", "--resume", "sess-1", "hi", "there"])
    code = main()
    assert code == 0
    assert _StubCliCls.last_session_id == "sess-1"
    assert _StubCliCls.last_request == "hi there"


def test_repl_call_shape_unchanged_when_no_flags(monkeypatch):
    """main()'s call to repl() keeps its exact pre-EXT-044 shape: session_id only."""
    monkeypatch.setattr("sys.argv", ["harness.cli"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    called = {}

    def fake_repl(session_id=None):
        called["session_id"] = session_id
        return 0

    monkeypatch.setattr(cli_mod, "repl", fake_repl)
    code = main()
    assert code == 0
    assert called == {"session_id": None}


def test_repl_call_shape_unchanged_when_continuing(monkeypatch):
    """Even with -c (REPL, no trailing request), repl() is still called with session_id only."""
    s = Session()
    save_session(s)
    monkeypatch.setattr("sys.argv", ["harness.cli", "-c"])
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    called = {}

    def fake_repl(session_id=None):
        called["session_id"] = session_id
        return 0

    monkeypatch.setattr(cli_mod, "repl", fake_repl)
    code = main()
    assert code == 0
    assert called == {"session_id": s.id}


# =====================================================================================
# `_parse_session_flags` unit coverage
# =====================================================================================

def test_parse_session_flags_no_flags_leaves_rest_unchanged():
    continue_flag, resume_ref, fork_ref, name, rest = _parse_session_flags(["fix", "it"])
    assert continue_flag is False
    assert resume_ref is None
    assert fork_ref is None
    assert name is None
    assert rest == ["fix", "it"]


def test_parse_session_flags_continue_shorthand_and_longhand():
    c1, *_ = _parse_session_flags(["-c", "req"])
    c2, *_ = _parse_session_flags(["--continue", "req"])
    assert c1 is True
    assert c2 is True


def test_parse_session_flags_dash_r_extracted():
    _, resume_ref, _, _, rest = _parse_session_flags(["-r", "abc123", "hello"])
    assert resume_ref == "abc123"
    assert rest == ["hello"]


def test_parse_session_flags_name_extracted():
    *_, name, rest = _parse_session_flags(["--name", "my-session", "do", "thing"])
    assert name == "my-session"
    assert rest == ["do", "thing"]


def test_parse_session_flags_fork_no_value_leaves_request_intact():
    """--fork with no resolvable following token doesn't eat the plain-language request."""
    _, _, fork_ref, _, rest = _parse_session_flags(["--fork", "do", "something", "useful"])
    assert fork_ref == ""
    assert rest == ["do", "something", "useful"]


def test_parse_session_flags_fork_with_resolvable_value(tmp_path):
    s = Session()
    save_session(s)
    _, _, fork_ref, _, rest = _parse_session_flags(["--fork", s.id, "continue"])
    assert fork_ref == s.id
    assert rest == ["continue"]


# =====================================================================================
# never-raises on a missing/corrupt index
# =====================================================================================

def test_never_raises_on_corrupt_index(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.json").write_text("{ this is not : valid json", encoding="utf-8")

    assert sess_mod._load_index() == {}
    assert most_recent_session_id() is None
    assert resolve_session_ref("anything") is None
    assert sess_mod.list_sessions(limit=5) == []
    assert fork_session("anything") is None


def test_never_raises_on_missing_index(tmp_path):
    # index.json simply doesn't exist yet
    assert most_recent_session_id() is None
    assert resolve_session_ref("whatever") is None


def test_save_session_never_raises_on_unwritable_dir(tmp_path, monkeypatch):
    """A sessions "directory" that is actually a FILE can't be mkdir'd into -- save_session
    must degrade gracefully (best-effort) rather than raise."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")   # a file, not a dir
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", blocked / "sessions")
    s = Session()
    save_session(s)   # must not raise
