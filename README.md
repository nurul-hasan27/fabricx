# FabricX

A small, reproducible **EVPN-VXLAN leaf-spine lab** with a **validation engine** around it: it generates the fabric from one inventory file, checks that it works, breaks it in controlled ways, measures what happens and writes up the root cause.

> Status: Milestone 2 (Phases 0-6 of `docs/PROJECT_PLAN.md`). The GitHub Actions workflow is written but has not been run yet; SONiC, telemetry and the congestion study (Phases 7-8) are not built. Everything below was run for real on a Mac M1 (OrbStack Linux VM, FRR 10.2.1, Containerlab 0.83.0).

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
| Experiments with raw data | `experiments/E1`, `E2`, `E3`, `E4`, `E5`, `E7`, `E9` |
| Root-cause reports | `docs/rca/RCA-001` (MTU), `RCA-002` (ECMP), `RCA-003` (route-target) |
| Fault catalogue, diagnose, drill | `docs/fault-catalogue.md`, `src/fabricx/diagnose.py`, `experiments/E9/` |
| Packet captures explained | `docs/packet-walkthrough.md` |
| Teaching notes per phase | `docs/phases/` |
| Requirement -> test -> evidence matrix | `docs/traceability.md`, specs in `tests/specs/` |
| CI | `.github/workflows/ci.yml` |

## Honest-scope box
| Capability | Tier |
|---|---|
| eBGP underlay, ECMP, BFD | BUILT + MEASURED (E1) |
| VXLAN-EVPN, symmetric IRB, anycast gateway, 2 VRFs | BUILT (pcap + route evidence) |
| Inventory -> config generation | BUILT |
| Validation engine, 91 automated tests, drift detection, YAML specs + traceability matrix (21 requirements) | BUILT |
| Fault catalogue (14 faults), evidence bundles, layered `diagnose`, blind drill | BUILT + MEASURED (12/14 first pass, 14/14 after tuning) |
| ECMP, EVPN-misconfig, MAC-mobility and underlay-protocol experiments (E2, E4, E7, E5) | BUILT + MEASURED |
| Link-failure and MTU experiments | BUILT + MEASURED |
| GitHub Actions CI + Trivy scan (Trivy run locally once; workflow not yet run) | BUILT (CI unrun) |
| SONiC track, telemetry, ECN/DCTCP congestion study, RoCE test plan | NOT YET (Phases 7-8) |
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
