"""Spec-driven (jarify-flow) loop (EXT-009) — deterministic check of the structured flow."""


def test_spec_driven_already_green(tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_m.py").write_text(
        "from m import f\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8")
    from harness.spec_loop import spec_driven_loop
    r = spec_driven_loop("make sure it works", str(tmp_path))
    assert r["solved"] is True and r["flow"] == "already-green"
