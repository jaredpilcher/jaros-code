"""EXT-039 REQ-1: offline tests for the SQLite datastore acceptance oracle.

Every fixture here is a small, hand-written CLI script written to a temp directory -- never a live
``build_system``/gemma run (that is an explicit, separate manual smoke, not part of this pytest
suite). No external service, no network: stdlib ``sqlite3`` only.
"""

# #EXT-039-REQ-1 Start
# TASK-1
import sys
import textwrap
from pathlib import Path

from harness.datastore_oracle import (
    DatastoreInfo,
    DatastoreResult,
    count_all_rows,
    detect_sqlite_datastore,
    verify_persistence,
)

PY = sys.executable or "python"


def _write_main(root: Path, source: str) -> None:
    (root / "main.py").write_text(textwrap.dedent(source), encoding="utf-8")


GOOD_CLI = """
    import sqlite3, sys

    def _conn():
        c = sqlite3.connect("notes.db")
        c.execute("CREATE TABLE IF NOT EXISTS notes (text TEXT)")
        c.commit()
        return c

    def main():
        args = sys.argv[1:]
        if not args:
            return
        conn = _conn()
        cmd = args[0]
        if cmd == "add":
            text = " ".join(args[1:])
            conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
            conn.commit()
            print("added")
        elif cmd == "list":
            for row in conn.execute("SELECT text FROM notes ORDER BY rowid"):
                print(row[0])
        elif cmd == "count":
            n = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            print(n)
        conn.close()

    if __name__ == "__main__":
        main()
"""

# Prints a success message on `add` but never touches sqlite/the db file at all -- the exact
# hollow-persistence class the oracle exists to catch.
HOLLOW_CLI = """
    import sys

    def main():
        args = sys.argv[1:]
        if not args:
            return
        if args[0] == "add":
            print("Saved!")
        elif args[0] == "count":
            print("0")
        elif args[0] == "list":
            pass

    if __name__ == "__main__":
        main()
"""

# Writes real rows to notes.db on `add` (so an IMMEDIATE independent check right after that
# invocation would pass) but silently DROPS and recreates its own table at the start of every
# single invocation -- so any state written by a PRIOR invocation is wiped out by the next one.
# This is a realistic "looks persistent within one run, isn't really" bug, caught specifically by
# the cross-invocation check (a second, fresh CLI call).
RESET_ON_EVERY_RUN_CLI = """
    import sqlite3, sys

    def main():
        conn = sqlite3.connect("notes.db")
        conn.execute("DROP TABLE IF EXISTS notes")
        conn.execute("CREATE TABLE notes (text TEXT)")
        conn.commit()
        args = sys.argv[1:]
        if args and args[0] == "add":
            text = " ".join(args[1:])
            conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
            conn.commit()
            print("added")
        elif args and args[0] == "count":
            n = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            print(n)
        conn.close()

    if __name__ == "__main__":
        main()
"""

BROKEN_CLI = """
    import sys
    raise RuntimeError("boom")
"""


def _row_count_is(n: int):
    return lambda cur: count_all_rows(cur) == n


# --------------------------------------------------------------------------------------------
# verify_persistence -- known-good fixture
# --------------------------------------------------------------------------------------------

def test_verify_persistence_ok_for_known_good_cli(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "note", "one"], None), (["add", "note", "two"], None)],
        assertions=[_row_count_is(2)],
        cross_invocation_cmd=(["count"], None),
        python_exe=PY,
    )
    assert isinstance(result, DatastoreResult)
    assert result.ok is True
    assert result.failures == []
    assert result.rows_checked >= 1


def test_verify_persistence_real_rows_via_sql_tuple_assertion(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "hello", "world"], None)],
        assertions=[("SELECT text FROM notes", [("hello world",)])],
        cross_invocation_cmd=(["count"], None),
        python_exe=PY,
    )
    assert result.ok is True


# --------------------------------------------------------------------------------------------
# THE LOAD-BEARING CATCH -- hollow persistence (prints success, never writes)
# --------------------------------------------------------------------------------------------

def test_verify_persistence_catches_hollow_persistence(tmp_path):
    _write_main(tmp_path, HOLLOW_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "buy", "milk"], None)],
        assertions=[_row_count_is(1)],
        cross_invocation_cmd=(["count"], None),
        python_exe=PY,
    )
    assert result.ok is False
    assert "never" in result.note.lower() or "hollow" in result.note.lower() or \
        "created" in result.note.lower()


# --------------------------------------------------------------------------------------------
# Cross-invocation catch -- state does not survive a fresh process
# --------------------------------------------------------------------------------------------

def test_verify_persistence_catches_reset_on_every_run(tmp_path):
    _write_main(tmp_path, RESET_ON_EVERY_RUN_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "buy", "milk"], None)],
        assertions=[_row_count_is(1)],
        cross_invocation_cmd=(["count"], None),
        python_exe=PY,
    )
    assert result.ok is False
    assert "cross-invocation" in result.note.lower() or "process boundary" in result.note.lower() \
        or "in-memory" in result.note.lower()


# --------------------------------------------------------------------------------------------
# detect_sqlite_datastore
# --------------------------------------------------------------------------------------------

def test_detect_sqlite_datastore_finds_db(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    (tmp_path / "notes.db").write_bytes(b"")
    info = detect_sqlite_datastore(tmp_path)
    assert isinstance(info, DatastoreInfo)
    assert info.uses_sqlite is True
    assert info.db_path == "notes.db"


def test_detect_sqlite_datastore_honestly_returns_none(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    info = detect_sqlite_datastore(tmp_path)
    assert info is None


def test_detect_sqlite_datastore_never_raises_on_garbage(tmp_path):
    assert detect_sqlite_datastore(None) is None
    assert detect_sqlite_datastore(12345) is None
    assert detect_sqlite_datastore(tmp_path / "does_not_exist") is None


# --------------------------------------------------------------------------------------------
# Never-raises discipline
# --------------------------------------------------------------------------------------------

def test_verify_persistence_never_raises_on_missing_entrypoint(tmp_path):
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "x"], None)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result.ok is False
    assert "entrypoint" in result.note.lower()


def test_verify_persistence_never_raises_on_broken_cli(tmp_path):
    _write_main(tmp_path, BROKEN_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "x"], None)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result.ok is False
    assert result.failures == [] or isinstance(result.failures, list)


def test_verify_persistence_never_raises_on_malformed_drive_cmds(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=None,
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result.ok is False

    result2 = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[("not-a-tuple",)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result2.ok is False


def test_verify_persistence_never_raises_on_malformed_assertions(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    result = verify_persistence(
        tmp_path, db_path="notes.db",
        drive_cmds=[(["add", "x"], None)],
        assertions=None,
        python_exe=PY,
    )
    assert result.ok is False


def test_verify_persistence_never_raises_on_invalid_root():
    result = verify_persistence(
        object(), db_path="notes.db",
        drive_cmds=[(["add", "x"], None)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result.ok is False

    result2 = verify_persistence(
        "/this/path/does/not/exist/at/all", db_path="notes.db",
        drive_cmds=[(["add", "x"], None)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result2.ok is False


def test_verify_persistence_never_raises_on_missing_db_path(tmp_path):
    _write_main(tmp_path, GOOD_CLI)
    result = verify_persistence(
        tmp_path, db_path=None,
        drive_cmds=[(["add", "x"], None)],
        assertions=[_row_count_is(1)],
        python_exe=PY,
    )
    assert result.ok is False


# --------------------------------------------------------------------------------------------
# count_all_rows helper
# --------------------------------------------------------------------------------------------

def test_count_all_rows_is_schema_agnostic(tmp_path):
    import sqlite3
    db_file = tmp_path / "t.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE items (name TEXT)")
    conn.execute("CREATE TABLE other (id INTEGER)")
    conn.execute("INSERT INTO items (name) VALUES ('a')")
    conn.execute("INSERT INTO items (name) VALUES ('b')")
    conn.execute("INSERT INTO other (id) VALUES (1)")
    conn.commit()
    cur = conn.cursor()
    assert count_all_rows(cur) == 3
    conn.close()
# #EXT-039-REQ-1 End
