# RCA-001 — "Bulk transfers stall between racks; ping works"

| Field | Content |
|---|---|
| ID / severity | RCA-001 / S2 (reproduced in the lab, not a customer incident) |
| Customer-visible impact | Hosts on different leaves (h1 -> h3, same tenant): small pings and TCP connects succeed, bulk TCP (iperf3) transfers 0 bit/s. Other paths fine. |
| Environment | FabricX Phase 4; FRR 10.2.1 containers, Containerlab 0.83.0, arm64; VXLAN `df set`, host MTU 1500, fabric MTU 9100 except one link at 1500 |
| Timeline | Mismatch injected (link MTU 1500) -> DF ping sweep -> iperf3 -> ICMP drop added. All timestamps are inside `experiments/E3/results/*.json` runs |
| Data collected | `experiments/E3/results/{baseline,local,remote,remote_icmp_blocked}.json` (max DF payload, iperf3 output, host ping evidence) |

## Symptom matrix
| Check | Result |
|---|---|
| `ping h3` (64 B) | OK |
| TCP handshake / small transfers | OK |
| `ping -M do -s 1400` | OK |
| `ping -M do -s 1430` | fails |
| `iperf3 -c h3` | **0 bit/s**, only a few retransmits |

## Analysis (hypotheses and what ruled them out)
1. *Routing / EVPN problem?* No: `fabricx validate` passes (BGP, BFD, ECMP, EVPN routes all fine) and small packets cross the same path.
2. *Packet loss on a link?* No: loss is size-dependent, not random.
3. *Size-dependent drop.* A DF ping size sweep (bisect) found the exact boundary: **largest working payload 1422 bytes**. Theory for a 1500-byte link: 1500 - 50 (outer IP 20 + UDP 8 + VXLAN 8 + inner Ethernet 14) - 28 (inner IP + ICMP) = 1422. Exact match, so the underlay path MTU is 1500, not 9100.
4. *Why does TCP stall rather than adapt?* Path MTU discovery needs the router at the narrow link to send ICMP "fragmentation needed" back. With ICMP working (scenarios `local`, `remote`), the Linux VTEP learned MTU 1450 and TCP ran at about 5 Gbit/s. With that ICMP dropped (`remote_icmp_blocked`), nothing tells the sender, full-size segments (1500 B inner -> 1550 B outer, DF set) vanish, and TCP retries forever: a **PMTUD black hole**.

## Root cause
One underlay link had MTU 1500 instead of 9100, so VXLAN-encapsulated full-size frames (1550 B, DF set) could not cross it, and the ICMP "fragmentation needed" message that would let TCP adapt did not reach the sender.

## First command that reveals it
From the host: `ping -M do -s 1430 <dst>` (size sweep). On the switches: `ip -j link` MTU per fabric link, which `fabricx validate` checks (`underlay-mtu` finding).

## Fix and verification
Restore the link to 9100 (the generated config value). Verified: max DF payload back to 1472, iperf3 back to normal (baseline row in E3). Quick test on a healthy fabric: `make test`.

## Prevention
- Validator rule `underlay-mtu` (`src/fabricx/validators.py`) flags any fabric interface whose MTU differs from the inventory; unit test `test_mtu_mismatch_detected`.
- A DF-ping size check belongs in the functional suite for real deployments (planned for Phase 5).

## Limitations of this reproduction
The ICMP suppression is emulated with a `tc` filter. Linux VTEPs act on ICMP; some hardware VTEPs do not, so on a real PowerSwitch the failure might appear even with ICMP permitted. The 1500/9100 numbers are lab values, not a customer's.
