"""E6 - What does incast do to a switch queue, and how much do ECN and DCTCP help?

4 senders (h1, h2, h6 on leaf1; h4 on leaf2) -> 1 receiver (h3 on leaf2). The bottleneck is leaf2's port to h3,
shaped with a token bucket (TBF) to RATE. (HTB was tried first: in the Mac's VM it delivered only 16-55 Mbit/s of
a 100 Mbit/s class, TBF 91-95 Mbit/s - see analysis.md.) Under the shaper, the queue is one of:
  A  tail-drop  : pfifo, LIMIT_PKTS packets               hosts: cubic, ECN off
  B  RED + ECN  : step-like marking at ~K bytes queued    hosts: cubic, ECN on   (classic ECN)
  C  RED + ECN  : same queue                              hosts: DCTCP (needs the kernel's tcp_dctcp: x86 CI)
Per run (RUN_S seconds, 2 TCP streams per sender): receiver-side throughput per sender, Jain fairness,
retransmits, queue drops and ECN marks from `tc -s`, and RTT through the queue two ways: ping h1 -> h3 every
50 ms sent as ECN-capable (ToS ECT(0), `-Q 2`: a plain ping is not ECN-capable, so RED dropped 36% of the probes
in the first trial and the survivors understated the delay) and TCP's own smoothed RTT (iperf3 mean_rtt). Usage: python experiments/E6/run.py [scenarios] [runs]   e.g.  A,B 5
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

from fabricx import model, parsers
from fabricx.runner import PREFIX, node_exec

F = model.load("inventory/variants/e6-incast.yaml")
LAB = F.name
H = F.hosts_by_name()
SENDERS = ["h1", "h2", "h6", "h4"]
RECV = "h3"
LEAF = H[RECV].leaf
PORT = next(hl.leaf_if for hl in F.host_links() if hl.host == RECV)
RATE = "100mbit"
LIMIT_PKTS = 1000                        # tail-drop buffer: 1000 x 1.5 kB = 1.5 MB = 120 ms at 100 Mbit/s
K_MIN, K_MAX = 30000, 31500              # RED thresholds (bytes): marks once ~20 full packets are queued
RED = (f"red limit 400000 min {K_MIN} max {K_MAX} avpkt 1500 burst 21 bandwidth {RATE} probability 1.0 ecn")
SCEN = {"A": ("tail-drop, cubic", f"pfifo limit {LIMIT_PKTS}", "cubic", 0),
        "B": ("RED+ECN, cubic", RED, "cubic", 1),
        "C": ("RED+ECN, DCTCP", RED, "dctcp", 1)}
RUN_S = 20
OUT = Path("experiments/E6/results")


def ex(node: str, cmd: str, timeout: int = 60) -> str:
    return node_exec(LAB, node, cmd, timeout=timeout).stdout


def setup(qdisc: str, cc: str, ecn: int) -> None:
    ex(LEAF, f"sh -c 'tc qdisc del dev {PORT} root 2>/dev/null; true'")
    ex(LEAF, f"tc qdisc add dev {PORT} root handle 1: tbf rate {RATE} burst 60k limit 1000000")
    ex(LEAF, f"tc qdisc add dev {PORT} parent 1:1 handle 10: {qdisc}")
    for h in SENDERS + [RECV]:
        ex(h, f"sysctl -qw net.ipv4.tcp_ecn={ecn} net.ipv4.tcp_congestion_control={cc}")
        got = ex(h, "sysctl -n net.ipv4.tcp_congestion_control").strip()
        assert got == cc, f"{h}: congestion control is {got}, wanted {cc}"


def qstats() -> dict[str, int]:
    return parsers.tc_child_qdisc_stats(ex(LEAF, f"tc -s qdisc show dev {PORT}"))


def ping_rtts(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"time=([\d.]+) ms", text)]


def pct(v: list[float], p: float) -> float:
    s = sorted(v)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))] if s else float("nan")


def one_run(scen: str) -> dict:
    _, qdisc, cc, ecn = SCEN[scen]
    setup(qdisc, cc, ecn)
    idle = ping_rtts(ex("h1", f"ping -c 20 -i 0.05 {H[RECV].ip}"))
    servers = " ; ".join(f"iperf3 -s -D -p {5201 + i}" for i in range(len(SENDERS)))
    ex(RECV, f"sh -c 'pkill iperf3; sleep 0.3; {servers}'")
    time.sleep(0.5)
    procs = {s: subprocess.Popen(shlex.split(PREFIX) + shlex.split(
        f"docker exec clab-{LAB}-{s} iperf3 -c {H[RECV].ip} -p {5201 + i} -t {RUN_S} -P 2 -J"),
        stdout=subprocess.PIPE, text=True) for i, s in enumerate(SENDERS)}
    time.sleep(3)
    loaded = ping_rtts(ex("h1", f"ping -Q 2 -c {(RUN_S - 6) * 20} -i 0.05 {H[RECV].ip}", timeout=RUN_S + 30))
    res = {s: json.loads(p.communicate(timeout=RUN_S + 60)[0]) for s, p in procs.items()}
    q = qstats()
    thr = {s: r["end"]["sum_received"]["bits_per_second"] / 1e6 for s, r in res.items()}
    tot = sum(thr.values())
    jain = tot ** 2 / (len(thr) * sum(x * x for x in thr.values()))
    tcp_rtt = [st["sender"]["mean_rtt"] / 1000 for r in res.values() for st in r["end"]["streams"]
               if "mean_rtt" in st.get("sender", {})]
    return {"scenario": scen, "throughput_mbps": {s: round(v, 2) for s, v in thr.items()},
            "total_mbps": round(tot, 2), "jain": round(jain, 3),
            "retransmits": sum(r["end"]["sum_sent"].get("retransmits", 0) for r in res.values()),
            "queue": q, "rtt_idle_ms_median": round(statistics.median(idle), 3),
            "rtt_loaded_ms": {"n": len(loaded), "median": round(statistics.median(loaded), 2),
                              "p95": round(pct(loaded, 95), 2), "p99": round(pct(loaded, 99), 2),
                              "max": round(max(loaded), 2)} if loaded else {"n": 0},
            "ping_loss_pct": round(100 * (1 - len(loaded) / ((RUN_S - 6) * 20)), 1),
            "tcp_mean_rtt_ms": round(statistics.mean(tcp_rtt), 2) if tcp_rtt else None}


def main() -> None:
    scens = (sys.argv[1] if len(sys.argv) > 1 else "A,B,C").split(",")
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    OUT.mkdir(parents=True, exist_ok=True)
    avail = ex(RECV, "sysctl -n net.ipv4.tcp_available_congestion_control").split()
    meta = {"rate": RATE, "pfifo_limit_pkts": LIMIT_PKTS, "red": RED, "run_s": RUN_S, "senders": SENDERS,
            "receiver": RECV, "bottleneck": f"{LEAF}:{PORT}", "available_cc": avail,
            "kernel": node_exec(LAB, RECV, "uname -r").stdout.strip()}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1))
    for s in scens:
        if SCEN[s][2] not in avail:
            print(f"{s}: SKIPPED - {SCEN[s][2]} not available in this kernel ({avail})")
            (OUT / f"{s}.json").write_text(json.dumps({"skipped": f"{SCEN[s][2]} not available", "available": avail}))
            continue
        rows = []
        for i in range(runs):
            r = one_run(s)
            rows.append(r)
            print(f"{s} run {i + 1}: total {r['total_mbps']} Mbit/s, jain {r['jain']}, drops {r['queue']['dropped']}, "
                  f"marks {r['queue'].get('marked', '-')}, rtt med/p99 {r['rtt_loaded_ms'].get('median')}/"
                  f"{r['rtt_loaded_ms'].get('p99')} ms (idle {r['rtt_idle_ms_median']}), ping loss {r['ping_loss_pct']}%, "
                  f"tcp rtt {r['tcp_mean_rtt_ms']} ms, retrans {r['retransmits']}")
        (OUT / f"{s}.json").write_text(json.dumps({"name": SCEN[s][0], "runs": rows}, indent=1))
    ex(LEAF, f"tc qdisc del dev {PORT} root")
    for h in SENDERS + [RECV]:
        ex(h, "sysctl -qw net.ipv4.tcp_ecn=2 net.ipv4.tcp_congestion_control=cubic")


if __name__ == "__main__":
    main()
