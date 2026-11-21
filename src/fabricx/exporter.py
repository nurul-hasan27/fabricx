"""Prometheus exporter for the FRR (and SONiC-VS) fabric.

On every scrape it runs ONE `docker exec` per switch that prints BGP summary, BFD peers, EVPN routes (leaves)
and interface counters, separated by a marker line; it parses them with the same parsers the validators use
and answers /metrics in Prometheus text format (standard library only).

Collect-on-scrape is deliberate. The first version polled on its own 5 s timer while Prometheus scraped on
another 5 s timer; unsynchronised, two scrapes could see the same counters (rate 0) and the next one ten
seconds of bytes (double rate) - seen in the Phase 8 demo. A scrape now always gets fresh counters.
Metric names follow the blueprint: fabricx_bgp_peer_up, fabricx_bfd_peer_up, fabricx_evpn_routes{type},
interface byte/drop counters.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import parsers
from .model import Fabric
from .runner import NodeUnreachable, node_exec

SEP = "@@FABRICX@@"
FABRIC_IF = re.compile(r"^(eth[1-9]\d*|Ethernet\d+)$")   # data ports only: not eth0 (management) or lo
HELP = {
    "fabricx_up": ("gauge", "1 if the switch answered the last poll"),
    "fabricx_bgp_peer_up": ("gauge", "1 if the BGP session to the peer is Established"),
    "fabricx_bfd_peer_up": ("gauge", "1 if the BFD session to the peer is up"),
    "fabricx_evpn_routes": ("gauge", "EVPN routes in the switch's table, by route type"),
    "fabricx_iface_up": ("gauge", "1 if the interface operstate is UP"),
    "fabricx_iface_rx_bytes_total": ("counter", "bytes received"),
    "fabricx_iface_tx_bytes_total": ("counter", "bytes sent"),
    "fabricx_iface_rx_dropped_total": ("counter", "packets dropped on receive"),
    "fabricx_iface_tx_dropped_total": ("counter", "packets dropped on transmit"),
    "fabricx_poll_seconds": ("gauge", "how long the last poll of all switches took"),
}


@dataclass
class Sample:
    name: str
    labels: dict[str, str] = field(default_factory=dict)
    value: float = 0.0


def command(f: Fabric, node: str) -> str:
    parts = ["vtysh -c 'show bgp summary json'"]
    if f.underlay.bfd_enabled:
        parts.append("vtysh -c 'show bfd peers json'")
    if f.switch(node) in f.leaves:
        parts.append("vtysh -c 'show bgp l2vpn evpn route json'")
    parts.append("ip -j -s link show")
    return "sh -c \"" + f"; echo {SEP}; ".join(parts) + "\""


def parse_node(f: Fabric, node: str, raw: str) -> list[Sample]:
    """Turn one node's combined output into samples. Pure: unit-tested with captured outputs."""
    secs = [s.strip() for s in raw.split(SEP)]
    names = {str(n.peer_ip): n.peer for n in f.neighbors(node)}
    out: list[Sample] = []
    i = 0
    for ip, state in parsers.bgp_peers(secs[i] or "{}").items():
        out.append(Sample("fabricx_bgp_peer_up", {"node": node, "peer": ip, "peer_name": names.get(ip, ip)},
                          float(state == "Established")))
    i += 1
    if f.underlay.bfd_enabled:
        for ip, status in parsers.bfd_peers(secs[i] or "[]").items():
            out.append(Sample("fabricx_bfd_peer_up", {"node": node, "peer": ip, "peer_name": names.get(ip, ip)},
                              float(status == "up")))
        i += 1
    if f.switch(node) in f.leaves:
        counts = parsers.evpn_counts(parsers.evpn_route_keys(secs[i] or "{}"))
        for typ, n in sorted(counts.items()):
            out.append(Sample("fabricx_evpn_routes", {"node": node, "type": str(typ)}, float(n)))
        i += 1
    for itf in json.loads(secs[i] or "[]"):
        name = itf.get("ifname", "")
        if not FABRIC_IF.match(name):
            continue
        lab = {"node": node, "iface": name}
        st = itf.get("stats64", {})
        out.append(Sample("fabricx_iface_up", lab, float(itf.get("operstate") == "UP")))
        for d in ("rx", "tx"):
            out.append(Sample(f"fabricx_iface_{d}_bytes_total", lab, float(st.get(d, {}).get("bytes", 0))))
            out.append(Sample(f"fabricx_iface_{d}_dropped_total", lab, float(st.get(d, {}).get("dropped", 0))))
    return out


def poll(f: Fabric) -> list[Sample]:
    t0 = time.monotonic()
    out: list[Sample] = []
    for sw in f.spines + f.leaves:
        try:
            r = node_exec(f.name, sw.name, command(f, sw.name), timeout=10)
            samples = parse_node(f, sw.name, r.stdout) if r.returncode == 0 else []
        except (NodeUnreachable, ValueError, IndexError):
            samples = []
        out.append(Sample("fabricx_up", {"node": sw.name}, float(bool(samples))))
        out.extend(samples)
    out.append(Sample("fabricx_poll_seconds", {}, round(time.monotonic() - t0, 3)))
    return out


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def render(samples: list[Sample]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for s in sorted(samples, key=lambda x: x.name):
        if s.name not in seen:
            seen.add(s.name)
            typ, text = HELP.get(s.name, ("gauge", s.name))
            lines += [f"# HELP {s.name} {text}", f"# TYPE {s.name} {typ}"]
        lab = ",".join(f'{k}="{_esc(v)}"' for k, v in sorted(s.labels.items()))
        lines.append(f"{s.name}{{{lab}}} {s.value:g}" if lab else f"{s.name} {s.value:g}")
    return "\n".join(lines) + "\n"


def serve(f: Fabric, port: int = 9101, min_age: float = 1.0) -> None:
    """Collect on scrape. Results younger than `min_age` seconds are reused, so two scrapers at once do not
    double the load on the switches."""
    lock = threading.Lock()
    cache = {"t": 0.0, "text": ""}

    def metrics() -> str:
        with lock:
            if time.monotonic() - cache["t"] > min_age:   # type: ignore[operator]
                cache["text"] = render(poll(f))
                cache["t"] = time.monotonic()
            return str(cache["text"])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:   # noqa: N802 (http.server API)
            body = metrics().encode() if self.path.startswith("/metrics") else b"fabricx exporter: /metrics\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
