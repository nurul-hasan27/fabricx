"""E7: does EVPN MAC mobility work, and how fast?

Host h4 (VLAN 20, MAC M) is physically moved between leaf2 and leaf1 by replacing its veth: the old cable is
deleted, a new one is created between h4 and the other leaf's br20 and h4 gets its MAC/IP back, then sends
one ping to the gateway (a host move is normally announced with a gratuitous ARP). A 1 ms probe h2 -> h4
(same subnet, L2VNI 10020, h2 stays on leaf1) measures the outage. Recorded per move: loss window, time to
first received probe after the cable swap, the EVPN MAC-mobility sequence number (MM) of h4's MAC, and
whether the previous leaf stopped claiming the MAC.
"""
from __future__ import annotations

import json
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from fabricx import model  # noqa: E402
from fabricx.faults import runner as fr  # noqa: E402
from fabricx.probe import analyze  # noqa: E402
from fabricx.runner import PREFIX, node_exec, sh  # noqa: E402

F = model.load()
LAB = F.name
H = F.hosts_by_name()
OUT = Path("experiments/E7/results")
OUT.mkdir(parents=True, exist_ok=True)
GW = F.vlan(20).gateway


def pid(node: str) -> str:
    return sh(f"docker inspect -f {{{{.State.Pid}}}} clab-{LAB}-{node}").stdout.strip()


def mac_of(node: str) -> str:
    return node_exec(LAB, node, "cat /sys/class/net/eth1/address").stdout.strip()


def free_port(leaf: str) -> str:
    out = node_exec(LAB, leaf, "ls /sys/class/net").stdout.split()
    n = 1
    while f"eth{n}" in out:
        n += 1
    return f"eth{n}"


def port_of_h4(leaf: str) -> str | None:
    """Which leaf port is bridged in br20 and faces h4 (the one whose peer is h4's eth1)?"""
    idx = node_exec(LAB, "h4", "cat /sys/class/net/eth1/iflink").stdout.strip()
    for name in node_exec(LAB, leaf, "ls /sys/class/net").stdout.split():
        if node_exec(LAB, leaf, f"cat /sys/class/net/{name}/ifindex").stdout.strip() == idx:
            return name
    return None


def move_live(src_leaf: str, dst_leaf: str, mac: str) -> None:
    """Live-migration style: the new port announces the MAC on the new leaf BEFORE the old cable is removed."""
    new_if = free_port(dst_leaf)
    sh("ip link add fxa type veth peer name fxb")
    sh(f"ip link set fxa netns {pid('h4')}")
    sh(f"ip link set fxb netns {pid(dst_leaf)}")
    node_exec(LAB, "h4", f"ip link set fxa address {mac} up")
    node_exec(LAB, "h4", f"ip addr add {H['h4'].ip}/{F.vlan(20).subnet.prefixlen} dev fxa noprefixroute")
    node_exec(LAB, dst_leaf, f"ip link set fxb name {new_if}")
    node_exec(LAB, dst_leaf, f"ip link set {new_if} master br20 up")
    node_exec(LAB, "h4", f"ping -c 2 -W 1 -I fxa {GW}")   # new leaf learns the MAC while the old leaf still has it
    node_exec(LAB, "h4", f"sh -c 'ip link del eth1; ip link set fxa name eth1; ip route replace default via {GW} dev eth1'")


def move(src_leaf: str, dst_leaf: str, mac: str) -> None:
    node_exec(LAB, "h4", "ip link del eth1")             # removes both ends of the old veth
    new_if = free_port(dst_leaf)
    sh("ip link add fxa type veth peer name fxb")
    sh(f"ip link set fxa netns {pid('h4')}")
    sh(f"ip link set fxb netns {pid(dst_leaf)}")
    node_exec(LAB, "h4", f"ip link set fxa name eth1 address {mac}")
    node_exec(LAB, dst_leaf, f"ip link set fxb name {new_if}")
    node_exec(LAB, dst_leaf, f"ip link set {new_if} master br20 up")
    node_exec(LAB, "h4", f"ip addr add {H['h4'].ip}/{F.vlan(20).subnet.prefixlen} dev eth1")
    node_exec(LAB, "h4", "ip link set eth1 up")
    node_exec(LAB, "h4", f"ip route replace default via {GW} dev eth1")


def mm_seq(leaf: str, mac: str) -> int | None:
    out = node_exec(LAB, leaf, "vtysh -c 'show bgp l2vpn evpn route json'").stdout
    seqs = [int(x) for x in re.findall(r"MM:(\d+)", "".join(
        json.dumps(p) for rd, v in json.loads(out).items() if isinstance(v, dict)
        for k, p in v.items() if k.startswith("[2]") and mac in k))]
    return max(seqs) if seqs else 0


def claimed_local(leaf: str, mac: str) -> bool:
    out = node_exec(LAB, leaf, "vtysh -c 'show evpn mac vni 10020 json'").stdout
    return json.loads(out).get("macs", {}).get(mac, {}).get("type") == "local"


def one_move(k: int, src: str, dst: str, mode: str) -> dict:
    mac = mac_of("h4")
    rx = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-h4 python3 /opt/probe.py recv --bind {H['h4'].ip} --port 9000 --duration 14 --out /tmp/r.csv"),
        stdout=subprocess.PIPE, text=True)
    time.sleep(1)
    tx = subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-h2 python3 /opt/probe.py send --src {H['h2'].ip} --dst {H['h4'].ip} --port 9000 "
        f"--interval-ms 1 --duration 10"), stdout=subprocess.PIPE, text=True)
    time.sleep(3)
    t_move = time.time_ns()
    (move_live if mode == "live" else move)(src, dst, mac)
    t_moved = time.time_ns()
    node_exec(LAB, "h4", f"ping -c 1 -W 1 {GW}")            # announce the host on the new leaf
    sent = int(tx.communicate(timeout=60)[0].strip())
    rx.communicate(timeout=60)
    csv = node_exec(LAB, "h4", "cat /tmp/r.csv", 60).stdout.splitlines()[1:]
    rows = [tuple(int(x) for x in ln.split(",")) for ln in csv]
    res = analyze(rows, sent)
    after = sorted(r[2] for r in rows if r[2] > t_moved)
    time.sleep(3)
    res.update({"run": k, "mode": mode, "from": src, "to": dst, "mm_seq_after": mm_seq("leaf1" if dst != "leaf1" else "leaf2", mac),
                "old_leaf_still_claims_mac": claimed_local(src, mac),
                "first_rx_after_cable_swap_ms": (after[0] - t_moved) / 1e6 if after else None,
                "cable_swap_took_ms": (t_moved and (t_moved - t_move) / 1e6)})
    return res


def main(n: int = 10, mode: str = "live") -> None:
    fr.wait_healthy(F)
    node_exec(LAB, "h2", f"ping -c 1 -W 1 {GW}")
    where = "leaf2"
    results = []
    for k in range(1, n + 1):
        dst = "leaf1" if where == "leaf2" else "leaf2"
        r = one_move(k, where, dst, mode)
        where = dst
        results.append(r)
        print(r, flush=True)
        time.sleep(5)
    (OUT / f"{mode}_moves.json").write_text(json.dumps(results, indent=1))
    g = [r["longest_gap_ms"] for r in results]
    lost = [r["lost"] for r in results]
    summ = {"n": n, "outage_ms": {"min": min(g), "median": statistics.median(g), "max": max(g)},
            "lost_median": statistics.median(lost),
            "mm_seq_after": [r["mm_seq_after"] for r in results],
            "old_leaf_claims_after": sum(r["old_leaf_still_claims_mac"] for r in results)}
    (OUT / f"{mode}_summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main(mode=sys.argv[1] if len(sys.argv) > 1 else "live")
