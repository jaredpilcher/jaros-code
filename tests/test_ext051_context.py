"""EXT-051: context management for long sessions -- `@path`/`@dir/` references + `/compact`.

OFFLINE -- no live model. `harness.atrefs` is pure deterministic string composition, exercised
directly with fake `read_file`/`list_dir` callables (no host I/O at all). CLI-level integration
tests reuse the `test_ext050_subagents.py` stubbing pattern (`cli._load_agent` replaced by a
recording stub orchestrator) so `@`-expansion is proven to reach the router's augmented context for
BOTH a typed plain request and a skill-substituted rendered template, through real files on disk
read via the EXISTING gated `fs.read`/`fs.list` tools. `compact_session` is exercised against
`harness.session`'s real `Session`/persistence machinery with `_summarize_turns` stubbed so no
model call ever happens.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness import atrefs as ar
from harness import session as sess_mod
from harness.cli import JcodeCli


class _FakeDecision:
    def __init__(self, action: str, arg: str) -> None:
        self.payload = {"action": action, "arg": arg}


class _StubOrchestrator:
    """Records every context dict `decide()` receives; routes to a fixed action."""

    def __init__(self, action: str = "help", arg: str = "") -> None:
        self.calls: "list[dict]" = []
        self._action = action
        self._arg = arg

    def decide(self, context):
        self.calls.append(context)
        return [_FakeDecision(self._action, self._arg)]


def _stub_cli(action: str = "help", arg: str = "") -> "tuple[JcodeCli, _StubOrchestrator]":
    cli = JcodeCli()
    stub = _StubOrchestrator(action, arg)
    cli._load_agent = lambda filename, llm: stub   # any agent name -> the stub
    return cli, stub


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors
    test_ext050_subagents.py)."""
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    """Point Path.home() at an isolated tmp dir so these tests never read/write anything under
    the REAL ~/.jcode/ on the machine running the suite (mirrors test_ext050_subagents.py)."""
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    import harness.skills as sk
    monkeypatch.setattr(sk.Path, "home", staticmethod(lambda: fake_home))
    import harness.jcode_md as jm
    monkeypatch.setattr(jm.Path, "home", staticmethod(lambda: fake_home))
    import harness.subagents as sa
    monkeypatch.setattr(sa.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def _write_skill(root, name: str, body: str) -> None:
    d = root / ".jcode" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(body, encoding="utf-8")


def _make_session_with_turns(n: int) -> "sess_mod.Session":
    s = sess_mod.Session()
    for i in range(n):
        s.append("user", f"turn {i} " + ("x" * 20))
    return s


# =====================================================================================
# harness.atrefs.find_at_refs -- pure regex token scan
# =====================================================================================

def test_find_at_refs_basic_and_dedup():
    assert ar.find_at_refs("explain @foo.py and also @foo.py again") == ["foo.py"]


def test_find_at_refs_strips_trailing_sentence_punctuation():
    assert ar.find_at_refs("please check @foo.py.") == ["foo.py"]
    assert ar.find_at_refs("see @bar.py, then fix it") == ["bar.py"]


def test_find_at_refs_preserves_trailing_slash_for_directory_ref():
    assert ar.find_at_refs("look at @src/") == ["src/"]


def test_find_at_refs_never_matches_mid_word_at():
    assert ar.find_at_refs("email me at foo@bar.com") == []


def test_find_at_refs_none_and_empty_never_raises():
    assert ar.find_at_refs(None) == []
    assert ar.find_at_refs("") == []


def test_find_at_refs_multiple_distinct_refs_first_seen_order():
    assert ar.find_at_refs("compare @a.py and @b.py then @a.py") == ["a.py", "b.py"]


# =====================================================================================
# harness.atrefs.expand_at_refs -- pure string composition over injected callables
# =====================================================================================

def test_expand_at_refs_inlines_file_content():
    def read_file(ref):
        assert ref == "foo.py"
        return "print('hi')", False

    def list_dir(ref):
        raise AssertionError("a file ref must never call list_dir")

    out = ar.expand_at_refs("explain @foo.py", read_file, list_dir)
    assert out.startswith("explain @foo.py")     # original @token left in place
    assert "print('hi')" in out
    assert "not found" not in out


def test_expand_at_refs_truncates_and_notes_overflow():
    long_content = "x" * 100

    out = ar.expand_at_refs("read @big.py", lambda ref: (long_content, False), None, max_chars=10)
    assert "[truncated]" in out
    assert out.count("x") == 10


def test_expand_at_refs_missing_file_degrades_to_honest_annotation():
    out = ar.expand_at_refs("read @missing.py", lambda ref: (None, False), None)
    assert "@missing.py" in out         # token left in place, not rewritten
    assert "not found" in out


def test_expand_at_refs_read_file_raising_degrades_honestly_never_raises():
    def boom(ref):
        raise IOError("boom")

    out = ar.expand_at_refs("read @bad.py", boom, None)
    assert "not found" in out


def test_expand_at_refs_dir_ref_calls_list_dir_and_bounds_entries():
    entries = [f"file{i}.py" for i in range(100)]

    def read_file(ref):
        raise AssertionError("a directory ref must never call read_file")

    out = ar.expand_at_refs("look at @src/", read_file, lambda ref: (entries, False),
                             max_dir_entries=5)
    assert "[truncated]" in out
    assert out.count("file") == 5


def test_expand_at_refs_missing_dir_degrades_honestly():
    out = ar.expand_at_refs("look at @nosuchdir/", None, lambda ref: (None, False))
    assert "not found" in out


def test_expand_at_refs_no_refs_is_byte_identical():
    text = "just a plain request with no refs at all"
    out = ar.expand_at_refs(text, lambda r: (None, False), lambda r: (None, False))
    assert out == text


def test_expand_at_refs_none_text_is_safe():
    assert ar.expand_at_refs(None, lambda r: (None, False), lambda r: (None, False)) == ""


# =====================================================================================
# CLI integration: @-expansion reaches the router for BOTH typed + skill-substituted requests
# =====================================================================================

def test_at_ref_read_adapter_reads_a_real_file_through_the_gated_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hello.txt").write_text("hello world", encoding="utf-8")
    cli, _stub = _stub_cli()
    content, truncated = cli._at_ref_read("hello.txt")
    assert content == "hello world"
    assert truncated is False


def test_at_ref_read_adapter_missing_file_is_honest_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _stub = _stub_cli()
    content, truncated = cli._at_ref_read("nope.txt")
    assert content is None
    assert truncated is False


def test_at_ref_list_adapter_lists_a_real_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.py").write_text("x", encoding="utf-8")
    cli, _stub = _stub_cli()
    entries, _truncated = cli._at_ref_list("sub/")
    assert entries is not None
    assert any("a.py" in e for e in entries)


def test_route_plain_expands_at_ref_for_a_typed_plain_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "note.py").write_text("def foo(): pass\n", encoding="utf-8")
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.handle("explain @note.py")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    assert "explain @note.py" in routed_request
    assert "def foo(): pass" in routed_request
    assert isinstance(out, str)


def test_route_plain_expands_at_ref_for_a_skill_substituted_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "note.py").write_text("def foo(): pass\n", encoding="utf-8")
    _write_skill(tmp_path, "reviewme", "Please look at @note.py and consider: $ARGUMENTS")
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.dispatch("/reviewme check it carefully")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    assert "def foo(): pass" in routed_request
    assert "check it carefully" in routed_request
    assert isinstance(out, str)


def test_route_plain_at_ref_to_a_missing_file_never_crashes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.handle("explain @nosuchfile.py")

    assert len(stub.calls) == 1
    routed_request = stub.calls[0]["request"]
    assert "not found" in routed_request
    assert isinstance(out, str)


def test_route_plain_with_no_at_ref_is_byte_identical_routing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, stub = _stub_cli(action="help", arg="")

    out = cli.handle("just a plain request with no refs")

    assert len(stub.calls) == 1
    # no history/memory/project_md/jcode_md exist for a fresh repo -> _augment_with_history is a
    # no-op too, so the routed request is untouched (matches pre-EXT-051 behavior exactly)
    assert stub.calls[0]["request"] == "just a plain request with no refs"
    assert isinstance(out, str)


# =====================================================================================
# harness.session.compact_session -- reuses the EXISTING _summarize_turns()/condense() mechanism
# =====================================================================================

def test_compact_session_folds_older_turns_and_persists(tmp_path, monkeypatch):
    session = _make_session_with_turns(20)
    before_turns = len(session.turns)
    before_chars = sum(len(t["text"]) for t in session.turns)

    calls = []

    def fake_summarize(turns, llm=None):
        calls.append(len(turns))
        return "FAKE SUMMARY TEXT"

    monkeypatch.setattr(sess_mod, "_summarize_turns", fake_summarize)

    result = sess_mod.compact_session(session, keep=6)

    assert result["compacted"] is True
    assert result["before_turns"] == before_turns
    assert result["before_chars"] == before_chars
    assert result["after_turns"] == 7          # 1 summary turn + 6 recent turns
    assert result["after_turns"] < result["before_turns"]
    assert result["after_chars"] < result["before_chars"]
    assert calls == [before_turns - 6]          # _summarize_turns got exactly the OLDER turns

    assert len(session.turns) == 7
    assert session.turns[0]["role"] == "summary"
    assert session.turns[0]["text"] == "FAKE SUMMARY TEXT"
    assert session.turns[-1]["text"] == f"turn {before_turns - 1} " + ("x" * 20)

    reloaded = sess_mod.load_session(session.id)
    assert reloaded is not None
    assert len(reloaded.turns) == 7
    assert reloaded.turns[0]["role"] == "summary"


def test_compact_session_short_session_is_an_honest_noop(tmp_path, monkeypatch):
    session = _make_session_with_turns(3)

    def fake_summarize(turns, llm=None):
        raise AssertionError("_summarize_turns must never be called for a short session")

    monkeypatch.setattr(sess_mod, "_summarize_turns", fake_summarize)

    result = sess_mod.compact_session(session, keep=6)

    assert result["compacted"] is False
    assert result["before_turns"] == result["after_turns"] == 3
    assert result["before_chars"] == result["after_chars"]
    assert "already short" in result["message"]
    assert len(session.turns) == 3   # left entirely unchanged


def test_compact_session_never_raises_on_a_malformed_session():
    class _NotASession:
        pass

    result = sess_mod.compact_session(_NotASession())
    assert result["compacted"] is False
    assert isinstance(result["message"], str)


def test_compact_session_never_raises_when_summarize_fails(tmp_path, monkeypatch):
    session = _make_session_with_turns(20)

    def boom(turns, llm=None):
        raise RuntimeError("model unreachable")

    monkeypatch.setattr(sess_mod, "_summarize_turns", boom)

    result = sess_mod.compact_session(session, keep=6)
    assert result["compacted"] is False
    assert "failed" in result["message"]


# =====================================================================================
# CLI wiring: /compact
# =====================================================================================

def test_cmd_compact_calls_compact_session_and_returns_its_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _stub = _stub_cli()

    calls = []

    def fake_compact(session, llm=None):
        calls.append(session)
        return {"message": "compacted 20 turns (500 chars) -> 7 turns (140 chars)"}

    monkeypatch.setattr(sess_mod, "compact_session", fake_compact)

    out = cli.dispatch("/compact")

    assert calls == [cli.session]
    assert out == "compacted 20 turns (500 chars) -> 7 turns (140 chars)"


def test_cmd_compact_on_a_fresh_short_session_is_an_honest_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli, _stub = _stub_cli()

    out = cli.dispatch("/compact")

    assert "already short" in out.lower() or "nothing to compact" in out.lower()


def test_help_documents_compact_and_at_refs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli.__new__(JcodeCli)   # avoid full __init__ -- /help needs no runtime state
    out = cli.cmd_help("")
    assert "/compact" in out
    assert "@path" in out or "@dir" in out
