# E2 analysis (raw: `results/summary.json`)

| Traffic | Policy 0 (L3 only) | Policy 1 (L3+L4) |
|---|---|---|
| 64 plain routed UDP flows, leaf1 -> leaf2 loopback (control) | 100% / 0% on the two uplinks (both runs) | 53/47 and 58/42 |
| 64 VXLAN-encapsulated TCP flows, h1 -> h3 | **100% / 0%** (both runs) | **100% / 0%** (both runs) |

- The kernel hash policy does control spreading for ordinary routed traffic: policy 0 puts every flow on one uplink, policy 1 spreads them roughly evenly.
- **VXLAN traffic from a Linux VTEP stays on ONE uplink under either policy**, although 64 to 65 distinct outer UDP source ports were visible on the wire (so the entropy exists). The result is consistent with the kernel's VXLAN device reusing the route it resolved for the remote VTEP instead of re-hashing per flow; I did not verify that mechanism in the kernel source or with a kernel trace, so treat the cause as a hypothesis.
- Consequence for this lab: ECMP is *configured and present* (two next-hops in RIB and FIB) but is not *used* by overlay traffic from a Linux VTEP. This is the "three levels" point of the interview answer: RIB shows two paths, the FIB shows two paths, counters show one. An ASIC VTEP hashes in hardware and would spread these flows; I make no claim about it.
- This is why F11 (hash policy L3-only) has no visible effect on overlay traffic here; it is detected by comparing the sysctl with the inventory and shows up for plain routed flows.
- The inventory now sets `ecmp_hash_policy: 1` because it spreads routed flows and costs nothing; E1 was measured before this change (policy 0). E1's probe flow is a single flow pinned to one uplink either way, so the E1 numbers are not affected.
