# FabricX

A small, reproducible **EVPN-VXLAN leaf-spine lab** with a **validation engine** around it. One inventory file generates
the whole fabric; Python/Pytest checks that it works, breaks it in controlled ways, measures what happens and writes up
the root cause. Every number in this repo comes from a stored file, and every capability carries an honesty label.

> **Status: complete (Phases 0–9 of [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)).** The FRR fabric runs on a Mac M1
> (OrbStack Linux VM, FRR 10.2.1, Containerlab 0.83.0) and on a fresh x86 GitHub Actions machine on every push. The
> SONiC track runs on x86 CI with the official SONiC-VS image (202505, build 1238524). Azure was not needed.

```
             spine1 (AS 65000)        spine2 (AS 65000)          eBGP underlay, BFD, ECMP
               /     |      \          /     |      \
          leaf1 (65001)   leaf2 (65002)   leaf3 (65003)          VXLAN-EVPN, symmetric IRB, anycast gateway
          h1  h2           h3  h4          h5                    VRF RED (VLAN 10/20), VRF BLUE (VLAN 30)
```
Full addressing: [`docs/topology.md`](docs/topology.md) (generated from [`inventory/fabric.yaml`](inventory/fabric.yaml)).

## Quick start (from nothing to a green suite)
On a Mac with [OrbStack](https://orbstack.dev) (tested on an Apple M1, 8 GB):
```bash
orbctl create ubuntu:noble fabricx-lab      # the Linux machine the lab runs in
git clone https://github.com/nurul-hasan27/fabricx.git && cd fabricx
make vm-setup   # Docker, tcpdump, Containerlab 0.83.0 inside the VM (idempotent)
make setup      # Python venv with pinned tools + build the lab host image
make up         # generate configs, deploy 10 containers (2 spines, 3 leaves, 5 hosts), wait to converge
make test       # lint + types + 121 tests (78 unit + 43 lab) + validate + drift + traceability; non-zero exit on any failure
make down       # tear it all down
```
On a Linux x86/arm64 machine, run the same commands with `RUN=sudo` (`make vm-setup RUN=sudo`, ...) and
`export FABRICX_EXEC=sudo`; this is exactly what [CI](.github/workflows/ci.yml) does on a fresh machine every push.
Needs Python ≥ 3.10. The lab's two images take ~400 MB and its 10 containers ~125 MB of RAM
([`artifacts/phase9/resources.txt`](artifacts/phase9/resources.txt)). Optional: `make resilience` (inject and undo all 14 faults,
~10 min), `make drill` (blind diagnosis drill, ~15 min). Phase 9's clean-room rerun is in
[`artifacts/phase9/`](artifacts/phase9/).

## Where to start reading
1. [`docs/phases/`](docs/phases/) — one teaching note per phase: what was built, step by step, in plain words, what went
   wrong, and how to explain it. [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) is the short diary.
2. [`docs/limitations.md`](docs/limitations.md) — what a virtual lab cannot prove.
3. [`docs/DEMO.md`](docs/DEMO.md) — the 6-minute demo script.
4. The experiments below (each `analysis.md` states question, method, raw data, result and limits).

## What's in the box
| Piece | Where |
|---|---|
| Single source of truth (IPs, ASNs, VLANs, VNIs, timers) | [`inventory/fabric.yaml`](inventory/fabric.yaml), variants in [`inventory/variants/`](inventory/variants/) |
| Typed model, config generation (Jinja2) | [`src/fabricx/model.py`](src/fabricx/model.py), [`templates/`](templates/), `fabricx generate` |
| Collectors, parsers, validators, reports | `src/fabricx/{collectors,parsers,validators,report}.py`, `fabricx validate` |
| Drift detection (running config vs generated) | [`src/fabricx/drift.py`](src/fabricx/drift.py), `fabricx drift` |
| Loss-window probe (1 ms UDP sequence) | [`src/fabricx/probe.py`](src/fabricx/probe.py) |
| Fault catalogue (14), evidence bundles, layered diagnosis, blind drill | [`docs/fault-catalogue.md`](docs/fault-catalogue.md), [`src/fabricx/faults/`](src/fabricx/faults/), [`src/fabricx/diagnose.py`](src/fabricx/diagnose.py) |
| Root-cause reports | [`docs/rca/`](docs/rca/) (MTU, ECMP polarisation, route-target) |
| Packet captures explained | [`docs/packet-walkthrough.md`](docs/packet-walkthrough.md) |
| SONiC: leaf3 variant, route tracer, lossless-QoS auditor | [`inventory/variants/sonic-leaf3.yaml`](inventory/variants/sonic-leaf3.yaml), [`src/fabricx/adapters/sonic.py`](src/fabricx/adapters/sonic.py), [`src/fabricx/audit/qos_lossless.py`](src/fabricx/audit/qos_lossless.py) |
| Telemetry: exporter, Prometheus + Grafana, fault annotations | [`src/fabricx/exporter.py`](src/fabricx/exporter.py), [`monitoring/`](monitoring/), [`scripts/monitoring.sh`](scripts/monitoring.sh) |
| Requirement → test → evidence matrix (28 requirements) | [`docs/traceability.md`](docs/traceability.md), specs in [`tests/specs/`](tests/specs/) |
| RoCE hardware test plan | [`docs/roce-test-plan.md`](docs/roce-test-plan.md) |
| CI | [`ci.yml`](.github/workflows/ci.yml) (every push: lint + full lab on fresh x86), [`sonic.yml`](.github/workflows/sonic.yml) and [`e6.yml`](.github/workflows/e6.yml) (manual, x86) |

## Honest-scope box
| Capability | Tier |
|---|---|
| eBGP underlay, ECMP, BFD | BUILT + MEASURED ([E1](experiments/E1/results.md)) |
| VXLAN-EVPN, symmetric IRB, anycast gateway, 2 VRFs | BUILT ([pcap + route evidence](docs/packet-walkthrough.md)) |
| Inventory → config generation, drift detection | BUILT |
| Validation engine: 121 tests in `make test` (78 unit + 43 lab) + 15 resilience tests, 28 traced requirements | BUILT ([traceability](docs/traceability.md)) |
| Fault catalogue (14 faults), evidence bundles, layered `diagnose`, blind drill | BUILT + MEASURED ([E9](experiments/E9/): 12/14 first pass, 14/14 after tuning) |
| ECMP, EVPN-misconfig, MAC-mobility, underlay-protocol and MTU experiments (E2, E4, E7, E5, E3) | BUILT + MEASURED |
| Clean-room reproduction: fresh clone → green suite with only the README | BUILT + RUN (Mac, [`artifacts/phase9/`](artifacts/phase9/); fresh x86 machine in CI) |
| SONiC-VS leaf interoperating with FRR spines (BGP, BFD, ECMP) | BUILT + MEASURED (x86 CI; lab suite 41 passed / 1 skipped) |
| E8: one route through bgpd → zebra → APPL_DB → orchagent → ASIC_DB, frozen orchagent | BUILT + MEASURED ([E8](experiments/E8/analysis.md); vslib, not a real ASIC) |
| Lossless-QoS auditor (PFC/ECN/DSCP/buffers/watchdog) against a real SONiC CONFIG_DB | BUILT (static analysis) |
| FRR exporter → Prometheus → Grafana with fault annotations | BUILT + MEASURED ([F01 demo](experiments/telemetry/results/summary.md)) |
| E6 incast: tail-drop vs RED+ECN vs DCTCP | EMULATED + MEASURED ([E6](experiments/E6/analysis.md), x86 CI, N=5) |
| RoCE/PFC on real hardware | STUDIED ([test plan](docs/roce-test-plan.md)) |
| EVPN overlay on the SONiC leaf, gNMI from SONiC (image has no gNMI service), SONiC-VM, Soft-RoCE, EVPN multihoming | NOT DONE |
| ASIC behaviour, line rate, optics, PFC frames, scale | OUT OF SCOPE ([limitations](docs/limitations.md)) |

## Evidence index (every number below comes from a file)
| Claim | Evidence |
|---|---|
| Carrier loss: median outage ~4.6 ms (BFD) / ~3.2 ms (no BFD), N=10; at the probe's noise floor | [`experiments/E1/results.md`](experiments/E1/results.md) |
| Gray failure: median 812 ms with BFD vs 10.3 s with BGP 3/9 s timers (N=10) vs 141–197+ s with BGP defaults (N=3) | [`experiments/E1/results.md`](experiments/E1/results.md), raw in [`results/`](experiments/E1/results/) |
| VXLAN bridged traffic uses L2VNI 10010; routed traffic uses L3VNI 50001 with TTL 63 | [`artifacts/phase3/leaf2-vxlan.txt`](artifacts/phase3/leaf2-vxlan.txt) |
| MTU mismatch: DF ping boundary at 1422 bytes (= 1500 − 50 − 28); TCP stalls only when ICMP frag-needed is suppressed | [`experiments/E3/analysis.md`](experiments/E3/analysis.md), [`RCA-001`](docs/rca/RCA-001-mtu-black-hole.md) |
| Plain routed flows spread with hash policy 1, but VXLAN flows from a Linux VTEP stay on one uplink | [`experiments/E2/analysis.md`](experiments/E2/analysis.md), [`RCA-002`](docs/rca/RCA-002-ecmp-polarisation.md) |
| With BFD a gray failure costs ~0.75 s (OSPF), ~0.81 s (eBGP), ~1.6 s (IS-IS); without BFD 7 to 31 s | [`experiments/E5/results.md`](experiments/E5/results.md) |
| Live MAC move: median 9.4 ms, 0 lost packets (N=10) | [`experiments/E7/analysis.md`](experiments/E7/analysis.md) |
| Blind drill: 12/14 localised before tuning, 14/14 after (rules tuned on the same catalogue) | [`experiments/E9/`](experiments/E9/) |
| SONiC: ECMP route = one SAI next-hop group with a member per path; announce → ASIC_DB median 0.219 s (N=10, resolution 0.053 s) | [`experiments/E8/analysis.md`](experiments/E8/analysis.md) |
| Frozen orchagent: route stays in `_ROUTE_TABLE` / `ROUTE_TABLE_KEY_SET` while zebra still says `offloaded=True` | [`experiments/E8/results/trace_orchagent_frozen.md`](experiments/E8/results/trace_orchagent_frozen.md) |
| SONiC accepts PFC without buffers/ECN/watchdog silently; the auditor reports 10 findings | [`experiments/E8/results/`](experiments/E8/results/) (`qos_2_pfc_only_*`) |
| FRR EVPN start-up race (duplicate BGP VRF instance, no Type-5) reproduced on purpose; check-and-repair verified | [`docs/phases/phase-7-sonic-track.md`](docs/phases/phase-7-sonic-track.md) |
| Link failure on the dashboard: annotations, BGP change within one scrape, uplink shift; no visible 1 s throughput dip | [`experiments/telemetry/results/`](experiments/telemetry/results/) |
| Incast queue delay: tail-drop 111 ms, RED+ECN 2.06 ms, DCTCP 2.67 ms (median, N=5); DCTCP 0 drops, Jain 1.000 | [`experiments/E6/analysis.md`](experiments/E6/analysis.md), [`results_ci/`](experiments/E6/results_ci/) |
| Classic ECN: 1–3 of 12 connections per run fell back to non-ECN after a dropped SYN | [`experiments/E6/results_ci/B.json`](experiments/E6/results_ci/B.json) |
| Fresh clone → `make setup` + `make up` + `make test` all green on the Mac; `make resilience` 15/15 | [`artifacts/phase9/`](artifacts/phase9/) |
