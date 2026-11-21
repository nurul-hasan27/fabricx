# Packet walkthrough (from real captures)

Source files: `artifacts/phase3/leaf2-vxlan.pcap` (raw), `leaf2-vxlan.txt` (decoded). Captured on leaf2 with
`scripts/capture_vxlan.sh` while h1 pinged h3 (same subnet) and h4 (different subnet).

## Case A: h1 -> h3 (same subnet, different leaf) = BRIDGING over L2VNI 10010
```
10.0.0.11.53586 > 10.0.0.12.4789: VXLAN, flags [I] (0x08), vni 10010
  aa:c1:ab:a3:08:c4 > aa:c1:ab:6c:9b:ed  10.10.10.101 > 10.10.10.103  ICMP echo request  ttl 64
```
- **Outer:** source = leaf1 loopback (VTEP), destination = leaf2 loopback (VTEP), UDP port **4789**. The spines only read this part.
- **VXLAN header:** flag `I` = "VNI is valid", **vni 10010** = VLAN 10's segment number.
- **Inner:** the original Ethernet frame with the *hosts'* own MAC addresses. TTL is still 64: nothing routed it.

## Case B: h1 -> h4 (different subnet, different leaf) = ROUTING over L3VNI 50001 (symmetric IRB)
```
10.0.0.11.50354 > 10.0.0.12.4789: VXLAN, flags [I] (0x08), vni 50001
  e6:56:81:e1:50:97 > fe:83:1f:17:9f:83  10.10.10.101 > 10.20.20.104  ICMP echo request  ttl 63
```
- The VNI is **50001** (the tenant RED's routing VNI), not 10020 (h4's VLAN). That is what "symmetric" means: ingress leaf routes into the tenant VNI, egress leaf routes out of it.
- The inner MACs are the two leaves' **router MACs** (carried in EVPN), not the hosts' MACs.
- **TTL 63**: the packet was routed once (by leaf1). Leaf2 routes it again on the way out; that last hop is not visible on the wire.

## What the spines see
Only the outer IP/UDP header. They do ordinary ECMP routing on loopback-to-loopback traffic and never learn any host or VNI.

## Control-plane view (same run)
- `leaf1-evpn-routes.json`, `leaf2-evpn-routes.json`: Type-2 (MAC and MAC+IP), Type-3 (one per VNI per VTEP), Type-5 (one per subnet).
- `leaf1-vrf-RED-routes.txt`: shows `10.20.20.104/32 ... via 10.0.0.12, br50001 onlink`, the remote host route reaching h4 through the L3VNI.
