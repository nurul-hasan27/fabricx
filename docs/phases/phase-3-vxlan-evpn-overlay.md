# Phase 3 — VXLAN-EVPN overlay (envelopes inside envelopes)

## The goal, in kid words
The staircases (spines) only know how to carry notes between floor monitors (leaves). But classroom kids on different floors want to talk as if they sat in the same room. So the monitor puts the kid's note inside a **bigger envelope** addressed to the other floor's monitor (**VXLAN**). A **noticeboard** (**EVPN**, carried by BGP) tells every monitor who sits where, so nobody has to shout in the hallway to find someone.

## What I did, step by step
1. **Described the overlay in the inventory:** one `anycast_gw_mac`. VLANs, VNIs, VRFs were already there from Phase 1. The model works out which VLANs/VRFs each leaf needs from the hosts plugged into it (`leaf_vlans`, `leaf_vrfs`).
2. **Wrote a Linux "plumbing" script template** (`templates/leaf-setup.sh.j2`) that runs on each leaf after the links exist. For every VLAN it creates a **bridge** (`br10`), a **VXLAN device** (`vx10010`, `nolearning`, source = the leaf's loopback), gives the bridge the **anycast gateway** IP and MAC, and puts the host's port into the bridge. For every VRF it creates a **VRF** (a separate routing table), plus a bridge + VXLAN device for the **L3VNI**.
3. **Extended the FRR config template:** turned on the `l2vpn evpn` address family between leaves and spines; leaves get `advertise-all-vni`; each VRF gets its own BGP instance that advertises the tenant subnets (Type-5) and its L3VNI.
4. **Deployed and debugged in small steps.** First same-subnet (h1->h3), then routed (h1->h4), then isolation (h1->h5). Three real bugs fixed (listed below).
5. **Captured packets** on leaf2 with tcpdump while pinging, and saved the pcap and the decoded text.
6. **Wrote 11 lab tests** and ran the whole suite: 52 passed (13 unit + 39 lab). Wrote `docs/packet-walkthrough.md` from the captures.

## Key terms
- **VXLAN:** wraps an Ethernet frame in UDP (port 4789) so a Layer-2 network can stretch over a routed Layer-3 network. Adds 50 bytes, which is why the fabric MTU is 9100.
- **VTEP:** the device that wraps/unwraps (here: each leaf, using its loopback IP).
- **VNI:** the VXLAN segment number, like a room number on the envelope. **L2VNI** = a bridged subnet (VLAN 10 = 10010). **L3VNI** = a tenant's routing segment (RED = 50001).
- **EVPN:** BGP carrying "who is where". Route types seen: **Type-2** (a host's MAC, and MAC+IP), **Type-3** (this VTEP is part of VNI X, used to flood broadcasts), **Type-5** (a whole IP subnet).
- **Anycast gateway:** every leaf owns the same gateway IP and MAC (10.x.x.1 / 02:fa:b0:00:00:01), so a kid's gateway is always on its own floor.
- **Symmetric IRB:** the first leaf routes the packet into the tenant's L3VNI; the last leaf routes it out. Only the VNIs of local hosts are needed on each leaf.
- **VRF:** separate routing table per tenant. RED and BLUE can't see each other, which proves segmentation.
- **Route-target (RT):** a label saying which VRF/VNI should import a route. FRR auto-derived working RTs here.
- **Next-hop preservation:** EVPN routes must keep the originating leaf (VTEP) as next hop when the spine passes them on, otherwise tunnels would point at the spine. FRR 10.2.1 does this by default for EVPN over eBGP. (I originally added `nexthop-unchanged` on the spines believing it was required; Phase 5 testing showed it is not, so it was removed.)
- **Silent host:** a host that never sent anything is unknown to EVPN until it does.

## Results (real)
- h1->h3 (same subnet, other leaf): works, VNI 10010, TTL 64, inner = hosts' MACs.
- h1->h2 (other subnet, same leaf): works, local routing.
- h1->h4 (other subnet, other leaf): works, VNI **50001**, TTL 63, inner = leaves' router MACs. VNI 10020 never appears.
- h1<->h5 (different VRF): fails both ways, as required.
- Every leaf has Type-2 for all 5 hosts, Type-3 from every VTEP for each VNI it carries, and Type-5 for all 3 subnets. Anycast MAC is identical on all leaves.

## What went wrong / lessons
1. **VRF name mismatch:** I named the Linux VRF `vrfRED`, FRR config said `RED`; FRR showed the L3VNI's tenant as "Unknown". Names must match exactly.
2. **Host default route failed at start:** the leaf port wasn't up yet. Hosts now retry in the background.
3. **Possible duplicate RDs for Type-5:** FRR picked the anycast gateway IP as the VRF's router-id on every leaf. I set the router-id to the loopback so route distinguishers differ.
4. **Silent host:** the first h1->h4 ping failed until h4 had sent traffic. This is how EVPN works, not a bug. Tests prime every host first.
5. **My own test wait-loop** looked for a word that never appears and hung; I replaced it with direct checks.

## How to explain it in an interview
"I built symmetric IRB EVPN-VXLAN on Linux + FRR. I proved it from the wire: bridged traffic carries the L2VNI, routed traffic carries the tenant L3VNI with TTL decremented once, and the destination L2VNI never appears. Spines forward only the outer header. I also hit and fixed the common pitfalls: VRF naming, RD uniqueness, and silent-host learning."
