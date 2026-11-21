# E1 — Outage when a leaf-spine link fails, with and without BFD

**Question:** how long is the outage for a flow when the uplink it uses fails, for (a) a clean carrier loss and (b) a gray failure (link stays UP but drops everything), under three detection profiles?

**Hypothesis:** carrier loss is detected instantly by the kernel regardless of protocol (veth drops carrier on both ends). A gray failure is only detected by BFD (about 3 x 300 ms) or the BGP hold timer (9 s with the datacenter timers, 180 s with BGP defaults).

## Method
- Probe: `fabricx-probe` (`src/fabricx/probe.py`), sequence-numbered UDP, 1 ms interval, h1 -> h3 (same subnet, different leaf, L2VNI).
- Before each run, find which leaf1 uplink the flow uses (TX counters across a 1 s probe). Fail exactly that uplink on leaf1:
  - carrier: `ip link set <if> down`
  - gray: `tc qdisc add dev <if> root netem loss 100%` (interface stays UP)
- Inject 3 s after the sender starts; restore after the sender ends; wait until all leaves again have 2 next-hops to each other.
- Outage = longest gap between two consecutive received probes (ms). Lost = packets sent minus received.
- Profiles are applied at run time with vtysh (no BFD / BGP 3/9 s / BGP 60/180 s), then `clear bgp *`.
- N = 10 runs per cell (3 for the 180 s hold-timer profile, because each run lasts 200 s).

## Resolution and limits (read before trusting numbers)
- Resolution is about +/- one probe interval (1 ms) plus scheduler jitter: a clean 4 s run in Phase 2 showed a 3.12 ms longest gap, so differences below ~5 ms are noise.
- All containers share one VM and one clock; CPUs are shared, so timings are noisy. Min / median / max are reported, not single numbers.
- veth carrier loss is instant and symmetric; real optics are not. This is why the gray failure matters.
- Software forwarding in the Linux kernel; no claims about ASIC behaviour.

## Files
`results/<profile>_<fault>/runNN/{result.json, probe.csv.gz}`, `summary.json` per cell, `run.log`, `analysis.md`.
