# FabricX

A small, reproducible **EVPN-VXLAN leaf-spine lab** with a **validation engine** around it: it generates the fabric from one inventory file, checks that it works, breaks it in controlled ways, measures what happens and writes up the root cause.

> Status: Phases 0-8 of `docs/PROJECT_PLAN.md`. The FRR fabric runs on a Mac M1 (OrbStack Linux VM, FRR 10.2.1, Containerlab 0.83.0) and in GitHub Actions on x86. The SONiC track (Phase 7) runs only on x86 CI, with the official SONiC-VS image (202505, build 1238524). Telemetry (Prometheus/Grafana) and the E6 congestion study were added in Phase 8; E6's DCTCP scenario runs on x86 CI.

## Quick start
```bash
make up        # generate configs, deploy 10 containers (2 spines, 3 leaves, 5 hosts), wait to converge
make test      # lint + types + unit + live lab tests + validate + drift check + traceability (non-zero exit on any failure)
make down      # tear it all down
```
Needs: OrbStack with a Linux VM named `fabricx-lab` that has Docker and Containerlab (see `docs/phases/phase-0-setup.md`), and `python3 -m venv .venv && .venv/bin/pip install -e . pytest`.

## What's in the box
| Piece | Where |
|---|---|
| The single source of truth (IPs, ASNs, VLANs, VNIs, timers) | `inventory/fabric.yaml` |
| Typed model + derived state | `src/fabricx/model.py` |
| Config generation (Jinja2) | `templates/`, `fabricx generate` -> `generated/` |
| Collectors / parsers / validators / reports | `src/fabricx/{collectors,parsers,validators,report}.py`, `fabricx validate` |
| Loss-window probe | `src/fabricx/probe.py` |
| Experiments with raw data | `experiments/E1`-`E9`, `experiments/telemetry` |
| Telemetry: exporter, Prometheus + Grafana, fault annotations | `src/fabricx/exporter.py`, `monitoring/`, `scripts/monitoring.sh` |
| RoCE hardware test plan | `docs/roce-test-plan.md` |
| Root-cause reports | `docs/rca/RCA-001` (MTU), `RCA-002` (ECMP), `RCA-003` (route-target) |
| Fault catalogue, diagnose, drill | `docs/fault-catalogue.md`, `src/fabricx/diagnose.py`, `experiments/E9/` |
| Packet captures explained | `docs/packet-walkthrough.md` |
| Teaching notes per phase | `docs/phases/` |
| Requirement -> test -> evidence matrix | `docs/traceability.md`, specs in `tests/specs/` |
| CI | `.github/workflows/ci.yml` (every push), `.github/workflows/sonic.yml` (manual, SONiC on x86) |
| SONiC: leaf3 variant, adapter + route tracer, QoS/lossless auditor | `inventory/variants/sonic-leaf3.yaml`, `src/fabricx/adapters/sonic.py`, `src/fabricx/audit/qos_lossless.py` |

## Honest-scope box
| Capability | Tier |
|---|---|
| eBGP underlay, ECMP, BFD | BUILT + MEASURED (E1) |
| VXLAN-EVPN, symmetric IRB, anycast gateway, 2 VRFs | BUILT (pcap + route evidence) |
| Inventory -> config generation | BUILT |
| Validation engine, 122 automated tests (79 unit + 43 lab), drift detection, YAML specs + traceability matrix (28 requirements) | BUILT |
| Fault catalogue (14 faults), evidence bundles, layered `diagnose`, blind drill | BUILT + MEASURED (12/14 first pass, 14/14 after tuning) |
| ECMP, EVPN-misconfig, MAC-mobility and underlay-protocol experiments (E2, E4, E7, E5) | BUILT + MEASURED |
| Link-failure and MTU experiments | BUILT + MEASURED |
| GitHub Actions CI (lint, unit, full lab on x86, Trivy) | BUILT + RUN (see stability note in `docs/phases/phase-7-sonic-track.md`) |
| SONiC-VS leaf interoperating with FRR spines (BGP, BFD, ECMP); lab suite 41 passed / 1 skipped | BUILT + MEASURED (x86 CI) |
| E8: one route through bgpd -> zebra -> APPL_DB -> orchagent -> ASIC_DB, orchagent fault, timings | BUILT + MEASURED (vslib, not a real ASIC) |
| Lossless-QoS auditor (PFC/ECN/DSCP/buffers/watchdog), checked against a real SONiC CONFIG_DB | BUILT (static analysis) |
| EVPN overlay on the SONiC leaf, gNMI from SONiC (image has no gNMI service), SONiC-VM | NOT DONE |
| FRR exporter -> Prometheus -> Grafana with fault annotations | BUILT + MEASURED (F01 demo) |
| E6 incast: tail-drop vs RED+ECN vs DCTCP | EMULATED + MEASURED (x86 CI, N=5) |
| RoCE on real hardware | STUDIED (test plan) |
| ASIC behaviour, line rate, optics, PFC/RDMA, scale | OUT OF SCOPE (see `docs/limitations.md`) |

## Evidence index (every number below comes from a file)
| Claim | Evidence |
|---|---|
| Carrier loss: median outage ~4.6 ms (BFD) / ~3.2 ms (no BFD), N=10; at probe noise floor | `experiments/E1/results.md` |
| Gray failure: median 812 ms with BFD vs 10.3 s with BGP 3/9 s timers (N=10) vs 141-197+ s with BGP defaults (N=3) | `experiments/E1/results.md`, raw in `experiments/E1/results/` |
| VXLAN bridged traffic uses L2VNI 10010; routed traffic uses L3VNI 50001 with TTL 63 | `artifacts/phase3/leaf2-vxlan.txt` |
| MTU mismatch: DF ping boundary at 1422 bytes (= 1500 - 50 - 28); TCP stalls only when ICMP frag-needed is suppressed | `experiments/E3/results/*.json`, `experiments/E3/analysis.md` |
| `underlay-mtu` and 5 other checks detect faults | `tests/unit/test_parsers_validators.py` |
| Blind drill: 12/14 localised before tuning, 14/14 after (rules tuned on the same catalogue) | `experiments/E9/results.md`, `analysis.md` |
| Plain routed flows spread with hash policy 1 but VXLAN flows from a Linux VTEP stay on one uplink | `experiments/E2/analysis.md` |
| With BFD a gray failure costs ~0.75 s (OSPF), ~0.81 s (eBGP), ~1.6 s (IS-IS); without BFD 7 to 31 s | `experiments/E5/results.md` |
| Live MAC move: median 9.4 ms, 0 lost packets (N=10) | `experiments/E7/analysis.md` |
| SONiC: ECMP route = one SAI next-hop group with a member per path; announce -> ASIC_DB median 0.219 s (N=10, resolution 0.053 s) | `experiments/E8/analysis.md`, `experiments/E8/results/` |
| Frozen orchagent: route stays in `_ROUTE_TABLE` / `ROUTE_TABLE_KEY_SET`, zebra still says `offloaded=True` | `experiments/E8/results/trace_orchagent_frozen.md` |
| SONiC accepts PFC without buffers/ECN/watchdog silently (PFC bitmask 24); the auditor reports 10 findings | `experiments/E8/results/qos_2_pfc_only_*` |
| FRR EVPN start-up race (duplicate BGP VRF instance, no Type-5) reproduced on purpose; check-and-repair verified | `docs/phases/phase-7-sonic-track.md` |
| Link failure on the dashboard: annotations, BGP change within one scrape, uplink shift; no visible 1 s throughput dip | `experiments/telemetry/results/` |
| Incast queue delay: tail-drop 111 ms, RED+ECN 2.06 ms, DCTCP 2.67 ms (median, N=5); DCTCP 0 drops, Jain 1.000 | `experiments/E6/analysis.md`, `experiments/E6/results_ci/` |
| Classic ECN: 1-3 of 12 connections per run fell back to non-ECN after a dropped SYN | `experiments/E6/results_ci/B.json` |
