# Phase 5 — Hardening the engine, drift detection, spec-driven tests, CI

## The goal, in kid words
The robot inspector from Phase 4 works, but it is still a bit fragile: it may hang if a monitor falls asleep, it cannot tell if somebody secretly scribbled on a monitor's instruction sheet, and nobody can see *why* each test exists. This phase makes the inspector tougher, adds a "was the sheet changed?" detector (**drift**), writes each rule as a short card (**spec**) with a table linking rules to tests (**traceability**), and prepares an **automatic school-checker** (GitHub Actions **CI**) that runs everything on every change.

## What I did, step by step
1. **Code quality gates.** Installed `ruff` (style/bug linter) and `mypy` (type checker), configured them in `pyproject.toml`, fixed all findings (32 style items, 2 typing issues). `make lint` now runs both.
2. **Tougher runner** (`runner.py`): every command has a timeout and retries; a stopped / paused / silent container raises `NodeUnreachable` instead of hanging. Collectors catch it and record `unreachable`; the validators skip that node and add a `node-unreachable` finding.
3. **Drift detection** (`drift.py`, `fabricx drift`): compares each switch's running FRR config (`show running-config`) with what the inventory would generate now. Each line is stored with its parent path (`router bgp 65001 > address-family ipv4 unicast > maximum-paths 2`), so a line in the wrong block counts as drift. A short explicit list of lines FRR adds or hides by itself is ignored.
4. **More CLI:** `fabricx deploy`, `destroy`, `drift`, `report`, `trace` (plus `generate`, `validate` from before). `inject`/`restore`/`diagnose` belong to Phase 6.
5. **Spec-driven tests:** 16 requirement cards in `tests/specs/*.yaml` (ID, requirement, steps, pass criteria, tests, evidence). `fabricx trace` checks every card points at real tests, reads the JUnit XML from the last run, and writes `docs/traceability.md`.
6. **Tests that settle first:** a new `tests/conftest.py` makes every lab test module wait until the fabric is healthy and quiet, so a previous test's disturbance can't leak in.
7. **CI** (`.github/workflows/ci.yml`): job 1 lint + types + unit + *config-diff* (regenerate and fail if `generated/` differs from what is committed) + trace; job 2 deploys the lab on a free x86 runner and runs the whole suite, validate and drift; job 3 Trivy-scans the lab images. Makefile has `RUN=sudo` so the same commands work on the runner.
8. **Trivy scan** run for real (in the VM, image removed afterwards).
9. `make test` is now: lint + types + 77 tests (JUnit XML) + `validate` + `drift` + `trace`.

## Key terms
- **Drift:** the live device no longer matches the intended config (somebody typed something by hand).
- **Spec-driven / traceability:** every requirement has an ID, a pass rule and linked tests, so you can answer "which test proves requirement X?"
- **JUnit XML:** a standard test-result file that CI tools understand.
- **CI (Continuous Integration):** a robot that rebuilds and tests the project on every push.
- **Config diff:** CI regenerates files and fails if committed copies are stale.
- **Trivy:** scans container images for known vulnerabilities (CVEs).
- **Timeout / retry:** give up after N seconds / try again before giving up.
- **mypy / ruff:** type checker / linter.

## Results (real)
- `make test`: lint OK, mypy OK, **77 tests passed** (35 unit, 42 lab), `validate` PASS, `drift` "no drift", `trace` 16 requirements, all with passing tests.
- Drift check on the live lab: a hand-made `neighbor FABRIC timers 1 3` on leaf2 and a rogue `ip route 192.0.2.0/24 blackhole` on spine1 were both reported (exit 1); reverting gave exit 0.
- Paused leaf3: reported as `node-unreachable`, the rest still checked, no crash.
- Trivy (HIGH/CRITICAL): `fabricx-host:1` 2 HIGH (musl); `frr:10.2.1` 41 HIGH + 2 CRITICAL (mostly libssl/libcrypto, libexpat, musl). **Both images are Alpine 3.20, which Trivy reports as end-of-support.** Acceptable for an isolated lab, not for production; noted in the limitations.

## What went wrong / lessons
1. **A wrong claim from Phase 3.** The drift check flagged `nexthop-unchanged` as "missing from the running config" on the spines. Investigating showed FRR 10.2.1 never lists it and EVPN works without it (FRR keeps the VTEP as next hop by default). I had assumed it was required without testing. Removed the line and corrected the Phase 3 docs (see the CORRECTION note in `docs/BUILD_LOG.md`).
2. **Test pollution.** After the paused-node test BGP needed a while to re-establish, and later tests failed or showed 300 ms probe gaps. Fixed with the settle fixture. Lesson: tests that disturb the lab must wait for recovery.
3. **A noise-sensitive threshold.** The healthy-fabric probe test failed at 68 ms and 303 ms gaps with zero loss. A 50 ms limit was too tight for a shared VM; I set 250 ms (real failover is >= 700 ms) and documented why.
4. A YAML spec failed to parse because a value started with a backtick; quoted it.
5. Trivy's vulnerability DB download timed out once; I had also deleted the cache too early. Retried.
6. **Not verified:** the GitHub Actions workflow has **not been run** (no GitHub repo exists yet), so the x86 run and experiment E10 (reproducible on both architectures) are still open. Specs were written *after* most tests existed, not before; from Phase 6 on I write the spec first.

## How to explain it in an interview
"The engine fails loudly and specifically: timeouts, unreachable nodes as findings, and drift detection that compares running config with generated intent by block path. Requirements live as YAML specs and a generated traceability matrix ties each to tests and evidence. My own drift checker caught a mistaken assumption of mine, which I corrected in the docs."
