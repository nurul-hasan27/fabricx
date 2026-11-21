# Known limitations (what this lab does NOT prove)

| Real hardware does | FabricX does | Consequence |
|---|---|---|
| Forwards in an ASIC (TCAM, hardware ECMP hash) | The Linux kernel forwards | No throughput/latency claims. ECMP hash behaviour is the kernel's, not an ASIC's |
| Detects link loss in microseconds via PHY | veth carrier changes instantly on both ends | Carrier-loss failover looks unrealistically good; gray failure (E1) is the realistic case |
| Has dedicated control-plane CPU | All nodes share one VM's CPUs | Timings are noisy; we report min/median/max and the probe resolution (about 3-9 ms) |
| Has PFC, shared buffers, optics, FEC | None of these | Lossless Ethernet is studied/audited, not demonstrated |
| Many ASICs do not generate/propagate ICMP frag-needed for VXLAN | Linux does | MTU black-hole behaviour in the lab may differ from a given switch (see E3) |
| Scales to hundreds of switches | 5 switches, 5 hosts | Scale is reasoned about, not demonstrated |
| SONiC / real SAI / platform layer | FRR on Linux (SONiC comes in Phase 7, container only) | Nothing here says anything about Dell PowerSwitch hardware |

Honesty tiers used in this repo: BUILT+MEASURED, BUILT, EMULATED, STUDIED, OUT OF SCOPE (see `docs/blueprint_v2.html` section 4).
