"""Adapter tests with a FAKE node (outputs hand-written in the documented sonic-db-cli format).
They prove the parsing and the chain logic, not that a real SONiC behaves this way."""
import subprocess

from fabricx.adapters import sonic

ROUTE_KEY = 'ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:{"dest":"10.99.0.0/24","switch_id":"oid:0x21000000000000","vr":"oid:0x3000000000022"}'
ANSWERS = {
    "APPL_DB keys 'ROUTE_TABLE:10.99.0.0/24'": "ROUTE_TABLE:10.99.0.0/24",
    "APPL_DB HGETALL 'ROUTE_TABLE:10.99.0.0/24'": "{'nexthop': '10.1.1.1', 'ifname': 'Ethernet0'}",
    "ASIC_DB keys 'ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:*'": ROUTE_KEY + "\n",
    f"ASIC_DB HGETALL '{ROUTE_KEY}'": "{'SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID': 'oid:0x400000000064d'}",
    "ASIC_DB HGETALL 'ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP:oid:0x400000000064d'": "{}",
    "ASIC_DB HGETALL 'ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:oid:0x400000000064d'": "{'SAI_NEXT_HOP_ATTR_IP': '10.1.1.1'}",
}


def fake(answers):
    def _exec(lab, node, cmd, timeout=60, retries=0):
        key = cmd.replace("sonic-db-cli ", "")
        return subprocess.CompletedProcess(cmd, 0, answers.get(key, ""), "")
    return _exec


def test_parsers():
    assert sonic.parse_keys("a\n\nb\n") == ["a", "b"]
    assert sonic.parse_hgetall("{'a': 'b'}") == {"a": "b"}
    assert sonic.parse_hgetall("") == {}


def test_trace_follows_appl_to_asic_to_nexthop(monkeypatch):
    monkeypatch.setattr(sonic, "node_exec", fake(ANSWERS))
    hops = sonic.trace_route("lab", "leaf3", "10.99.0.0/24")
    db = [h for h in hops if h.db.endswith("_DB")]
    assert [h.db for h in hops][:2] == ["FRR bgpd", "FRR zebra"]
    assert [h.db for h in db] == ["APPL_DB", "ASIC_DB", "ASIC_DB"]
    assert db[0].fields["nexthop"] == "10.1.1.1"
    assert db[2].fields["SAI_NEXT_HOP_ATTR_IP"] == "10.1.1.1"


def test_trace_shows_where_chain_stops(monkeypatch):
    monkeypatch.setattr(sonic, "node_exec", fake({k: v for k, v in ANSWERS.items() if k.startswith("APPL_DB")}))
    hops = sonic.trace_route("lab", "leaf3", "10.99.0.0/24")
    db = [h for h in hops if h.db.endswith("_DB")]
    assert db[0].fields and not db[1].fields
    assert "no route entry" in db[1].key
    assert "nothing found" in sonic.render_trace("10.99.0.0/24", hops)


def test_ecmp_group_members_are_followed(monkeypatch):
    grp = "oid:0x5000000000611"
    m1 = "ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER:oid:0x2d000000000612"
    ans = dict(ANSWERS)
    ans[f"ASIC_DB HGETALL '{ROUTE_KEY}'"] = f"{{'SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID': '{grp}'}}"
    ans[f"ASIC_DB HGETALL 'ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP:{grp}'"] = "{'SAI_NEXT_HOP_GROUP_ATTR_TYPE': 'SAI_NEXT_HOP_GROUP_TYPE_DYNAMIC_UNORDERED_ECMP'}"
    ans["ASIC_DB keys 'ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER:*'"] = m1
    ans[f"ASIC_DB HGETALL '{m1}'"] = (f"{{'SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID': '{grp}', "
                                      "'SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_ID': 'oid:0x400000000064d'}")
    monkeypatch.setattr(sonic, "node_exec", fake(ans))
    hops = sonic.trace_route("lab", "leaf3", "10.99.0.0/24")
    stages = [h.stage for h in hops]
    assert "orchagent (routeorch ECMP group)" in stages and "orchagent (ECMP member)" in stages
    assert hops[-1].fields["SAI_NEXT_HOP_ATTR_IP"] == "10.1.1.1"


def test_frr_hops_are_summarised():
    bgp = {"paths": [{"aspath": {"string": "65000 65001"}, "nexthops": [{"ip": "10.1.1.4"}],
                      "bestpath": {"overall": True}}]}
    assert sonic._bgp_fields(bgp)["path1"] == "as-path [65000 65001] via 10.1.1.4 best"
    z = {"p": [{"protocol": "bgp", "selected": True, "offloaded": True,
                "nexthops": [{"ip": "10.1.1.4", "interfaceName": "Ethernet0", "fib": True}]}]}
    f = sonic._zebra_fields(z, "p")
    assert f["offloaded"] == "True" and "Ethernet0" in f["nexthop1"]
