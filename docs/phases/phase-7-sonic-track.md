# Phase 7 — SONiC track

## The idea in simple words
SONiC is the switch software Dell sells (Dell Enterprise SONiC). Inside a SONiC switch, a route travels like a parcel
through a post office, and every counter has its own notebook (a **Redis database**):

`bgpd` decides → `zebra` keeps the route book and passes it on over **FPM** → `fpmsyncd` writes it into **APPL_DB**
(the "to-do list") → `orchagent` translates it into chip language in **ASIC_DB** → `syncd` hands it to the chip
through **SAI** (the standard chip API). Settings live in **CONFIG_DB**, live state in **STATE_DB**, counters in
**COUNTERS_DB**. In the virtual SONiC (**SONiC-VS**) the "chip" is a software library (**vslib**) that programs the
Linux kernel.

Phase 7 did four things:
1. put a **real SONiC switch** in the fabric as leaf3, talking BGP + BFD to our FRR spines;
2. follow one route and one interface through every database (**experiment E8**);
3. teach our engine to talk to SONiC (adapter, tracer, NOS-aware checks);
4. build a **lossless-QoS auditor** and test it against the real switch's CONFIG_DB.

## Where it runs (and why)
SONiC-VS is built for x86 only; the Mac is ARM. You chose **GitHub Actions** (free x86 machines), so the repo became
public (`nurul-hasan27/fabricx`) and SONiC runs there through a manual workflow (`.github/workflows/sonic.yml`,
`gh workflow run sonic.yml -f mode=fabric`). Azure was not used.

Image: the **official** `docker-sonic-vs` from SONiC's own build pipeline, pinned to branch `202505`, build `1238524`
(228 MB download, 851 MB loaded, sha256 in `artifacts/phase7/sonic-image.txt`). `scripts/sonic_image.sh` fetches it.

## Step by step
1. **Probe first, build second.** A tiny lab (one SONiC + one FRR node) and `scripts/sonic_probe.sh` recorded what the
   image really contains (`artifacts/phase7/sonic-probe.txt`): FRR 10.3 inside, `zebra` with the FPM module, `bgpd`
   present but not started, `bfdd` present with no service for it, **no config daemon** (so BGP is configured with
   `vtysh`), **no gNMI/telemetry service**, port names from `lanemap.ini` (`eth1` → `Ethernet0`, `eth2` → `Ethernet4`).
2. **Inventory variant** `inventory/variants/sonic-leaf3.yaml`: leaf3 has `nos: sonic-vs`; the BLUE tenant and h5 are
   left out (the SONiC leaf is underlay-only in this phase). The model refuses a SONiC leaf with hosts, a non-eBGP
   underlay, or no image.
3. **Generated bring-up** `templates/sonic-setup.sh.j2` — the SONiC way: write ports, /31 addresses and Loopback0 into
   **CONFIG_DB**; the `*mgrd` daemons turn them into kernel/ASIC state; wait for the image's own boot (`start.sh`) to
   finish; start `bgpd` and `bfdd`; load the FRR config generated from the **same template** as the other leaves
   (minus the address lines).
4. **Engine made NOS-aware** (only where SONiC really differs): MTU is checked on the routed port (`Ethernet0`), the
   loopback lives on `Loopback0`, six `zebra` lines the image adds itself are not drift, the CLI and tests follow
   `FABRICX_INVENTORY` so the same suite runs against the variant.
5. **Adapter + tracer** `src/fabricx/adapters/sonic.py`: bgpd → zebra → APPL_DB (incl. the staging key) → ASIC_DB route →
   ECMP group → members → next hops; and one port through CONFIG/APPL/STATE/ASIC/COUNTERS DB.
6. **QoS auditor** `src/fabricx/audit/qos_lossless.py` (`fabricx audit-qos`): checks that DSCP maps, traffic classes,
   priority groups, queues, buffers, ECN/WRED and the PFC watchdog agree for each lossless priority.
7. **E8** `experiments/E8/run_e8.py` — results and analysis in `experiments/E8/`.

## What broke on the way (and the real cause)
| # | Symptom | Cause | Fix |
|---|---|---|---|
| S1 | SONiC leaf: BGP stuck `Active`, spines show it `Idle` | `bfdd` could not start (`failed to mkdir /var/run/frr`), and FRR keeps BGP down while BFD is down | start FRR daemons only after the image's boot created the directory |
| S2 | `bgpd` exited right after start | started before the image's `start.sh` had created `/var/run/frr` and started `zebra` | wait for `start.sh` exited + `zebra` running (not just "ports ready") |
| S3 | validator: `eth1 mtu 9122` | in SONiC-VS the wire is 22 bytes bigger than the port; ASIC_DB shows `SAI_PORT_ATTR_MTU 9122` for a 9100 port | MTU checked on `Ethernet0` |
| S4 | drift on leaf3 | six `zebra` lines from the image (`fpm address 127.0.0.1`, …) | explicit SONiC ignore list |
| S5 | drift test compared SONiC with the plain inventory | CLI defaults ignored `FABRICX_INVENTORY` | CLI follows it like `model.load()` |

## What CI taught us about the FRR fabric itself
Running CI for the first time (on x86) found bugs the Mac never showed:

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `make fabric-up` failed | CI used the system Python; the Makefile expects `.venv/` | workflow creates `.venv` |
| 2 | 19-minute hang | `runner.sh` could not kill a `sudo` (root) child; Python waited on its pipes forever | timeout enforced **inside** the sudo process (`timeout -k`) + job and per-test limits |
| 3 | pcap test saw VNI 10020 on a routed ping | background IPv6 router solicitations, not the ping | test inspects only the ping packets |
| 4 | no Type-5 routes, fabric never healthy | **FRR start-up race**: if bgpd gets zebra's L3VNI announcement before it knows the VRF's id, it creates a second, automatic BGP instance that owns the L3VNI; the configured one never originates Type-5 | three layers: kernel plumbing before FRR starts; BGP VRF block before `vrf/vni` in frr.conf; **check-and-repair** after start-up (below) |
| 5 | `br10: Device does not exist` | `ports.sh` ran before the start command had built the bridges | `ports.sh` waits for each bridge |

**The check-and-repair (honest label: a workaround around FRR timing).** Ordering alone took CI from about 1 in 2 failing
to 2 failures in 16 lab runs — better, not fixed. So each leaf now checks after start-up that it originates a Type-5 for
each of its own subnets (`show bgp l2vpn evpn route type prefix self-originate`); if not, it withdraws and re-adds the
L3VNI and logs it in `/var/log/fabricx-heal.log`.
- **Reproduced on purpose:** configuring `vrf BLUE / vni 50002` before `router bgp 65003 vrf BLUE` on a running leaf gives
  exactly the CI failure (two `Instance BLUE`, no Type-5, `validate` 3 findings). Running the repair: "repaired",
  `validate` PASS, no drift. The empty automatic instance stays behind, harmless.
- **Seen in the wild:** in SONiC run 44923272077 the race hit leaf2; the repair logged "repaired" and the suite passed.
- CI stability after the repair: see the table at the end.

Simple version: two workers (zebra and bgpd) start at the same moment and sometimes one shouts "here is your room
number!" before the other has opened the door. Now, after start-up, someone walks past each room and checks the light is on.

## Results
- **SONiC leaf in the fabric:** BGP Established and BFD up with both FRR spines; the FRR leaves get two ECMP next hops to
  the SONiC leaf's loopback and vice versa. Our existing lab suite against the variant: **41 passed, 1 skipped**
  (the cross-VRF test, which needs two tenants); `fabricx validate` PASS; `fabricx drift` no drift
  (`artifacts/phase7/`).
- **E8** (`experiments/E8/analysis.md`): the full chain with real keys; ECMP = one SAI next-hop group with one member per
  path; a frozen `orchagent` leaves routes in `_ROUTE_TABLE` / `ROUTE_TABLE_KEY_SET` while zebra still says
  `offloaded=True`; announce → ASIC_DB median 0.219 s (N=10, resolution 0.053 s, orchagent's own step below resolution).
- **QoS auditor vs the real switch:** image default = nothing to audit; PFC enabled alone = SONiC programs it silently
  (PFC bitmask 24) while the auditor reports 10 findings; complete config = no findings and orchagent programs WRED on
  queue 3 and the lossless buffer on priority group 3.

## Honest status (tiers)
| Item | Tier |
|---|---|
| SONiC-VS leaf in the fabric (underlay: BGP, BFD, ECMP) | BUILT + MEASURED (CI) |
| E8 DB trace, orchagent fault, timings | BUILT + MEASURED (CI, N=10, vslib not a real ASIC) |
| QoS/lossless auditor | BUILT (static analysis), checked against a real SONiC CONFIG_DB |
| EVPN/VXLAN overlay on the SONiC leaf | NOT DONE (leaf3 is underlay-only in the variant) |
| gNMI streaming from SONiC | NOT POSSIBLE with this image (no gNMI/telemetry service; probe) |
| SONiC-VM (vrnetlab, KVM) | NOT DONE (would need Azure with nested virtualisation) |
| PFC/lossless behaviour | STUDIED/audited only — veth has no PFC |

## How to explain it in an interview
"I swapped one leaf for the official SONiC-VS image and let it peer with FRR spines over BGP with BFD. Then I traced a route
from bgpd through zebra, FPM and fpmsyncd into APPL_DB and through orchagent into ASIC_DB, where ECMP is a SAI next-hop
group with a member per path. Freezing orchagent showed that the route stays in the producer staging key and
`ROUTE_TABLE_KEY_SET` — so a growing key set is the fingerprint of a stuck orchagent, and zebra's offload flag alone did not
prove programming. I also built a lossless-QoS auditor and showed that SONiC silently accepts PFC without buffers, ECN or
watchdog, while the auditor flags exactly those gaps. Along the way CI exposed an FRR start-up race in EVPN that I
reproduced on purpose and handled with a verified check-and-repair."

## CI stability after the check-and-repair
Same commit (`7a60a98`), main CI run 44923262130, 6 attempts, plus SONiC run 44923272077:

| Run | Result | Repair log |
|---|---|---|
| CI attempt 1 | pass | leaf2: Type-5 missing after 20 s → repaired |
| CI attempts 2–5 | pass | all leaves: own Type-5 present after ~1–2 s |
| CI attempt 6 | pass | leaf3: Type-5 missing after 20 s → repaired |
| SONiC run | pass (41 passed, 1 skipped) | leaf2: missing → repaired |

So the race still happens — in 3 of 20 FRR leaf start-ups here — and every time the repair caught it and the run passed
(7 of 7). Before the repair, the same race failed 2 of 16 CI lab runs after the config-order fix, and about 1 in 2 before it.
Seven passes is a small sample: "no failure seen in 7 with the repair", not "can never fail".
