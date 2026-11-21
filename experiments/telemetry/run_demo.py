"""Phase 8 acceptance demo: a link failure seen on the telemetry pipeline with real timestamps.

Needs: the fabric up, `fabricx exporter` running, Prometheus + Grafana up (scripts/monitoring.sh up),
FABRICX_PROM_URL and FABRICX_GRAFANA_URL set. Writes experiments/telemetry/results/.

Timeline: iperf3 h1 -> h3 (4 TCP streams, 50 Mbit/s each) for the whole run; at +30 s inject F01 (leaf1 eth1 down)
through the normal fault runner (which posts a Grafana annotation); at +60 s restore (annotation); stop at ~+95 s.
Then pull from Prometheus (5 s resolution) and keep iperf3's own 1 s intervals (finer than the scrape).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fabricx import model
from fabricx.faults import get
from fabricx.faults import runner as fr
from fabricx.runner import PREFIX, node_exec

F = model.load()
OUT = Path("experiments/telemetry/results")
OUT.mkdir(parents=True, exist_ok=True)
PROM = os.environ["FABRICX_PROM_URL"].rstrip("/")
GRAF = os.environ["FABRICX_GRAFANA_URL"].rstrip("/")
H = F.hosts_by_name()
LEAF = "leaf1"
DURATION = 95


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def prom_range(expr: str, start: float, end: float) -> list[dict]:
    q = urllib.parse.urlencode({"query": expr, "start": start, "end": end, "step": 5})
    return get_json(f"{PROM}/api/v1/query_range?{q}")["data"]["result"]


def main() -> None:
    node_exec(F.name, "h3", "sh -c 'pkill iperf3; iperf3 -s -D'")
    time.sleep(1)
    t0 = time.time()
    client = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{F.name}-h1 iperf3 -c {H['h3'].ip} -P 4 -b 50M -t {DURATION} -i 1 --json"),
        stdout=subprocess.PIPE, text=True)
    fault = get("F01")
    time.sleep(30)
    state = fr.inject(F, fault)
    t_inject = time.time()
    time.sleep(30)
    fr.restore(F, fault, state)
    t_restore = time.time()
    out, _ = client.communicate(timeout=DURATION + 60)
    t_end = time.time()
    time.sleep(12)   # let Prometheus scrape the tail

    ip = json.loads(out)
    base = ip["start"]["timestamp"]["timesecs"]
    iperf = [{"t": round(base + iv["sum"]["start"], 3), "mbps": round(iv["sum"]["bits_per_second"] / 1e6, 1)}
             for iv in ip["intervals"]]
    series = {
        "bgp_up": prom_range(f'fabricx_bgp_peer_up{{node="{LEAF}"}}', t0 - 10, t_end + 10),
        "bfd_up": prom_range(f'fabricx_bfd_peer_up{{node="{LEAF}"}}', t0 - 10, t_end + 10),
        "uplink_bps": prom_range(f'8 * irate(fabricx_iface_tx_bytes_total{{node="{LEAF}",iface=~"eth1|eth2"}}[20s])',
                                 t0 - 10, t_end + 10),
    }
    ann = get_json(f"{GRAF}/api/annotations?tags=fabricx&from={int(t0 * 1000)}&to={int(t_end * 1000)}")
    data = {"t0": t0, "t_inject": t_inject, "t_restore": t_restore, "t_end": t_end,
            "iperf_1s": iperf, "prometheus": series,
            "grafana_annotations": [{"time_ms": a["time"], "text": a["text"], "tags": a["tags"]} for a in ann],
            "iperf_retransmits": ip["end"]["sum_sent"].get("retransmits")}
    (OUT / "demo.json").write_text(json.dumps(data, indent=1))
    (OUT / "timeline.svg").write_text(svg(data))
    print(summary(data))
    (OUT / "summary.md").write_text(summary(data))


def _pts(vals: list[tuple[float, float]], t0: float, t1: float, vmax: float, y0: int, h: int, w: int) -> str:
    return " ".join(f"{60 + (t - t0) / (t1 - t0) * (w - 80):.1f},{y0 + h - (v / vmax) * h if vmax else y0 + h:.1f}"
                    for t, v in vals)


def svg(d: dict) -> str:
    """A plain timeline: iperf3 1 s throughput, leaf1 uplink tx (Prometheus), BGP/BFD sessions up, annotations."""
    w, t0, t1 = 900, d["t0"] - 5, d["t_end"] + 10
    ip = [(p["t"], p["mbps"]) for p in d["iperf_1s"]]
    rows = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} 520" font-family="sans-serif" font-size="12">',
            '<rect width="100%" height="100%" fill="white"/>']

    def band(title: str, y0: int, lines: list[tuple[str, str, list[tuple[float, float]]]], vmax: float, unit: str) -> None:
        rows.append(f'<text x="10" y="{y0 - 6}" font-weight="bold">{title}</text>')
        rows.append(f'<line x1="60" y1="{y0 + 110}" x2="{w - 20}" y2="{y0 + 110}" stroke="#999"/>')
        rows.append(f'<text x="10" y="{y0 + 10}">{vmax:g} {unit}</text><text x="10" y="{y0 + 110}">0</text>')
        for i, (label, color, vals) in enumerate(lines):
            rows.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.6" '
                        f'points="{_pts(vals, t0, t1, vmax, y0, 110, w)}"/>')
            rows.append(f'<text x="{w - 220}" y="{y0 + 14 + 14 * i}" fill="{color}">{label}</text>')

    band("iperf3 h1->h3 total (1 s intervals)", 30, [("throughput", "#1f6feb", ip)],
         max(v for _, v in ip) * 1.1, "Mbit/s")
    colors = {"eth1": "#d1242f", "eth2": "#1a7f37"}
    up = [(f"leaf1 {s['metric']['iface']} tx", colors.get(s["metric"]["iface"], "#555"),
           [(float(t), float(v) / 1e6) for t, v in s["values"]]) for s in d["prometheus"]["uplink_bps"]]
    vmax = max((v for _, _, vals in up for _, v in vals), default=1) * 1.1
    band("leaf1 uplinks (Prometheus, 5 s)", 190, up, vmax, "Mbit/s")

    def total(name: str) -> list[tuple[float, float]]:
        acc: dict[float, float] = {}
        for s in d["prometheus"][name]:
            for t, v in s["values"]:
                acc[float(t)] = acc.get(float(t), 0) + float(v)
        return sorted(acc.items())
    band("leaf1 sessions up (Prometheus)", 350, [("BGP", "#8250df", total("bgp_up")), ("BFD", "#bf8700", total("bfd_up"))],
         2.2, "")
    for a in d["grafana_annotations"]:
        x = 60 + (a["time_ms"] / 1000 - t0) / (t1 - t0) * (w - 80)
        rows.append(f'<line x1="{x:.1f}" y1="20" x2="{x:.1f}" y2="480" stroke="red" stroke-dasharray="4 3"/>')
        rows.append(f'<text x="{x + 3:.1f}" y="500" fill="red">{a["text"].split(":")[0]}</text>')
    rows.append(f'<text x="60" y="515" fill="#555">time axis: {t1 - t0:.0f} s; red dashed = Grafana annotations posted '
                'by the fault runner</text></svg>')
    return "\n".join(rows)


def summary(d: dict) -> str:
    def first_change(name: str, after: float, want: float) -> float | None:
        for s in d["prometheus"][name]:
            for t, v in s["values"]:
                if float(t) >= after and float(v) == want:
                    return float(t)
        return None
    ip = d["iperf_1s"]
    during = [p["mbps"] for p in ip if d["t_inject"] <= p["t"] < d["t_inject"] + 3]
    before = [p["mbps"] for p in ip if d["t_inject"] - 10 <= p["t"] < d["t_inject"]]
    down = first_change("bgp_up", d["t_inject"], 0.0)
    back = first_change("bgp_up", d["t_restore"], 1.0)
    lines = ["# Telemetry demo: F01 (leaf1 eth1 down) seen on the pipeline", "",
             f"- annotations posted: {[a['text'] for a in d['grafana_annotations']]}",
             f"- iperf3 mean 10 s before inject: {sum(before) / max(len(before), 1):.1f} Mbit/s; "
             f"first 3 s after inject: {during}",
             f"- first Prometheus sample showing a leaf1 BGP session down: "
             f"{'+%.1f s after inject' % (down - d['t_inject']) if down else 'none'}",
             f"- first sample with it back up after restore: "
             f"{'+%.1f s after restore' % (back - d['t_restore']) if back else 'none'}",
             f"- iperf3 retransmits (whole run): {d['iperf_retransmits']}",
             "- resolution: Prometheus 5 s scrape (exporter collects on each scrape); iperf3 1 s intervals"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
