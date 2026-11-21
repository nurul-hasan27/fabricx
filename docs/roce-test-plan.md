# How I would validate RoCEv2 on a real fabric (test plan)

**Tier: STUDIED.** Nothing in this plan was run: FabricX has no RDMA NICs and veth has no PFC. It is the plan I would
execute on real PowerSwitch-class switches running SONiC with RoCE-capable NICs. It deliberately contains **no target
numbers**: pass thresholds come from the vendor's RoCE design guide and from the baseline measured in step 3, not from
this document.

What FabricX already contributes: the lossless-config **auditor** (`fabricx audit-qos`, step 1), the **E6** congestion
study (how ECN marking and a DCTCP-style sender keep a queue short, the TCP analogue of DCQCN), the **E8** knowledge of
where config turns into ASIC state, and the fault/evidence discipline (steps 6–7).

## 0. What "working" means for RoCE
RDMA over Converged Ethernet v2 (UDP 4791) assumes the network almost never drops its packets. Two mechanisms provide
that, and both must agree end to end:
- **PFC** (Priority Flow Control, 802.1Qbb): a switch tells its neighbour to pause *one priority* when that priority's
  ingress buffer reaches its xoff threshold. Makes one traffic class lossless; risk: pause spreading, deadlock.
- **ECN + DCQCN**: switches mark packets before buffers fill; the receiver NIC sends CNPs (congestion notification
  packets) and the sender NIC slows that flow down. Keeps PFC as the last resort, not the normal case.

## 1. Configuration consistency (before any traffic)
On every switch and NIC, for the RoCE priority (often priority 3) and the CNP priority:
| Check | Switch (SONiC) | NIC |
|---|---|---|
| DSCP trust and DSCP → TC map, same on all hops | `DSCP_TO_TC_MAP`, `PORT_QOS_MAP` | NIC trust mode = DSCP, RoCE DSCP value |
| TC → queue and TC → priority group | `TC_TO_QUEUE_MAP`, `TC_TO_PRIORITY_GROUP_MAP` | — |
| PFC enabled on exactly the RoCE priority, on every port in the path | `PORT_QOS_MAP.pfc_enable` | PFC enabled on the same priority |
| Lossless ingress buffer (xon/xoff, headroom for cable length and speed) | `BUFFER_PG`, `BUFFER_PROFILE`, `CABLE_LENGTH` | — |
| ECN/WRED on the lossless queue, thresholds below the PFC xoff point | `WRED_PROFILE` + `QUEUE.wred_profile` | DCQCN enabled (reaction and notification points) |
| PFC watchdog | `PFC_WD` | — |
| CNPs in their own (high) priority | scheduler / DSCP map | CNP DSCP / priority |

Tooling: `fabricx audit-qos <config_db.json>` on every switch (QOS-001..009). E8 showed SONiC accepts a half-done
lossless config silently, so this step is a gate, not a formality. Also confirm with `show interfaces status`, `show
priority-group`/`show buffer` and ASIC_DB that the config was programmed (PFC bitmask, queue WRED, PG profile).

## 2. Functional
- RDMA connection between every NIC pair (`ib_write_bw`/`ib_send_bw` from **perftest**, short runs).
- Capture shows RoCEv2 on UDP 4791 with the right DSCP and ECT bits, on the expected priority.
- Counters move on the intended queue only: `show queue counters`, `show pfc counters`.

## 3. Baseline performance (no congestion)
- perftest bandwidth (`ib_write_bw`, `ib_read_bw`, `ib_send_bw`) and latency (`ib_write_lat`, `ib_send_lat`) between
  pairs: same leaf, across the spine, all ECMP paths.
- **NCCL tests** (`all_reduce_perf`, `all_gather_perf`) across all GPUs/hosts; record bus bandwidth per message size.
- This baseline *defines* later pass criteria ("within X % of baseline", X agreed with the customer/vendor guide).

## 4. Congestion (where ECN/DCQCN and PFC earn their keep)
| Test | Load | Watch | Healthy looks like |
|---|---|---|---|
| Incast N→1 (as E6, with RDMA) | perftest from N senders to 1 receiver | ECN-marked packets, CNPs sent/received, PFC pause frames, queue watermarks, drops | marks and CNPs rise, PFC rare, **zero drops** on the lossless priority, fair share |
| Many-to-many (all-reduce) | NCCL tests at large message sizes | same, per port | bus bandwidth near baseline, no persistent pauses |
| Mixed lossy + lossless | TCP bulk on another class + RoCE | lossy-class drops vs lossless class | lossless unaffected, lossy class takes the drops |
| ECN threshold sweep | repeat incast with different WRED min/max | marks vs pauses vs latency | marking starts before xoff; pick thresholds from data |

## 5. PFC safety
- **PFC watchdog:** make a receiver stop draining (e.g. pause its NIC queue) → a PFC storm toward the switch; the
  watchdog must detect it and apply its action (drop/forward) on that queue only, then restore (`pfcwd show stats`).
- **Pause propagation:** confirm pauses do not spread to unrelated ports/priorities (head-of-line blocking).
- **Headroom:** longest cable + highest speed: no drops on the lossless priority at the moment of pause.

## 6. Failures during a workload (FabricX's fault discipline)
Run NCCL all-reduce continuously and inject, one at a time: link down, gray failure, spine reboot, BGP flap, a
mis-set DSCP map on one hop, PFC disabled on one hop. For each: outage/throughput dip (NCCL and perftest),
detection (BFD/BGP/counters), and that the lossless class returns to zero drops after recovery.

## 7. Evidence per test (same bundle format as FabricX)
Before/during/after snapshots of: switch CONFIG_DB/ASIC state, `show pfc counters`, queue and PG watermarks, ECN
mark counters, NIC counters (CNPs sent/handled, out-of-sequence, retransmissions), perftest/NCCL output, timestamps.
Every number in the report comes from one of these files.

## What would be different from FabricX
Real ASIC buffers and thresholds, real PFC frames, real NIC congestion control (DCQCN in hardware), line-rate traffic.
FabricX shows the *mechanisms* (queue build-up, ECN marking, a DCTCP sender reacting) and the *config logic*; it
does not show any of those hardware behaviours.
