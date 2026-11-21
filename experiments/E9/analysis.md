# E9 analysis — blind drill

Two passes over all 14 catalogue faults in a seeded random order (`fabricx drill --seed N`); diagnose sees only live state + inventory. Table: `results.md`.

| Pass | Seed | Localised | Notes |
|---|---|---|---|
| 1 (first version of diagnose) | 11 | **12/14** | misses: F06, F12 |
| 2 (after fixing the two misses) | 22 | **14/14** | F06 and F13 also report a generic `bgp-session-down` beside the specific cause |

## Miss analysis (pass 1)
- **F06 BGP ASN mismatch** was reported as HEALTHY. Two weaknesses: no rule flagged a BGP session that was simply not Established, and the expected evidence ("Bad Peer AS" notification) never appears here because removing the neighbour from the peer-group also removed its BFD config, so the session died on BFD before any OPEN exchange. Fix: compare each neighbour's configured `remoteAs` with the peer's real AS from the inventory, and add a generic `bgp-session-down` fallback so no dead session is invisible.
- **F12 duplicate MAC** was reported as HEALTHY. My rule looked for the same MAC advertised from two VTEPs in the same instant, but MAC mobility makes the older advertisement disappear. FRR itself exposes the evidence (`show evpn mac vni N json`: `isDuplicate`, `detectionCount`). Fix: read those fields. A second fix: the fault's restore now clears FRR's duplicate flag, which otherwise stayed set after the fault was gone.

## Honest caveats
- Pass 2 used rules tuned on the pass-1 misses, so 14/14 measures the fixed rules on the same catalogue, not generalisation to unseen faults. Pass 1 (12/14, before tuning) is the cleaner blind number.
- The faults are ones I wrote; diagnose rules and faults share an author, so there is selection bias.
- A fault outside the catalogue ("`no advertise-all-vni` on leaf2", `experiments/E4/extra_advertise_all_vni.json`) was diagnosed at the right layer but as `missing-l3vni`, a symptom, not the true cause; a rule for it (`advertise-all-vni-missing`) was added afterwards and is unit-tested only.
- Diagnosis takes about 12 to 30 s (active link tests on all 6 links).

## Later changes and re-check
After the two drill passes, two restore problems and one rule problem surfaced when I added a drift assertion to the round-trip test:
- F08's restore left an empty `vni 10010` stanza in leaf2's config (drift found it); restore now removes the stanza.
- F12's restore left FRR move counters behind and the old MAC entry on h3's port; restore now deletes that entry and clears the counters. The duplicate-MAC rule was tightened to ignore stale counters on a MAC that is currently remote (`type=local` plus a high count, or FRR's own `isDuplicate` flag).
- Re-check drill (seed 33, F12 + F08 + F13 only, `results_recheck/`): 3/3 localised. `make resilience`: 14/14 round-trips end with validate clean **and** drift clean.
