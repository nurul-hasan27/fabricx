"""E5: does the underlay protocol matter for failure recovery? Same fault as E1 (leaf1 uplink used by the h1 -> h3 probe),
underlay generated from the inventory as eBGP (E1 data), OSPF or IS-IS (+ iBGP EVPN, spines as route reflectors).

Usage: python experiments/E5/run.py <ospf|isis> <bfd|nobfd> <carrier|gray> <runs> <duration>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "experiments/E1")
import run as e1  # noqa: E402

from fabricx.faults.catalogue import vty  # noqa: E402

F = e1.F
OUT = Path("experiments/E5/results")


def set_bfd(proto: str, on: bool) -> None:
    cmd = {"ospf": "ip ospf bfd", "isis": "isis bfd"}[proto]
    for sw in F.spines + F.leaves:
        for lp in F.link_peers(sw.name):
            vty(F, sw.name, f"interface {lp.local_if}", cmd if on else f"no {cmd}")
    e1.wait_converged()


def main() -> None:
    proto, bfd, fault, runs, dur = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
    set_bfd(proto, bfd == "bfd")
    label = f"{proto}-{bfd}"
    res = []
    for k in range(1, runs + 1):
        r = e1.one_run(label, fault, dur, OUT, k)
        res.append(r)
        print(f"{label}/{fault} run {k}: lost={r['lost']} gap={r['longest_gap_ms']:.1f} ms", flush=True)
        e1.wait_converged()
    g = [r["longest_gap_ms"] for r in res]
    summ = {"protocol": proto, "bfd": bfd, "fault": fault, "n": len(g), "min_ms": min(g),
            "median_ms": statistics.median(g), "max_ms": max(g)}
    (OUT / f"{label}_{fault}").mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}_{fault}" / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    main()
