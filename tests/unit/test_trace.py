from fabricx import trace


def test_every_spec_points_at_real_tests_and_evidence_path_is_a_string():
    specs = trace.load_specs()
    assert len(specs) >= 14
    ids = trace.collected_ids()
    md, problems = trace.build(specs, ids, {})
    assert problems == [], problems
    assert all(s["id"].startswith("REQ-") and s["tests"] and s["pass"] and s["steps"] for s in specs)
    assert len({s["id"] for s in specs}) == len(specs)


def test_build_reports_missing_test():
    _, problems = trace.build([{"id": "REQ-X", "title": "t", "tests": ["tests/nope.py::test_x"], "evidence": []}], [], {})
    assert problems
