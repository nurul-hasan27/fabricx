"""Resilience: every fault can be injected and fully undone (run on demand: make resilience)."""
import subprocess
import sys
import time

import pytest

from fabricx import collectors, model, validators
from fabricx.faults import CATALOGUE
from fabricx.faults import runner as fr

pytestmark = [pytest.mark.lab, pytest.mark.resilience]
F = model.load()


@pytest.mark.parametrize("fault", CATALOGUE, ids=lambda x: x.id)
def test_every_fault_restores_to_healthy(fault):
    fr.wait_healthy(F)
    state = fr.inject(F, fault)
    time.sleep(min(fault.settle_s, 10))
    fr.restore(F, fault, state)
    fr.wait_healthy(F)
    assert validators.validate(F, collectors.Collector(F).snapshot()) == []
    r = subprocess.run([sys.executable, "-m", "fabricx.cli", "drift"], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout  # config must be back to what the inventory generates
