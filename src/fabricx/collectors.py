"""Collectors: run a command on a node, ALWAYS keep the raw output, then normalise separately."""
from __future__ import annotations

from pathlib import Path

from . import parsers
from .model import Fabric
from .runner import NodeUnreachable, node_exec


class Collector:
    def __init__(self, fabric: Fabric, outdir: Path | None = None):
        self.f = fabric
        self.out = outdir

    def run(self, node: str, cmd: str, name: str) -> str:
        r = node_exec(self.f.name, node, cmd, timeout=15, retries=1)
        text = r.stdout if r.returncode == 0 else ""
        if self.out:
            p = self.out / "raw" / node / f"{name}.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(r.stdout + (f"\n[rc={r.returncode}] {r.stderr}" if r.returncode else ""))
        return text

    def node_state(self, node: str) -> dict:
        try:
            return self._node_state(node)
        except NodeUnreachable as e:
            return {"unreachable": e.reason}

    def _node_state(self, node: str) -> dict:
        sw = self.f.switch(node)
        st = {
            "bgp": parsers.bgp_peers(self.run(node, "vtysh -c 'show bgp summary json'", "bgp_summary") or "{}"),
            "interfaces": parsers.interfaces(self.run(node, "ip -j link show", "ip_link") or "[]"),
        }
        if self.f.underlay.bfd_enabled:
            st["bfd"] = parsers.bfd_peers(self.run(node, "vtysh -c 'show bfd peers json'", "bfd_peers") or "[]")
        if sw in self.f.leaves:
            st["nexthops"] = {o.name: parsers.nexthop_count(
                self.run(node, f"ip route show {o.loopback}", f"route_{o.name}"))
                for o in self.f.leaves if o.name != node}
            keys = parsers.evpn_route_keys(self.run(
                node, "vtysh -c 'show bgp l2vpn evpn route json'", "evpn_routes") or "{}")
            st["evpn_keys"] = keys
        return st

    def prime_hosts(self) -> None:
        """EVPN only learns hosts that have sent traffic ('silent host'): each host pings its gateway once."""
        for h in self.f.hosts:
            try:
                node_exec(self.f.name, h.name, f"ping -c 1 -W 2 {self.f.vlan(h.vlan).gateway}", timeout=15)
            except NodeUnreachable:
                pass  # reported by the reachability check, not here

    def snapshot(self) -> dict[str, dict]:
        self.prime_hosts()
        return {sw.name: self.node_state(sw.name) for sw in self.f.spines + self.f.leaves}
