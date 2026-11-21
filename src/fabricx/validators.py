"""Validators: pure functions (fabric intent, collected state) -> findings. No lab needed to test them."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import parsers
from .model import Fabric


@dataclass
class Finding:
    check: str
    node: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _alive(state: dict, names: list[str]) -> list[str]:
    return [n for n in names if "unreachable" not in state[n]]


def check_reachability(f: Fabric, state: dict) -> list[Finding]:
    return [Finding("node-unreachable", n, state[n]["unreachable"])
            for n in sorted(state) if "unreachable" in state[n]]


def check_bgp(f: Fabric, state: dict) -> list[Finding]:
    out = []
    for sw in f.spines + f.leaves:
        if "unreachable" in state[sw.name]:
            continue
        want = {str(n.peer_ip) for n in f.neighbors(sw.name)}
        got = state[sw.name]["bgp"]
        for ip in sorted(want - set(got)):
            out.append(Finding("bgp-peer-missing", sw.name, f"peer {ip} not configured/visible"))
        for ip, st in sorted(got.items()):
            if st != "Established":
                out.append(Finding("bgp-not-established", sw.name, f"peer {ip} is {st}"))
    return out


def check_bfd(f: Fabric, state: dict) -> list[Finding]:
    if not f.underlay.bfd_enabled:
        return []
    out = []
    for sw in f.spines + f.leaves:
        if "unreachable" in state[sw.name]:
            continue
        got = state[sw.name].get("bfd", {})
        want = {str(n.peer_ip) for n in f.link_peers(sw.name)}
        for ip in sorted(want):
            if got.get(ip) != "up":
                out.append(Finding("bfd-down", sw.name, f"BFD to {ip} is {got.get(ip, 'missing')}"))
    return out


def check_ecmp(f: Fabric, state: dict) -> list[Finding]:
    out = []
    for leaf in f.leaves:
        if "unreachable" in state[leaf.name]:
            continue
        for other, n in state[leaf.name]["nexthops"].items():
            if n != len(f.spines):
                out.append(Finding("ecmp-nexthops", leaf.name,
                                   f"{n} next-hops to {other} loopback, expected {len(f.spines)}"))
    return out


def check_mtu(f: Fabric, state: dict) -> list[Finding]:
    out = []
    for lk in f.fabric_links():
        for node, ifname in ((lk.spine, lk.spine_if), (lk.leaf, lk.leaf_if)):
            if "unreachable" in state[node]:
                continue
            i = state[node]["interfaces"].get(ifname)
            if not i or i["state"] != "UP":
                out.append(Finding("link-down", node, f"{ifname} is {i and i['state']}"))
                continue
            rif = f.routed_if(node, ifname)
            r = state[node]["interfaces"].get(rif)
            if r and r["mtu"] != f.fabric_mtu:
                out.append(Finding("underlay-mtu", node, f"{rif} mtu {r['mtu']}, expected {f.fabric_mtu}"))
    return out


def check_evpn(f: Fabric, state: dict) -> list[Finding]:
    out = []
    for leaf in f.leaves:
        if "unreachable" in state[leaf.name]:
            continue
        keys = state[leaf.name]["evpn_keys"]
        t2ip = [k for k in keys if k.startswith("[2]") and k.count("[") > 4]
        t3 = [k for k in keys if k.startswith("[3]")]
        t5 = [k for k in keys if k.startswith("[5]")]
        for h in f.hosts:
            if not any(f"[{h.ip}]" in k for k in t2ip):
                out.append(Finding("evpn-type2-missing", leaf.name, f"no Type-2 MAC+IP for {h.name} ({h.ip})"))
        for other in f.leaves:
            n = sum(1 for k in t3 if f"[{other.loopback}]" in k)
            need = len(f.leaf_vlans(other.name))
            if n < need:
                out.append(Finding("evpn-type3-missing", leaf.name,
                                   f"{n}/{need} Type-3 routes from {other.name}"))
        for v in f.vlans:
            if not any(f"[{v.subnet.network_address}]" in k for k in t5):
                out.append(Finding("evpn-type5-missing", leaf.name, f"no Type-5 for {v.subnet}"))
    return out


ALL = (check_reachability, check_bgp, check_bfd, check_ecmp, check_mtu, check_evpn)


def validate(f: Fabric, state: dict) -> list[Finding]:
    return [x for chk in ALL for x in chk(f, state)]


__all__ = ["Finding", "validate", "ALL", "parsers"]
