"""The blind-drill score is read from the stored drill results (produced by `fabricx drill`)."""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.lab


def latest():
    files = sorted(Path("experiments/E9/results").glob("drill_seed*.json"))
    if not files:
        pytest.skip("no drill results yet (run `fabricx drill --seed 1`)")
    return json.loads(files[-1].read_text())


def test_blind_drill_score_meets_target():
    d = latest()
    assert d["total"] >= 12
    assert d["localised"] >= 10, [r["fault"] for r in d["results"] if not r["localised"]]
