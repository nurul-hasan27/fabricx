# RCA-002 — "One uplink is saturated, the other idle" (ECMP not spreading)

| Field | Content |
|---|---|
| ID / severity | RCA-002 / S3 (reproduced in the lab) |
| Customer-visible impact | Multi-flow traffic between racks fills one leaf uplink while the second is almost unused; throughput capped at one link's worth. No packet loss, nothing is "down". |
| Environment | FabricX Phase 6, FRR 10.2.1 on Linux, eBGP underlay with 2 ECMP paths, VXLAN-EVPN, inventory policy `ecmp_hash_policy` 1 (fault F11 sets 0 on leaf1) |
| Data collected | `experiments/E2/results/summary.json`, `experiments/E2/analysis.md`, fault bundle `artifacts/runs/*_F11` |

## Symptom
Counters on leaf1's uplinks over a 64-flow test: 100% on one, 0% on the other. Routing is healthy: BGP shows two paths, the kernel route has two `nexthop via` entries, BFD up on both links.

## Analysis (three levels, each ruled in or out)
1. **RIB / FIB:** two next-hops to every remote loopback. ECMP is *configured* and installed. Rules out a routing problem.
2. **Hash policy:** `sysctl net.ipv4.fib_multipath_hash_policy`. Policy 0 hashes only source/destination IP, so every flow between the same two addresses takes the same path. With policy 1 (L3+L4) 64 plain UDP flows split 53/47 and 58/42 (control experiment). So policy 0 is **one cause**.
3. **Overlay:** for VXLAN-encapsulated flows, all 64 flows still used one uplink under *both* policies even though 64 to 65 distinct outer UDP source ports were on the wire. A Linux VTEP therefore adds a second cause independent of the sysctl (hypothesis: it keeps using the route it resolved for the remote VTEP; not verified in the kernel).

## Root cause
Two layered causes: (a) hash policy 0 (L3 only) pins all flows of an address pair to one path; (b) in this software fabric the VXLAN encapsulation path from a Linux VTEP does not spread flows across uplinks at all, with either policy.

## Fix and verification
(a) Set the inventory value `ecmp_hash_policy: 1` (generated into every node); `fabricx diagnose` flags any switch that differs (`ecmp-hash-policy`, caught in the blind drill). (b) Cannot be fixed by configuration on a Linux VTEP; with real ASIC VTEPs verify the spread with per-uplink counters under many flows.

## Prevention
Validator/diagnose rule `ecmp-hash-policy`; the experiment E2 is the template for a multi-flow counter check on real hardware.

## Limitations
Kernel hashing is not ASIC hashing. One source/destination pair and a single link pair were tested; no claim about hash seeds, polarisation across several spine tiers, or resilient hashing.
