"""E3: what does an underlay MTU mismatch look like to a customer?

Scenarios (one fabric link set to MTU 1500, everything else 9100):
  local  : the bad link is leaf1's own uplink used by the probe flow
  remote : the bad link is the spine->leaf2 link on the path (leaf1 cannot see it directly)
Measured per scenario: largest DF ping payload that works (bisect), and iperf3 TCP throughput h1 -> h3.
Raw outputs are stored under experiments/E3/results/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "experiments/E1")
import run as e1  # noqa: E402  (reuse used_uplink, wait_converged)

from fabricx.runner import node_exec  # noqa: E402

F, LAB = e1.F, e1.LAB
H = F.hosts_by_name()
OUT = Path("experiments/E3/results")
OUT.mkdir(parents=True, exist_ok=True)


def setmtu(node: str, ifname: str, mtu: int) -> None:
    node_exec(LAB, node, f"ip link set {ifname} mtu {mtu}")


def flush() -> None:
    for n in ("leaf1", "leaf2", "spine1", "spine2", "h1", "h3"):
        node_exec(LAB, n, "ip route flush cache")


def ping_ok(size: int) -> bool:
    return node_exec(LAB, "h1", f"ping -M do -c 2 -W 1 -s {size} {H['h3'].ip}", 20).returncode == 0


def max_payload(lo: int = 1000, hi: int = 1472) -> int:
    """Largest ICMP payload that passes with DF set (bisect; assumes monotonic)."""
    flush()
    assert ping_ok(lo), "even a small DF ping fails"
    if ping_ok(hi):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        flush()
        lo, hi = (mid, hi) if ping_ok(mid) else (lo, mid)
    return lo


def iperf(seconds: int = 5) -> dict:
    node_exec(LAB, "h3", "pkill iperf3")
    node_exec(LAB, "h3", "iperf3 -s -D")
    r = node_exec(LAB, "h1", f"timeout {seconds + 15} iperf3 -c {H['h3'].ip} -t {seconds} -J", seconds + 30)
    try:
        j = json.loads(r.stdout)
        return {"bits_per_second": j["end"]["sum_sent"]["bits_per_second"],
                "retransmits": j["end"]["sum_sent"].get("retransmits"), "error": j.get("error")}
    except Exception:  # noqa: BLE001
        return {"bits_per_second": 0, "retransmits": None, "error": "no result (timed out / stalled): " + r.stdout[-200:]}


def block_icmp_frag(node: str, ifname: str, on: bool) -> None:
    """Emulate 'ICMP filtered somewhere': drop ICMP type 3 leaving <node>:<ifname> (tc u32, no iptables in the image)."""
    if on:
        node_exec(LAB, node, f"tc qdisc add dev {ifname} root handle 1: prio")
        node_exec(LAB, node, f"tc filter add dev {ifname} parent 1: protocol ip prio 1 u32 "
                             "match ip protocol 1 0xff match ip icmp_type 3 0xff action drop")
    else:
        node_exec(LAB, node, f"tc qdisc del dev {ifname} root")


def scenario(name: str, targets: list[tuple[str, str]], icmp_block: tuple[str, str] | None = None) -> dict:
    for n, i in targets:
        setmtu(n, i, 1500)
    if icmp_block:
        block_icmp_frag(*icmp_block, True)
    res = {"scenario": name, "bad_links": targets, "icmp_blocked_on": icmp_block}
    flush()
    ev = node_exec(LAB, "h1", f"ping -M do -c 2 -W 1 -s 1430 {H['h3'].ip}", 20)
    res["evidence_ping_1430"] = (ev.stdout + ev.stderr).strip()
    res["max_df_payload"] = max_payload()
    res["expected_threshold"] = 1500 - 50 - 28
    res["iperf"] = iperf()
    if icmp_block:
        block_icmp_frag(*icmp_block, False)
    for n, i in targets:
        setmtu(n, i, F.fabric_mtu)
    flush()
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res), flush=True)
    return res


def main() -> None:
    e1.wait_converged()
    base = {"scenario": "baseline", "max_df_payload": max_payload(), "iperf": iperf()}
    (OUT / "baseline.json").write_text(json.dumps(base, indent=1))
    print(json.dumps(base), flush=True)
    up = e1.used_uplink()
    lk = next(x for x in F.fabric_links() if x.leaf == "leaf1" and x.leaf_if == up)
    spine = lk.spine
    scenario("local", [("leaf1", up), (spine, lk.spine_if)])
    lk2 = next(x for x in F.fabric_links() if x.leaf == "leaf2" and x.spine == spine)
    bad = [(spine, lk2.spine_if), ("leaf2", lk2.leaf_if)]
    scenario("remote", bad)
    scenario("remote_icmp_blocked", bad, icmp_block=(spine, lk.spine_if))  # spine -> leaf1 direction


if __name__ == "__main__":
    main()
