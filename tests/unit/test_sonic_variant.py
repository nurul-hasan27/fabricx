import pytest
import yaml
from pydantic import ValidationError

from fabricx import generate, model

V = "inventory/variants/sonic-leaf3.yaml"


def test_port_name_mapping_follows_lanemap():
    assert model.sonic_port("eth1") == "Ethernet0"
    assert model.sonic_port("eth2") == "Ethernet4"


def test_sonic_variant_generates_db_driven_bringup():
    f = model.load(V)
    files = generate.render_all(f)
    clab = files[f"{f.name}.clab.yml"]
    assert "kind: sonic-vs" in clab and f.sonic.image in clab
    setup = files["configs/leaf3/sonic-setup.sh"]
    lk = next(x for x in f.fabric_links() if x.leaf == "leaf3" and x.spine == "spine1")
    assert f'INTERFACE|Ethernet0|{lk.leaf_ip}/31' in setup
    assert f"LOOPBACK_INTERFACE|Loopback0|{f.switch('leaf3').loopback}/32" in setup
    frr = files["configs/leaf3/frr.conf"]
    assert "interface eth1" not in frr and "ip address" not in frr   # addresses come from CONFIG_DB
    assert "router bgp 65003" in frr and f"network {f.switch('leaf3').loopback}/32" in frr
    assert "configs/leaf3/setup.sh" not in files and "configs/leaf3/daemons" not in files


def test_sonic_leaf_with_hosts_is_rejected():
    d = yaml.safe_load(open(V))
    d["hosts"].append({"name": "h9", "leaf": "leaf3", "ip": "10.10.10.109", "vlan": 10})
    with pytest.raises(ValidationError):
        model.Fabric.model_validate(d)


def test_sonic_without_image_is_rejected():
    d = yaml.safe_load(open(V))
    d.pop("sonic")
    with pytest.raises(ValidationError):
        model.Fabric.model_validate(d)
