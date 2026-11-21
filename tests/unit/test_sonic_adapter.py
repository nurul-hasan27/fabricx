"""Adapter tests with a FAKE node (outputs hand-written in the documented sonic-db-cli format).
They prove the parsing and the chain logic, not that a real SONiC behaves this way."""
import subprocess

from fabricx.adapters import sonic

ROUTE_KEY = 'ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:{"dest":"10.99.0.0/24","switch_id":"oid:0x21000000000000","vr":"oid:0x3000000000022"}'
ANSWERS = {
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
    assert [h.db for h in hops] == ["APPL_DB", "ASIC_DB", "ASIC_DB"]
    assert hops[0].fields["nexthop"] == "10.1.1.1"
    assert hops[2].fields["SAI_NEXT_HOP_ATTR_IP"] == "10.1.1.1"


def test_trace_shows_where_chain_stops(monkeypatch):
    monkeypatch.setattr(sonic, "node_exec", fake({k: v for k, v in ANSWERS.items() if k.startswith("APPL_DB")}))
    hops = sonic.trace_route("lab", "leaf3", "10.99.0.0/24")
    assert hops[0].fields and not hops[1].fields
    assert "no route entry" in hops[1].key
    assert "nothing found" in sonic.render_trace("10.99.0.0/24", hops)
