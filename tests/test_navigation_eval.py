"""Navigation eval runs green in CI (EXT-004) — guards the AST nav family's subtle behaviors."""


def test_navigation_eval_all_green():
    from harness.navigation_eval import run_navigation_eval
    sc = run_navigation_eval()
    assert sc["solved"] == sc["total"] == 5, sc["perTask"]
