# Phase 7 - SONiC track (part A: done on the Mac; part B: waiting for an x86 machine)

## The idea in simple words
SONiC is the switch software Dell sells. Inside it, a route travels like a parcel through a post office:
`bgpd` (decides) -> `zebra` -> `fpmsyncd` -> **APPL_DB** (Redis "to-do list") -> `orchagent` -> **ASIC_DB**
(the same list in chip language) -> `syncd` -> the chip. In the virtual version the "chip" is the Linux kernel.
Phase 7 = (1) swap leaf3 for a real SONiC node, (2) follow one route through those databases (experiment E8),
(3) teach our engine to talk to SONiC, (4) build a checker for "lossless" network settings.

## The blocker (why it is split in two)
SONiC-VS only exists for x86 PCs. This Mac is ARM (M1). So the real SONiC node must run on a free GitHub x86
machine or the Azure VM. Both need your OK (publishing a repo / downloading a ~1 GB image / spending credits).

## Part A - done now, no SONiC image needed
| What | File | Tested how |
|---|---|---|
| QoS / lossless auditor: checks that PFC, DSCP, queue, buffer, ECN and watchdog settings agree with each other | `src/fabricx/audit/qos_lossless.py`, CLI `fabricx audit-qos <config_db.json>` | 12 unit tests on a **hand-written synthetic** CONFIG_DB, one mutation per check |
| SONiC adapter + route tracer (reads Redis with `sonic-db-cli`, follows APPL_DB -> ASIC_DB -> next hop) | `src/fabricx/adapters/sonic.py`, CLI `fabricx sonic-trace` | 3 unit tests on a **fake** node |
Specs: `tests/specs/sonic.yaml` (REQ-SONIC-001/002).

## Honest status (tiers)
- QoS auditor: BUILT (static analysis). Its test data is synthetic, not from a real switch yet.
- Adapter/tracer: BUILT but **unverified on real SONiC**; command formats come from documentation.
- E8 (the real trace), SONiC leaf in the fabric, gNMI: **NOT DONE** - need the image.
- veth has no PFC, so lossless behaviour is audited, never demonstrated.

## Part B - needs x86 (next)
1. Get the image (docker-sonic-vs from the sonic-buildimage build artifacts; community Docker Hub copies are old).
2. Add `sonic-leaf3` variant: containerlab `kind: sonic-vs`, config_db template, eBGP to the FRR spines.
3. Run E8, run the auditor on a real `sonic-cfggen -d --print-data` dump, fix whatever the real image disagrees with.

---
# What GitHub CI taught us (done after you chose GitHub Actions)

We created the public repo and ran our CI for the first time ever. It is a real x86 machine, so it behaves a bit
differently from the Mac. That was useful: it **found real bugs that the Mac never showed**.

| # | What CI showed | Real cause | Fix |
|---|---|---|---|
| 1 | `make fabric-up` failed | CI used the system Python, the Makefile expects `.venv/` | workflow creates `.venv` |
| 2 | Hung for 19 minutes, no output | `runner.sh` timeouts could not kill a `sudo` (root) child, so Python waited forever | timeout now enforced **inside** the sudo process (`timeout -k`); CI also has a job time limit and per-test limit |
| 3 | pcap test saw VNI 10020 on a routed ping | not the ping: background IPv6 router solicitations from young hosts | test now inspects only the ping packets (bridged -> L2VNI only, routed -> L3VNI only) |
| 4 | Fabric never became healthy: no Type-5 routes | **start-up race**: FRR started before `setup.sh` made the kernel VRF, so FRR bound the L3VNI to an auto-created BGP instance (two instances for `RED`, one with router-id 0.0.0.0) that never originated Type-5 | VRF/VXLAN plumbing now runs **before** FRR starts (clab `cmd`); host ports in a second script |
| 5 | `br10: Device does not exist` | `ports.sh` (clab `exec`) can run before the start command finished | `ports.sh` waits (max 30 s) for each bridge |

Simple version: the school's builders and the electricity company used to start at the same time. On the Mac the
builders usually won the race; on the faster x86 machine the electricity company sometimes won and switched on
before the rooms existed. Now the rooms are always built first.

| 6 | still flaky after fix 4 (2 of 4 attempts passed): duplicate BGP instance again, and once a routed ping partly in L2VNI | FRR event order: zebra announced the L3VNI before bgpd had read `router bgp ... vrf X` | `frr.conf` now defines the BGP VRF block **before** the `vrf X / vni N` block |

Stability evidence: after fix 6 the same commit passed CI **5 of 5** attempts (106 passed, 1 skipped each time; the skip is the
drill test, which needs results that CI does not have). Five is a small sample: "no failure seen in 5", not "can never fail".

Side effect: the **OSPF variant** puzzle from Phase 6 (missing Type-5 routes) very likely had this same cause. One fresh
OSPF deploy and one fresh IS-IS deploy now validate PASS (n=1 each, so "consistent with", not "proven").

Mac checks after the fix: `make test` 107 passed + validate PASS + no drift + 23 requirements traced; `make resilience` 14/14.
