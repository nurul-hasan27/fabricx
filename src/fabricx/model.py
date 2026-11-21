"""Typed fabric model. Loads inventory/fabric.yaml and derives everything else."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator


class Underlay(BaseModel):
    # ebgp | ospf | isis. For ospf/isis: iBGP EVPN over loopbacks, spines are route reflectors.
    protocol: str = "ebgp"
    ibgp_asn: int = 65000
    igp_hello_s: int = 10           # OSPF/IS-IS hello interval (protocol defaults 10 s; dead/hold = 4x / 3x)
    igp_dead_s: int = 40
    bgp_keepalive: int = 3
    bgp_hold: int = 9
    bfd_enabled: bool = True
    bfd_interval_ms: int = 300
    bfd_multiplier: int = 3
    max_paths: int = 2


class Neighbor(BaseModel):
    peer: str
    peer_ip: ipaddress.IPv4Address
    peer_asn: int
    local_if: str = ""


class LinkPeer(BaseModel):
    """The other end of a fabric link (always the /31 address), whatever the underlay protocol."""
    peer: str
    peer_ip: ipaddress.IPv4Address
    local_if: str


class Vrf(BaseModel):
    name: str
    l3vni: int


class Vlan(BaseModel):
    id: int
    vni: int
    subnet: ipaddress.IPv4Network
    vrf: str

    @property
    def gateway(self) -> ipaddress.IPv4Address:
        """Anycast gateway = first address of the subnet."""
        return self.subnet.network_address + 1


class Switch(BaseModel):
    name: str
    asn: int
    loopback: ipaddress.IPv4Address
    nos: str = "frr"   # frr | sonic-vs


class Sonic(BaseModel):
    """Settings for SONiC-VS nodes (Phase 7). trace_prefix is only used by experiment E8."""
    image: str
    trace_prefix: ipaddress.IPv4Network | None = None


def sonic_port(ifname: str) -> str:
    """Container interface -> SONiC port name, from the image's lanemap.ini (eth1 -> Ethernet0, eth2 -> Ethernet4)."""
    return f"Ethernet{4 * (int(ifname.removeprefix('eth')) - 1)}"


class Host(BaseModel):
    name: str
    leaf: str
    ip: ipaddress.IPv4Address
    vlan: int


class FabricLink(BaseModel):
    """One spine-leaf point-to-point /31."""
    spine: str
    leaf: str
    spine_if: str
    leaf_if: str
    spine_ip: ipaddress.IPv4Address
    leaf_ip: ipaddress.IPv4Address
    prefixlen: int = 31


class HostLink(BaseModel):
    host: str
    leaf: str
    leaf_if: str
    host_if: str = "eth1"


class Fabric(BaseModel):
    name: str
    frr_image: str
    host_image: str
    fabric_mtu: int
    vxlan_df: str = "set"
    ecmp_hash_policy: int = 1
    host_mtu: int
    fabric_link_base: ipaddress.IPv4Network
    anycast_gw_mac: str
    underlay: Underlay = Underlay()
    sonic: Sonic | None = None
    vrfs: list[Vrf]
    vlans: list[Vlan]
    spines: list[Switch]
    leaves: list[Switch]
    hosts: list[Host]

    @model_validator(mode="after")
    def _check(self) -> Fabric:
        names = [s.name for s in self.spines + self.leaves] + [h.name for h in self.hosts]
        if len(names) != len(set(names)):
            raise ValueError("node names must be unique")
        loops = [s.loopback for s in self.spines + self.leaves]
        if len(loops) != len(set(loops)):
            raise ValueError("loopbacks must be unique")
        leaf_asns = [leaf.asn for leaf in self.leaves]
        if len(leaf_asns) != len(set(leaf_asns)):
            raise ValueError("leaf ASNs must be unique")
        vlans = {v.id: v for v in self.vlans}
        vrfs = {v.name for v in self.vrfs}
        leaves = {leaf.name for leaf in self.leaves}
        for v in self.vlans:
            if v.vrf not in vrfs:
                raise ValueError(f"vlan {v.id} uses unknown vrf {v.vrf}")
        for h in self.hosts:
            if h.leaf not in leaves:
                raise ValueError(f"{h.name}: unknown leaf {h.leaf}")
            if h.vlan not in vlans:
                raise ValueError(f"{h.name}: unknown vlan {h.vlan}")
            if h.ip not in vlans[h.vlan].subnet:
                raise ValueError(f"{h.name}: {h.ip} not in {vlans[h.vlan].subnet}")
        for sw in self.spines + self.leaves:
            if sw.nos not in ("frr", "sonic-vs"):
                raise ValueError(f"{sw.name}: unknown nos {sw.nos}")
            if sw.nos == "sonic-vs":
                if self.sonic is None:
                    raise ValueError(f"{sw.name}: nos sonic-vs needs a 'sonic:' section with the image")
                if sw not in self.leaves or self.underlay.protocol != "ebgp":
                    raise ValueError(f"{sw.name}: SONiC-VS is supported as an eBGP leaf only")
                if any(h.leaf == sw.name for h in self.hosts):
                    raise ValueError(f"{sw.name}: SONiC-VS leaf is underlay-only in this phase (no hosts)")
        return self

    # ---- derived state (never hand-listed) ----
    def vlan(self, vlan_id: int) -> Vlan:
        return next(v for v in self.vlans if v.id == vlan_id)

    def fabric_links(self) -> list[FabricLink]:
        out = []
        base = int(self.fabric_link_base.network_address)
        for si, spine in enumerate(self.spines, start=1):
            for li, leaf in enumerate(self.leaves, start=1):
                a = base + si * 256 + 2 * (li - 1)
                out.append(FabricLink(
                    spine=spine.name, leaf=leaf.name,
                    spine_if=f"eth{li}", leaf_if=f"eth{si}",
                    spine_ip=ipaddress.IPv4Address(a),
                    leaf_ip=ipaddress.IPv4Address(a + 1),
                ))
        return out

    def host_links(self) -> list[HostLink]:
        out: list[HostLink] = []
        used: dict[str, int] = {}
        first_free = len(self.spines) + 1
        for h in self.hosts:
            n = used.get(h.leaf, first_free)
            used[h.leaf] = n + 1
            out.append(HostLink(host=h.name, leaf=h.leaf, leaf_if=f"eth{n}"))
        return out

    def leaf_vlans(self, leaf: str) -> list[Vlan]:
        """VLANs a leaf needs = the VLANs of the hosts plugged into it."""
        ids = sorted({h.vlan for h in self.hosts if h.leaf == leaf})
        return [self.vlan(i) for i in ids]

    def leaf_vrfs(self, leaf: str) -> list[Vrf]:
        names = {v.vrf for v in self.leaf_vlans(leaf)}
        return [v for v in self.vrfs if v.name in names]

    def hosts_by_name(self) -> dict[str, Host]:
        return {h.name: h for h in self.hosts}

    def switch(self, name: str) -> Switch:
        return next(s for s in self.spines + self.leaves if s.name == name)

    def routed_if(self, node: str, ifname: str) -> str:
        """Interface that carries IP for a fabric link. FRR nodes: the container interface itself.
        SONiC-VS: the SONiC port (Ethernet0...); the container's eth1 is only the wire underneath, and
        SONiC sizes it 22 bytes larger than the port MTU (seen on CI: eth1 9122 for Ethernet0 9100)."""
        return sonic_port(ifname) if self.switch(node).nos == "sonic-vs" else ifname

    def link_peers(self, name: str) -> list[LinkPeer]:
        res = []
        for lk in self.fabric_links():
            if lk.spine == name:
                res.append(LinkPeer(peer=lk.leaf, peer_ip=lk.leaf_ip, local_if=lk.spine_if))
            elif lk.leaf == name:
                res.append(LinkPeer(peer=lk.spine, peer_ip=lk.spine_ip, local_if=lk.leaf_if))
        return res

    def isis_net(self, name: str) -> str:
        """IS-IS NET derived from the loopback: each octet padded to 3 digits -> 12-digit system id."""
        digits = "".join(f"{int(o):03d}" for o in str(self.switch(name).loopback).split("."))
        return f"49.0001.{digits[0:4]}.{digits[4:8]}.{digits[8:12]}.00"

    def neighbors(self, name: str) -> list[Neighbor]:
        """BGP neighbours of a switch. eBGP underlay: link addresses. IGP underlay: iBGP to loopbacks
        (leaves peer with both spines; spines are route reflectors for every leaf)."""
        if self.underlay.protocol != "ebgp":
            sw = self.switch(name)
            others = self.leaves if sw in self.spines else self.spines
            return [Neighbor(peer=o.name, peer_ip=o.loopback, peer_asn=self.underlay.ibgp_asn) for o in others]
        res = []
        for lk in self.fabric_links():
            if lk.spine == name:
                res.append(Neighbor(peer=lk.leaf, peer_ip=lk.leaf_ip,
                                    peer_asn=self.switch(lk.leaf).asn, local_if=lk.spine_if))
            elif lk.leaf == name:
                res.append(Neighbor(peer=lk.spine, peer_ip=lk.spine_ip,
                                    peer_asn=self.switch(lk.spine).asn, local_if=lk.leaf_if))
        return res

    def iface_ips(self, switch: str) -> list[tuple[str, str]]:
        """(interface, 'a.b.c.d/31') for a switch's fabric links."""
        res = []
        for lk in self.fabric_links():
            if lk.spine == switch:
                res.append((lk.spine_if, f"{lk.spine_ip}/{lk.prefixlen}"))
            elif lk.leaf == switch:
                res.append((lk.leaf_if, f"{lk.leaf_ip}/{lk.prefixlen}"))
        return sorted(res)


def load(path: str | Path | None = None) -> Fabric:
    """Load the inventory. Default: $FABRICX_INVENTORY, else inventory/fabric.yaml (so the lab tests can run
    against a variant without code changes)."""
    path = path or os.environ.get("FABRICX_INVENTORY", "inventory/fabric.yaml")
    return Fabric.model_validate(yaml.safe_load(Path(path).read_text()))
