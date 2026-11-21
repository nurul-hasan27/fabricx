import copy

import pytest
import yaml
from pydantic import ValidationError

from fabricx import generate, model

RAW = yaml.safe_load(open("inventory/fabric.yaml"))


def test_inventory_loads():
    f = model.load()
    assert len(f.spines) == 2 and len(f.leaves) == 3 and len(f.hosts) == 5


def test_link_addressing_matches_blueprint():
    f = model.load()
    lk = next(x for x in f.fabric_links() if x.spine == "spine1" and x.leaf == "leaf2")
    assert str(lk.spine_ip) == "10.1.1.2" and str(lk.leaf_ip) == "10.1.1.3"


def test_six_links_all_unique_subnets():
    links = model.load().fabric_links()
    assert len(links) == 6
    assert len({str(lk.spine_ip) for lk in links} | {str(lk.leaf_ip) for lk in links}) == 12


def test_host_ports_do_not_clash_with_uplinks():
    f = model.load()
    ports = [(h.leaf, h.leaf_if) for h in f.host_links()]
    assert len(ports) == len(set(ports))
    assert all(p[1] not in ("eth1", "eth2") for p in ports)


def test_host_outside_subnet_rejected():
    bad = copy.deepcopy(RAW)
    bad["hosts"][0]["ip"] = "10.99.0.5"
    with pytest.raises(ValidationError):
        model.Fabric.model_validate(bad)


def test_duplicate_leaf_asn_rejected():
    bad = copy.deepcopy(RAW)
    bad["leaves"][1]["asn"] = bad["leaves"][0]["asn"]
    with pytest.raises(ValidationError):
        model.Fabric.model_validate(bad)


def test_generation_is_deterministic_and_complete():
    f = model.load()
    a, b = generate.render_all(f), generate.render_all(f)
    assert a == b
    assert len(a) == 1 + 5 * 3 + 2 * len(f.leaves)  # clab + 3 files per node + leaf setup.sh and ports.sh
    assert "10.0.0.12/32" in a["configs/leaf2/frr.conf"]
