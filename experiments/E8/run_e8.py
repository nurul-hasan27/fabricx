"""E8 - How does a route get from BGP to the 'ASIC' inside SONiC?  (runs on an x86 CI runner)

Needs the sonic-leaf3 variant deployed. Writes everything to experiments/E8/results/.
  1. trace leaf1's loopback on the SONiC leaf (learned from both spines = ECMP)
  2. trace one interface (Ethernet0) through CONFIG/APPL/STATE/ASIC/COUNTERS DB
  3. timing: leaf1 announces trace_prefix N times; time until it is in APPL_DB ROUTE_TABLE (= consumed by
     orchagent; fpmsyncd first writes a staging key '_ROUTE_TABLE:...') and in ASIC_DB
  4. fault: freeze orchagent (SIGSTOP, inside the lab container), announce, trace -> the route stays in the
     staging key; unfreeze (SIGCONT) and time until ROUTE_TABLE and ASIC_DB catch up
  5. QoS auditor against the real CONFIG_DB in three stages: image default / PFC enabled only (a half-done
     change) / complete lossless config; plus the ASIC_DB objects orchagent programmed for each stage
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


def staged() -> bool:
    keys = sonic.staged_route_keys(LAB, SW)
    return any(k in keys for k in (P, P.removesuffix("/32")))


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


def hset(key: str, fields: dict[str, str]) -> None:
    args = " ".join(f"{k} {v}" for k, v in fields.items())
    # redis-cli, not sonic-db-cli: sonic-db-cli parses a value like '-3' as a command-line option.
    r = node_exec(LAB, SW, f"redis-cli -n 4 HSET '{key}' {args}", timeout=30)   # CONFIG_DB = Redis DB 4
    assert r.returncode == 0, r.stdout + r.stderr


def asic_qos_evidence(port: str) -> dict[str, dict[str, str]]:
    """What orchagent programmed: the port's PFC bitmask, and queue 3 / priority group 3 objects."""
    def oid(table: str, name: str) -> str:
        return node_exec(LAB, SW, f"sonic-db-cli COUNTERS_DB HGET {table} {name}", timeout=30).stdout.strip()
    port_oid = oid("COUNTERS_PORT_NAME_MAP", port)
    port_attrs = sonic.db_hgetall(LAB, SW, "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_PORT:{port_oid}")
    q = oid("COUNTERS_QUEUE_NAME_MAP", f"{port}:3")
    pg = oid("COUNTERS_PG_NAME_MAP", f"{port}:3")
    return {"port": {k: v for k, v in port_attrs.items() if "PRIORITY_FLOW_CONTROL" in k or "QOS" in k},
            "queue3": sonic.db_hgetall(LAB, SW, "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_QUEUE:{q}") if q else {},
            "pg3": sonic.db_hgetall(LAB, SW, "ASIC_DB",
                                    f"ASIC_STATE:SAI_OBJECT_TYPE_INGRESS_PRIORITY_GROUP:{pg}") if pg else {}}


def qos_stages() -> None:
    """Auditor vs the real switch. Buffer sizes below are configuration values chosen for the test,
    not measurements."""
    ports = [model.sonic_port(i) for i, _ in F.iface_ips(SW)]
    pfc = {"dscp_to_tc_map": "AZURE", "tc_to_queue_map": "AZURE", "tc_to_pg_map": "AZURE",
           "pfc_to_queue_map": "AZURE", "pfc_enable": "3,4"}
    stages: list[tuple[str, list[tuple[str, dict[str, str]]]]] = [
        ("1_default", []),
        ("2_pfc_only", [(f"PORT_QOS_MAP|{p}", pfc) for p in ports]),
        ("3_complete", [("BUFFER_PROFILE|ingress_lossless_profile",
                         {"pool": "ingress_lossless_pool", "size": "56352", "dynamic_th": "-3",
                          "xon": "18432", "xoff": "38816"}), ("PFC_WD|GLOBAL", {"POLL_INTERVAL": "200"})]
         + [(f"BUFFER_PG|{p}|3-4", {"profile": "ingress_lossless_profile"}) for p in ports]
         + [(f"QUEUE|{p}|3-4", {"wred_profile": "AZURE_LOSSLESS"}) for p in ports]
         + [(f"PFC_WD|{p}", {"action": "drop", "detection_time": "200", "restoration_time": "200"})
            for p in ports]),
    ]
    mark = node_exec(LAB, SW, "sh -c 'wc -l < /var/log/syslog'").stdout.strip() or "0"
    for name, writes in stages:
        for key, fields in writes:
            hset(key, fields)
        time.sleep(5 if writes else 0)
        cdb = sonic.dump_config_db(LAB, SW)
        write(f"qos_{name}_config_db.json", json.dumps(cdb, indent=1, sort_keys=True))
        write(f"qos_{name}_audit.txt", qos_lossless.render(qos_lossless.audit(cdb)) + "\n")
        errs = node_exec(LAB, SW, f"sh -c \"tail -n +{int(mark) + 1} /var/log/syslog | grep -E 'ERR|WARN' "
                                  f"| grep -E 'orchagent|syncd|buffermgrd' | tail -20\"").stdout
        mark = node_exec(LAB, SW, "sh -c 'wc -l < /var/log/syslog'").stdout.strip() or mark
        write(f"qos_{name}_asic.json", json.dumps({"asic": asic_qos_evidence(ports[0]),
                                                   "orchagent_syncd_errors_or_warnings": errs.splitlines()},
                                                  indent=1))


def main() -> None:
    meta = {"sonic_version": node_exec(LAB, SW, "cat /etc/sonic/sonic_version.yml").stdout,
            "frr_version": node_exec(LAB, SW, "vtysh -c 'show version'").stdout.splitlines()[0],
            "bgp_summary": node_exec(LAB, SW, "vtysh -c 'show bgp summary'").stdout,
            "bfd_peers": node_exec(LAB, SW, "vtysh -c 'show bfd peers brief'").stdout}
    write("versions_and_sessions.json", json.dumps(meta, indent=1))

    # port counters are off by default in SONiC-VS; switch them on so COUNTERS_DB has something to show
    for grp in ("PORT", "QUEUE", "PG_WATERMARK"):   # QUEUE / PG also create the queue and PG name maps
        node_exec(LAB, SW, f"sonic-db-cli CONFIG_DB HSET 'FLEX_COUNTER_TABLE|{grp}' FLEX_COUNTER_STATUS enable")
    time.sleep(5)
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
        rows.append({"run": i + 1, "route_table_s": None if a is None else round(a, 3),
                     "asic_s": None if b is None else round((a or 0) + b, 3)})
        withdraw()
        wait(lambda: not in_asic() and not in_appl())
        print(rows[-1], f"(loop {time.monotonic() - t_start:.1f}s)")
    ok = [r for r in rows if r["route_table_s"] is not None and r["asic_s"] is not None]
    summary = {"n": N, "complete": len(ok), "poll_period_s": round(poll, 3),
               "meaning": "seconds after leaf1's announce command until the prefix is in APPL_DB ROUTE_TABLE "
                          "(consumed by orchagent) / in ASIC_DB; resolution = poll period",
               "median_route_table_s": statistics.median(r["route_table_s"] for r in ok) if ok else None,
               "median_asic_s": statistics.median(r["asic_s"] for r in ok) if ok else None,
               "runs": rows}
    write("timing.json", json.dumps(summary, indent=1))

    # fault: orchagent frozen
    node_exec(LAB, SW, "pkill -STOP -x orchagent")
    try:
        announce()
        a = wait(staged)
        time.sleep(10)
        frozen = sonic.trace_route(LAB, SW, P)
        keyset = sonic.staged_route_keys(LAB, SW)
        still_staged = staged()
        write("trace_orchagent_frozen.md", sonic.render_trace(
            P, frozen, title=f"Route trace with orchagent frozen (staged after {a and round(a, 3)} s, "
                             f"checked again 10 s later: still staged={still_staged}, "
                             f"ROUTE_TABLE_KEY_SET={keyset})"))
    finally:
        node_exec(LAB, SW, "pkill -CONT -x orchagent")
    t0 = time.monotonic()
    rt = wait(in_appl)
    b = wait(in_asic)
    total = time.monotonic() - t0 if b is not None else None
    resumed = sonic.trace_route(LAB, SW, P)
    write("trace_orchagent_resumed.md", sonic.render_trace(
        P, resumed, title=f"Route trace after orchagent resumed (ROUTE_TABLE after {rt and round(rt, 3)} s, "
                          f"ASIC_DB after {total and round(total, 3)} s; poll period {round(poll, 3)} s)"))
    withdraw()
    wait(lambda: not in_asic() and not in_appl())

    qos_stages()



if __name__ == "__main__":
    main()
