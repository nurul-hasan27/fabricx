# Phase 6 — Breaking things on purpose, finding out why, and more experiments (Milestone 2)

## The goal, in kid words
So far we built the school and checked it. Now a "naughty helper" breaks one thing at a time (a cut hallway, a monitor with a wrong name tag, a stuck monitor...). A **detective robot** (`fabricx diagnose`) then walks the school floor by floor, from the ground up, and says "the problem is on THIS floor, because of THIS clue". We test the detective **blind**: it is never told what was broken. We also run four more experiments and write two more detective reports.

## What I did, step by step
1. **Wrote the rule cards first** (`tests/specs/faults.yaml`, spec-first this time): what a fault, an evidence bundle, a diagnose rule and a blind drill must satisfy.
2. **E2 first**, because it decides a setting: does ECMP really spread traffic? (Answer below; it made me add `ecmp_hash_policy: 1` to the inventory.)
3. **Fault catalogue** (`src/fabricx/faults/catalogue.py`): 14 faults, each with `inject`, `restore`, its layer, the cause the detective should name, the customer symptom I *expect* (a hypothesis), and the first command that reveals it. They only run inside lab containers.
4. **Evidence bundle per run** (`fabricx run-fault F08`): baseline snapshot, state 2 s after injecting, state after settling, the blind diagnosis, restore, snapshot after, `timeline.json`, `manifest.json`, `report.md` under `artifacts/runs/`.
5. **`fabricx diagnose`** (`src/fabricx/diagnose.py`): collects live state (including an active test on every link, both directions) and applies pure rules layer by layer: L1 links, underlay MTU, BGP sessions, VTEP reachability, EVPN routes, VNI/VLAN maps, forwarding, FDB/ARP. The lowest failing layer is the **primary** diagnosis; findings above it are "probable consequences". 4 pure unit tests cover the rules (a healthy state plus one injected defect for each of 16 cause keys, and the layer-ordering rule).
6. **Blind drill** (`fabricx drill --seed N`): injects every fault in a random order; score = diagnose names the right cause in the right layer.
7. **Two drill passes.** Pass 1: 12/14. I analysed the two misses, fixed the rules, then ran pass 2 with a new seed: 14/14.
8. **E4 / E7 / E5** with raw data: EVPN misconfiguration symptoms, MAC mobility, OSPF and IS-IS underlay variants (new templates, iBGP route-reflector overlay).
9. **Round-trip resilience test** for all 14 faults (`make resilience`) and `make test` (91 tests plus validate, drift, trace).
10. Wrote RCA-002 (ECMP) and RCA-003 (route-target mismatch).

## Key terms
- **Fault injection:** breaking something on purpose in a controlled way, with an undo.
- **Blind drill:** the diagnoser is not told the answer. Score = how often it finds it.
- **Layered diagnosis:** check the bottom layer first; a broken floor below explains broken floors above.
- **Cause key:** a short name for a root cause (`rt-mismatch`, `bgp-asn-mismatch`...) used to score diagnoses.
- **Route-target (RT):** the label deciding which VNIs import which EVPN routes. If two leaves use different labels they ignore each other.
- **MAC mobility:** when a host moves, the new leaf advertises its MAC with a higher sequence number so everyone updates.
- **Route reflector (RR):** a spine that re-advertises iBGP routes so leaves don't need a full mesh.
- **OSPF / IS-IS:** link-state routing protocols, alternatives to eBGP for the underlay.
- **Spec-first:** write the requirement and test names before the code.

## Results (real, from files)
- **Catalogue:** 14 faults, all restore cleanly (`make resilience`, see log in BUILD_LOG).
- **Blind drill:** pass 1 **12/14**, pass 2 **14/14** (E9 analysis lists the misses and the caveat that pass 2 used rules tuned on pass 1).
- **E2:** plain routed flows spread 53/47 and 58/42 with hash policy 1 and 100/0 with policy 0; **VXLAN flows from a Linux VTEP stayed 100/0 under both**, although 64+ outer UDP source ports were visible.
- **E4:** RT mismatch and VNI mismatch break same-subnet traffic across leaves only; two of my symptom hypotheses (F10, F12) were wrong.
- **E7:** live-migration style move: median outage 9.4 ms, 0 lost packets; cold move: ~0.7 s, dominated by the host being absent.
- **E5:** with BFD, gray failure costs ~0.75 s (OSPF) / ~0.81 s (eBGP) / ~1.6 s (IS-IS); without BFD 7 to 31 s. Detection dominates; protocol matters little.

## What went wrong / lessons
1. **My fault F06 first looked like a BGP ASN mismatch but killed the session through BFD**, so the "Bad Peer AS" clue I planned never appeared; the diagnoser missed it. Lesson: confirm the real signature of a fault before writing the rule.
2. **FRR keeps a "duplicate MAC" flag after the cause is gone**; restore had to clear it. Also the first duplicate-MAC rule looked at the wrong clue.
3. **Two hypotheses about symptoms were wrong** (F10, F12). Recorded, not edited away.
4. **E2 surprised me:** I expected policy 1 to fix ECMP for overlay traffic; it doesn't on a Linux VTEP. The cause is a hypothesis, not verified.
5. **E5 OSPF variant:** some Type-5 routes never appeared; IS-IS did not show it. *(Cause found in Phase 7: a start-up race, now fixed - see phase-7 note.)* Runs where the fault missed the flow are reported separately.
6. A few shell mistakes (`setsid` does not exist on macOS, a zsh variable that is not word-split) cost time; the E5 script ran twice by accident (the first attempt never started).
7. Still open: GitHub CI has never run; Phase 7 needs x86 (SONiC) and may use Azure.

## How to explain it in an interview
"I wrote a 14-fault catalogue with undo and evidence bundles, and a rule-based layered diagnoser that is scored blind: 12 of 14 before tuning, 14 of 14 after, and I can tell you exactly which two it missed and why. The experiments gave surprises I reported as such: Linux VXLAN pins flows to one uplink whatever the hash policy, BFD matters far more than the choice of underlay protocol, and removing an L3VNI mapping did not instantly cut traffic."
