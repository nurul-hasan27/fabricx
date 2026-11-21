"""E1: how long is the outage when a leaf-spine link fails, with and without BFD?

Usage: python experiments/E1/run.py --profile bfd|nobfd|default --fault carrier|gray --runs 10 --duration 10
Everything runs against the live lab. Raw probe data is kept (gzipped) next to each result.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from fabricx import model  # noqa: E402
from fabricx.probe import analyze  # noqa: E402
from fabricx.runner import PREFIX, node_exec  # noqa: E402

F = model.load()
LAB = F.name
SRC, DST = "h1", "h3"                      # same subnet, different leaf (L2VNI)
SENDER_LEAF = "leaf1"
PROFILES = {  # name: (bfd?, keepalive, hold)
    "bfd": (True, 3, 9),
    "nobfd": (False, 3, 9),
    "default": (False, 60, 180),
}


def vty(node: str, *cmds: str) -> None:
    args = " ".join(f"-c {shlex.quote(c)}" for c in ["configure terminal", *cmds])
    node_exec(LAB, node, f"vtysh {args}")


def set_profile(name: str) -> None:
    bfd, ka, hold = PROFILES[name]
    for sw in F.spines + F.leaves:
        cmds = [f"router bgp {sw.asn}", f"neighbor FABRIC timers {ka} {hold}"]
        if bfd:
            cmds += ["neighbor FABRIC bfd", "neighbor FABRIC bfd profile dc"]
        else:
            cmds += ["no neighbor FABRIC bfd"]
        vty(sw.name, *cmds)
    for sw in F.spines + F.leaves:
        node_exec(LAB, sw.name, "vtysh -c 'clear bgp *'")
    wait_converged()


def nexthops(leaf: str, dst: str) -> int:
    out = node_exec(LAB, leaf, f"ip route show {F.switch(dst).loopback}").stdout
    return out.count("nexthop via")


def wait_converged(timeout: int = 400) -> float:
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = all(nexthops(l.name, o.name) == len(F.spines)
                 for l in F.leaves for o in F.leaves if l.name != o.name)
        if ok:
            time.sleep(3)
            return time.time() - t0
        time.sleep(2)
    raise RuntimeError("fabric did not converge")


def tx(leaf: str, ifname: str) -> int:
    return int(node_exec(LAB, leaf, f"cat /sys/class/net/{ifname}/statistics/tx_packets").stdout)


def used_uplink() -> str:
    """Which leaf1 uplink does the probe flow use? Compare tx counters across a short probe."""
    ups = sorted({lk.leaf_if for lk in F.fabric_links() if lk.leaf == SENDER_LEAF})
    before = {u: tx(SENDER_LEAF, u) for u in ups}
    node_exec(LAB, SRC, f"python3 /opt/probe.py send --src {F.hosts_by_name()[SRC].ip} "
                        f"--dst {F.hosts_by_name()[DST].ip} --port 9001 --interval-ms 1 --duration 1", 30)
    delta = {u: tx(SENDER_LEAF, u) - before[u] for u in ups}
    return max(delta, key=delta.get)


def one_run(profile: str, fault: str, duration: float, outdir: Path, k: int) -> dict:
    h = F.hosts_by_name()
    uplink = used_uplink()
    inject_at = 3.0
    rx = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-{DST} python3 /opt/probe.py recv --bind {h[DST].ip} --port 9000 "
        f"--duration {duration + 4} --out /tmp/r.csv"), stdout=subprocess.PIPE, text=True)
    time.sleep(1)
    tx_p = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-{SRC} python3 /opt/probe.py send --src {h[SRC].ip} --dst {h[DST].ip} "
        f"--port 9000 --interval-ms 1 --duration {duration}"), stdout=subprocess.PIPE, text=True)
    time.sleep(inject_at)
    inj = ("ip link set {i} down" if fault == "carrier" else "tc qdisc add dev {i} root netem loss 100%").format(i=uplink)
    t_inj = int(node_exec(LAB, SENDER_LEAF, f"sh -c 'python3 /opt/probe.py now; {inj}'").stdout.split()[0])
    sent = int(tx_p.communicate(timeout=duration + 60)[0].strip())
    rx.communicate(timeout=60)
    rest = ("ip link set {i} up" if fault == "carrier" else "tc qdisc del dev {i} root").format(i=uplink)
    t_rest = int(node_exec(LAB, SENDER_LEAF, f"sh -c 'python3 /opt/probe.py now; {rest}'").stdout.split()[0])
    csv = node_exec(LAB, DST, "cat /tmp/r.csv", 60).stdout
    rows = [tuple(int(x) for x in ln.split(",")) for ln in csv.splitlines()[1:]]
    res = analyze(rows, sent)
    ordered = sorted(rows, key=lambda r: r[2])
    gaps = [(b[2] - a[2], a[2]) for a, b in zip(ordered, ordered[1:])]
    g, start = max(gaps) if gaps else (0, 0)
    res.update({"profile": profile, "fault": fault, "run": k, "uplink": uplink,
                "gap_start_after_inject_ms": (start - t_inj) / 1e6, "inject_ts_ns": t_inj,
                "restore_ts_ns": t_rest, "interval_ms": 1.0})
    d = outdir / f"{profile}_{fault}" / f"run{k:02d}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(json.dumps(res, indent=1))
    with gzip.open(d / "probe.csv.gz", "wt") as fh:
        fh.write(csv)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=PROFILES, required=True)
    ap.add_argument("--fault", choices=["carrier", "gray"], required=True)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--duration", type=float, default=10)
    ap.add_argument("--out", default="experiments/E1/results")
    ap.add_argument("--keep-profile", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    set_profile(a.profile)
    results = []
    for k in range(1, a.runs + 1):
        r = one_run(a.profile, a.fault, a.duration, out, k)
        print(f"{a.profile}/{a.fault} run {k}: lost={r['lost']} longest_gap_ms={r['longest_gap_ms']:.1f} "
              f"starts +{r['gap_start_after_inject_ms']:.0f}ms uplink={r['uplink']}", flush=True)
        results.append(r)
        wait_converged()
    gaps = [r["longest_gap_ms"] for r in results]
    summary = {"profile": a.profile, "fault": a.fault, "n": len(gaps), "min_ms": min(gaps),
               "median_ms": statistics.median(gaps), "max_ms": max(gaps)}
    (out / f"{a.profile}_{a.fault}" / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
