"""Phase 1 acceptance: needs the lab deployed (make fabric-up)."""
import pytest

from fabricx import model
from fabricx.runner import node_exec, sh

pytestmark = [pytest.mark.lab, pytest.mark.smoke]
F = model.load()
LAB = F.name


def test_all_ten_nodes_running():
    out = sh("docker ps --format {{.Names}}").stdout.split()
    expected = {f"clab-{LAB}-{n}" for n in
                [s.name for s in F.spines + F.leaves] + [h.name for h in F.hosts]}
    assert expected <= set(out)


@pytest.mark.parametrize("lk", F.fabric_links(), ids=lambda lk: f"{lk.spine}-{lk.leaf}")
def test_link_up_with_mtu_and_pingable_both_ways(lk):
    for node, ifname, peer in ((lk.spine, lk.spine_if, lk.leaf_ip), (lk.leaf, lk.leaf_if, lk.spine_ip)):
        r = node_exec(LAB, node, f"ip -o link show {ifname}")
        assert "state UP" in r.stdout or "UP," in r.stdout, r.stdout
        assert f"mtu {F.fabric_mtu}" in r.stdout, r.stdout
        p = node_exec(LAB, node, f"ping -c 2 -W 2 {peer}")
        assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("sw", F.spines + F.leaves, ids=lambda s: s.name)
def test_loopback_configured(sw):
    r = node_exec(LAB, sw.name, "ip -o addr show dev lo")
    assert f"{sw.loopback}/32" in r.stdout, r.stdout


@pytest.mark.parametrize("h", F.hosts, ids=lambda h: h.name)
def test_host_has_address_and_gateway(h):
    r = node_exec(LAB, h.name, "ip -o addr show dev eth1")
    assert f"{h.ip}/" in r.stdout, r.stdout
    gw = node_exec(LAB, h.name, "ip route show default").stdout
    assert str(F.vlan(h.vlan).gateway) in gw, gw
