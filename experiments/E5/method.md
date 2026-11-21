# E5 — Does the underlay protocol matter for failure recovery?

Same fault and probe as E1 (1 ms probe h1 -> h3; fail the leaf1 uplink the flow uses: carrier loss or a gray failure), with the underlay
**generated from the inventory** as (a) eBGP (E1 data), (b) OSPF area 0 + iBGP EVPN over loopbacks, (c) IS-IS level-2 + iBGP EVPN over
loopbacks. In (b)/(c) the spines are route reflectors. Variants: `inventory/variants/{ospf,isis}.yaml` (one line differs: `underlay.protocol`).
BFD (300 ms x 3) on the fabric links for the "BFD" rows; for "no BFD" rows it is removed at run time with vtysh. IGP timers: OSPF hello 10 s / dead 40 s,
IS-IS hello 10 s with multiplier 4 (hold 40 s, from `igp_dead_s`). N = 10 per
cell (3 for the slow no-BFD rows). `aggregate.py` includes the trailing-gap correction described in E1.
