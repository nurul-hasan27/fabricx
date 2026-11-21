"""Phase 2 acceptance: BGP, ECMP, BFD, probe. Needs the lab deployed with routing."""
import json
import shlex
import subprocess
import time

import pytest

from fabricx import model
from fabricx.probe import analyze
from fabricx.runner import PREFIX, node_exec

pytestmark = [pytest.mark.lab, pytest.mark.smoke]
F = model.load()
LAB = F.name
SWITCHES = F.spines + F.leaves
LEAVES = F.leaves


def vtysh_json(node, cmd):
    r = node_exec(LAB, node, f"vtysh -c '{cmd}'")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_all_bgp_sessions_established():
    """6 links x 2 ends = 12 session ends, all Established."""
    total = 0
    for sw in SWITCHES:
        peers = vtysh_json(sw.name, "show bgp summary json")["ipv4Unicast"]["peers"]
        expected = {str(n.peer_ip) for n in F.neighbors(sw.name)}
        assert set(peers) == expected, f"{sw.name}: peers {set(peers)} != {expected}"
        bad = {ip: p["state"] for ip, p in peers.items() if p["state"] != "Established"}
        assert not bad, f"{sw.name}: {bad}"
        total += len(peers)
    assert total == 2 * len(F.fabric_links())


@pytest.mark.parametrize("leaf", LEAVES, ids=lambda s: s.name)
def test_two_kernel_nexthops_to_every_remote_leaf_loopback(leaf):
    for other in LEAVES:
        if other.name == leaf.name:
            continue
        out = node_exec(LAB, leaf.name, f"ip route show {other.loopback}").stdout
        assert out.count("nexthop via") == len(F.spines), f"{leaf.name}->{other.name}: {out}"


@pytest.mark.parametrize("sw", SWITCHES, ids=lambda s: s.name)
def test_bfd_peers_up(sw):
    peers = vtysh_json(sw.name, "show bfd peers json")
    assert len(peers) == len(F.neighbors(sw.name))
    assert all(p["status"] == "up" for p in peers), peers


def test_loopback_to_loopback_ping_all_leaf_pairs():
    for a in LEAVES:
        for b in LEAVES:
            if a.name != b.name:
                r = node_exec(LAB, a.name, f"ping -c 2 -W 2 -I {a.loopback} {b.loopback}")
                assert r.returncode == 0, r.stdout


def test_probe_across_fabric_no_loss_and_documented_resolution():
    """Leaf1 loopback -> leaf3 loopback for 4 s at 1 ms. Clean fabric must show ~0 loss."""
    src, dst = LEAVES[0], LEAVES[-1]
    rx = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-{dst.name} python3 /opt/probe.py recv --bind {dst.loopback} "
        f"--port 9000 --duration 6 --out /tmp/r.csv"), stdout=subprocess.PIPE, text=True)
    time.sleep(1)
    tx = node_exec(LAB, src.name, f"python3 /opt/probe.py send --src {src.loopback} "
                                  f"--dst {dst.loopback} --port 9000 --interval-ms 1 --duration 4", 30)
    sent = int(tx.stdout.strip())
    rx.wait(timeout=30)
    csv = node_exec(LAB, dst.name, "cat /tmp/r.csv").stdout.splitlines()[1:]
    rows = [tuple(int(x) for x in ln.split(",")) for ln in csv]
    res = analyze(rows, sent)
    print(res)
    assert sent > 3000, f"sender too slow: {sent} packets in 4 s"
    assert res["lost"] == 0 and res["reordered"] == 0, res
    # Scheduler noise on the shared VM gave gaps of 3-100 ms on healthy runs (see E1); a real failover is >= 700 ms.
    assert res["longest_gap_ms"] < 250, res
