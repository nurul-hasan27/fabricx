# versions.lock.md  (recorded 2026-11-20, Phase 0)

| Item | Value |
|---|---|
| Mac | M1 (arm64), 8 GB RAM, macOS Darwin 27.2.0 |
| OrbStack | 2.2.5 (via `brew install --cask orbstack`) |
| Lab VM | `fabricx-lab`, Ubuntu 24.04.5 LTS arm64 |
| Kernel (VM) | 7.2.12-orbstack-00394-gbecdd6130068 aarch64 |
| Docker (in VM) | 29.1.3 (Ubuntu docker.io package) |
| Containerlab | 0.83.0 (.deb from GitHub release) |
| FRR image | quay.io/frrouting/frr:10.2.1 — manifest has arm64 and amd64 — local digest sha256:e47e67bd612030cb1bedee2bde85b73913f2ea021573b749deb21d94940f03c1 (313 MB) |
| Host image | alpine:3.20 — sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc (14.6 MB) |
| /dev/kvm in VM | absent (so no SONiC-VM locally; expected) |
| tcp_dctcp module in VM | NOT available (modprobe fails) → E6 (DCTCP) must run on CI/cloud x86 |

## Measured (hello lab, idle)
- r1 (FRR container): 13.75 MiB, h1 (alpine): 1.07 MiB
- Host disk used by OrbStack + VM + images: free space went 40 GB → 36 GB

## Added in Phase 4
| Item | Value |
|---|---|
| Host image | fabricx-host:1 built from images/host/Dockerfile (alpine:3.20 + python3, iperf3, tcpdump, iputils, iproute2), image id sha256:8993553a58718bf5ad92381d13094db3578c98c3302bf41bc45a76fee69646b8, 84 MB |
| tcpdump in VM | installed with apt (for pcap capture/read) |
| Python (Mac venv) | 3.14.6; pydantic 2.14.4, jinja2 3.1.6, typer 0.29.2, pytest 9.2.0 |

## Added in Phase 7
| Item | Value |
|---|---|
| SONiC-VS image | official `docker-sonic-vs`, branch 202505, build 1238524 (commit ff3c0c9f6, built 2026-10-04), 228,399,828 bytes gz, sha256 40697b8c16096d418490dc59f571aaa3d35a0472c21a5e823c9b5a32c1a91005; loaded 850,770,450 bytes, amd64 (`artifacts/phase7/sonic-image.txt`) |
| FRR inside SONiC | 10.3 (sonic) |
| x86 runner | GitHub Actions `ubuntu-latest` (kernel 7.0.0-1020-azure in the logs), Python 3.12 / 3.14 venv |
| pytest-timeout | used in CI only |

## Added in Phase 8
| Item | Value |
|---|---|
| Prometheus | prom/prometheus:v3.1.0 (404 MB on disk in the VM) |
| Grafana | grafana/grafana:11.4.0 (629 MB on disk in the VM) |
| E6 x86 runner | kernel 7.0.0-1016-aws, 4 vCPU, tcp_dctcp loadable (`experiments/E6/results_ci/runner.txt`) |

## Added in Phase 9
| Item | Value |
|---|---|
| Test tools (pinned, `pyproject.toml` `dev` extra) | pytest 9.2.0, pytest-timeout 2.4.0, ruff 0.17.6, mypy 2.4.1, types-PyYAML 6.0.12.20261113 |
| Containerlab install | `scripts/vm_setup.sh` (0.83.0 .deb for amd64/arm64 from the GitHub release) |
| Clean-room host | Mac M1, VM kernel 7.2.12-orbstack, Python 3.14.6 (`artifacts/phase9/cleanroom.md`) |
