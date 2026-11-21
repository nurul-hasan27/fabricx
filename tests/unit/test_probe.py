from fabricx.probe import analyze

MS = 1_000_000


def rows(seqs, step_ms=1, start=0):
    return [(s, 0, start + s * step_ms * MS) for s in seqs]


def test_clean_run_no_loss():
    r = analyze(rows(range(100)), sent=100)
    assert r["lost"] == 0 and r["reordered"] == 0 and r["longest_gap_ms"] == 1.0


def test_synthetic_outage_is_measured():
    # packets 40..79 missing -> 40 lost, gap between seq 39 and seq 80 is 41 ms
    r = analyze(rows(list(range(40)) + list(range(80, 100))), sent=100)
    assert r["lost"] == 40
    assert r["longest_gap_ms"] == 41.0


def test_reorder_counted():
    r = analyze([(0, 0, 0), (2, 0, MS), (1, 0, 2 * MS), (3, 0, 3 * MS)], sent=4)
    assert r["reordered"] == 1 and r["lost"] == 0


def test_duplicates_not_double_counted():
    r = analyze([(0, 0, 0), (0, 0, MS), (1, 0, 2 * MS)], sent=2)
    assert r["received"] == 2 and r["duplicates"] == 1 and r["lost"] == 0


def test_nothing_received_is_total_loss():
    assert analyze([], sent=50)["lost"] == 50
