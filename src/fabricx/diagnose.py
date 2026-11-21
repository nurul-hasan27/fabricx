"""fabricx diagnose: a bottom-up, rule-based fault localiser. No machine learning, every finding cites evidence.

It only looks at LIVE state plus the inventory's intent; it is never told which fault was injected.
Layers (lowest first): L1 links -> underlay MTU -> BGP sessions -> VTEP reachability -> EVPN routes ->
VNI/VLAN maps -> forwarding -> FDB/ARP. The first layer with findings is the primary diagnosis; findings in
higher layers are reported as probable consequences. Rules are pure functions of the collected state.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import parsers
from .model import Fabric
from .runner import NodeUnreachable, node_exec

LAYERS = ["L1 links", "Underlay MTU", "BGP sessions", "VTEP reachability", "EVPN routes",
          "VNI/VLAN maps", "Forwarding", "FDB / ARP"]
PING_N = 300


@dataclass
class DFinding:
    layer: str
    cause_key: str
    nodes: list[str]
    evidence: list[str]
    probable_cause: str
    confidence: str  # high | medium

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Diagnosis:
    primary: list[DFinding] = field(default_factory=list)
    consequences: list[DFinding] = field(default_factory=list)
    symptoms: dict[str, bool] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return not self.primary

    def to_dict(self) -> dict:
        return {"primary": [x.to_dict() for x in self.primary],
                "consequences": [x.to_dict() for x in self.consequences], "symptoms": self.symptoms}


# ---------------------------------------------------------------------------------------------------
# Collection (talks to the lab)
# ---------------------------------------------------------------------------------------------------
def _try(f: Fabric, node: str, cmd: str, timeout: int = 8) -> str | None:
    try:
        r = node_exec(f.name, node, cmd, timeout=timeout)
    except NodeUnreachable:
        return None
    return r.stdout if r.returncode == 0 else None


def _vty(f: Fabric, node: str, cmd: str) -> str | None:
    return _try(f, node, f"vtysh -c '{cmd}'")


def _rx_tx(f: Fabric, node: str, ifname: str) -> tuple[int, int]:
    base = f"cat /sys/class/net/{ifname}/statistics/"
    rx = int(_try(f, node, base + "rx_packets") or 0)
    tx = int(_try(f, node, base + "tx_packets") or 0)
    return rx, tx


def _ping_loss(f: Fabric, node: str, ip: str) -> float:
    out = _try(f, node, f"ping -c {PING_N} -i 0.005 -W 1 -q {ip}", timeout=40) or ""
    m = re.search(r"(\d+)% packet loss", out)
    return float(m.group(1)) if m else 100.0


def _link_test(f: Fabric, lk) -> dict:
    """Directional active test on one /31: A pings B (B's rx must rise), then B pings A (A's rx must rise)."""
    res: dict = {"spine": lk.spine, "leaf": lk.leaf, "spine_if": lk.spine_if, "leaf_if": lk.leaf_if}
    b_rx0, _ = _rx_tx(f, lk.spine, lk.spine_if)
    res["leaf_ping_loss_pct"] = _ping_loss(f, lk.leaf, str(lk.spine_ip))
    b_rx1, _ = _rx_tx(f, lk.spine, lk.spine_if)
    res["leaf_to_spine_arrived"] = b_rx1 - b_rx0
    a_rx0, _ = _rx_tx(f, lk.leaf, lk.leaf_if)
    res["spine_ping_loss_pct"] = _ping_loss(f, lk.spine, str(lk.leaf_ip))
    a_rx1, _ = _rx_tx(f, lk.leaf, lk.leaf_if)
    res["spine_to_leaf_arrived"] = a_rx1 - a_rx0
    return res


def collect(f: Fabric) -> dict:
    """Gather everything the rules need. Slow parts (active link tests) run in parallel."""
    st: dict = {"nodes": {}, "links": [], "dataplane": {}}
    with ThreadPoolExecutor(max_workers=6) as ex:
        link_futs = [ex.submit(_link_test, f, lk) for lk in f.fabric_links()]
        for sw in f.spines + f.leaves:
            st["nodes"][sw.name] = _collect_node(f, sw.name)
        st["links"] = [x.result() for x in link_futs]
    st["dataplane"] = _dataplane(f)
    return st


def _collect_node(f: Fabric, name: str) -> dict:
    n: dict = {"reachable": _try(f, name, "true") is not None}
    if not n["reachable"]:
        return n
    bg = _try(f, name, "sh -c 'grep State /proc/$(pidof bgpd)/status'")
    n["bgpd_state"] = bg.split()[1] if bg and len(bg.split()) > 1 else None
    n["interfaces"] = parsers.interfaces(_try(f, name, "ip -j link show") or "[]")
    bfd = _vty(f, name, "show bfd peers json")
    n["bfd"] = parsers.bfd_peers(bfd) if bfd else {}
    summ = _vty(f, name, "show bgp summary json")
    n["vtysh_bgp_ok"] = summ is not None
    n["bgp"] = parsers.bgp_peers(summ) if summ else {}
    n["bgp_error"] = {}
    nb_all = _vty(f, name, "show bgp neighbors json")
    try:
        nbj = json.loads(nb_all) if nb_all else {}
    except ValueError:
        nbj = {}
    n["bgp_remote_as"] = {ip: v.get("remoteAs") for ip, v in nbj.items() if isinstance(v, dict)}
    for ip, state in n["bgp"].items():
        if state != "Established":
            nb = _vty(f, name, f"show bgp neighbors {ip} json") or "{}"
            n["bgp_error"][ip] = _notification_text(nb)
    n["hash_policy"] = int((_try(f, name, "sysctl -n net.ipv4.fib_multipath_hash_policy") or "-1").strip())
    if name.startswith("leaf"):
        n["nexthops"] = {o.name: parsers.nexthop_count(_try(f, name, f"ip route show {o.loopback}") or "")
                         for o in f.leaves if o.name != name}
        raw = _vty(f, name, "show bgp l2vpn evpn route json") or "{}"
        n["evpn_by_rd"] = _evpn_by_rd(raw)
        vni = _vty(f, name, "show evpn vni json") or "{}"
        n["evpn_vni"] = json.loads(vni) if vni.strip().startswith("{") else {}
        n["evpn_macs"] = {}
        n["vni_rts"] = {}
        for v, info in n["evpn_vni"].items():
            if info.get("type") == "L2":
                mj = _vty(f, name, f"show evpn mac vni {v} json") or "{}"
                try:
                    n["evpn_macs"][v] = json.loads(mj).get("macs", {})
                except ValueError:
                    n["evpn_macs"][v] = {}
                j = _vty(f, name, f"show bgp l2vpn evpn vni {v} json") or "{}"
                d = json.loads(j) if j.strip().startswith("{") else {}
                n["vni_rts"][v] = {"import": d.get("importRts", []), "export": d.get("exportRts", [])}
        vx = json.loads(_try(f, name, "ip -d -j link show type vxlan") or "[]")
        n["vxlan"] = {i.get("master", ""): i["linkinfo"]["info_data"]["id"] for i in vx}
        n["bridge_mac"] = {}
        for v in f.leaf_vlans(name):
            lk = json.loads(_try(f, name, f"ip -j link show br{v.id}") or "[]")
            if lk:
                n["bridge_mac"][f"br{v.id}"] = lk[0]["address"]
    return n


def _notification_text(raw: str) -> str:
    try:
        d = json.loads(raw)
    except ValueError:
        return ""
    peer: dict = next(iter(d.values()), {}) if isinstance(d, dict) else {}
    keys = ("lastNotificationReason", "lastResetDueTo", "lastErrorCodeSubcode", "bgpState")
    return "; ".join(f"{k}={peer[k]}" for k in keys if k in peer)


def _evpn_by_rd(raw: str) -> dict[str, list[str]]:
    try:
        d = json.loads(raw)
    except ValueError:
        return {}
    return {rd: [k for k in v if k.startswith("[")] for rd, v in d.items()
            if isinstance(v, dict) and rd.count(":") == 1}


def _dataplane(f: Fabric) -> dict:
    h = f.hosts_by_name()
    for x in f.hosts:  # EVPN only knows hosts that have spoken ('silent host'): each pings its gateway first
        _try(f, x.name, f"ping -c 1 -W 1 {f.vlan(x.vlan).gateway}", timeout=10)

    def p(src: str, dst: str, extra: str = "") -> bool:
        r = _try(f, src, f"ping -c 2 -W 1 {extra} {h[dst].ip}", timeout=15)
        return r is not None
    return {"c1": p("h1", "h3"), "c2": p("h1", "h2"), "c3": p("h1", "h4"), "c4": p("h1", "h5")}


# ---------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------
def rule_l1(f: Fabric, st: dict) -> list[DFinding]:
    out: list[DFinding] = []
    for lk in st["links"]:
        a, b = lk["leaf"], lk["spine"]
        names = f"{a}:{lk['leaf_if']} <-> {b}:{lk['spine_if']}"
        ia = st["nodes"][a].get("interfaces", {}).get(lk["leaf_if"], {})
        ib = st["nodes"][b].get("interfaces", {}).get(lk["spine_if"], {})
        if ia.get("state") not in (None, "UP") or ib.get("state") not in (None, "UP"):
            out.append(DFinding("L1 links", "link-down", [a, b],
                                [f"{a}:{lk['leaf_if']} state {ia.get('state')}, {b}:{lk['spine_if']} state {ib.get('state')}"],
                                f"Link {names} is down", "high"))
            continue
        fwd_dead = lk["leaf_to_spine_arrived"] < PING_N * 0.2      # leaf -> spine direction
        rev_dead = lk["spine_to_leaf_arrived"] < PING_N * 0.2      # spine -> leaf direction
        ev = [f"{a} ping loss {lk['leaf_ping_loss_pct']}%, {b} ping loss {lk['spine_ping_loss_pct']}%",
              f"requests arriving: {a}->{b} {lk['leaf_to_spine_arrived']}/{PING_N}, {b}->{a} {lk['spine_to_leaf_arrived']}/{PING_N}",
              "both interfaces report UP"]
        if fwd_dead and rev_dead:
            out.append(DFinding("L1 links", "gray-failure", [a, b], ev,
                                f"Link {names} is UP but carries nothing in either direction (gray failure)", "high"))
        elif fwd_dead != rev_dead:
            direction = f"{a}->{b}" if fwd_dead else f"{b}->{a}"
            out.append(DFinding("L1 links", "unidirectional-loss", [a if fwd_dead else b], ev,
                                f"Link {names} drops traffic only in direction {direction}", "high"))
        elif max(lk["leaf_ping_loss_pct"], lk["spine_ping_loss_pct"]) >= 0.5:
            out.append(DFinding("L1 links", "lossy-link", [a, b], ev,
                                f"Link {names} is UP but drops part of the traffic", "high"))
    return out


def rule_mtu(f: Fabric, st: dict) -> list[DFinding]:
    out = []
    for lk in f.fabric_links():
        for node, wire in ((lk.leaf, lk.leaf_if), (lk.spine, lk.spine_if)):
            ifn = f.routed_if(node, wire)
            i = st["nodes"][node].get("interfaces", {}).get(ifn)
            if i and i["mtu"] != f.fabric_mtu:
                out.append(DFinding("Underlay MTU", "underlay-mtu", [node],
                                    [f"{node}:{ifn} mtu {i['mtu']} but the inventory says {f.fabric_mtu}"],
                                    f"Underlay MTU mismatch on {node}:{ifn}; VXLAN frames up to "
                                    f"{f.host_mtu + 50} bytes will not cross it", "high"))
    return out


def rule_bgp(f: Fabric, st: dict) -> list[DFinding]:
    out: list[DFinding] = []
    for sw in f.spines + f.leaves:
        n = st["nodes"][sw.name]
        if not n.get("reachable"):
            out.append(DFinding("BGP sessions", "node-unreachable", [sw.name], ["container does not answer"],
                                f"{sw.name} is not reachable", "high"))
            continue
        if n.get("bgpd_state") == "T" or not n.get("vtysh_bgp_ok"):
            out.append(DFinding("BGP sessions", "bgp-daemon-hung", [sw.name],
                                [f"bgpd process state {n.get('bgpd_state')}", "`show bgp summary` got no answer"],
                                f"bgpd on {sw.name} is stopped/hung while the node itself is up", "high"))
            continue
        expected_as = {str(x.peer_ip): x.peer_asn for x in f.neighbors(sw.name)}
        explained: set[str] = set()
        for ip, got in n.get("bgp_remote_as", {}).items():
            if ip in expected_as and got != expected_as[ip]:
                explained.add(ip)
                out.append(DFinding("BGP sessions", "bgp-asn-mismatch", [sw.name],
                                    [f"{sw.name}: neighbor {ip} is configured with remote-as {got}, the peer really runs AS {expected_as[ip]}",
                                     f"session state {n['bgp'].get(ip)}"],
                                    f"{sw.name} expects the wrong AS number for peer {ip}", "high"))
        for ip, state in n["bgp"].items():
            if state == "Established" or ip in explained:
                continue
            err = n["bgp_error"].get(ip, "")
            if not re.search(r"Bad Peer AS", err, re.I):
                out.append(DFinding("BGP sessions", "bgp-session-down", [sw.name],
                                    [f"{sw.name} -> {ip}: {state}; {err}"],
                                    f"BGP session {sw.name} -> {ip} is not Established and no more specific cause was found",
                                    "medium"))
            if re.search(r"Bad Peer AS", err, re.I):
                out.append(DFinding("BGP sessions", "bgp-asn-mismatch", [sw.name],
                                    [f"{sw.name} -> {ip}: {state}; {err}"],
                                    f"{sw.name} and the peer {ip} disagree about the peer's AS number", "high"))
    # sessions dead only because the other end's daemon is hung are consequences; flag unexplained ones last
    return out


def rule_vtep(f: Fabric, st: dict) -> list[DFinding]:
    out = []
    for other in f.leaves:
        missing = [leaf.name for leaf in f.leaves if leaf.name != other.name
                   and st["nodes"][leaf.name].get("nexthops", {}).get(other.name) == 0]
        if len(missing) == len(f.leaves) - 1:
            out.append(DFinding("VTEP reachability", "loopback-not-advertised", [other.name],
                                [f"{', '.join(missing)} have no route to {other.name}'s loopback {other.loopback}",
                                 "BGP sessions are up, so the prefix is not being advertised or is filtered"],
                                f"{other.name} is not advertising its VTEP loopback", "high"))
    return out


def _rt_local(rts: list[str]) -> set[str]:
    return {r.split(":")[-1] for r in rts}  # FRR matches the VNI part for auto-derived eBGP RTs


def rule_evpn(f: Fabric, st: dict) -> list[DFinding]:
    out = []
    for v in f.vlans:
        have = {leaf.name: st["nodes"][leaf.name].get("vni_rts", {}).get(str(v.vni))
                for leaf in f.leaves if st["nodes"][leaf.name].get("vni_rts", {}).get(str(v.vni))}
        bad: set[str] = set()
        ev = []
        for a, ra in have.items():
            for b, rb in have.items():
                if a != b and not (_rt_local(ra["import"]) & _rt_local(rb["export"])):
                    bad.add(a)
                    ev.append(f"VNI {v.vni}: {a} imports {ra['import']} but {b} exports {rb['export']}")
        if bad:
            out.append(DFinding("EVPN routes", "rt-mismatch", sorted(bad), ev[:4],
                                f"Route-targets of VNI {v.vni} do not match between leaves; routes are not imported",
                                "high"))
    return out


def rule_maps(f: Fabric, st: dict) -> list[DFinding]:
    out = []
    for leaf in f.leaves:
        n = st["nodes"][leaf.name]
        if not n.get("reachable"):
            continue
        if not any(i.get("type") == "L2" for i in n.get("evpn_vni", {}).values()):
            out.append(DFinding("VNI/VLAN maps", "advertise-all-vni-missing", [leaf.name],
                                [f"{leaf.name}: FRR EVPN knows no VNI at all although the kernel has VXLAN devices"],
                                f"{leaf.name} runs no `advertise-all-vni`: EVPN is not picking up any VNI", "medium"))
            continue
        for v in f.leaf_vlans(leaf.name):
            got = n.get("vxlan", {}).get(f"br{v.id}")
            if got != v.vni:
                out.append(DFinding("VNI/VLAN maps", "vni-mismatch", [leaf.name],
                                    [f"{leaf.name}: bridge br{v.id} carries VNI {got}, inventory says {v.vni}"],
                                    f"VLAN {v.id} is mapped to the wrong VNI on {leaf.name}", "high"))
        for vrf in f.leaf_vrfs(leaf.name):
            info = n.get("evpn_vni", {}).get(str(vrf.l3vni))
            if not info or info.get("type") != "L3" or info.get("tenantVrf") != vrf.name:
                out.append(DFinding("VNI/VLAN maps", "missing-l3vni", [leaf.name],
                                    [f"{leaf.name}: EVPN has no L3 VNI {vrf.l3vni} bound to VRF {vrf.name} (saw {info})"],
                                    f"L3VNI {vrf.l3vni} is not mapped to VRF {vrf.name} on {leaf.name}", "high"))
    return out


def rule_forwarding(f: Fabric, st: dict) -> list[DFinding]:
    out = []
    for sw in f.spines + f.leaves:
        pol = st["nodes"][sw.name].get("hash_policy")
        if pol not in (None, -1) and pol != f.ecmp_hash_policy:
            out.append(DFinding("Forwarding", "ecmp-hash-policy", [sw.name],
                                [f"{sw.name}: fib_multipath_hash_policy={pol}, inventory says {f.ecmp_hash_policy}"],
                                f"{sw.name} hashes routed flows on L3 only; multi-flow traffic polarises onto one uplink",
                                "high"))
    return out


def rule_fdb(f: Fabric, st: dict) -> list[DFinding]:
    out: list[DFinding] = []
    for leaf in f.leaves:
        for br, mac in st["nodes"][leaf.name].get("bridge_mac", {}).items():
            if mac.lower() != f.anycast_gw_mac.lower():
                out.append(DFinding("FDB / ARP", "gateway-mac-mismatch", [leaf.name],
                                    [f"{leaf.name}:{br} MAC {mac}, anycast MAC is {f.anycast_gw_mac}"],
                                    f"The anycast gateway MAC on {leaf.name} differs from the fabric-wide value", "high"))
    for leaf in f.leaves:
        for vni, macs in st["nodes"][leaf.name].get("evpn_macs", {}).items():
            for mac, info in macs.items():
                if info.get("isDuplicate") or (info.get("type") == "local" and info.get("detectionCount", 0) >= 2):
                    out.append(DFinding("FDB / ARP", "duplicate-mac", [leaf.name],
                                        [f"{leaf.name} VNI {vni}: MAC {mac} moving between leaves "
                                         f"(detectionCount {info.get('detectionCount')}, seq {info.get('localSequence')}/"
                                         f"{info.get('remoteSequence')}, duplicate={info.get('isDuplicate')})"],
                                        f"MAC {mac} keeps moving between two leaves: duplicate address or loop", "high"))
    seen: dict[str, set[str]] = {}
    for leaf in f.leaves:
        for rd, keys in st["nodes"][leaf.name].get("evpn_by_rd", {}).items():
            for k in keys:
                mm = re.match(r"\[2\]:\[0\]:\[48\]:\[([0-9a-f:]+)\]", k)
                if mm:
                    seen.setdefault(mm.group(1), set()).add(rd.split(":")[0])
    dups = {m: o for m, o in seen.items() if len(o) > 1}
    for m, o in sorted(dups.items()):
        out.append(DFinding("FDB / ARP", "duplicate-mac", sorted(o),
                            [f"MAC {m} is advertised as local by VTEPs {sorted(o)}"],
                            f"The same MAC {m} lives behind two leaves (duplicate address or loop)", "medium"))
    return out


RULES = [("L1 links", rule_l1), ("Underlay MTU", rule_mtu), ("BGP sessions", rule_bgp),
         ("VTEP reachability", rule_vtep), ("EVPN routes", rule_evpn), ("VNI/VLAN maps", rule_maps),
         ("Forwarding", rule_forwarding), ("FDB / ARP", rule_fdb)]


def analyse(f: Fabric, st: dict) -> Diagnosis:
    """Apply the rules layer by layer. First layer with findings = primary; the rest = consequences."""
    d = Diagnosis(symptoms=st.get("dataplane", {}))
    for _layer, rule in RULES:
        found = rule(f, st)
        if found and not d.primary:
            d.primary = found
        elif found:
            d.consequences += found
    return d


def diagnose(f: Fabric) -> tuple[Diagnosis, dict]:
    st = collect(f)
    return analyse(f, st), st


def render(d: Diagnosis) -> str:
    lines = []
    if d.healthy:
        lines.append("HEALTHY: no layer reports a problem.")
    for i, x in enumerate(d.primary, 1):
        lines += [f"[{i}] Layer: {x.layer}", f"    Cause: {x.cause_key} on {', '.join(x.nodes)} (confidence {x.confidence})",
                  f"    Probable cause: {x.probable_cause}"] + [f"    Evidence: {e}" for e in x.evidence]
    for x in d.consequences:
        lines.append(f"  (higher layer, probable consequence) {x.layer}: {x.cause_key} on {', '.join(x.nodes)}")
    names = {"c1": "h1>h3 same-subnet", "c2": "h1>h2 local-route", "c3": "h1>h4 routed", "c4": "h1>h5 isolation"}
    lines.append("Customer view: " + ", ".join(
        f"{names.get(k, k)}={('BREACH' if v else 'isolated') if k == 'c4' else ('ok' if v else 'FAIL')}"
        for k, v in d.symptoms.items()))
    return "\n".join(lines)


__all__ = ["analyse", "collect", "diagnose", "render", "Diagnosis", "DFinding", "LAYERS", "time"]
