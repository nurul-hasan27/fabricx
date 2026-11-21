"""Phase 5: drift detection and unreachable-node handling against the live lab."""
import subprocess
import sys

import pytest

from conftest import wait_healthy
from fabricx import collectors, model, validators
from fabricx.runner import node_exec, sh

pytestmark = [pytest.mark.lab, pytest.mark.functional]
F = model.load()


def cli(*args):
    return subprocess.run([sys.executable, "-m", "fabricx.cli", *args], capture_output=True, text=True, timeout=300)


def test_drift_clean_then_detects_manual_vtysh_change_then_clean_again():
    assert cli("drift").returncode == 0
    node_exec(F.name, "leaf2", "vtysh -c 'configure terminal' -c 'router bgp 65002' -c 'neighbor FABRIC timers 1 3'")
    try:
        r = cli("drift")
        assert r.returncode == 1, r.stdout
        assert "leaf2" in r.stdout and "timers 1 3" in r.stdout and "timers 3 9" in r.stdout, r.stdout
    finally:
        node_exec(F.name, "leaf2", "vtysh -c 'configure terminal' -c 'router bgp 65002' -c 'neighbor FABRIC timers 3 9'")
    assert cli("drift").returncode == 0


def test_paused_node_is_reported_unreachable_not_a_crash():
    sh(f"docker pause clab-{F.name}-leaf3")
    try:
        state = collectors.Collector(F).snapshot()
        found = validators.validate(F, state)
        assert any(x.check == "node-unreachable" and x.node == "leaf3" for x in found), found
        assert "unreachable" not in state["leaf1"]
    finally:
        sh(f"docker unpause clab-{F.name}-leaf3")
        wait_healthy()
