# BUILD_LOG

## Phase 0 — Setup (2026-11-20) — DONE
- Installed OrbStack 2.2.5; created Ubuntu 24.04 arm64 VM `fabricx-lab`; installed Docker and Containerlab 0.83.0 inside it.
- Verified image manifests: FRR 10.2.1 and alpine:3.20 both have arm64.
- Hello lab (1 FRR + 1 host) deployed, h1 pinged r1 over a /31 (3/3, 0% loss), then destroyed cleanly (0 containers left).
- Idle RAM of hello lab: ~15 MiB total. Full 10-node fabric should fit easily.
- Findings: no /dev/kvm and no tcp_dctcp in OrbStack kernel → SONiC-VM and DCTCP work go to CI/cloud (as the blueprint predicted).
- FRR container started without a config (expected for a bare "linux" node); Phase 1 generates real configs.
- Cloud decision: nothing started on Azure. Will check /dev/kvm there only in Phase 7 if CI can't do the job.
- Mac disk free: 40 GB → 36 GB.

## How to run things
Commands run inside the VM: `orb -m fabricx-lab bash -lc '...'`. The Mac project folder is visible in the VM at the same path.

## Phase 1 — Inventory, config generation, bare fabric (2026-11-20) — DONE
- `inventory/fabric.yaml` is the only place with IPs/ASNs/VLANs/VNIs. `src/fabricx/model.py` (pydantic) validates it and derives links: 6 spine-leaf /31s (spine1-leaf2 = 10.1.1.2/31, as in the blueprint), host ports, loopbacks.
- `fabricx generate` renders `generated/fabricx.clab.yml` + per-node `frr.conf`/`daemons`/`vtysh.conf` from Jinja2 templates; also writes `docs/topology.md` (Mermaid diagram, replaces `containerlab graph`).
- Host layout: h1,h2 on leaf1; h3,h4 on leaf2; h5 (BLUE) on leaf3. Hosts have IP + default route via future anycast gateway (.1); gateway does not exist until Phase 3, so cross-host ping fails now (expected).
- Routing daemons (bgpd, bfdd) are off; only zebra runs. Phase 2 turns them on (`fabricx generate --routing`).
- Tests: 8 unit tests (no lab; incl. rule "no IP literal in src/ or templates/") pass. 17 lab tests pass on the live fabric: 10 nodes running, all 6 links UP with MTU 9100 and pingable both ways, 5 loopbacks, 5 hosts addressed.
- Sanity check: downing spine1:eth1 made the link test FAIL; restoring made it PASS (tests can actually fail).
- Measured RAM, full idle fabric: switches ~13-14 MiB each, hosts ~1 MiB each (~70 MiB total).
- Issue/decision: Typer needed an explicit callback so `generate` is a subcommand. Pinned nothing new (same images).
- Not done / deferred: CI check of the grep rule (CI comes in Phase 5; rule already runs as a unit test).
- Fabric torn down after testing (`make fabric-down`).

### Commands
`make fabric-up` · `make lab-test` · `make unit` · `make fabric-down`

## Documentation rule (added after Phase 1)
Every phase gets a teaching note in `docs/phases/` (plain-words goal, step-by-step what was done, key terms, real results, problems, interview explanation).

## Phase 2 — BGP underlay, ECMP, BFD, probe (2026-11-20) — DONE
- Inventory gained `underlay:` (BGP 3/9 s, BFD 300 ms x3, max 2 paths); model derives neighbours; FRR template emits bfd profile + router bgp (peer-group FABRIC, `no bgp ebgp-requires-policy`, `network <lo>/32`, `maximum-paths 2`); `fabricx generate` defaults routing on.
- `src/fabricx/probe.py` (stdlib only, bind-mounted to /opt/probe.py in every container). 5 unit tests. FRR image already has Python 3.12.8.
- Lab tests: 12/12 BGP Established, 2 kernel next-hops leaf->leaf loopbacks, 12/12 BFD up, loopback pings OK, probe 4000/4000 with 0 loss, longest gap 3.12 ms (noise floor of 1 ms probe in this VM).
- Gray failure sanity check: netem 100% loss on spine1:eth1 -> BFD down + single path within 1 s; tests failed then passed after restore. Full suite: 41 passed (13 unit, 28 lab).
- Deviation: BFD "datacenter" profile and BGP timers are fixed at inventory values; the E1 timer variants (default / 3-9 / BFD) are run in Phase 4 by changing inventory values.
- Fabric torn down after testing.

## Phase 3 — VXLAN-EVPN overlay, symmetric IRB (2026-11-20) — DONE
- Inventory: added `anycast_gw_mac`. Model derives per-leaf VLANs/VRFs from the hosts plugged into each leaf.
- New template `leaf-setup.sh.j2` (run via containerlab `exec`): per VRF a kernel VRF + `br<l3vni>` + `vx<l3vni>`; per VLAN `br<vlan>` (anycast MAC + gateway IP, enslaved to the VRF) + `vx<vni>` (`nolearning`); host ports enslaved to the VLAN bridge.
- FRR: `l2vpn evpn` activated on FABRIC; leaves `advertise-all-vni`; spines originally had `nexthop-unchanged` (see CORRECTION in Phase 5: it is not needed in FRR 10.2.1); per-VRF `router bgp <asn> vrf X` with `redistribute connected` and `advertise ipv4 unicast` (Type-5); `vrf X / vni <l3vni>`.
- Route-targets: FRR auto-derived RTs worked across different leaf ASNs (no explicit RT needed). Explicit RTs only in the RT-mismatch fault (Phase 6).
- Bugs found and fixed: (1) kernel VRF was named `vrfRED` but FRR config says `vrf RED` -> L3VNI showed "Unknown" tenant VRF; kernel VRF must be named exactly `RED`. (2) Host default route failed because the leaf port had no carrier yet -> hosts now retry in the background. (3) Per-VRF BGP router-id defaulted to the anycast gateway IP (same on every leaf, risks identical RDs for Type-5) -> set to the leaf loopback.
- Finding (silent host): first h1->h4 ping failed until h4 had sent any traffic, because EVPN learns host /32 routes from ARP/Type-2. Tests prime every host by pinging its gateway; this is documented behaviour, not a bug.
- Isolation: h1<->h5 fails both ways; leaf3 (BLUE only) has no RED routes.
- Evidence: `artifacts/phase3/` (pcap, decode, EVPN JSON, VRF routes) + `docs/packet-walkthrough.md`. Bridged traffic carries VNI 10010 with TTL 64; routed traffic carries VNI 50001 with TTL 63 and never VNI 10020.
- Tests: 11 new lab tests (4 traffic classes, anycast MAC identical on all leaves, route types 2/3/5 on every leaf, no RED leakage into BLUE, pcap assertions). Full suite passes.
- Added: `scripts/capture_vxlan.sh`; `tcpdump` installed in the VM; `.gitignore` keeps `artifacts/phase*/`.

## Phase 4 — Test suite, E1, E3, RCA-001, README (2026-11-20) — DONE (Milestone 1)
- Host image fabricx-host:1 (images/host/Dockerfile). `vxlan_df: set` added to inventory/leaf template.
- New: parsers.py, collectors.py, validators.py, report.py, `fabricx validate`; fixtures from live outputs; markers smoke/functional; `make up|test|down|smoke`.
- Tests: 25 unit + 40 lab = 65 passed; `fabricx validate` PASS; a broken link gave 10 findings and exit 1.
- E1 (experiments/E1): N=10 per cell. Carrier loss median 4.6 ms (BFD) / 3.2 ms (no BFD). Gray failure median 812 ms (BFD) / 10.3 s (BGP 3/9, no BFD) / 141 s, 192 s, >=197 s (BGP default 60/180, N=3). Raw gz CSVs kept (~4 MB total experiments dir).
- Measurement bug found: trailing (unrecovered) outage missed by "longest gap"; `aggregate.py` corrects it (flag `*`).
- E3 (experiments/E3): DF ping boundary 1422 for 1500-byte link (matches 1500-50-28). TCP unaffected while ICMP frag-needed works; 0 bit/s when ICMP type 3 dropped via tc u32.
- RCA-001 written (docs/rca). README and docs/limitations.md written.
- Deviations: profile switching for E1 done at run time with vtysh instead of regenerating configs; BGP-default profile only N=3. Not done: CI, ruff/mypy (Phase 5).
- Disk: experiments 3.9 MB, artifacts 1.1 MB, venv 46 MB; Mac free space ~38 GB.
- Fabric torn down at the end.


### CORRECTION (found in Phase 5 by the drift check)
Phase 3 said spines need `neighbor FABRIC nexthop-unchanged` for EVPN. That was an untested assumption. FRR 10.2.1 does not even show the line in `show running-config`, and when I removed it live the EVPN next-hop stayed the leaf loopback and h1->h3 still worked. FRR preserves the EVPN next-hop on eBGP by default. The line was removed from the template.

## Phase 5 — Engine hardening, drift, specs, CI (2026-11-20) — DONE (CI written, not yet run)
- ruff + mypy configured and clean. Runner: timeouts/retries, `NodeUnreachable`. Validators/collectors handle unreachable nodes.
- `drift.py` + `fabricx drift`; CLI additions: deploy, destroy, drift, report, trace. `fabricx trace` + `tests/specs/*.yaml` (16 requirements) -> `docs/traceability.md`.
- `tests/conftest.py` settle fixture; probe healthy-fabric threshold relaxed to 250 ms (documented).
- `make test` = lint + mypy + pytest (JUnit) + validate + drift + trace: 77 passed, exit 0. `make RUN=sudo ...` for CI.
- CORRECTION: `nexthop-unchanged` on spines removed (not needed in FRR 10.2.1).
- Trivy: host image 2 HIGH; FRR image 41 HIGH + 2 CRITICAL; both Alpine 3.20 EOSL. Raw: artifacts/phase5/.
- `.github/workflows/ci.yml` (lint-unit incl. config-diff, lab, trivy) written. NOT executed: no GitHub repo yet. E10 stays open.
- Fabric torn down. Mac disk: project ~160 MB incl. 46 MB venv.

## Phase 6 — Fault catalogue, diagnose, drill, E2/E4/E5/E7/E9, RCA-002/003 (2026-11-20/21) — DONE (Milestone 2)
- Specs first: `tests/specs/faults.yaml` (5 requirements; 21 total with earlier ones).
- Inventory: `ecmp_hash_policy: 1` (from E2), `underlay.protocol` (ebgp|ospf|isis), `ibgp_asn`, IGP hello/dead; templates for OSPF and IS-IS with iBGP EVPN (spines = RR); variants in `inventory/variants/`. `fabricx validate`/model are protocol-aware (BGP neighbours = loopbacks for IGP variants; BFD peers = link addresses). BGP summary parser reads all address families.
- New code: `faults/catalogue.py` (14 faults), `faults/runner.py` (evidence bundle), `diagnose.py` (8 layers), CLI `faults|inject|restore|diagnose|run-fault|drill`. Bundles are written to `artifacts/runs/` (git-ignored; 13 MB).
- Blind drill: seed 11 = 12/14 (misses F06, F12) -> rules fixed (remote-as vs inventory, `bgp-session-down` fallback, FRR `show evpn mac` duplicate flags, restore clears dup flag) -> seed 22 = 14/14. Results: `experiments/E9/`.
- E2: policy 0 pins plain routed flows to one uplink, policy 1 spreads them; VXLAN flows pinned under both (hypothesis: route caching in the VXLAN device, unverified). E4: `experiments/E4/symptoms.md` + extra (`no advertise-all-vni`). E7: live move median 9.4 ms (N=10), cold move ~0.7 s. E5: see `experiments/E5/results.md` (OSPF/IS-IS vs eBGP).
- RCA-002 (ECMP polarisation) and RCA-003 (RT mismatch) written. `docs/fault-catalogue.md`, `docs/traceability.md` generated.
- Tests: `make test` = lint + mypy + 91 tests (48 unit, 43 lab) + validate + drift + trace (21 requirements). `make resilience` (14 round-trips) and `make drill` on demand.
- Known gaps: OSPF variant lacks some Type-5 routes (unresolved); E7 old-leaf-claim and MM-seq readings unreliable; GitHub CI still never run; diagnose tuned on the same catalogue (see E9 caveat); E10 open.
- Late fixes (Phase 6): F08/F12 restore left config/state behind (found by adding a drift assertion to `tests/lab/test_faults_roundtrip.py`); fixed. Duplicate-MAC rule tightened (stale counters on a remote MAC no longer flagged). Final: `make resilience` 14/14 (validate + drift clean), recheck drill 3/3, `make test` 91 passed + validate + drift + trace. Fabric torn down.

## Phase 7 part A - SONiC track, Mac-side work
- Blueprint check: docker-sonic-vs is x86-only; OrbStack VM here is aarch64 -> real SONiC needs CI or Azure.
- Built `audit/qos_lossless.py` (+ CLI audit-qos, 12 tests) and `adapters/sonic.py` (+ CLI sonic-trace, 3 tests).
- Unit tests 48 -> 63 passing; ruff and mypy clean. Specs REQ-SONIC-001/002 added.
- Not run on real SONiC. Waiting for user decision on where the x86 run happens.

## Phase 7 - GitHub repo and first CI runs
- User chose GitHub Actions for the x86 machine and a PUBLIC repo `nurul-hasan27/fabricx`. Excluded `docs/blueprint_v2.html` (personal job notes).
- First CI runs exposed 5 problems (CI python, runner timeout hang, pcap test noise, FRR start-up race for the L3VNI, ports.sh ordering). Details: docs/phases/phase-7-sonic-track.md.
- Mistake: first commit included containerlab runtime files (`generated/clab-fabricx/`: lab CA key, authorized_keys, Mac username in paths). Untracked, git-ignored, and removed from the public history on the user's approval (history squashed into one commit and force-pushed, 2026-11-21). GitHub may still serve the old commits by their ID for a while. The CA key only signed this throwaway lab.
- Phase 6 OSPF "missing Type-5" puzzle: probable cause = same race; OSPF and IS-IS deploys validate PASS after fix (n=1).
- FRR config order: `router bgp ... vrf X` now comes before `vrf X / vni` in frr.conf (bgpd must have its VRF instance before zebra announces the L3VNI). CI lab job on one commit: plumbing fix only = 2 of 4 attempts passed; after this reorder = 5 of 5 attempts passed (run 44905247829).

## Phase 7 part B - real SONiC on x86 CI
- Image pinned: official docker-sonic-vs 202505 build 1238524 (228 MB gz, sha256 in artifacts/phase7/sonic-image.txt), fetched on the GitHub runner only (nothing downloaded to the Mac). Probe run 44915950736 recorded what the image contains (no gNMI service, no config daemon, bfdd without a service, eth1->Ethernet0).
- Built: sonic-leaf3 variant, CONFIG_DB-driven bring-up template, NOS-aware checks (MTU on Ethernet0, Loopback0, SONiC zebra lines not drift), CLI follows FABRICX_INVENTORY, tracer for bgpd/zebra/APPL_DB staging/ASIC_DB/ECMP members and one interface, E8 script, manual workflow `sonic.yml`.
- Bring-up bugs found with evidence: bfdd/bgpd started before the image's start.sh had created /var/run/frr (BFD down kept BGP Idle on the spines); MTU 9122 on the wire vs 9100 port; image zebra lines reported as drift; drift test used the wrong inventory.
- Result (run 44923272077): SONiC leaf BGP Established + BFD up with both FRR spines; lab suite 41 passed, 1 skipped; validate PASS; no drift.
- E8: full chain with real keys; frozen orchagent leaves routes in _ROUTE_TABLE / ROUTE_TABLE_KEY_SET while zebra shows offloaded=True; announce -> ASIC_DB median 0.219 s (N=10, resolution 0.053 s). QoS auditor vs real CONFIG_DB: default = nothing to audit, PFC-only = 10 findings while SONiC programs PFC silently, complete = no findings.
- FRR start-up race not eliminated by ordering (2 failures in 16 CI lab runs). Reproduced on purpose (L3VNI before BGP VRF instance -> duplicate instance, no Type-5). Added a check-and-repair after leaf start-up, verified on the reproduced failure. Same commit afterwards: 7 of 7 runs passed; the repair fired in 3 of 20 FRR leaf start-ups and fixed each.
- Local Mac after all changes: make test 116 passed + validate PASS + no drift + 25 requirements traced; make resilience 14/14.
- Not done: EVPN overlay on the SONiC leaf, gNMI (no service in this image), SONiC-VM. Azure not used.

## Phase 8 - telemetry and the congestion study
- Exporter (`fabricx exporter`, stdlib only, one docker exec per switch per scrape), Prometheus v3.1.0 + Grafana 11.4.0 (`scripts/monitoring.sh`), one provisioned dashboard, Grafana annotations from the fault runner.
- Acceptance demo (F01 under 200 Mbit/s iperf3): both annotations; leaf1 eth1 -> 0 and eth2 carrying all traffic during the fault; dashboard shows the BGP change 4.6 s after inject / 4.4 s after restore; no visible dip in iperf3's 1 s throughput (failover is ms, as in E1).
- Mistakes found: silent annotation failure on a cold Grafana; exporter polled on its own timer -> impossible rates (now collect-on-scrape); E6 throughput summed over different windows (now common span); ping not ECN-capable under RED (now -Q 2 + TCP RTT); tc parser missed marks (now in parsers.py with a test).
- E6 on GitHub x86 (N=5, run 44932925203): tail-drop median queue RTT 111 ms; RED+ECN cubic 2.06 ms but 1-3 of 12 connections fell back to non-ECN per run and 3 of 5 runs had ~1600 drops; DCTCP 2.67 ms, 0 drops, Jain 1.000. Mac cross-check for A/B agrees; HTB unusable in the Mac VM (TBF used).
- Containers can only use congestion-control algorithms on the host's allowed list (DCTCP needed `net.ipv4.tcp_allowed_congestion_control`).
- RoCE hardware test plan written (STUDIED). gNMI from SONiC not possible with the pinned image.

## Phase 9 - clean-room rerun, final docs, demo
- Clean-room #1 (fresh clone of the published README, host image hidden): `make up` failed (host image never built by the README), `make test` failed (no ruff/mypy); after hand fixes 121 passed + 1 skipped. The skip was a unit test that read git-ignored bundles, so it skipped on every fresh clone and in CI.
- Fixes: `make vm-setup` (scripts/vm_setup.sh: Docker, tcpdump, Containerlab 0.83.0, idempotent), `make setup` (venv + pinned `.[dev]` + host image), `--timeout=400` in `make test`, bundle check is now a lab test (`test_run_fault_writes_complete_bundle`, REQ-FAULT-003 repointed), CI lab job runs the README's commands on a fresh x86 machine, `src/fabricx.egg-info/` untracked.
- Clean-room #2 (fresh clone of the fixed commit): make setup 11.3 s, make test 121 passed / 0 skipped + validate PASS + no drift + 28 requirements, make resilience 15/15; traceability identical to the committed one. Evidence: artifacts/phase9/.
- Not covered: a brand-new arm64 VM (existing VM reused; host image from build cache).
- Docs: README rewritten (quick start from nothing, reading order, linked evidence index), limitations merged into one page incl. reproducibility limits, docs/DEMO.md rehearsed on the lab (F08 demo: diagnose ~12 s, everything else < 5 s). Resume bullets and interview rehearsal kept private in git-ignored docs/private/.
- Mistakes caught before publishing: README draft had spine ASN 65100 (is 65000), untested "Intel Mac" and "4 GB RAM" claims; demo script claimed validate checks traffic classes (it doesn't).
