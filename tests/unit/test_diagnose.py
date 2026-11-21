"""Pure tests of the diagnose rules: a healthy synthetic state, then one defect per rule."""
import copy

from fabricx import diagnose, model

F = model.load()


def healthy():
    nodes = {}
    for sw in F.spines + F.leaves:
        n = {"reachable": True, "bgpd_state": "S", "vtysh_bgp_ok": True, "hash_policy": F.ecmp_hash_policy,
             "interfaces": {x.local_if: {"state": "UP", "mtu": F.fabric_mtu} for x in F.neighbors(sw.name)},
             "bfd": {str(x.peer_ip): "up" for x in F.neighbors(sw.name)},
             "bgp": {str(x.peer_ip): "Established" for x in F.neighbors(sw.name)}, "bgp_error": {},
             "bgp_remote_as": {str(x.peer_ip): x.peer_asn for x in F.neighbors(sw.name)}}
        if sw in F.leaves:
            n["nexthops"] = {o.name: len(F.spines) for o in F.leaves if o.name != sw.name}
            n["vni_rts"] = {str(v.vni): {"import": [f"{sw.asn}:{v.vni}"], "export": [f"{sw.asn}:{v.vni}"]}
                            for v in F.leaf_vlans(sw.name)}
            n["evpn_vni"] = {str(v.vni): {"type": "L2", "tenantVrf": v.vrf} for v in F.leaf_vlans(sw.name)}
            n["evpn_vni"].update({str(r.l3vni): {"type": "L3", "tenantVrf": r.name} for r in F.leaf_vrfs(sw.name)})
            n["vxlan"] = {f"br{v.id}": v.vni for v in F.leaf_vlans(sw.name)}
            n["bridge_mac"] = {f"br{v.id}": F.anycast_gw_mac for v in F.leaf_vlans(sw.name)}
            k = F.leaves.index(sw)
            n["evpn_by_rd"] = {f"{sw.loopback}:3": [f"[2]:[0]:[48]:[aa:bb:cc:0{k}:00:{i:02x}]" for i in range(2)]}
        nodes[sw.name] = n
    links = [{"spine": lk.spine, "leaf": lk.leaf, "spine_if": lk.spine_if, "leaf_if": lk.leaf_if,
              "leaf_ping_loss_pct": 0.0, "spine_ping_loss_pct": 0.0,
              "leaf_to_spine_arrived": 300, "spine_to_leaf_arrived": 300} for lk in F.fabric_links()]
    return {"nodes": nodes, "links": links, "dataplane": {"c1": True, "c2": True, "c3": True, "c4": False}}


def causes(st):
    d = diagnose.analyse(F, st)
    return {x.cause_key for x in d.primary}


def test_healthy_state_has_no_findings():
    assert diagnose.analyse(F, healthy()).healthy


def mutate(fn):
    st = copy.deepcopy(healthy())
    fn(st)
    return st


def test_each_rule_detects_its_defect():
    lk = next(x for x in st_links() if x["leaf"] == "leaf1" and x["spine"] == "spine1")
    cases = {
        "link-down": lambda s: s["nodes"]["leaf1"]["interfaces"]["eth1"].update(state="DOWN"),
        "gray-failure": lambda s: [s["links"][0].update(leaf_to_spine_arrived=0, spine_to_leaf_arrived=0,
                                                        leaf_ping_loss_pct=100.0, spine_ping_loss_pct=100.0)],
        "unidirectional-loss": lambda s: s["links"][0].update(leaf_to_spine_arrived=0, leaf_ping_loss_pct=100.0,
                                                              spine_ping_loss_pct=100.0),
        "lossy-link": lambda s: s["links"][0].update(leaf_ping_loss_pct=2.0),
        "underlay-mtu": lambda s: s["nodes"]["leaf1"]["interfaces"]["eth1"].update(mtu=1500),
        "bgp-asn-mismatch": lambda s: [s["nodes"]["spine1"]["bgp"].update({"10.1.1.3": "Active"}),
                                       s["nodes"]["spine1"]["bgp_remote_as"].update({"10.1.1.3": 65999})],
        "bgp-session-down": lambda s: s["nodes"]["leaf1"]["bgp"].update({"10.1.1.0": "Idle"}),
        "bgp-daemon-hung": lambda s: s["nodes"]["spine1"].update(bgpd_state="T"),
        "loopback-not-advertised": lambda s: [s["nodes"][x]["nexthops"].update({"leaf3": 0}) for x in ("leaf1", "leaf2")],
        "rt-mismatch": lambda s: s["nodes"]["leaf2"]["vni_rts"]["10010"].update(**{"import": ["65002:99999"], "export": ["65002:99999"]}),
        "vni-mismatch": lambda s: s["nodes"]["leaf2"]["vxlan"].update({"br10": 10099}),
        "missing-l3vni": lambda s: s["nodes"]["leaf2"]["evpn_vni"].pop("50001"),
        "advertise-all-vni-missing": lambda s: s["nodes"]["leaf2"].update(evpn_vni={}),
        "ecmp-hash-policy": lambda s: s["nodes"]["leaf1"].update(hash_policy=0),
        "gateway-mac-mismatch": lambda s: s["nodes"]["leaf2"]["bridge_mac"].update({"br10": "02:fa:b0:00:00:99"}),
        "duplicate-mac": lambda s: s["nodes"]["leaf2"].update(
            evpn_macs={"10010": {"aa:bb:cc:00:00:00": {"isDuplicate": True, "detectionCount": 5}}}),
    }
    assert lk
    for want, fn in cases.items():
        assert want in causes(mutate(fn)), want


def st_links():
    return healthy()["links"]


def test_lower_layer_wins_and_higher_become_consequences():
    def both(s):
        s["nodes"]["leaf1"]["interfaces"]["eth1"].update(state="DOWN")
        s["nodes"]["leaf1"].update(hash_policy=0)
    d = diagnose.analyse(F, mutate(both))
    assert {x.cause_key for x in d.primary} == {"link-down"}
    assert {x.cause_key for x in d.consequences} == {"ecmp-hash-policy"}


def test_bfd_independent_unreachable_node_reported():
    d = diagnose.analyse(F, mutate(lambda s: s["nodes"]["leaf3"].clear() or s["nodes"]["leaf3"].update(reachable=False)))
    assert "node-unreachable" in {x.cause_key for x in d.primary}


def test_stale_move_counters_on_a_remote_mac_are_not_a_duplicate():
    stale = {"10010": {"aa:bb:cc:00:00:00": {"type": "remote", "isDuplicate": False, "detectionCount": 4}}}
    assert "duplicate-mac" not in causes(mutate(lambda s: s["nodes"]["leaf2"].update(evpn_macs=stale)))
    live = {"10010": {"aa:bb:cc:00:00:00": {"type": "local", "isDuplicate": False, "detectionCount": 3}}}
    assert "duplicate-mac" in causes(mutate(lambda s: s["nodes"]["leaf2"].update(evpn_macs=live)))
