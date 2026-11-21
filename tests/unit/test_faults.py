from fabricx.faults import CATALOGUE, get


def test_catalogue_has_at_least_12_complete_faults():
    assert len(CATALOGUE) >= 12
    ids = [x.id for x in CATALOGUE]
    assert len(ids) == len(set(ids))
    for x in CATALOGUE:
        assert x.name and x.layer and x.cause_key and x.how and x.symptom and x.first_evidence
        assert callable(x.inject) and callable(x.restore) and x.settle_s > 0
        assert isinstance(x.expected_failing, list)
    assert get("f08").cause_key == "rt-mismatch"


def test_cause_keys_are_unique():
    keys = [x.cause_key for x in CATALOGUE]
    assert len(keys) == len(set(keys))


def test_bundle_layout():
    """The latest evidence bundle on disk has the files the blueprint (10.2) requires."""
    from pathlib import Path

    import pytest
    runs = sorted(Path("artifacts/runs").glob("*_F*"))
    if not runs:
        pytest.skip("no evidence bundles yet (run `fabricx run-fault F02`)")
    d = runs[-1]
    for rel in ("manifest.json", "timeline.json", "report.md", "baseline", "during/diagnosis.json", "after"):
        assert (d / rel).exists(), f"{d}: missing {rel}"
