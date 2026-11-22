# Known limitations (what this lab does NOT prove)

Honesty tiers used in this repo: **BUILT + MEASURED** (working and quantified, evidence stored), **BUILT** (working,
functionally verified), **EMULATED** (a software stand-in for a hardware behaviour), **STUDIED** (design notes / test
plan, nothing run), **OUT OF SCOPE**, **NOT DONE** (planned but not built).

## Hardware vs this lab
| Real hardware does | FabricX does | Consequence |
|---|---|---|
| Forwards in an ASIC (TCAM, hardware ECMP hash) | The Linux kernel forwards | No throughput/latency claims about switches. ECMP hashing is the kernel's (E2), not an ASIC's |
| Detects link loss in microseconds via the PHY | veth carrier changes instantly on both ends | Carrier-loss failover looks unrealistically good; gray failure (E1) is the realistic case |
| Has a dedicated control-plane CPU | All nodes share one VM's CPUs | Timings are noisy; results report min/median/max and the probe resolution (about 3–9 ms) |
| Has PFC, shared buffers, headroom, optics, FEC | None of these | Lossless Ethernet is audited (QoS auditor) and studied (RoCE test plan), not demonstrated |
| Many ASICs do not generate/propagate ICMP frag-needed for VXLAN | Linux does | MTU black-hole behaviour may differ on a given switch (E3) |
| Scales to hundreds of switches | 5 switches, 5 hosts | Scale is reasoned about, not demonstrated |

## By area
| Area | What the lab does | What it cannot say |
|---|---|---|
| SONiC | SONiC-VS container on x86 CI: real SONiC databases, orchagent and syncd, but the SAI is vslib programming the Linux kernel; leaf3 underlay only (BGP, BFD, ECMP) | anything about Dell PowerSwitch hardware, a real ASIC's tables, timing or SAI behaviour; EVPN on SONiC (NOT DONE) |
| gNMI | not available | the pinned SONiC-VS image has no gNMI service (Phase 7 probe); telemetry uses an FRR exporter instead |
| FRR EVPN start-up | a check-and-repair after start-up handles an FRR race (duplicate BGP VRF instance, no Type-5 routes) | it is a workaround for FRR timing, not a fix inside FRR; it fired in 3 of 20 CI leaf start-ups when measured |
| Congestion (E6) | Linux TBF + pfifo/RED on a veth port at 100 Mbit/s, TCP cubic/DCTCP, 4 senders | switch shared-buffer behaviour, PFC, DCQCN in NICs, line-rate numbers |
| Telemetry | one `docker exec` per switch per 5 s Prometheus scrape | sub-second events (a millisecond failover is invisible in the graphs) |
| Mac VM shaping | HTB cannot hold its rate in the OrbStack VM; TBF used | whether HTB is fine on bare metal (not tested) |
| Blind drill (E9) | 14/14 localised on pass 2 | the rules were tuned on the same catalogue after pass 1 (12/14); a new fault class is the real test |
| Experiments | N = 3–10 per scenario (stated in each result), one machine | small samples; no confidence intervals claimed |

## Reproducibility: what the Phase 9 clean-room run did and did not cover
| Covered | Not covered |
|---|---|
| Fresh `git clone` on the Mac → `make setup`, `make up`, `make test`, `make resilience` all green (`artifacts/phase9/`) | A **brand-new** arm64 VM: the Mac rerun reused the existing `fabricx-lab` VM (Docker, Containerlab and the FRR image already present; `vm_setup.sh` found everything installed) |
| The host image was rebuilt by `make setup` | It came from Docker's build cache (same image id as Phase 4); a no-cache rebuild today would pull newer Alpine packages |
| Fresh x86 machine on every CI push, running the README's commands (`make vm-setup`/`setup`/`up`/`test`) | Intel Macs and other Linux distributions (only Ubuntu 24.04 tested) |
| Pinned: FRR 10.2.1, Containerlab 0.83.0, SONiC-VS build 1238524, Python tool versions (`pyproject.toml` `dev` extra) | Runtime Python libraries (pydantic, jinja2, typer, pyyaml) are not pinned; base images are pinned by tag, digests are recorded in `versions.lock.md` |
