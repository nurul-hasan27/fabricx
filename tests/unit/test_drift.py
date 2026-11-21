from pathlib import Path

from fabricx import drift, generate, model

F = model.load()
GEN = generate.render_all(F)["configs/leaf1/frr.conf"]
RUN = Path("tests/fixtures/leaf1_running_config.txt").read_text()


def test_real_running_config_matches_generated():
    assert drift.diff(GEN, RUN) == ([], [])


def test_changed_timer_detected_both_ways():
    changed = RUN.replace("neighbor FABRIC timers 3 9", "neighbor FABRIC timers 1 3")
    missing, extra = drift.diff(GEN, changed)
    assert any("timers 3 9" in m for m in missing) and any("timers 1 3" in e for e in extra)


def test_extra_static_route_detected():
    missing, extra = drift.diff(GEN, RUN + "ip route 192.0.2.0/24 blackhole\n")
    assert missing == [] and extra == ["ip route 192.0.2.0/24 blackhole"]


def test_line_moved_to_other_block_detected():
    moved = RUN.replace("  maximum-paths 2\n", "").replace(
        " address-family l2vpn evpn\n  neighbor FABRIC activate", " address-family l2vpn evpn\n  maximum-paths 2\n  neighbor FABRIC activate", 1)
    missing, extra = drift.diff(GEN, moved)
    assert missing and extra
