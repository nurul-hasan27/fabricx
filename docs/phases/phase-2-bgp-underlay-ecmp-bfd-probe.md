# Phase 2 — BGP underlay, ECMP, BFD, and our own loss meter

## The goal, in kid words
Right now every floor monitor (leaf) only knows its own hallways. This phase teaches them to **shout** where they can be reached (BGP), so every monitor learns a path to every other monitor through **both** staircases (ECMP). We add a **fast heartbeat** (BFD) so a broken staircase is noticed in under a second, and we build a **stopwatch tool** (`fabricx-probe`) that counts lost notes.

## What I did, step by step
1. **Added an `underlay:` block to `inventory/fabric.yaml`** (BGP timers 3/9 s, BFD 300 ms x 3, max 2 paths). Still one source of truth. The model (`model.py`) now *derives* each switch's BGP neighbours from the links (`Fabric.neighbors()`).
2. **Extended the FRR template** (`templates/frr.conf.j2`): a `bfd` profile, `router bgp <ASN>`, a **peer-group** `FABRIC` (`remote-as external`, timers, BFD), one `neighbor <ip> peer-group FABRIC` per link, `network <loopback>/32` to advertise the loopback, and `maximum-paths 2` for ECMP. `no bgp ebgp-requires-policy` skips mandatory route-maps (the blueprint allows this for the lab).
3. **Turned on `bgpd` and `bfdd`** in the `daemons` file (`fabricx generate` now defaults to routing on).
4. **Wrote `src/fabricx/probe.py`** — sender sends UDP packets numbered 0,1,2... with a timestamp; receiver logs arrivals; `analyze()` computes **lost**, **longest gap** (= outage estimate) and **reordered**. Standard library only, so the same file runs on the Mac (unit tests) and inside containers (bind-mounted at `/opt/probe.py`; the FRR image already has Python 3.12).
5. **Unit-tested the probe** with synthetic data (clean run, a fake 40 ms outage, reordering, duplicates, nothing received): 5 tests, no lab needed.
6. **Deployed** the fabric and wrote 11 lab tests in `tests/lab/test_phase2_underlay.py`.
7. **Broke it on purpose** (gray failure, see below) to prove the tests can fail, restored, ran everything again.
8. Fixed one rule failure: my own "no IP literal in code" test caught an example IP in a docstring.

## Key terms
- **BGP / eBGP:** routers tell neighbours which addresses they can reach. "e" = between different AS numbers. Each leaf has its own AS (65001-65003); both spines share AS 65000 on purpose (RFC 7938 style): a route can't loop back through the other spine because spine2 sees its own AS in the path and drops it.
- **Peer-group:** one shared settings block for many neighbours.
- **ECMP (Equal-Cost Multi-Path):** two equally good paths, both used. Proven by the Linux kernel route having two `nexthop via ...` lines.
- **RIB vs FIB:** RIB = BGP's table; FIB = the kernel's forwarding table. We check the kernel's too (`ip route`), because "configured" is not the same as "used".
- **BFD (Bidirectional Forwarding Detection):** tiny packets every 300 ms; 3 misses = path declared dead. Much faster than BGP's 9 s hold timer.
- **Gray failure:** the link looks UP but silently drops packets. We create it with `tc netem loss 100%`.
- **Loopback `/32`:** the router's permanent address; advertised so all leaves can reach each other (and later the VXLAN tunnel end).
- **Probe resolution:** the probe's timing accuracy is about one send interval (plus scheduling jitter).

## Results (real)
- BGP: 12/12 session ends Established (6 links x 2).
- ECMP: every leaf has 2 kernel next-hops to each other leaf's loopback.
- BFD: all 12 session ends `up`.
- Loopback-to-loopback ping works for all leaf pairs.
- Probe leaf1 -> leaf3, 1 ms interval, 4 s: **4000 sent, 4000 received, 0 lost, 0 reordered, longest gap 3.12 ms**. So on this VM the probe's noise floor is about 3 ms; outages below that cannot be resolved. This goes into the E1 method notes.
- Gray failure test (100% loss on spine1:eth1, link still UP): within 1 s BFD went down on that link and leaf1 dropped to a single path to leaf3; the path tests failed while broken and the whole suite (41 tests: 13 unit + 28 lab) passed again after restore.

## What went wrong / lessons
- First check of my own "nexthop count" misread: with only one path the kernel prints `via` without the word `nexthop`, so a count of 0 means "single path".
- zsh doesn't split a variable holding a command; I used a shell function instead.
- Hosts still can't reach each other: no overlay yet (Phase 3).

## How to explain it in an interview
"eBGP Clos underlay with a shared spine ASN, ECMP verified at three levels (BGP, kernel FIB, later counters), BFD for sub-second failure detection, and a custom sequence-numbered UDP probe whose measurement resolution I documented. I verified the tests fail under a gray failure."
