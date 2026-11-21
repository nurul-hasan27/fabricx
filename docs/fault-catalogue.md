# Fault catalogue (generated from src/fabricx/faults/catalogue.py)

Every fault runs only inside lab containers, has `inject` and `restore`, and is exercised by `fabricx run-fault <ID>` which writes an evidence bundle under `artifacts/runs/`.

| ID | Fault | Layer | How it is injected | Customer symptom (hypothesis) | First evidence | Diagnose cause key |
|---|---|---|---|---|---|---|
| F01 | Leaf-spine link down | L1 links | ip link set eth1 down on leaf1 | Brief loss, then traffic uses the other spine; fabric degraded | ip -j link on leaf1 (eth1 DOWN); show bfd peers | `link-down` |
| F02 | Gray failure (both directions) | L1 links | tc netem loss 100% on both ends of leaf1-spine1, link stays UP | Link looks up but carries nothing; BGP/BFD drop; traffic reroutes after detection | tc -s qdisc on the link ends; BFD down while interface UP | `gray-failure` |
| F03 | Unidirectional loss | L1 links | netem loss 100% only on leaf1's transmit side of leaf1-spine1 | One direction dead; sessions drop; half-working link | tc -s qdisc drops on one end only | `unidirectional-loss` |
| F04 | Lossy link (2%) | L1 links | netem loss 2% on leaf1 transmit side of leaf1-spine1 | Slow applications; nothing is 'down' | tc -s qdisc dropped counter rising on the link | `lossy-link` |
| F05 | Underlay MTU 1500 on one link | Underlay MTU | ip link set mtu 1500 on both ends of leaf1-spine1 | Pings work, large transfers on flows via that link stall | ip -j link (mtu) on the fabric interfaces; DF ping size sweep | `underlay-mtu` |
| F06 | BGP ASN mismatch | BGP sessions | spine1 expects AS 65999 from leaf2 | leaf2 loses one spine; fabric degraded, no outage | show bgp neighbors <leaf2 ip> (Bad Peer AS) | `bgp-asn-mismatch` |
| F07 | Loopback not advertised | VTEP reachability | leaf3 stops advertising its /32 loopback | leaf3's VTEP is unreachable; BLUE hosts cut off from the fabric | ip route show <leaf3 loopback> on other leaves (empty) | `loopback-not-advertised` |
| F08 | Route-target mismatch on one VNI | EVPN routes | leaf2 uses RT 65002:99999 for VNI 10010 | Same-subnet traffic to/from leaf2 in VLAN 10 fails | show bgp l2vpn evpn vni 10010 (importRts differ between leaves) | `rt-mismatch` |
| F09 | VNI/VLAN mapping mismatch | VNI/VLAN maps | leaf2's VLAN 10 bridge carries VNI 10099 instead of 10010 | Same-subnet traffic to/from leaf2 in VLAN 10 fails | ip -d link show type vxlan (id differs from inventory) | `vni-mismatch` |
| F10 | Missing L3VNI on one leaf | VNI/VLAN maps | leaf2: `vrf RED / no vni 50001` | Routed traffic to/from leaf2 fails; bridged still works | show evpn vni (50001 missing / tenant VRF unknown) | `missing-l3vni` |
| F11 | ECMP hash policy L3-only | Forwarding | leaf1 fib_multipath_hash_policy=0 | Routed multi-flow traffic polarises onto one uplink; no packet loss | sysctl net.ipv4.fib_multipath_hash_policy; per-uplink counters | `ecmp-hash-policy` |
| F12 | Duplicate MAC on two leaves | FDB / ARP | h3 (leaf2) takes h1's MAC (leaf1) | Intermittent reachability for h1/h3 | EVPN Type-2 for the same MAC from two VTEPs (MAC mobility) | `duplicate-mac` |
| F13 | bgpd hung on a spine | BGP sessions | kill -STOP bgpd on spine1 (BFD keeps running) | Sessions via spine1 die after the hold timer; traffic uses spine2 | ps/proc state of bgpd; vtysh show bgp times out | `bgp-daemon-hung` |
| F14 | Anycast gateway MAC mismatch | FDB / ARP | leaf2's br10 has a different MAC than the inventory's anycast MAC | Hosts that move to leaf2 break; routed traffic from VLAN 10 on leaf2 misbehaves | ip link show br10 on every leaf (MAC differs) | `gateway-mac-mismatch` |
