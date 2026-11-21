"""SONiC adapter: read the Redis databases of a docker-sonic-vs node and trace one route through them.

STATUS: written against the documented sonic-db-cli / sonic-cfggen behaviour and unit-tested with a fake
node. It has NOT yet been run against a real SONiC image (needs x86). Anything marked in
docs/phases/phase-7 as 'verified on image' has been; the rest is still an assumption.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..runner import node_exec

DBS = {"APPL_DB": 0, "ASIC_DB": 1, "COUNTERS_DB": 2, "CONFIG_DB": 4, "STATE_DB": 6}


@dataclass
class Hop:
    stage: str              # which program wrote this
    db: str
    key: str
    fields: dict[str, str] = field(default_factory=dict)


def parse_keys(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def parse_hgetall(text: str) -> dict[str, str]:
    """sonic-db-cli prints a Python dict repr; an empty/missing key prints {}."""
    text = text.strip()
    if not text:
        return {}
    val = ast.literal_eval(text)
    return {str(k): str(v) for k, v in val.items()} if isinstance(val, dict) else {}


def db_keys(lab: str, node: str, db: str, pattern: str) -> list[str]:
    r = node_exec(lab, node, f"sonic-db-cli {db} keys '{pattern}'", timeout=30, retries=1)
    return parse_keys(r.stdout)


def db_hgetall(lab: str, node: str, db: str, key: str) -> dict[str, str]:
    r = node_exec(lab, node, f"sonic-db-cli {db} HGETALL '{key}'", timeout=30, retries=1)
    return parse_hgetall(r.stdout)


def dump_config_db(lab: str, node: str) -> dict[str, Any]:
    """Whole CONFIG_DB as config_db.json-shaped data (input for the QoS auditor)."""
    r = node_exec(lab, node, "sonic-cfggen -d --print-data", timeout=60, retries=1)
    data: dict[str, Any] = json.loads(r.stdout)
    return data


def _json(text: str) -> Any:
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}


def vtysh_json(lab: str, node: str, cmd: str) -> Any:
    return _json(node_exec(lab, node, f"vtysh -c '{cmd} json'", timeout=30, retries=1).stdout)


def _bgp_fields(d: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for n, p in enumerate(d.get("paths", []), 1):
        best = "best" if p.get("bestpath", {}).get("overall") else ("multipath" if p.get("multipath") else "")
        nhs = ",".join(x.get("ip", "") for x in p.get("nexthops", []))
        out[f"path{n}"] = f"as-path [{p.get('aspath', {}).get('string', '')}] via {nhs} {best}".strip()
    return out


def _zebra_fields(d: dict[str, Any], prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in d.get(prefix, []):
        out["protocol"] = str(r.get("protocol", ""))
        for k in ("selected", "installed", "offloaded", "failed", "queued"):
            if k in r:
                out[k] = str(r[k])
        for n, nh in enumerate(r.get("nexthops", []), 1):
            out[f"nexthop{n}"] = f"{nh.get('ip', '')} dev {nh.get('interfaceName', '')} fib={nh.get('fib', False)}"
    return out


def staged_route_keys(lab: str, node: str) -> list[str]:
    """Route keys fpmsyncd has produced that orchagent has not consumed yet."""
    r = node_exec(lab, node, "sonic-db-cli APPL_DB SMEMBERS ROUTE_TABLE_KEY_SET", timeout=30)
    return parse_keys(r.stdout)


def appl_route_key(lab: str, node: str, prefix: str) -> str:
    """fpmsyncd stores host routes without '/32' on some branches; try both spellings."""
    for key in (f"ROUTE_TABLE:{prefix}", f"ROUTE_TABLE:{prefix.removesuffix('/32')}"):
        if db_keys(lab, node, "APPL_DB", key):
            return key
    return f"ROUTE_TABLE:{prefix}"


def asic_route_key(lab: str, node: str, prefix: str) -> str:
    esc = re.escape(prefix)
    return next((k for k in db_keys(lab, node, "ASIC_DB", "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:*")
                 if re.search(rf'"dest":"{esc}"', k)), "")


def trace_route(lab: str, node: str, prefix: str) -> list[Hop]:
    """Follow one prefix through a SONiC node, in the order the software hands it on:
    bgpd (best path) -> zebra (RIB; FPM to fpmsyncd) -> APPL_DB ROUTE_TABLE (fpmsyncd) -> ASIC_DB route
    entry and next hop / next-hop group (orchagent) -> syncd. A hop that is not found keeps empty fields,
    so the gap shows exactly where the chain stops."""
    hops = [Hop("bgpd (best path)", "FRR bgpd", f"show bgp ipv4 unicast {prefix}",
                _bgp_fields(vtysh_json(lab, node, f"show bgp ipv4 unicast {prefix}"))),
            Hop("zebra (RIB -> FPM)", "FRR zebra", f"show ip route {prefix}",
                _zebra_fields(vtysh_json(lab, node, f"show ip route {prefix}"), prefix))]
    akey = appl_route_key(lab, node, prefix)
    appl = db_hgetall(lab, node, "APPL_DB", akey)
    if not appl:   # ProducerStateTable: fpmsyncd writes '_ROUTE_TABLE:<key>'; orchagent moves it into ROUTE_TABLE
        for skey in (f"_{akey}", f"_ROUTE_TABLE:{prefix.removesuffix('/32')}"):
            staged = db_hgetall(lab, node, "APPL_DB", skey)
            if staged:
                hops.append(Hop("fpmsyncd (written, NOT yet consumed by orchagent)", "APPL_DB", skey, staged))
                break
    hops.append(Hop("fpmsyncd -> orchagent consumed", "APPL_DB", akey, appl))
    route_key = asic_route_key(lab, node, prefix)
    route = db_hgetall(lab, node, "ASIC_DB", route_key) if route_key else {}
    hops.append(Hop("orchagent (routeorch)", "ASIC_DB", route_key or f"(no route entry for {prefix})", route))
    oid = route.get("SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID", "")
    if oid and oid != "oid:0x0":
        nh = db_hgetall(lab, node, "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:{oid}")
        if nh:
            hops.append(Hop("orchagent (neighorch)", "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:{oid}", nh))
        else:
            gkey = f"ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP:{oid}"
            hops.append(Hop("orchagent (routeorch ECMP group)", "ASIC_DB", gkey,
                            db_hgetall(lab, node, "ASIC_DB", gkey)))
            for mkey in db_keys(lab, node, "ASIC_DB", "ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER:*"):
                m = db_hgetall(lab, node, "ASIC_DB", mkey)
                if m.get("SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID") != oid:
                    continue
                hops.append(Hop("orchagent (ECMP member)", "ASIC_DB", mkey, m))
                nkey = f"ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:{m.get('SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_ID', '')}"
                hops.append(Hop("orchagent (neighorch)", "ASIC_DB", nkey, db_hgetall(lab, node, "ASIC_DB", nkey)))
    return hops


def trace_interface(lab: str, node: str, port: str) -> list[Hop]:
    """One port through the databases: CONFIG_DB (intent) -> APPL_DB (portmgrd/portsyncd) -> STATE_DB
    (state) -> ASIC_DB port object (orchagent) -> COUNTERS_DB (syncd/flex counters)."""
    oid = node_exec(lab, node, f"sonic-db-cli COUNTERS_DB HGET COUNTERS_PORT_NAME_MAP {port}",
                    timeout=30).stdout.strip()
    counters = db_hgetall(lab, node, "COUNTERS_DB", f"COUNTERS:{oid}") if oid else {}
    keep = {k: v for k, v in counters.items() if k in (
        "SAI_PORT_STAT_IF_IN_UCAST_PKTS", "SAI_PORT_STAT_IF_OUT_UCAST_PKTS",
        "SAI_PORT_STAT_IF_IN_OCTETS", "SAI_PORT_STAT_IF_OUT_OCTETS", "SAI_PORT_STAT_IF_IN_DISCARDS")}
    def get(db: str, key: str) -> dict[str, str]:
        return db_hgetall(lab, node, db, key)
    return [Hop("config (intent)", "CONFIG_DB", f"PORT|{port}", get("CONFIG_DB", f"PORT|{port}")),
            Hop("portmgrd / portsyncd", "APPL_DB", f"PORT_TABLE:{port}", get("APPL_DB", f"PORT_TABLE:{port}")),
            Hop("portsyncd (kernel state)", "STATE_DB", f"PORT_TABLE|{port}", get("STATE_DB", f"PORT_TABLE|{port}")),
            Hop("orchagent (portsorch)", "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_PORT:{oid}",
                db_hgetall(lab, node, "ASIC_DB", f"ASIC_STATE:SAI_OBJECT_TYPE_PORT:{oid}") if oid else {}),
            Hop("syncd (flex counters)", "COUNTERS_DB", f"COUNTERS:{oid}", keep)]


def render_trace(prefix: str, hops: list[Hop], title: str = "Route trace") -> str:
    lines = [f"# {title} for {prefix}", ""]
    for i, h in enumerate(hops, 1):
        lines += [f"## {i}. {h.stage} -> {h.db}", f"`{h.key}`", ""]
        lines += [f"- {k} = {v}" for k, v in sorted(h.fields.items())] or ["- (nothing found here)"]
        lines.append("")
    return "\n".join(lines)
