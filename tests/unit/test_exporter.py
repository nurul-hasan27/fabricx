"""Exporter parsing and text format, using outputs captured from the lab (tests/fixtures)."""
import json
from pathlib import Path

from fabricx import annotate, exporter, model

F = model.load("inventory/fabric.yaml")
FX = Path("tests/fixtures")
LINK = json.dumps([
    {"ifname": "eth0", "operstate": "UP", "stats64": {"rx": {"bytes": 9, "dropped": 0}, "tx": {"bytes": 9, "dropped": 0}}},
    {"ifname": "eth1", "operstate": "UP", "stats64": {"rx": {"bytes": 1000, "dropped": 2}, "tx": {"bytes": 2000, "dropped": 0}}},
    {"ifname": "br10", "operstate": "UP", "stats64": {"rx": {"bytes": 5, "dropped": 0}, "tx": {"bytes": 5, "dropped": 0}}},
])


def leaf1_raw():
    parts = [(FX / "leaf1_bgp_summary.json").read_text(), (FX / "leaf1_bfd_peers.json").read_text(),
             (FX / "leaf1_evpn_routes.json").read_text(), LINK]
    return f"\n{exporter.SEP}\n".join(parts)


def test_one_exec_per_switch_with_all_sections():
    cmd = exporter.command(F, "leaf1")
    assert cmd.count(exporter.SEP) == 3 and "show bfd peers json" in cmd and "evpn route json" in cmd
    assert "evpn" not in exporter.command(F, "spine1")


def test_parse_leaf_output():
    s = exporter.parse_node(F, "leaf1", leaf1_raw())
    bgp = [x for x in s if x.name == "fabricx_bgp_peer_up"]
    assert len(bgp) >= 2 and all(x.value == 1.0 for x in bgp)
    assert {x.labels["peer_name"] for x in bgp} >= {"spine1", "spine2"}
    assert all(x.value == 1.0 for x in s if x.name == "fabricx_bfd_peer_up")
    assert {x.labels["type"] for x in s if x.name == "fabricx_evpn_routes"} == {"type2_mac", "type2_macip", "type3", "type5"}
    ifs = {x.labels["iface"] for x in s if x.name.startswith("fabricx_iface")}
    assert ifs == {"eth1"}   # management eth0 and bridges are not fabric ports
    rx = next(x for x in s if x.name == "fabricx_iface_rx_dropped_total")
    assert rx.value == 2.0


def test_text_format():
    text = exporter.render(exporter.parse_node(F, "leaf1", leaf1_raw())
                           + [exporter.Sample("fabricx_poll_seconds", {}, 0.5)])
    assert "# TYPE fabricx_iface_tx_bytes_total counter" in text
    assert 'fabricx_iface_tx_bytes_total{iface="eth1",node="leaf1"} 2000' in text
    assert "fabricx_poll_seconds 0.5" in text
    assert text.count("# HELP fabricx_bgp_peer_up") == 1


def test_annotation_is_a_noop_without_grafana(monkeypatch):
    monkeypatch.delenv("FABRICX_GRAFANA_URL", raising=False)
    assert annotate.post("x", ["inject"]) is False


def test_annotation_failure_is_reported_not_silent(monkeypatch, capsys):
    monkeypatch.setenv("FABRICX_GRAFANA_URL", "http://127.0.0.1:9")   # nothing listens on port 9
    assert annotate.post("inject F01", ["inject"]) is False
    assert "could not post 'inject F01'" in capsys.readouterr().err
