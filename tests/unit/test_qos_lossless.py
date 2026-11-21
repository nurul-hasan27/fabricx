"""QoS auditor tests. The fixture is a HAND-WRITTEN synthetic CONFIG_DB (table and field names follow the
SONiC schema); it is not a dump from a real switch. Phase 7's x86 run re-checks it against a real dump."""
import copy
import json
from pathlib import Path

import pytest

from fabricx.audit import qos_lossless as q

GOOD = json.loads(Path("tests/fixtures/sonic_config_db_lossless_good.json").read_text())


def checks(db):
    return {x.check for x in q.audit(db)}


def mutated(fn):
    db = copy.deepcopy(GOOD)
    fn(db)
    return db


def test_good_config_has_no_findings():
    assert q.audit(GOOD) == []


def test_old_bracket_reference_style_is_accepted():
    db = mutated(lambda d: d["PORT_QOS_MAP"]["Ethernet0,Ethernet4"].update(dscp_to_tc_map="[DSCP_TO_TC_MAP|AZURE]"))
    assert q.audit(db) == []


@pytest.mark.parametrize("name,fn,expected", [
    ("missing map", lambda d: d["TC_TO_QUEUE_MAP"].clear(), "QOS-001"),
    ("dscp gap", lambda d: d["DSCP_TO_TC_MAP"]["AZURE"].pop("40"), "QOS-002"),
    ("pg mismatch", lambda d: d["TC_TO_PRIORITY_GROUP_MAP"]["AZURE"].update({"3": "5"}), "QOS-003"),
    ("lossy shares queue", lambda d: (d["TC_TO_QUEUE_MAP"]["AZURE"].update({"1": "3"})), "QOS-005"),
    ("lossy profile", lambda d: d["BUFFER_PROFILE"]["pg_lossless"].pop("xoff"), "QOS-006"),
    ("no ecn", lambda d: d["WRED_PROFILE"]["AZURE_LOSSLESS"].update(ecn="ecn_none"), "QOS-007"),
    ("bad thresholds", lambda d: d["WRED_PROFILE"]["AZURE_LOSSLESS"].update(green_min_threshold="3000000"), "QOS-007"),
    ("no watchdog", lambda d: d["PFC_WD"].pop("Ethernet0"), "QOS-008"),
])
def test_each_inconsistency_is_found(name, fn, expected):
    assert expected in checks(mutated(fn)), name


def test_ports_disagreeing_on_lossless_priorities():
    def split(d):
        e = d["PORT_QOS_MAP"].pop("Ethernet0,Ethernet4")
        d["PORT_QOS_MAP"]["Ethernet0"] = dict(e)
        d["PORT_QOS_MAP"]["Ethernet4"] = dict(e, pfc_enable="3")
    assert "QOS-009" in checks(mutated(split))


def test_render_mentions_count():
    assert "findings" in q.render(q.audit(mutated(lambda d: d["PFC_WD"].clear())))
    assert q.render([]).startswith("QoS audit: no findings")


def test_no_pfc_anywhere_is_reported_as_nothing_to_audit():
    db = mutated(lambda d: d["PORT_QOS_MAP"].update({"Ethernet0,Ethernet4": {"dscp_to_tc_map": "AZURE"}}))
    assert [(x.check, x.severity) for x in q.audit(db)] == [("QOS-000", "info")]
