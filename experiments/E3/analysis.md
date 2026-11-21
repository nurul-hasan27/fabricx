# E3 analysis

Method: `method.md`. Raw: `results/*.json`. Host MTU 1500, VXLAN outer DF bit set, one fabric link at 1500 MTU.

| Scenario | Largest DF ping payload that works | iperf3 TCP h1->h3 |
|---|---|---|
| Healthy (all links 9100) | 1472 (the host-MTU maximum; no limit found) | 5256 Mbit/s |
| Bad link = leaf1's own uplink | **1422** | 4895 Mbit/s |
| Bad link = spine -> leaf2 (remote) | **1422** | 5233 Mbit/s |
| Remote bad link **and** ICMP "frag needed" dropped on the way back | **1422** | **0 Mbit/s (stalled)** |

(Throughput numbers are software-forwarding figures and are not a performance claim; TCP retransmit counts are high even in the baseline because of veth queueing, so they are not reported as a result.)

## What the data says
- The threshold is exactly the theory: 1500 - 50 (outer IP 20 + UDP 8 + VXLAN 8 + inner Ethernet 14) - 28 (inner IP+ICMP) = **1422**. Any DF packet whose inner IP packet is over 1450 bytes cannot cross a 1500-byte underlay link.
- **With ICMP working, TCP survives.** The Linux VTEP learns the smaller path MTU from ICMP "fragmentation needed" (host sees `Frag needed and DF set (mtu = 1450)`) and TCP shrinks its segments. Only ping sizes between 1423 and 1472 fail. In the remote case the first large packet is lost before the MTU is learned.
- **With ICMP suppressed, the black hole appears:** small pings and the TCP handshake work, full-size data packets vanish, iperf3 reports 0 bit/s. This is the classic "ping works but transfers stall" escalation. See `docs/rca/RCA-001-mtu-black-hole.md`.

## Limits
- ICMP suppression was emulated with a `tc u32` drop on one spine interface; it stands in for a firewall/ACL/ASIC that does not generate or forward frag-needed. Real platforms vary.
- Linux VTEPs are PMTUD-aware; some hardware VTEPs are not, so the first two rows can look different on real switches.
