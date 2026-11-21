from pathlib import Path

from fabricx import model, parsers, validators

FX = Path("tests/fixtures")
F = model.load()


def test_parse_bgp_fixture():
    peers = parsers.bgp_peers((FX / "leaf1_bgp_summary.json").read_text())
    assert peers == {"10.1.1.0": "Established", "10.1.2.0": "Established"}


def test_parse_bfd_fixture():
    assert set(parsers.bfd_peers((FX / "leaf1_bfd_peers.json").read_text()).values()) == {"up"}


def test_parse_interfaces_fixture():
    i = parsers.interfaces((FX / "leaf1_ip_link.json").read_text())
    assert i["eth1"]["mtu"] == 9100 and i["eth2"]["mtu"] == 9100 and i["br10"]["mtu"] == 1500


def test_parse_nexthop_fixture_and_single_path():
    assert parsers.nexthop_count((FX / "leaf1_route_leaf3.txt").read_text()) == 2
    assert parsers.nexthop_count("10.0.0.13 nhid 29 via 10.1.2.0 dev eth2 proto bgp metric 20") == 1
    assert parsers.nexthop_count("") == 0


def test_parse_evpn_fixture_has_all_types():
    c = parsers.evpn_counts(parsers.evpn_route_keys((FX / "leaf1_evpn_routes.json").read_text()))
    assert c["type2_macip"] >= 5 and c["type3"] >= 5 and c["type5"] >= 3


def good_state():
    """State that exactly matches intent, built from the inventory (not from a lab)."""
    st = {}
    for sw in F.spines + F.leaves:
        s = {"bgp": {str(n.peer_ip): "Established" for n in F.neighbors(sw.name)},
             "bfd": {str(n.peer_ip): "up" for n in F.neighbors(sw.name)},
             "interfaces": {n.local_if: {"state": "UP", "mtu": F.fabric_mtu} for n in F.neighbors(sw.name)}}
        if sw in F.leaves:
            s["nexthops"] = {o.name: len(F.spines) for o in F.leaves if o.name != sw.name}
            keys = [f"[2]:[0]:[48]:[aa:bb]:[32]:[{h.ip}]" for h in F.hosts]
            for o in F.leaves:
                keys += [f"[3]:[0]:[32]:[{o.loopback}]"] * len(F.leaf_vlans(o.name))
            keys += [f"[5]:[0]:[24]:[{v.subnet.network_address}]" for v in F.vlans]
            s["evpn_keys"] = keys
        st[sw.name] = s
    return st


def test_good_state_has_no_findings():
    assert validators.validate(F, good_state()) == []


def _checks(st):
    return {x.check for x in validators.validate(F, st)}


def test_bgp_down_detected():
    st = good_state(); st["leaf1"]["bgp"]["10.1.1.0"] = "Active"
    assert "bgp-not-established" in _checks(st)


def test_bfd_down_detected():
    st = good_state(); st["spine1"]["bfd"]["10.1.1.1"] = "down"
    assert "bfd-down" in _checks(st)


def test_single_nexthop_detected():
    st = good_state(); st["leaf2"]["nexthops"]["leaf1"] = 1
    assert "ecmp-nexthops" in _checks(st)


def test_mtu_mismatch_detected():
    st = good_state(); st["leaf1"]["interfaces"]["eth1"]["mtu"] = 1500
    assert "underlay-mtu" in _checks(st)


def test_link_down_detected():
    st = good_state(); st["spine2"]["interfaces"]["eth3"]["state"] = "DOWN"
    assert "link-down" in _checks(st)


def test_missing_evpn_routes_detected():
    st = good_state()
    st["leaf1"]["evpn_keys"] = [k for k in st["leaf1"]["evpn_keys"] if "10.20.20.104" not in k]
    assert "evpn-type2-missing" in _checks(st)
    st = good_state(); st["leaf3"]["evpn_keys"] = [k for k in st["leaf3"]["evpn_keys"] if not k.startswith("[5]")]
    assert "evpn-type5-missing" in _checks(st)
    st = good_state(); st["leaf1"]["evpn_keys"] = [k for k in st["leaf1"]["evpn_keys"] if "10.0.0.12" not in k]
    assert "evpn-type3-missing" in _checks(st)


def test_unreachable_node_reported_and_does_not_crash_other_checks():
    st = good_state()
    st["leaf2"] = {"unreachable": "container is paused"}
    found = validators.validate(F, st)
    assert [x.check for x in found if x.node == "leaf2"] == ["node-unreachable"]
    assert all(x.check in ("node-unreachable", "bgp-peer-missing") or x.node != "leaf2" for x in found)


def test_tc_child_queue_counters_not_the_shapers():
    """E6 numbers come from the child queue under the TBF shaper (format captured from the lab)."""
    from fabricx import parsers
    red = parsers.tc_child_qdisc_stats(open("tests/fixtures/leaf2_tc_tbf_red.txt").read())
    assert red == {"sent_pkts": 49168, "dropped": 2, "marked": 1280, "early_drop": 1, "pdrop": 1}
    fifo = parsers.tc_child_qdisc_stats(open("tests/fixtures/leaf2_tc_tbf_pfifo.txt").read())
    assert fifo == {"sent_pkts": 49817, "dropped": 5}   # 5 = the pfifo's drops, not the tbf's 7
