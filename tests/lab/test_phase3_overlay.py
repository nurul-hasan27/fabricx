"""Phase 3 acceptance: VXLAN-EVPN overlay, four traffic classes, EVPN route types, packet proof."""
import json
import re
import subprocess

import pytest

from fabricx import model
from fabricx.runner import PREFIX, node_exec

pytestmark = [pytest.mark.lab, pytest.mark.functional]
F = model.load()
LAB = F.name
H = {h.name: h for h in F.hosts}


def ping(src, dst_ip, count=2):
    return node_exec(LAB, src, f"ping -c {count} -W 2 {dst_ip}").returncode == 0


@pytest.fixture(scope="module", autouse=True)
def prime_hosts():
    """Silent hosts are invisible to EVPN until they send traffic. Each host pings its gateway once."""
    for h in F.hosts:
        node_exec(LAB, h.name, f"ping -c 1 -W 2 {F.vlan(h.vlan).gateway}")


def test_class1_same_subnet_different_leaf_l2vni():  # h1 -> h3
    assert ping("h1", H["h3"].ip)


def test_class2_different_subnet_same_leaf_local_routing():  # h1 -> h2
    assert ping("h1", H["h2"].ip)


def test_class3_different_subnet_different_leaf_symmetric_irb():  # h1 -> h4
    assert ping("h1", H["h4"].ip)


def test_class4_different_vrf_must_fail():  # h1 -> a host in another VRF, and back
    a = F.hosts[0]
    other = [h for h in F.hosts if F.vlan(h.vlan).vrf != F.vlan(a.vlan).vrf]
    if not other:
        pytest.skip("this inventory has hosts in one VRF only (e.g. the sonic-leaf3 variant)")
    b = other[0]
    assert not ping(a.name, b.ip, 1)
    assert not ping(b.name, a.ip, 1)


def test_gateway_reachable_from_every_host():
    for h in F.hosts:
        assert ping(h.name, F.vlan(h.vlan).gateway, 1), h.name


def test_anycast_gateway_mac_identical_on_every_leaf():
    macs = set()
    for leaf in F.leaves:
        for v in F.leaf_vlans(leaf.name):
            out = node_exec(LAB, leaf.name, f"ip -o link show br{v.id}").stdout
            macs.add(re.search(r"link/ether ([0-9a-f:]+)", out).group(1))
    assert macs == {F.anycast_gw_mac}, macs


def evpn_routes(node):
    r = node_exec(LAB, node, "vtysh -c 'show bgp l2vpn evpn route json'")
    return json.loads(r.stdout)


def keys(node):
    out = []
    for rd, routes in evpn_routes(node).items():
        if isinstance(routes, dict) and rd.count(":") == 1:
            out += [k for k in routes if k.startswith("[")]
    return out


@pytest.mark.parametrize("leaf", F.leaves, ids=lambda s: s.name)
def test_evpn_route_types_present(leaf):
    ks = keys(leaf.name)
    t2 = [k for k in ks if k.startswith("[2]") and k.count("[") > 4]   # MAC+IP
    t3 = [k for k in ks if k.startswith("[3]")]
    t5 = [k for k in ks if k.startswith("[5]")]
    for h in F.hosts:  # every host appears as a Type-2 MAC+IP route
        assert any(f"[{h.ip}]" in k for k in t2), f"{leaf.name}: no Type-2 for {h.name}"
    for other in F.leaves:  # every VTEP advertises a Type-3 per VNI it carries
        n = sum(1 for k in t3 if f"[{other.loopback}]" in k)
        assert n >= len(F.leaf_vlans(other.name)), f"{leaf.name}: Type-3 from {other.name}={n}"
    for v in F.vlans:  # every subnet is advertised as a Type-5
        assert any(f"[{v.subnet.network_address}]" in k for k in t5), f"no Type-5 for {v.subnet}"


def test_red_routes_not_leaked_to_blue_vrf_table():
    """leaf3 only has BLUE; it must not install RED routes at all."""
    out = node_exec(LAB, "leaf3", "ip route show vrf BLUE").stdout
    assert "10.10.10" not in out and "10.20.20" not in out, out


def test_pcap_shows_vtep_outer_header_and_vnis(tmp_path):
    pcap = "/tmp/fabricx-leaf2.pcap"
    subprocess.run(["scripts/capture_vxlan.sh", "leaf2", pcap, "h1", str(H["h3"].ip), str(H["h4"].ip)],
                   capture_output=True, text=True, timeout=60)
    txt = subprocess.run(PREFIX.split() + ["tcpdump", "-nn", "-vv", "-r", pcap],
                         capture_output=True, text=True).stdout
    l1 = F.switch("leaf1").loopback
    l2 = F.switch("leaf2").loopback
    assert f"{l1}." in txt and f"{l2}.4789" in txt, "outer IP must be VTEP loopbacks, UDP 4789"
    # Judge only the packets that carry our test pings. A young lab also floods IPv6 router
    # solicitations over the L2VNIs (seen on CI); that background noise is not the ping's path.
    blocks = re.split(r"(?m)^(?=\d\d:\d\d:\d\d\.\d+ )", txt)

    def vnis_for(src, dst):
        return {m for b in blocks if f"{src} > {dst}: ICMP echo" in b or f"{dst} > {src}: ICMP echo" in b
                for m in re.findall(r"vni (\d+)", b)}
    bridged = vnis_for(H["h1"].ip, H["h3"].ip)
    routed = vnis_for(H["h1"].ip, H["h4"].ip)
    assert bridged == {str(F.vlan(10).vni)}, f"bridged (same subnet) traffic uses the L2VNI, saw {bridged}"
    odd = [b for b in blocks if f"{H['h1'].ip} > {H['h4'].ip}: ICMP echo" in b or f"{H['h4'].ip} > {H['h1'].ip}: ICMP echo" in b]
    assert routed == {str(F.vrfs[0].l3vni)}, ("routed (symmetric IRB) traffic uses only the L3VNI, saw "
                                              f"{routed}\n" + "\n".join(odd[:8]))
