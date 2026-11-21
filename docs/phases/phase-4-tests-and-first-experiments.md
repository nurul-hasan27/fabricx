# Phase 4 — The test suite, the first experiments, the first root-cause report (Milestone 1)

## The goal, in kid words
Until now we checked things by hand. Now a **robot inspector** walks the whole school, asks every monitor "who are your friends, are the hallways OK?", compares the answers with the school plan, and writes a **report card**. Then we play two experiments: (1) what happens to the notes when a staircase breaks, and (2) what happens when one hallway is too narrow for the big envelopes. Finally we write the **detective report** (RCA).

## What I did, step by step
1. **Host image.** Built `fabricx-host:1` (Alpine + Python + iperf3 + tcpdump + iputils) once in the VM (84 MB). Hosts need these to send probes and big transfers.
2. **VXLAN DF bit.** Set `vxlan_df: set` in the inventory (RFC 7348: VTEPs must not fragment). Needed for a realistic MTU experiment.
3. **Parsers** (`parsers.py`): turn raw device output (FRR JSON, `ip -j link`, route text) into small Python dicts. Unit-tested against **real captured fixtures** (`tests/fixtures/`), so they run on the Mac with no lab.
4. **Collectors** (`collectors.py`): run commands on nodes and **always save the raw output** first (`artifacts/validate/<time>/raw/...`), then parse. Also primes silent hosts so EVPN has learned them.
5. **Validators** (`validators.py`): pure functions that compare the *intent* (computed from the inventory) with the *state*. Checks: BGP, BFD, ECMP next-hop count, link state + MTU, EVPN route types. 12 unit tests build a good state, then break one thing at a time and assert the right finding appears.
6. **Report writer + CLI:** `fabricx validate` writes `report.json` + `report.md` and exits 1 on any finding. `make test` = pytest (65 tests, with `smoke` / `functional` markers) + `fabricx validate`.
7. **Proved the inspector can fail:** took a link down, `validate` listed 10 findings and exited 1; restored, it passed.
8. **E1 (link failure):** harness `experiments/E1/run.py` sends 1 ms probes h1 -> h3, finds which leaf1 uplink the flow really uses, then fails it by (a) carrier loss or (b) gray failure, with three detection profiles. 10 runs per cell, raw data kept.
9. **E3 (MTU):** one link at 1500; bisect the biggest DF ping that passes; iperf3; then also drop ICMP "frag needed".
10. **Wrote** RCA-001, the experiment analyses, `docs/limitations.md`, and the README.

## Key terms
- **Intent vs state:** intent = what the inventory says should be true; state = what the devices say is true. Validation = compare them.
- **Fixture:** a saved real output used as test input.
- **Raw vs normalised:** keep the exact device text, and separately the cleaned numbers, so you can always check the robot.
- **Gray failure:** link looks up, drops traffic. **Carrier loss:** link goes down cleanly.
- **BFD:** fast heartbeat (300 ms x 3). **BGP hold timer:** how long BGP waits before giving up on a silent neighbour (9 s here, 180 s by default).
- **Outage / loss window:** the longest gap between received probe packets. Resolution is about the probe interval plus jitter (3-9 ms in this VM).
- **Censored measurement:** a run that ends before the outage does, so the real outage is longer than what was measured.
- **PMTUD black hole:** a too-big packet is dropped and the ICMP message telling the sender to shrink never arrives, so the transfer stalls silently.
- **DF bit:** "Don't Fragment"; a packet with it set is dropped, not split, if too big.

## Results (real, from files)
- `make test`: **65 passed** + validation report PASS.
- E1 carrier loss: median **4.6 ms** (BFD) / **3.2 ms** (no BFD) over 10 runs, i.e. noise floor: veth carrier loss is instant.
- E1 gray failure: median **812 ms** with BFD, **10.3 s** with BGP 3/9 s only, **141 s / 192 s / >=197 s** with BGP defaults (N=3).
- E3: largest DF ping that works across a 1500-byte link is **1422** bytes (theory 1500-50-28). TCP still ran at ~5 Gbit/s while ICMP worked, and **stalled at 0 bit/s** once ICMP frag-needed was dropped.

## What went wrong / lessons
1. My probe analysis ignored an outage that was still going when the sender stopped (the 200 s default-timer runs showed it). Fixed in `aggregate.py` and documented.
2. `fabricx validate` first failed on a fresh lab because silent hosts weren't learned by EVPN yet; the collector now primes hosts.
3. My first E3 guess ("ping works, transfer stalls" will just happen) was wrong: Linux handles PMTUD fine. The stall only appears when ICMP is suppressed. Worth saying out loud in an interview.
4. busybox `date` has no nanoseconds, so I added a `now` mode to the probe tool for timestamps.
5. Not done: GitHub Actions CI and the Mac-side `ruff`/`mypy` (Phase 5). The README says so.

## How to explain it in an interview
"I validate intent against live state with pure functions, keep raw output beside parsed output, and prove checks can fail. Measured: BFD cuts a gray-failure outage from about 10 s (9 s hold timer) to under a second, while clean carrier loss is instant regardless. For MTU I derived the exact 1422-byte boundary and showed the stall needs ICMP suppression, which is a classic real-world escalation."
