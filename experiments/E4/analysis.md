# E4 analysis — how EVPN misconfigurations present

Matrix of customer symptoms: `symptoms.md` (generated from the drill runs). EVPN-specific rows:

| Fault | Same subnet across leaves | Routed across leaves | First command that reveals it |
|---|---|---|---|
| F08 route-target mismatch (VNI 10010 on leaf2) | **FAIL** | ok | `show bgp l2vpn evpn vni 10010` (compare import/export RTs) |
| F09 VNI mismatch (leaf2 VLAN 10 -> VNI 10099) | **FAIL** | ok | `ip -d link show type vxlan` (id differs from the inventory) |
| F10 missing L3VNI on leaf2 | ok | **ok (hypothesis was FAIL)** | `show evpn vni` (50001 missing) |
| F14 anycast gateway MAC mismatch | ok | ok | `ip link show br10` on every leaf |
| Extra: `no advertise-all-vni` on leaf2 | **FAIL** | **FAIL** | `show bgp l2vpn evpn vni` (no VNIs), `show evpn vni` |

- Two of my hypotheses were wrong (see the "Hypothesis matched" column): **F10** did not break routed traffic within the observation window (a likely reason, not verified: the VXLAN device and kernel routes stay in place after the FRR mapping is removed, so traffic keeps flowing until they age out or are flushed), and **F12** (duplicate MAC) did break same-subnet traffic although I expected no hard failure. Wrong hypotheses are a finding: do not trust a "nothing is broken" check made right after a config removal.
- The most common customer view is "one subnet unreachable from one rack while everything else works"; the cause can sit in the route-targets, the VNI mapping or the L3VNI binding, and only layer-by-layer inspection separates them.
- Faults that leave *every* traffic class working (F01 to F07, F11, F13, F14) are invisible to pings alone: they need state checks (BFD, MTU, ASN, advertisement) or counters.
