"""Pure parsers: raw device output (text/JSON) -> normalised dicts. Unit-tested against fixtures."""
from __future__ import annotations

import json
import re


def bgp_peers(raw: str) -> dict[str, str]:
    """`show bgp summary json` -> {peer_ip: state}"""
    out: dict[str, str] = {}
    for af in json.loads(raw).values():  # ipv4Unicast, l2VpnEvpn: an iBGP/EVPN-only underlay has no ipv4Unicast
        if isinstance(af, dict):
            out.update({ip: p["state"] for ip, p in af.get("peers", {}).items()})
    return out


def bfd_peers(raw: str) -> dict[str, str]:
    """`show bfd peers json` -> {peer_ip: status}"""
    return {p["peer"]: p["status"] for p in json.loads(raw)}


def interfaces(raw: str) -> dict[str, dict]:
    """`ip -j link show` -> {ifname: {state, mtu}}"""
    return {i["ifname"]: {"state": i["operstate"], "mtu": i["mtu"]} for i in json.loads(raw)}


def nexthop_count(raw: str) -> int:
    """`ip route show <prefix>` -> number of next-hops (0 = no route)."""
    raw = raw.strip()
    if not raw:
        return 0
    n = raw.count("nexthop via")
    return n if n else 1


def evpn_route_keys(raw: str) -> list[str]:
    """`show bgp l2vpn evpn route json` -> list of route keys like '[2]:[0]:[48]:[mac]:[32]:[ip]'."""
    out = []
    for rd, routes in json.loads(raw).items():
        if isinstance(routes, dict) and rd.count(":") == 1:
            out += [k for k in routes if k.startswith("[")]
    return out


def evpn_counts(keys: list[str]) -> dict[str, int]:
    """Count routes per EVPN type."""
    c = {"type2_mac": 0, "type2_macip": 0, "type3": 0, "type5": 0}
    for k in keys:
        m = re.match(r"\[(\d)\]", k)
        if not m:
            continue
        t = int(m.group(1))
        if t == 2:
            c["type2_macip" if k.count("[") > 4 else "type2_mac"] += 1
        elif t == 3:
            c["type3"] += 1
        elif t == 5:
            c["type5"] += 1
    return c


def tc_child_qdisc_stats(txt: str, handle: str = "10:") -> dict[str, int]:
    """`tc -s qdisc show` -> counters of the child queue under a shaper (E6): sent packets, drops and, for
    RED, ECN marks / early drops / pdrops. Only the child's block is read, never the shaper's."""
    m = re.search(rf"qdisc \w+ {re.escape(handle)}.*?(?=\nqdisc |\Z)", txt, re.S)
    if not m:
        raise ValueError(f"queue {handle} not found in tc output")
    block = m.group(0)

    def num(rx: str) -> int:
        f = re.search(rx, block)
        return int(f.group(1)) if f else 0
    out = {"sent_pkts": num(r"Sent \d+ bytes (\d+) pkt"), "dropped": num(r"dropped (\d+)")}
    if "marked" in block:
        out |= {"marked": num(r"marked (\d+)"), "early_drop": num(r"early (\d+)"), "pdrop": num(r"pdrop (\d+)")}
    return out
