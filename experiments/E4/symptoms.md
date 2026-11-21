# E4 / catalogue — what each fault looks like to the customer (generated)

c1 = same subnet across leaves (h1>h3), c2 = local routing (h1>h2), c3 = routed across leaves (h1>h4), c4 = RED to BLUE isolation (breach = reachable).

| Fault | c1 | c2 | c3 | Isolation breached | Hypothesis matched | First evidence |
|---|---|---|---|---|---|---|
| F01 Leaf-spine link down | ok | ok | ok | False | True | ip -j link on leaf1 (eth1 DOWN); show bfd peers |
| F02 Gray failure (both directions) | ok | ok | ok | False | True | tc -s qdisc on the link ends; BFD down while interface UP |
| F03 Unidirectional loss | ok | ok | ok | False | True | tc -s qdisc drops on one end only |
| F04 Lossy link (2%) | ok | ok | ok | False | True | tc -s qdisc dropped counter rising on the link |
| F05 Underlay MTU 1500 on one link | ok | ok | ok | False | True | ip -j link (mtu) on the fabric interfaces; DF ping size sweep |
| F06 BGP ASN mismatch | ok | ok | ok | False | True | show bgp neighbors <leaf2 ip> (Bad Peer AS) |
| F07 Loopback not advertised | ok | ok | ok | False | True | ip route show <leaf3 loopback> on other leaves (empty) |
| F08 Route-target mismatch on one VNI | FAIL | ok | ok | False | True | show bgp l2vpn evpn vni 10010 (importRts differ between leaves) |
| F09 VNI/VLAN mapping mismatch | FAIL | ok | ok | False | True | ip -d link show type vxlan (id differs from inventory) |
| F10 Missing L3VNI on one leaf | ok | ok | ok | False | False | show evpn vni (50001 missing / tenant VRF unknown) |
| F11 ECMP hash policy L3-only | ok | ok | ok | False | True | sysctl net.ipv4.fib_multipath_hash_policy; per-uplink counters |
| F12 Duplicate MAC on two leaves | FAIL | ok | ok | False | False | EVPN Type-2 for the same MAC from two VTEPs (MAC mobility) |
| F13 bgpd hung on a spine | ok | ok | ok | False | True | ps/proc state of bgpd; vtysh show bgp times out |
| F14 Anycast gateway MAC mismatch | ok | ok | ok | False | True | ip link show br10 on every leaf (MAC differs) |
