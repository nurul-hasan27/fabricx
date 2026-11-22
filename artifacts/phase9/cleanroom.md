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

## Not covered
A brand-new arm64 VM (the existing VM already had Docker, Containerlab and the FRR image; `vm_setup.sh` found all of
them and installed nothing). The x86 fresh-machine path is covered by CI on every push.

## x86 fresh machine (GitHub Actions run 44991965377, commit 78f6469)
`make vm-setup RUN=sudo` → "installing Containerlab 0.83.0 (amd64), found 'none'", ready on x86_64 kernel
7.0.0-1016-aws, Docker 29.4.2; `make setup`, `make up`, `make test` → 121 passed, validate PASS, no drift,
28 requirements. One run so far.
