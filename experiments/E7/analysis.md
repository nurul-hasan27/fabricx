# E7 — EVPN MAC mobility

Method: `run.py` moves host h4 (VLAN 20, MAC M) between leaf2 and leaf1 ten times, while a 1 ms probe runs h2 (leaf1) -> h4 (same subnet, L2VNI 10020).
Two modes: **cold** (old cable removed, new one created, host reappears about 0.8 s later) and **live** (the new port announces the same MAC on the new leaf *before* the old cable is removed, like a VM live migration).

| Mode (N=10) | Outage min / median / max (ms) | Lost packets (median) | MAC-mobility seq after the move |
|---|---|---|---|
| live | 4.1 / 9.4 / 488 | 0 | 1 in 8 of 10 runs, 0 in the first two |
| cold | 658 / 710 / 1271 | 709 | 0 in all runs |

(Raw: `results/live_moves.json`, `results/cold_moves.json`, summaries beside them.)

## What the data says
- **Live move:** traffic recovers within the probe noise floor (median 9 ms), one outlier at 488 ms. The new leaf advertises the MAC with a higher MAC-mobility sequence number and the old leaf stops being the owner.
- **Cold move:** the outage equals the time the host is physically absent (the cable swap commands took 0.8 s). The MAC is withdrawn when the port disappears and re-learned as a brand-new MAC, so no mobility sequence number is used (seq 0). EVPN itself added no measurable delay: packets arrived within 1 ms of the host coming back.
- So with this setup, **EVPN convergence after a move is below what I can measure** (about 1 ms to a few ms); the outage is dominated by how fast the host re-appears.

## Open points / caveats
- In 7 of 10 live runs the old leaf still listed the MAC as `local` 3 s after the move, and in the first two live runs I read sequence number 0. I did not find out why (possible: stale entry until FDB ageing, or my reading timing). Treat both readings as unreliable until checked.
- Timings share the noise floor of E1 (3-9 ms); the 488 ms outlier is unexplained.
- The host is moved with veth surgery in the VM, not by a real hypervisor.
