# Phase 9 — Clean-room rerun, final docs and the demo (Milestone 4)

## The goal, in kid words
We built a big Lego castle. Now we pretend we're a **stranger** who has only the instruction booklet (the README): we
take a brand-new box (a fresh `git clone`), follow the booklet word for word, and see whether the castle still comes
out right. Every place where the booklet was missing a step gets fixed in the booklet, not by remembering. Then we
tidy the shelf: one honest "what this can't do" page, a 6-minute show-and-tell script, and resume lines whose numbers
all come from the castle's own records.

## What I did, step by step
1. **Clean-room run #1: followed the old README literally** in a fresh clone (`~/Developer/fabricx-cleanroom`, cloned
   from GitHub). To act like a fresh machine I hid the lab host image (removed its tag, kept its layers).
2. **It failed twice, exactly where a stranger would get stuck:**
   - `make up` → `pull access denied for fabricx-host` — the README never said to build the host image.
   - `make test` → `.venv/bin/ruff: No such file or directory` — the README's install line had no ruff or mypy.

   After working around both by hand: 121 passed, **1 skipped**, validate PASS, no drift.
3. **The skipped test was a real gap.** `test_bundle_layout` only read evidence bundles left on disk by an earlier run.
   Those are git-ignored, so on a fresh clone (and in CI) it **always** skipped and checked nothing. I replaced it with a
   lab test that runs a full fault (F02) into a temporary folder and checks the bundle it wrote
   (`tests/lab/test_faults_roundtrip.py::test_run_fault_writes_complete_bundle`). The traceability check failed
   straight away because REQ-FAULT-003 still pointed at the old test, which is exactly what that check is for; I
   repointed it.
4. **Fixes so the booklet is complete:**
   - `make vm-setup` (`scripts/vm_setup.sh`): installs Docker, tcpdump and Containerlab 0.83.0 for the right CPU type.
     It is idempotent: on the existing VM it found everything and changed nothing.
   - `make setup`: venv + `pip install -e '.[dev]'` (test tools pinned in `pyproject.toml`) + builds the host image.
   - `make test` now passes `--timeout=400` per test on the Mac too (it was CI-only).
   - **CI now runs the README's own commands** (`make vm-setup`, `setup`, `up`, `test`) on a brand-new x86 machine
     on every push. So "fresh clone on a fresh VM → green" is re-checked automatically, not once by hand.
5. **Clean-room run #2:** committed the fixes locally, cloned that commit into a fresh folder, hid the host image again,
   then ran only the README's commands. Results are below; logs are in `artifacts/phase9/`.
6. **Docs:**
   - README rewritten as the final front page: quick start from nothing, reading order, the honest-scope box, and an
     evidence index where every claim links to its file.
   - `docs/limitations.md` merged into one complete page, including what the clean-room run did *not* cover.
   - `docs/DEMO.md`: the 6-minute demo script, rehearsed on the lab (`artifacts/phase9/demo-rehearsal.txt`).
7. **Private notes** (git-ignored `docs/private/`, like the blueprint): resume bullets where every number names its
   file, and an interview rehearsal. That rehearsal marks the places where the blueprint's model answers claim
   things this project didn't do (for example "every resilience test runs twice in CI").

## Key terms
- **Clean-room run:** rebuild from nothing but the published instructions, to prove the result doesn't depend on
  anything that only exists on the builder's machine.
- **Idempotent:** running it twice is the same as running it once; safe to re-run.
- **Pinned version:** an exact version number (`ruff==0.17.6`), so a future install gets the same tool.
- **Build cache:** Docker reuses layers it already has; fast, but it means the rebuild wasn't from zero.

## Results
All from `artifacts/phase9/` (`cleanroom.md` is the step-by-step record).

| Run | What | Result |
|---|---|---|
| Clean-room #1 (old README) | `make up` | failed: host image missing |
| | `make test` | failed: ruff missing; after hand fixes 121 passed, **1 skipped** |
| Clean-room #2 (fixed README) | `make setup` | ok, 11.3 s (host image from build cache) |
| | `make test` | **121 passed, 0 skipped** (78 unit + 43 lab), validate PASS, no drift, 28 requirements, 1 min 58 s |
| | `make resilience` | **15/15** (14 fault round-trips + new bundle test), 5 min 14 s |
| | traceability after both | identical to the committed matrix |
| Demo rehearsal | all script steps | F08 → same-subnet ping 100 % loss, routed ping ok, `diagnose` names `rt-mismatch` at layer "EVPN routes", restore → validate PASS, both Grafana annotations posted; every command < 5 s except `diagnose` (~12 s); prep `run-fault F08` 53 s |
| Resources | 10 lab containers | ~125 MB RAM in total; images FRR 313 MB + host 84 MB (`resources.txt`) |

## What went wrong (and what it taught)
| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `make up` failed on a fresh setup: `pull access denied for fabricx-host` | host image build was in CI only, never in the README | `make setup` builds it |
| 2 | `make test` failed: ruff not found | README install line was out of date with the Makefile | pinned `dev` extra; CI uses the same one |
| 3 | 1 test skipped on every fresh clone and in CI | the test depended on leftover git-ignored files | turned into a self-contained lab test |
| 4 | My first README draft had spine ASN 65100, "Intel Macs" and "4 GB RAM" | written from memory, not from files | checked against `inventory/fabric.yaml` and a measured `resources.txt`; Intel stays "not tested" |
| 5 | The demo script said `validate` checks the traffic classes and isolation | it doesn't: the lab tests and `diagnose` do | wording fixed after reading `validators.py` |
| 6 | A fresh install changed 6 tracked files | `src/fabricx.egg-info/` (a pip build by-product) had been committed in the first public commit | removed from git, `*.egg-info/` ignored |

## Honest status
| Item | Tier |
|---|---|
| Fresh clone → green suite with only the README (Mac) | BUILT + RUN (existing VM reused; host image from Docker's cache) |
| Fresh x86 machine on every CI push, README commands | BUILT (first run of the new workflow: see BUILD_LOG) |
| Brand-new arm64 VM from scratch | NOT DONE (would download ~0.5 GB; needs your OK) |
| Demo video | script and rehearsal done; recording is yours to do |

## How to explain it in an interview
"Before calling it done I did a clean-room run: a fresh clone, following only the README. It failed twice — the README
never built the host image and didn't install the lint tools — and it showed one test that silently skipped on every
fresh machine, so it had never really run in CI. I fixed the instructions, not my machine, turned that test into a
self-contained one, and made CI run the README's exact commands on a new VM every push. So reproducibility is now
tested continuously, not claimed."
