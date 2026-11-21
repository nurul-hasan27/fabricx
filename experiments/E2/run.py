"""E2: does ECMP actually spread traffic, and what controls it?

64 parallel TCP flows (different source ports) h1 -> h3 for 5 s, for fib_multipath_hash_policy 0 (L3 only)
and 1 (L3 + L4). Measured: per-link TX packet share on leaf1's uplinks and on the spines' downlinks to leaf2,
and how many distinct VXLAN outer UDP source ports leave leaf1 (the entropy transit spines can hash on).
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from fabricx import model  # noqa: E402
from fabricx.runner import PREFIX, node_exec, sh  # noqa: E402

F = model.load()
LAB = F.name
H = F.hosts_by_name()
OUT = Path("experiments/E2/results")
OUT.mkdir(parents=True, exist_ok=True)


def set_policy(p: int) -> None:
    for sw in F.spines + F.leaves:
        node_exec(LAB, sw.name, f"sysctl -w net.ipv4.fib_multipath_hash_policy={p}")


def tx(node: str, ifname: str) -> int:
    return int(node_exec(LAB, node, f"cat /sys/class/net/{ifname}/statistics/tx_packets").stdout)


def run(policy: int) -> dict:
    set_policy(policy)
    leaf_ups = [(lk.leaf, lk.leaf_if) for lk in F.fabric_links() if lk.leaf == "leaf1"]
    sp_downs = [(lk.spine, lk.spine_if) for lk in F.fabric_links() if lk.leaf == "leaf2"]
    pts = leaf_ups + sp_downs
    node_exec(LAB, "h3", "pkill iperf3")
    node_exec(LAB, "h3", "iperf3 -s -D")
    time.sleep(1)
    pid = sh(f"docker inspect -f {{{{.State.Pid}}}} clab-{LAB}-leaf1").stdout.strip()
    cap = subprocess.Popen(shlex.split(PREFIX) + ["nsenter", "-t", pid, "-n", "timeout", "6", "tcpdump", "-nn", "-i", "any",
                                                  "-c", "4000", "udp", "dst", "port", "4789"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    time.sleep(1)
    before = {p: tx(*p) for p in pts}
    r = node_exec(LAB, "h1", f"iperf3 -c {H['h3'].ip} -t 5 -P 64 -J", 60)
    after = {p: tx(*p) for p in pts}
    j = json.loads(r.stdout)
    text = cap.communicate(timeout=30)[0]
    ports = set(re.findall(rf"{F.switch('leaf1').loopback}\.(\d+) >", text))
    out = {"policy": policy, "tx_packets": {f"{n}:{i}": after[(n, i)] - before[(n, i)] for n, i in pts},
           "iperf_Mbps": round(j["end"]["sum_sent"]["bits_per_second"] / 1e6),
           "distinct_outer_udp_src_ports": len(ports)}
    for name, group in (("leaf1_uplinks", leaf_ups), ("spine_downlinks_to_leaf2", sp_downs)):
        vals = [after[p] - before[p] for p in group]
        tot = sum(vals) or 1
        out[name] = {"share": [round(v / tot, 3) for v in vals], "imbalance_ratio": round(max(vals) / max(min(vals), 1), 2)}
    return out


def underlay_flows(policy: int) -> dict:
    """Control experiment: 64 plain UDP flows (distinct source ports) leaf1 loopback -> leaf2 loopback, no VXLAN."""
    set_policy(policy)
    ups = [(lk.leaf, lk.leaf_if) for lk in F.fabric_links() if lk.leaf == "leaf1"]
    before = {p: tx(*p) for p in ups}
    l1, l2 = F.switch("leaf1").loopback, F.switch("leaf2").loopback
    node_exec(LAB, "leaf1", "sh -c 'for i in $(seq 64); do python3 /opt/probe.py send --src " + f"{l1} --dst {l2}"
              " --port 9000 --interval-ms 2 --duration 4 >/dev/null & done; wait'", 60)
    after = {p: tx(*p) for p in ups}
    vals = [after[p] - before[p] for p in ups]
    tot = sum(vals) or 1
    return {"policy": policy, "kind": "plain_udp_64_flows", "leaf1_uplink_share": [round(v / tot, 3) for v in vals]}


def main() -> None:
    res = {}
    for p in (0, 1, 0, 1):  # repeated to see run-to-run variation
        res.setdefault(f"policy{p}", []).append(run(p))
    res["control_plain_routed_flows"] = [underlay_flows(p) for p in (0, 1, 0, 1)]
    (OUT / "summary.json").write_text(json.dumps(res, indent=1))
    for r in res["control_plain_routed_flows"]:
        print("control", r)
    for k, runs in res.items():
        if k.startswith("control"):
            continue
        for r in runs:
            print(k, "leaf1 shares", r["leaf1_uplinks"]["share"], "spine->leaf2 shares",
                  r["spine_downlinks_to_leaf2"]["share"], "ports", r["distinct_outer_udp_src_ports"], r["iperf_Mbps"], "Mbps")


if __name__ == "__main__":
    main()
