"""Static auditor for lossless-Ethernet (PFC / ECN / DSCP) configuration in a SONiC CONFIG_DB dump.

Pure function: dict in, findings out. It checks that the pieces of a lossless class agree with each
other (the same priority is lossless in every table), not that the network performs. veth has no PFC,
so behaviour can't be shown in this lab; consistency of the configuration can be audited.

Input shape = config_db.json: {TABLE: {key: {field: value}}}. References may be plain names ("AZURE")
or the older "[TABLE|NAME]" form; both are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Db = dict[str, dict[str, dict[str, Any]]]
ECN_ON = {"ecn_green", "ecn_yellow", "ecn_red", "ecn_green_yellow", "ecn_green_red",
          "ecn_yellow_red", "ecn_all"}


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str   # error | warn
    where: str
    message: str


def _ref(v: Any) -> str:
    s = str(v or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].split("|", 1)[-1]
    return s


def _ints(v: Any) -> list[int]:
    out: list[int] = []
    for part in str(v or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _table(db: Db, name: str) -> dict[str, dict[str, Any]]:
    return db.get(name, {})


def _map(db: Db, table: str, name: str) -> dict[int, int] | None:
    """Return a {int: int} map such as DSCP_TO_TC_MAP|AZURE, or None if the table entry is missing."""
    entry = _table(db, table).get(name)
    if entry is None:
        return None
    return {int(k): int(v) for k, v in entry.items()}


def audit(db: Db) -> list[Finding]:
    f: list[Finding] = []
    pfc_sets: dict[str, tuple[int, ...]] = {}
    for key, qos in sorted(_table(db, "PORT_QOS_MAP").items()):
        if "pfc_enable" not in qos:
            continue
        ports = [p for p in key.split(",") if p]
        prios = sorted(set(_ints(qos["pfc_enable"])))
        for port in ports:
            pfc_sets[port] = tuple(prios)
        dscp = _map(db, "DSCP_TO_TC_MAP", _ref(qos.get("dscp_to_tc_map")))
        tc_q = _map(db, "TC_TO_QUEUE_MAP", _ref(qos.get("tc_to_queue_map")))
        tc_pg = _map(db, "TC_TO_PRIORITY_GROUP_MAP", _ref(qos.get("tc_to_pg_map")))
        pfc_q = _map(db, "MAP_PFC_PRIORITY_TO_QUEUE", _ref(qos.get("pfc_to_queue_map")))
        for label, m in (("dscp_to_tc_map", dscp), ("tc_to_queue_map", tc_q),
                         ("tc_to_pg_map", tc_pg), ("pfc_to_queue_map", pfc_q)):
            if m is None:
                f.append(Finding("QOS-001", "error", key,
                                 f"PFC is enabled but {label} '{_ref(qos.get(label))}' does not exist"))
        if dscp is None or tc_q is None or tc_pg is None or pfc_q is None:
            continue
        missing = sorted(set(range(64)) - set(dscp))
        if missing:
            f.append(Finding("QOS-002", "error", key,
                             f"DSCP_TO_TC_MAP does not cover DSCP values {missing[:6]}"
                             f"{'...' if len(missing) > 6 else ''}; unmapped traffic gets an undefined class"))
        lossless_tcs: set[int] = set()
        for p in prios:
            q = pfc_q.get(p)
            tcs = [t for t, pg in tc_pg.items() if pg == p and tc_q.get(t) == q]
            if q is None or not tcs:
                f.append(Finding("QOS-003", "error", key,
                                 f"priority {p} is PFC-enabled but no traffic class maps to priority group {p} "
                                 f"and queue {q}: the lossless class is inconsistent across the tables"))
                continue
            lossless_tcs.update(tcs)
            if not any(t in tcs for t in dscp.values()):
                f.append(Finding("QOS-004", "warn", key,
                                 f"priority {p}: no DSCP value maps to its traffic class, so no packet can use it"))
        lossless_q = {tc_q[t] for t in lossless_tcs if t in tc_q}
        lossless_pg = {tc_pg[t] for t in lossless_tcs if t in tc_pg}
        for t in sorted(set(tc_q) - lossless_tcs):
            if tc_q[t] in lossless_q or tc_pg.get(t) in lossless_pg:
                f.append(Finding("QOS-005", "error", key,
                                 f"lossy traffic class {t} shares a queue or priority group with a lossless class"))
        for port in ports:
            f.extend(_port_checks(db, port, prios, pfc_q))
    if len({v for v in pfc_sets.values()}) > 1:
        f.append(Finding("QOS-009", "error", "PORT_QOS_MAP",
                         "ports disagree on which priorities are lossless: "
                         + "; ".join(f"{p}={list(v)}" for p, v in sorted(pfc_sets.items()))))
    return f


def _port_checks(db: Db, port: str, prios: list[int], pfc_q: dict[int, int]) -> list[Finding]:
    f: list[Finding] = []
    for p in prios:
        pg_entry = next((v for k, v in _table(db, "BUFFER_PG").items()
                         if k.split("|")[0] == port and p in _ints(k.split("|")[-1])), None)
        if pg_entry is None:
            f.append(Finding("QOS-006", "warn", port,
                             f"no BUFFER_PG entry for lossless priority {p} in CONFIG_DB "
                             "(with the dynamic buffer model it is created at runtime in APPL_DB)"))
        else:
            prof = _table(db, "BUFFER_PROFILE").get(_ref(pg_entry.get("profile")), {})
            if "xoff" not in prof:
                f.append(Finding("QOS-006", "error", port,
                                 f"BUFFER_PG for priority {p} uses profile '{_ref(pg_entry.get('profile'))}' "
                                 "which has no xoff threshold, so it cannot be lossless"))
        q = pfc_q.get(p)
        qentry = next((v for k, v in _table(db, "QUEUE").items()
                       if k.split("|")[0] == port and q is not None and q in _ints(k.split("|")[-1])), None)
        wred = _table(db, "WRED_PROFILE").get(_ref((qentry or {}).get("wred_profile")))
        if wred is None:
            f.append(Finding("QOS-007", "error", port,
                             f"lossless queue {q} has no WRED/ECN profile: congestion is signalled only by PFC pause"))
        elif wred.get("ecn") not in ECN_ON:
            f.append(Finding("QOS-007", "error", port,
                             f"WRED profile on lossless queue {q} has ecn={wred.get('ecn')}: no ECN marking"))
        elif int(wred.get("green_min_threshold", 0)) >= int(wred.get("green_max_threshold", 1)):
            f.append(Finding("QOS-007", "error", port,
                             f"WRED min threshold is not below max threshold on lossless queue {q}"))
    wd = _table(db, "PFC_WD").get(port) or _table(db, "PFC_WD").get("GLOBAL")
    if not wd or "action" not in wd:
        f.append(Finding("QOS-008", "warn", port,
                         "PFC watchdog is not configured: a stuck receiver can pause the link indefinitely"))
    return f


def render(findings: list[Finding]) -> str:
    if not findings:
        return "QoS audit: no findings"
    lines = [f"{x.severity.upper():5} {x.check} {x.where}: {x.message}" for x in findings]
    return "\n".join(lines) + f"\n{len(findings)} findings"
