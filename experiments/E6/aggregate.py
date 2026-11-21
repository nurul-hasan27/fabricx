"""Summarise E6 result folders into a markdown table (median and min-max over runs).
Usage: python experiments/E6/aggregate.py experiments/E6/results_ci [experiments/E6/results_mac ...]"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

COLS = [("total Mbit/s", lambda r: r["total_mbps"]),
        ("Jain fairness", lambda r: r["jain"]),
        ("queue drops", lambda r: r["queue"]["dropped"]),
        ("ECN marks", lambda r: r["queue"].get("marked")),
        ("ping RTT median ms", lambda r: r["rtt_loaded_ms"].get("median")),
        ("ping RTT p99 ms", lambda r: r["rtt_loaded_ms"].get("p99")),
        ("TCP mean RTT ms", lambda r: r.get("tcp_mean_rtt_ms")),
        ("retransmits", lambda r: r["retransmits"]),
        ("ping loss %", lambda r: r["ping_loss_pct"]),
        ("start skew s (max)", lambda r: r.get("start_skew_s")),
        ("connections without ECN", lambda r: r.get("handshakes", {}).get("no_ecn")),
        ("connections", lambda r: r.get("handshakes", {}).get("connections"))]


def cell(vals: list, agg: str = "median") -> str:
    v = [x for x in vals if x is not None]
    if not v:
        return "-"
    if agg == "max":
        return f"{max(v):g}"
    return f"{statistics.median(v):g} ({min(v):g}-{max(v):g})"


def table(folder: Path) -> str:
    meta = json.loads((folder / "meta.json").read_text())
    lines = [f"### {folder.name}  (kernel {meta['kernel']}, bottleneck {meta['bottleneck']} at {meta['rate']}, "
             f"{meta['run_s']} s per run)", "",
             "| scenario | runs | " + " | ".join(c for c, _ in COLS) + " |",
             "|---" * (len(COLS) + 2) + "|"]
    idle = []
    for f in sorted(folder.glob("[ABC].json")):
        d = json.loads(f.read_text())
        if "skipped" in d:
            lines.append(f"| {f.stem} | - | skipped: {d['skipped']} |" + " |" * (len(COLS) - 1))
            continue
        runs = d["runs"]
        idle += [r["rtt_idle_ms_median"] for r in runs]
        cells = [cell([fn(r) for r in runs], "max" if name.startswith("start skew") else "median") for name, fn in COLS]
        lines.append(f"| {f.stem} {d['name']} | {len(runs)} | " + " | ".join(cells) + " |")
    lines += ["", f"Idle RTT (ping, before load): median {statistics.median(idle):g} ms." if idle else "", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    print("\n".join(table(Path(p)) for p in sys.argv[1:]))
