# FabricX — Phase Plan (adapted to this machine)

Source of truth: `docs/blueprint_v2.html`. This file only says **what we do, in what order, and where it runs**.

## Constraints
- Mac: M1, 8 GB RAM, ~40 GB free disk. Docker / OrbStack / Containerlab are **not installed yet**.
- Azure VM: very few credits. Used only for SONiC and ECN/DCTCP work (Phases 7-8), started briefly, then stopped.
  GitHub Actions (free x86) is used wherever possible instead of the VM.
- Keep the project small. No Kubernetes, no web frontend, no AI features.
- No number appears in any doc unless a script produced it.

## Where things run
| Place | Used for | Cost |
|---|---|---|
| Mac | editing, Python unit tests, git | free |
| OrbStack Linux VM on the Mac | the whole FRR fabric (10 small containers) | free |
| GitHub Actions | x86 lab runs, SONiC-VS container | free |
| Azure VM | only if CI cannot do it (SONiC-VM / KVM, DCTCP kernel module) | credits - last resort |

## Phases
| # | Phase | What we get | Runs on |
|---|---|---|---|
| 0 | Setup | OrbStack + Docker + Containerlab installed (about 3-4 GB), repo skeleton, tiny 2-node test lab, versions recorded | Mac |
| 1 | Inventory and config generation | One `fabric.yaml` generates every config; 5 switches + 5 hosts up, links addressed | Mac/OrbStack |
| 2 | BGP underlay, ECMP, BFD, probe tool | 6/6 BGP sessions, 2 paths everywhere, BFD up, our own packet-loss meter | Mac/OrbStack |
| 3 | VXLAN-EVPN overlay | Hosts talk across racks; RED/BLUE tenants isolated; packet capture explained | Mac/OrbStack |
| 4 | First test suite + first experiments (M1) | `make test` (~20 checks), E1 link failure, E3 MTU problem, RCA-001, README | Mac/OrbStack |
| 5 | Engine hardening + CI | CLI, drift detection, spec-driven tests, GitHub Actions running the lab | Mac + CI |
| 6 | Failure catalogue + diagnose (M2) | 12+ injectable faults, auto-diagnosis, blind drill, E2/E4/E5/E7, 2 more RCAs | Mac/OrbStack |
| 7 | SONiC track | SONiC-VS leaf, DB trace E8, QoS auditor | CI first, Azure only if needed |
| 8 | Telemetry + congestion study | Prometheus/Grafana dashboard, E6 ECN/DCTCP, RoCE hardware test plan | OrbStack, Azure briefly |
| 9 | Polish | Clean-room rerun, limitations page, final docs, demo script | Mac + CI |

Stretch items (EVPN multihoming, Soft-RoCE, Ixia-c, NETCONF) are skipped unless time and storage allow.

**Status (2026-11-22): Phases 0-9 done. Azure was never used (GitHub Actions covered all x86 work). Stretch items not done.**

## Rules for every phase
1. I explain the phase in simple words *before* we start.
2. You approve it.
3. I build it and test it end to end, then show the real output.
4. I explain what happened in simple words and update `docs/BUILD_LOG.md`.
5. Next phase starts only after you say go.

## Scope cuts if space or time runs short
Drop OSPF/IS-IS variants, the second VRF, stretch items, Grafana. Never drop measurements or evidence.
