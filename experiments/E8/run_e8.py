"""E8 - How does a route get from BGP to the 'ASIC' inside SONiC?  (runs on an x86 CI runner)

Needs the sonic-leaf3 variant deployed. Writes everything to experiments/E8/results/.
  1. trace leaf1's loopback on the SONiC leaf (learned from both spines = ECMP)
  2. trace one interface (Ethernet0) through CONFIG/APPL/STATE/ASIC/COUNTERS DB
  3. timing: leaf1 announces trace_prefix N times; time until it shows in APPL_DB and in ASIC_DB
  4. fault: freeze orchagent (SIGSTOP, inside the lab container), announce, trace -> chain stops at APPL_DB;
     unfreeze (SIGCONT) and time until ASIC_DB catches up
  5. dump the real CONFIG_DB and run the QoS/lossless auditor on it
Timings are polled through `docker exec`, so their resolution is the poll period (printed in the results).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from fabricx import model
from fabricx.adapters import sonic
from fabricx.audit import qos_lossless
from fabricx.runner import node_exec

INV = sys.argv[1] if len(sys.argv) > 1 else "inventory/variants/sonic-leaf3.yaml"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
OUT = Path("experiments/E8/results")
OUT.mkdir(parents=True, exist_ok=True)
F = model.load(INV)
LAB, SW = F.name, next(s.name for s in F.leaves if s.nos == "sonic-vs")
SRC = F.leaves[0]                      # an FRR leaf that announces the test prefix
assert F.sonic is not None and F.sonic.trace_prefix is not None
P = str(F.sonic.trace_prefix)


def vty(node: str, *lines: str) -> None:
    args = " ".join(f"-c '{x}'" for x in ("configure terminal",) + lines)
    r = node_exec(LAB, node, f"vtysh {args}", timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


def announce() -> None:
    vty(SRC.name, f"ip route {P} blackhole", f"router bgp {SRC.asn}", "address-family ipv4 unicast", f"network {P}")


def withdraw() -> None:
    vty(SRC.name, f"router bgp {SRC.asn}", "address-family ipv4 unicast", f"no network {P}", "exit", "exit",
        f"no ip route {P} blackhole")


def in_appl() -> bool:
    return bool(sonic.db_keys(LAB, SW, "APPL_DB", sonic.appl_route_key(LAB, SW, P)))


def in_asic() -> bool:
    return bool(sonic.asic_route_key(LAB, SW, P))


def wait(cond, timeout: float = 60) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return time.monotonic() - t0
    return None


def write(name: str, text: str) -> None:
    (OUT / name).write_text(text)
    print(f"wrote {OUT / name}")


def main() -> None:
    meta = {"sonic_version": node_exec(LAB, SW, "cat /etc/sonic/sonic_version.yml").stdout,
            "frr_version": node_exec(LAB, SW, "vtysh -c 'show version'").stdout.splitlines()[0],
            "bgp_summary": node_exec(LAB, SW, "vtysh -c 'show bgp summary'").stdout,
            "bfd_peers": node_exec(LAB, SW, "vtysh -c 'show bfd peers brief'").stdout}
    write("versions_and_sessions.json", json.dumps(meta, indent=1))

    loop = f"{SRC.loopback}/32"
    write("trace_route_loopback.md", sonic.render_trace(loop, sonic.trace_route(LAB, SW, loop)))
    write("trace_interface_Ethernet0.md",
          sonic.render_trace("Ethernet0", sonic.trace_interface(LAB, SW, "Ethernet0"), title="Interface trace"))

    # poll period = how long one check takes (each check is a docker exec)
    t0 = time.monotonic()
    for _ in range(5):
        in_asic()
    poll = (time.monotonic() - t0) / 5

    rows = []
    for i in range(N):
        t_start = time.monotonic()
        announce()
        a = wait(in_appl)
        b = wait(in_asic)
        rows.append({"run": i + 1, "appl_s": None if a is None else round(a, 3),
                     "asic_after_announce_s": None if b is None else round((a or 0) + b, 3)})
        withdraw()
        wait(lambda: not in_asic() and not in_appl())
        print(rows[-1], f"(loop {time.monotonic() - t_start:.1f}s)")
    ok = [r for r in rows if r["appl_s"] is not None and r["asic_after_announce_s"] is not None]
    summary = {"n": N, "complete": len(ok), "poll_period_s": round(poll, 3),
               "median_appl_s": statistics.median(r["appl_s"] for r in ok) if ok else None,
               "median_asic_s": statistics.median(r["asic_after_announce_s"] for r in ok) if ok else None,
               "runs": rows}
    write("timing.json", json.dumps(summary, indent=1))

    # fault: orchagent frozen
    node_exec(LAB, SW, "pkill -STOP -x orchagent")
    try:
        announce()
        a = wait(in_appl)
        time.sleep(10)
        frozen = sonic.trace_route(LAB, SW, P)
        write("trace_orchagent_frozen.md",
              sonic.render_trace(P, frozen, title=f"Route trace with orchagent frozen (APPL_DB after {a}s, waited 10 s more)"))
    finally:
        node_exec(LAB, SW, "pkill -CONT -x orchagent")
    b = wait(in_asic)
    resumed = sonic.trace_route(LAB, SW, P)
    write("trace_orchagent_resumed.md",
          sonic.render_trace(P, resumed, title=f"Route trace after orchagent resumed (ASIC_DB after {b}s)"))
    withdraw()
    wait(lambda: not in_asic() and not in_appl())

    cdb = sonic.dump_config_db(LAB, SW)
    write("config_db.json", json.dumps(cdb, indent=1, sort_keys=True))
    write("qos_audit.txt", qos_lossless.render(qos_lossless.audit(cdb)) + "\n")


if __name__ == "__main__":
    main()
