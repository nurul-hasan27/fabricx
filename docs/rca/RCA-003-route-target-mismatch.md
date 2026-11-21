# RCA-003 — "Hosts in the same subnet on two racks cannot talk, but routing works"

| Field | Content |
|---|---|
| ID / severity | RCA-003 / S2 (reproduced in the lab by fault F08) |
| Customer-visible impact | h1 (leaf1) cannot reach h3 (leaf2) in the same subnet (VLAN 10, VNI 10010). Local routing (h1 -> h2) and routed traffic across leaves (h1 -> h4) still work; RED/BLUE isolation intact. |
| Environment | FabricX Phase 6, FRR 10.2.1, EVPN symmetric IRB; leaf2 had `route-target both 65002:99999` on VNI 10010 |
| Data collected | `artifacts/runs/*_F08/` (baseline, during, after, diagnosis, timeline), blind drill `experiments/E9/results/` |

## Timeline (from `timeline.json` of one run)
Inject at t0; state observed 18 s later (settle time); diagnosis finished 31 s after inject; restore right after; validate clean again about 4 s after restore. (Exact timestamps: `timeline.json` in the bundle.)

## Symptom matrix
| Check | Result |
|---|---|
| h1 -> h3 (same subnet, other leaf, L2VNI 10010) | **FAIL** |
| h1 -> h2 (local routing) | ok |
| h1 -> h4 (routed over L3VNI 50001) | ok |
| h1 -> h5 (isolation) | isolated, as it should be |
| `fabricx validate` | passes BGP/BFD/ECMP/MTU; EVPN routes are still *present* |

## Analysis
1. Underlay fine (all links, BGP, BFD, loopback reachability): lower layers ruled out.
2. EVPN routes exist for VNI 10010 on both leaves, but the Type-2/3 routes are not *imported* into the bridge: the MAC of h3 is not in leaf1's FDB.
3. `show bgp l2vpn evpn vni 10010` on each leaf compares the route-targets: leaf1 imports `65001:10010`, leaf2 exports `65002:99999`, and vice versa. In this fabric FRR matches auto-derived eBGP route-targets on the VNI part, so `99999` never matches `10010`.

## Root cause
Leaf2 carries an explicit route-target `65002:99999` for VNI 10010 that no other leaf imports, so EVPN routes for that VNI are advertised but never imported across leaves.

## First command that reveals it
`vtysh -c "show bgp l2vpn evpn vni 10010 json"` on both leaves and compare `importRts` / `exportRts`.

## Fix and verification
`no route-target both 65002:99999` under the VNI on leaf2 (restores auto-derived RTs). The fault runner restores it and re-checks: validate clean, drift clean.

## Prevention
Rule `rt-mismatch` in `fabricx diagnose` (compares the VNI part of RTs across leaves; caught in both blind-drill passes); `fabricx drift` also flags the explicit line because it is not in the inventory.

## Limitations
Matching on the VNI part is how FRR behaves for auto RTs over eBGP; other NOSes or explicit-RT designs compare the full RT. The lab has only three leaves.
