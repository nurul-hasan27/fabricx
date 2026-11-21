# E3 — What does an underlay MTU mismatch look like to a customer?

**Question:** if one fabric link has MTU 1500 while the rest are 9100, what do the customer's hosts experience (host MTU 1500, so VXLAN-encapsulated full-size frames are 1550 bytes)?

## Method
- Scenarios: `local` (leaf1's own uplink on the probe path is 1500) and `remote` (the spine -> leaf2 link on the path is 1500). Both ends of the link are set.
- For each scenario and for a healthy baseline:
  1. Largest working ICMP payload with the DF bit set, from h1 to h3 (bisect between 1000 and 1472).
  2. `iperf3` TCP throughput h1 -> h3 for 5 s.
- Expected threshold if the outer path really is limited to 1500: 1500 - 50 (VXLAN + outer IP/UDP + inner Ethernet) - 28 (IP + ICMP header) = 1422.
- The VXLAN devices use `df set` (outer DF bit always on, as RFC 7348 requires VTEPs not to fragment).
- Route/PMTU caches are flushed before each probe so earlier learning does not distort results.

## Limits
Linux VTEPs and routers generate ICMP "fragmentation needed" and can react to it; many real ASIC platforms do not propagate it to the host. Results show what *this* software fabric does, not what a specific switch does.

Files: `results/*.json`, `analysis.md`, and the RCA in `docs/rca/RCA-001-mtu-black-hole.md`.
