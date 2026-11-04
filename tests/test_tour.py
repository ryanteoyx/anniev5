"""The "Play demo" tour depends on specific sample documents and case states. Fails if a sample change breaks the script.

    python tests/test_tour.py     (or: pytest tests/)
"""
import sys

from harness import ROOT, fresh

sys.path.insert(0, str(ROOT))
import tour  # noqa: E402


def test_tour_data_has_a_case_at_every_stage():
    annie, con, _ = fresh()
    chosen = tour._seed(con)
    counts = annie.counts(con)
    assert counts["s1"] and counts["s2"] and counts["calloff"] and counts["review"], counts
    assert [r["case_id"] for r in annie.case_rows(con, [annie.S_DONE])] == [chosen["complete"]]
    assert len(annie.archive_rows(con)) == 1
    assert chosen["pending"] in [r["case_id"] for r in annie.case_rows(con, [annie.S_GR])]
    assert chosen["open"] in [r["case_id"] for r in annie.case_rows(con, [annie.S_OPEN_PO])]


def test_every_stop_is_complete():
    stops = tour.steps(dict(open="CASE-1", pending="CASE-2", complete="CASE-3", calloff="CALL-1"))
    assert stops
    for s in stops:
        assert s["title"] and s["text"] and s["path"] and s["focus"], s


def main():
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"pass  {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
