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
