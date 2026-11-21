"""The 14 injectable faults. Each has inject(), restore(), a layer, the cause key diagnose must find,
the customer-visible symptoms we *expect* (a hypothesis, checked in the run report) and the first
command that reveals it."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..model import Fabric
from ..runner import node_exec

State = dict[str, str]


@dataclass
class Fault:
    id: str
    name: str
    layer: str                      # diagnose layer the root cause lives in
    cause_key: str                  # what diagnose must report to count as localised
    how: str                        # how it is injected (plain words)
    symptom: str                    # what a customer sees
    # traffic classes expected to FAIL: c1 h1>h3, c2 h1>h2, c3 h1>h4 (c4 = h1>h5 must always fail)
    expected_failing: list[str]
    first_evidence: str
    settle_s: int                   # seconds to wait after inject before observing
    inject: Callable[[Fabric], State]
    restore: Callable[[Fabric, State], None]
    extra: dict[str, str] = field(default_factory=dict)


def vty(f: Fabric, node: str, *cmds: str) -> None:
    args = " ".join(f"-c '{c}'" for c in ["configure terminal", *cmds])
    node_exec(f.name, node, f"vtysh {args}", timeout=30)


def sh(f: Fabric, node: str, cmd: str) -> str:
    return node_exec(f.name, node, cmd, timeout=30).stdout


def _link(f: Fabric, leaf: str, spine: str):
    return next(lk for lk in f.fabric_links() if lk.leaf == leaf and lk.spine == spine)


# ---- L1 / links ----------------------------------------------------------------------------------
def f01(f: Fabric) -> State:
    sh(f, "leaf1", "ip link set eth1 down")
    return {}


def f01r(f: Fabric, s: State) -> None:
    sh(f, "leaf1", "ip link set eth1 up")


def f02(f: Fabric) -> State:  # gray failure, both directions
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"tc qdisc add dev {lk.leaf_if} root netem loss 100%")
    sh(f, "spine1", f"tc qdisc add dev {lk.spine_if} root netem loss 100%")
    return {}


def f02r(f: Fabric, s: State) -> None:
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"tc qdisc del dev {lk.leaf_if} root")
    sh(f, "spine1", f"tc qdisc del dev {lk.spine_if} root")


def f03(f: Fabric) -> State:  # unidirectional: only leaf1 -> spine1 is dropped
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"tc qdisc add dev {lk.leaf_if} root netem loss 100%")
    return {}


def f03r(f: Fabric, s: State) -> None:
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"tc qdisc del dev {lk.leaf_if} root")


def f04(f: Fabric) -> State:  # lossy link
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"tc qdisc add dev {lk.leaf_if} root netem loss 2%")
    return {}


f04r = f03r


def f05(f: Fabric) -> State:  # MTU 1500 on one underlay link (both ends)
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"ip link set {lk.leaf_if} mtu 1500")
    sh(f, "spine1", f"ip link set {lk.spine_if} mtu 1500")
    return {}


def f05r(f: Fabric, s: State) -> None:
    lk = _link(f, "leaf1", "spine1")
    sh(f, "leaf1", f"ip link set {lk.leaf_if} mtu {f.fabric_mtu}")
    sh(f, "spine1", f"ip link set {lk.spine_if} mtu {f.fabric_mtu}")


# ---- control plane ------------------------------------------------------------------------------
def f06(f: Fabric) -> State:  # spine1 expects the wrong AS for leaf2
    lk = _link(f, "leaf2", "spine1")
    p = str(lk.leaf_ip)
    vty(f, "spine1", "router bgp 65000", f"no neighbor {p} peer-group FABRIC", f"neighbor {p} remote-as 65999")
    return {"peer": p}


def f06r(f: Fabric, s: State) -> None:
    p = s["peer"] if s else str(_link(f, "leaf2", "spine1").leaf_ip)
    vty(f, "spine1", "router bgp 65000", f"no neighbor {p} remote-as 65999",
        f"neighbor {p} peer-group FABRIC", f"neighbor {p} description leaf2")


def f07(f: Fabric) -> State:  # leaf3 stops advertising its loopback
    lo = f.switch("leaf3").loopback
    vty(f, "leaf3", "router bgp 65003", "address-family ipv4 unicast", f"no network {lo}/32")
    return {}


def f07r(f: Fabric, s: State) -> None:
    lo = f.switch("leaf3").loopback
    vty(f, "leaf3", "router bgp 65003", "address-family ipv4 unicast", f"network {lo}/32")


# ---- overlay ------------------------------------------------------------------------------------
def f08(f: Fabric) -> State:  # route-target mismatch on VNI 10010 at leaf2
    vty(f, "leaf2", "router bgp 65002", "address-family l2vpn evpn", "vni 10010", "route-target both 65002:99999")
    return {}


def f08r(f: Fabric, s: State) -> None:
    vty(f, "leaf2", "router bgp 65002", "address-family l2vpn evpn", "vni 10010", "no route-target both 65002:99999")
    vty(f, "leaf2", "router bgp 65002", "address-family l2vpn evpn", "no vni 10010")  # drop the empty stanza too


def _vx_cmds(f: Fabric, leaf: str, vni: int, br: int, mtu: int) -> str:
    lo = f.switch(leaf).loopback
    return (f"ip link add vx{vni} type vxlan id {vni} dstport 4789 local {lo} df {f.vxlan_df} nolearning && "
            f"ip link set vx{vni} mtu {mtu} master br{br} && ip link set vx{vni} up")


def f09(f: Fabric) -> State:  # leaf2: VLAN 10 bridge carries the wrong VNI
    sh(f, "leaf2", "ip link del vx10010")
    sh(f, "leaf2", f"sh -c '{_vx_cmds(f, 'leaf2', 10099, 10, f.host_mtu)}'")
    return {}


def f09r(f: Fabric, s: State) -> None:
    sh(f, "leaf2", "ip link del vx10099")
    sh(f, "leaf2", f"sh -c '{_vx_cmds(f, 'leaf2', 10010, 10, f.host_mtu)}'")


def f10(f: Fabric) -> State:  # leaf2 loses the L3VNI mapping of VRF RED
    vty(f, "leaf2", "vrf RED", "no vni 50001")
    return {}


def f10r(f: Fabric, s: State) -> None:
    vty(f, "leaf2", "vrf RED", "vni 50001")


def f11(f: Fabric) -> State:  # ECMP hashes L3 only on leaf1
    sh(f, "leaf1", "sysctl -w net.ipv4.fib_multipath_hash_policy=0")
    return {}


def f11r(f: Fabric, s: State) -> None:
    sh(f, "leaf1", f"sysctl -w net.ipv4.fib_multipath_hash_policy={f.ecmp_hash_policy}")


def f12(f: Fabric) -> State:  # h3 (leaf2) uses the MAC of h1 (leaf1)
    h1 = sh(f, "h1", "cat /sys/class/net/eth1/address").strip()
    orig = sh(f, "h3", "cat /sys/class/net/eth1/address").strip()
    sh(f, "h3", f"ip link set eth1 address {h1}")
    for _ in range(3):  # make leaf2 learn the MAC
        sh(f, "h3", f"ping -c 1 -W 1 {f.vlan(10).gateway}")
        sh(f, "h1", f"ping -c 1 -W 1 {f.vlan(10).gateway}")
    return {"orig": orig}


def f12r(f: Fabric, s: State) -> None:
    orig = (s or {}).get("orig")
    if orig:
        h1 = sh(f, "h1", "cat /sys/class/net/eth1/address").strip()
        sh(f, "h3", f"ip link set eth1 address {orig}")
        port = next(hl.leaf_if for hl in f.host_links() if hl.host == "h3")
        sh(f, "leaf2", f"bridge fdb del {h1} dev {port} master")  # drop the stale entry for h1's MAC on h3's port
        sh(f, "h3", f"ping -c 1 -W 1 {f.vlan(10).gateway}")
        sh(f, "h1", f"ping -c 1 -W 1 {f.vlan(10).gateway}")
        time.sleep(3)
    for leaf in f.leaves:  # FRR keeps the duplicate flag and move counters until cleared
        sh(f, leaf.name, "vtysh -c 'clear evpn dup-addr vni all'")


def f13(f: Fabric) -> State:  # bgpd hangs on spine1 (process frozen, container and BFD keep running)
    sh(f, "spine1", "sh -c 'kill -STOP $(pidof bgpd)'")
    return {}


def f13r(f: Fabric, s: State) -> None:
    sh(f, "spine1", "sh -c 'kill -CONT $(pidof bgpd)'")


def f14(f: Fabric) -> State:  # anycast gateway MAC differs on leaf2
    sh(f, "leaf2", "ip link set br10 address 02:fa:b0:00:00:99")
    return {}


def f14r(f: Fabric, s: State) -> None:
    sh(f, "leaf2", f"ip link set br10 address {f.anycast_gw_mac}")


CATALOGUE: list[Fault] = [
    Fault("F01", "Leaf-spine link down", "L1 links", "link-down", "ip link set eth1 down on leaf1",
          "Brief loss, then traffic uses the other spine; fabric degraded", [],
          "ip -j link on leaf1 (eth1 DOWN); show bfd peers", 12, f01, f01r),
    Fault("F02", "Gray failure (both directions)", "L1 links", "gray-failure",
          "tc netem loss 100% on both ends of leaf1-spine1, link stays UP",
          "Link looks up but carries nothing; BGP/BFD drop; traffic reroutes after detection", [],
          "tc -s qdisc on the link ends; BFD down while interface UP", 15, f02, f02r),
    Fault("F03", "Unidirectional loss", "L1 links", "unidirectional-loss",
          "netem loss 100% only on leaf1's transmit side of leaf1-spine1",
          "One direction dead; sessions drop; half-working link", [],
          "tc -s qdisc drops on one end only", 15, f03, f03r),
    Fault("F04", "Lossy link (2%)", "L1 links", "lossy-link", "netem loss 2% on leaf1 transmit side of leaf1-spine1",
          "Slow applications; nothing is 'down'", [], "tc -s qdisc dropped counter rising on the link", 12, f04, f04r),
    Fault("F05", "Underlay MTU 1500 on one link", "Underlay MTU", "underlay-mtu",
          "ip link set mtu 1500 on both ends of leaf1-spine1",
          "Pings work, large transfers on flows via that link stall", [],
          "ip -j link (mtu) on the fabric interfaces; DF ping size sweep", 10, f05, f05r),
    Fault("F06", "BGP ASN mismatch", "BGP sessions", "bgp-asn-mismatch",
          "spine1 expects AS 65999 from leaf2", "leaf2 loses one spine; fabric degraded, no outage",
          [], "show bgp neighbors <leaf2 ip> (Bad Peer AS)", 15, f06, f06r),
    Fault("F07", "Loopback not advertised", "VTEP reachability", "loopback-not-advertised",
          "leaf3 stops advertising its /32 loopback", "leaf3's VTEP is unreachable; BLUE hosts cut off from the fabric",
          [], "ip route show <leaf3 loopback> on other leaves (empty)", 12, f07, f07r),
    Fault("F08", "Route-target mismatch on one VNI", "EVPN routes", "rt-mismatch",
          "leaf2 uses RT 65002:99999 for VNI 10010", "Same-subnet traffic to/from leaf2 in VLAN 10 fails",
          ["c1"], "show bgp l2vpn evpn vni 10010 (importRts differ between leaves)", 15, f08, f08r),
    Fault("F09", "VNI/VLAN mapping mismatch", "VNI/VLAN maps", "vni-mismatch",
          "leaf2's VLAN 10 bridge carries VNI 10099 instead of 10010",
          "Same-subnet traffic to/from leaf2 in VLAN 10 fails", ["c1"],
          "ip -d link show type vxlan (id differs from inventory)", 15, f09, f09r),
    Fault("F10", "Missing L3VNI on one leaf", "VNI/VLAN maps", "missing-l3vni",
          "leaf2: `vrf RED / no vni 50001`", "Routed traffic to/from leaf2 fails; bridged still works", ["c3"],
          "show evpn vni (50001 missing / tenant VRF unknown)", 15, f10, f10r),
    Fault("F11", "ECMP hash policy L3-only", "Forwarding", "ecmp-hash-policy",
          "leaf1 fib_multipath_hash_policy=0", "Routed multi-flow traffic polarises onto one uplink; no packet loss",
          [], "sysctl net.ipv4.fib_multipath_hash_policy; per-uplink counters", 5, f11, f11r),
    Fault("F12", "Duplicate MAC on two leaves", "FDB / ARP", "duplicate-mac",
          "h3 (leaf2) takes h1's MAC (leaf1)", "Intermittent reachability for h1/h3",
          [], "EVPN Type-2 for the same MAC from two VTEPs (MAC mobility)", 15, f12, f12r),
    Fault("F13", "bgpd hung on a spine", "BGP sessions", "bgp-daemon-hung",
          "kill -STOP bgpd on spine1 (BFD keeps running)",
          "Sessions via spine1 die after the hold timer; traffic uses spine2",
          [], "ps/proc state of bgpd; vtysh show bgp times out", 20, f13, f13r),
    Fault("F14", "Anycast gateway MAC mismatch", "FDB / ARP", "gateway-mac-mismatch",
          "leaf2's br10 has a different MAC than the inventory's anycast MAC",
          "Hosts that move to leaf2 break; routed traffic from VLAN 10 on leaf2 misbehaves",
          [], "ip link show br10 on every leaf (MAC differs)", 10, f14, f14r),
]


def get(fid: str) -> Fault:
    return next(x for x in CATALOGUE if x.id == fid.upper())
