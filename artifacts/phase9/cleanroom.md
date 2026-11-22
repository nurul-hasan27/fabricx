# Phase 9 clean-room rerun (2026-11-22, Mac M1, OrbStack VM `fabricx-lab`, kernel 7.2.12-orbstack, Python 3.14.6)

## Run 1 — the README as published (commit 23cc643, cloned from GitHub into a new folder)
Fresh-machine simulation: the `fabricx-host:1` image tag was removed first (layers kept), as a new VM wouldn't have it.

| Step (from the README) | Result |
|---|---|
| `python3 -m venv .venv && .venv/bin/pip install -e . pytest` | ok (pytest 9.2.0; no ruff, no mypy) |
| `make up` | **FAILED**: `Failed to pull image docker.io/library/fabricx-host:1 ... pull access denied` (the README never builds the host image) |
| built the image by hand: `docker build -t fabricx-host:1 images/host`, then `make up` | ok |
| `make test` | **FAILED**: `make: .venv/bin/ruff: No such file or directory` |
| installed ruff, mypy, types-PyYAML, pytest-timeout by hand, then `make test` | exit 0: 121 passed, **1 skipped** (`tests/unit/test_faults.py:27: no evidence bundles yet`), validate PASS, no drift, 28 requirements |

The skipped test read git-ignored evidence bundles from an earlier run, so it skipped on every fresh clone and in CI.

## Fixes (commit e56cbae, then the Phase 9 commit)
`make setup` (venv + pinned `.[dev]` + host image build), `make vm-setup` (`scripts/vm_setup.sh`), `--timeout=400` in
`make test`, the skipping unit test replaced by a lab test that writes its own bundle, REQ-FAULT-003 repointed, CI's
lab job runs `make vm-setup / setup / up / test`, `src/fabricx.egg-info/` (a build by-product that a fresh install
modified) removed from git.

## Run 2 — README commands only (commit e56cbae cloned into a new folder; host image tag removed again)
| Command | Result | Evidence |
|---|---|---|
| `make setup` | ok in 11.3 s; host image id `sha256:8993553a…` (same as Phase 4, i.e. from Docker's build cache) | this file |
| `make up` | ok, 10 containers running | — |
| `make test` | exit 0: ruff + mypy clean, **121 passed, 0 skipped**, validate PASS, no drift, 28 requirements, 1 min 58 s | `make-test.log`, `junit.xml`, `validate-report.md` |
| `make resilience` | exit 0: **15 passed** (14 fault round-trips + the new bundle test), 5 min 14 s | `make-resilience.log`, `junit_resilience.xml` |
| `fabricx trace` after both | identical to the committed `docs/traceability.md` | `traceability.md` |
| `git status` afterwards | only `docs/traceability.md` (ordering: trace ran before resilience) and `src/fabricx.egg-info/*` changed → egg-info untracked | — |

## Not covered by run 2
A brand-new arm64 VM (the existing VM already had Docker, Containerlab and the FRR image; `vm_setup.sh` found all of
them and installed nothing). Covered by run 3 below.

## Run 3 — brand-new arm64 VM (2026-11-22, commit 5e93511 cloned from GitHub into a new folder)
`orbctl create ubuntu:noble fabricx-fresh` (Ubuntu 24.04.5, kernel 7.2.12-orbstack, created in 45 s; no Docker, no
Containerlab, no images). The old `fabricx-lab` VM was **stopped** for the whole run, so nothing could come from it.
Only deviation from the README: the VM name, passed as `VM=fabricx-fresh` and `FABRICX_EXEC="orb -m fabricx-fresh sudo"`.

| Command | Result | Evidence |
|---|---|---|
| `make vm-setup` | ok in 3 min 4 s: installed docker.io (29.1.3) + tcpdump, "installing Containerlab 0.83.0 (arm64), found 'none'" | this file |
| `make setup` | ok in 25.5 s; host image built **without cache** (new id `sha256:1e133d45…`, alpine:3.20 pulled); Docker printed a "legacy builder is deprecated, install buildx" notice, harmless | this file |
| `make up` | ok in 1 min 5 s incl. pulling FRR 10.2.1 (313 MB); 10 containers running | `fresh-vm/make-up.log` |
| `make test` | exit 0: ruff + mypy clean, **121 passed**, validate PASS, no drift, 28 requirements, 1 min 57 s | `fresh-vm/make-test.log`, `fresh-vm/junit.xml` |
| `make resilience` | exit 0: **15 passed**, 4 min 53 s | `fresh-vm/make-resilience.log`, `fresh-vm/junit_resilience.xml` |
| `fabricx trace` after both | identical to the committed `docs/traceability.md` | — |
| VM disk afterwards | 4.3 GB used of the VM's root; images FRR 313 MB, host 84 MB, alpine 15 MB | this file |

**Bug found by run 3:** after `make test`, `orbctl list` showed the stopped `fabricx-lab` VM **running again**.
`src/fabricx/report.py` hardcoded `orb -m fabricx-lab sudo containerlab version` for the report's metadata, so `validate`
woke up the old VM and recorded *its* Containerlab version (on CI, with no `orb`, the field was empty). Fixed to use
the same `FABRICX_EXEC` prefix as every other lab command; re-ran `validate` with `fabricx-lab` stopped → PASS, version
read from `fabricx-fresh`, old VM stayed stopped (also through the whole resilience run).

## x86 fresh machine (GitHub Actions run 44991965377, commit 78f6469)
`make vm-setup RUN=sudo` → "installing Containerlab 0.83.0 (amd64), found 'none'", ready on x86_64 kernel
7.0.0-1016-aws, Docker 29.4.2; `make setup`, `make up`, `make test` → 121 passed, validate PASS, no drift,
28 requirements. One run so far.
