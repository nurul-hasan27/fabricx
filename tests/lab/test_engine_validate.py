"""The validation engine against the live fabric: collects state, compares with inventory intent."""
import pytest

from fabricx import collectors, model, validators

pytestmark = [pytest.mark.lab, pytest.mark.smoke]


def test_engine_finds_nothing_on_healthy_fabric():
    f = model.load()
    state = collectors.Collector(f).snapshot()
    assert validators.validate(f, state) == []
