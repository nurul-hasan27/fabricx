import json

from fabricx import generate, model, parsers


def test_ospf_and_isis_variants_generate_complete_configs():
    for proto, marker in (("ospf", "router ospf"), ("isis", "router isis FABRIC")):
        f = model.load(f"inventory/variants/{proto}.yaml")
        files = generate.render_all(f)
        assert len(files) == 22
        leaf = files["configs/leaf1/frr.conf"]
        assert marker in leaf and "remote-as internal" in leaf and "update-source lo" in leaf
        assert "route-reflector-client" in files["configs/spine1/frr.conf"]
        assert f"ospfd={'yes' if proto == 'ospf' else 'no'}" in files["configs/leaf1/daemons"]
        assert f"isisd={'yes' if proto == 'isis' else 'no'}" in files["configs/leaf1/daemons"]


def test_ebgp_config_has_no_igp_lines():
    f = model.load()
    assert "router ospf" not in generate.render_all(f)["configs/leaf1/frr.conf"]


def test_igp_bgp_neighbors_are_loopbacks_but_bfd_peers_are_link_addresses():
    f = model.load("inventory/variants/ospf.yaml")
    assert {str(n.peer_ip) for n in f.neighbors("leaf1")} == {str(s.loopback) for s in f.spines}
    assert {str(n.peer_ip) for n in f.link_peers("leaf1")} == {"10.1.1.0", "10.1.2.0"}


def test_isis_net_is_derived_from_the_loopback():
    f = model.load("inventory/variants/isis.yaml")
    assert f.isis_net("leaf1") == "49.0001.0100.0000.0011.00"


def test_bgp_summary_with_only_evpn_family_is_parsed():
    raw = json.dumps({"l2VpnEvpn": {"peers": {"10.0.0.1": {"state": "Established"}}}})
    assert parsers.bgp_peers(raw) == {"10.0.0.1": "Established"}
