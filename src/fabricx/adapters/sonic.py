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


def trace_route(lab: str, node: str, prefix: str) -> list[Hop]:
    """Follow one prefix: APPL_DB ROUTE_TABLE (written by fpmsyncd) -> ASIC_DB route entry and its
    next hop (written by orchagent). Hops that are not found are returned with empty fields so the
    gap shows exactly where the chain stops."""
    hops: list[Hop] = []
    akey = f"ROUTE_TABLE:{prefix}"
    hops.append(Hop("fpmsyncd", "APPL_DB", akey, db_hgetall(lab, node, "APPL_DB", akey)))
    esc = re.escape(prefix)
    route_key = next((k for k in db_keys(lab, node, "ASIC_DB", "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:*")
                      if re.search(rf'"dest":"{esc}"', k)), "")
    route = db_hgetall(lab, node, "ASIC_DB", route_key) if route_key else {}
    hops.append(Hop("orchagent (routeorch)", "ASIC_DB", route_key or f"(no route entry for {prefix})", route))
    oid = route.get("SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID", "")
    if oid and oid != "oid:0x0":
        for typ in ("NEXT_HOP_GROUP", "NEXT_HOP"):
            key = f"ASIC_STATE:SAI_OBJECT_TYPE_{typ}:{oid}"
            fields = db_hgetall(lab, node, "ASIC_DB", key)
            if fields:
                hops.append(Hop("orchagent (nhg/neighorch)", "ASIC_DB", key, fields))
                break
    return hops


def render_trace(prefix: str, hops: list[Hop]) -> str:
    lines = [f"# Route trace for {prefix}", ""]
    for i, h in enumerate(hops, 1):
        lines += [f"## {i}. {h.stage} -> {h.db}", f"`{h.key}`", ""]
        lines += [f"- {k} = {v}" for k, v in sorted(h.fields.items())] or ["- (nothing found here)"]
        lines.append("")
    return "\n".join(lines)
