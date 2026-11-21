"""Shared fixtures. Lab test modules start only when the fabric is healthy and quiet, so a previous
test's disturbance (paused node, changed timers) cannot leak into the next module's measurements."""
import time

import pytest

from fabricx import collectors, model, validators


def wait_healthy(timeout: int = 180) -> None:
    f = model.load()
    t0 = time.time()
    findings: list = []
    while time.time() - t0 < timeout:
        findings = validators.validate(f, collectors.Collector(f).snapshot())
        if not findings:
            time.sleep(5)  # let routing settle after the last change
            return
        time.sleep(5)
    raise AssertionError("fabric did not become healthy; findings:\n"
                         + "\n".join(f"  {x.check} {x.node}: {x.message}" for x in findings[:15]))


_BROKEN: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def _settled(request):
    if request.node.get_closest_marker("lab"):
        if _BROKEN:   # do not wait 3 minutes per module for a fabric that already failed to converge
            pytest.exit(_BROKEN[0], returncode=2)
        try:
            wait_healthy()
        except AssertionError as e:
            _BROKEN.append(str(e))
            pytest.exit(str(e), returncode=2)
    yield
