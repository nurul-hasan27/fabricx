# E8 — How does a route get from BGP to the "ASIC" inside SONiC?

**Where it ran:** GitHub Actions x86 runner (SONiC-VS is x86-only). Image: official `docker-sonic-vs`, branch `202505`,
build `1238524`, FRR 10.3 (`artifacts/phase7/sonic-image.txt`, sha256 recorded there). Leaf3 of the fabric is the SONiC
switch (`inventory/variants/sonic-leaf3.yaml`), cabled to the two FRR spines. Script: `run_e8.py`. Raw results: `results/`
(from run 44923272077).

**Tier:** BUILT + MEASURED for the database chain and the timings; the "ASIC" is SONiC's virtual switch library
(vslib), which programs the Linux kernel. Nothing here says anything about a real ASIC (Broadcom/NVIDIA), its tables or timing.

## 1. One route, hop by hop (`results/trace_route_loopback.md`)
leaf1's loopback `10.0.0.11/32`, as seen on the SONiC leaf:

| # | Program | Where | What was there |
|---|---|---|---|
| 1 | bgpd | FRR | two paths (via spine1 and spine2), AS path `65000 65001`, one best + one multipath |
| 2 | zebra | FRR RIB | installed, both next hops `fib=True`, `offloaded=True`; sent over FPM (`dplane_fpm_sonic`) |
| 3 | fpmsyncd | APPL_DB `ROUTE_TABLE:10.0.0.11` | `nexthop=10.1.1.4,10.1.2.4`, `ifname=Ethernet0,Ethernet4` (note: no `/32` in the key) |
| 4 | orchagent (routeorch) | ASIC_DB `SAI_OBJECT_TYPE_ROUTE_ENTRY` `{"dest":"10.0.0.11/32",...}` | points to one object id |
| 5 | orchagent | ASIC_DB `NEXT_HOP_GROUP` | type `DYNAMIC_UNORDERED_ECMP` |
| 6–9 | orchagent (neighorch) | ASIC_DB 2 × `NEXT_HOP_GROUP_MEMBER` + 2 × `NEXT_HOP` | `10.1.1.4` and `10.1.2.4`, weight 1 each |
| — | syncd | (reads ASIC_DB, calls SAI; in VS, vslib programs the kernel) | not traced separately |

So ECMP in SONiC is one SAI next-hop **group** with one **member** per path — the same two paths the FRR leaves use.

## 2. One interface, hop by hop (`results/trace_interface_Ethernet0.md`)
CONFIG_DB `PORT|Ethernet0` (intent: admin up, mtu 9100) → APPL_DB `PORT_TABLE:Ethernet0` (oper up) → STATE_DB
`PORT_TABLE|Ethernet0` (state ok, netdev up) → ASIC_DB SAI port object → COUNTERS_DB (packets in/out, after we switched
port counter polling on; it is off by default in SONiC-VS).

Finding: the SAI port object has **`SAI_PORT_ATTR_MTU = 9122`** for a 9100-byte port. orchagent adds 22 bytes of L2
overhead (Ethernet header 14 + VLAN tag 4 + FCS 4). The same +22 appears on the container's `eth1` wire, which is why our
MTU check had to look at `Ethernet0`, not `eth1` (Phase 7 bug list).

## 3. Timing (`results/timing.json`, N=10)
leaf1 announces `10.99.0.0/24` (an E8-only test prefix from the variant inventory); we poll the SONiC leaf.

| Measured from leaf1's announce command | min | median | max |
|---|---|---|---|
| in APPL_DB `ROUTE_TABLE` (consumed by orchagent) | 0.162 s | 0.165 s | 0.269 s |
| in ASIC_DB | 0.214 s | 0.219 s | 0.323 s |

- One poll (a `docker exec`) takes **0.053 s**, so that is the resolution.
- The ASIC_DB step came exactly **one poll after** `ROUTE_TABLE` in all 10 runs (0.052–0.055 s): orchagent's own work is
  **below what this method can measure** (≤ ~53 ms). Most of the ~0.2 s is BGP propagation leaf1 → spine → leaf3 and
  the commands themselves.

## 4. Where an orchagent fault shows up (`results/trace_orchagent_frozen.md`, `..._resumed.md`)
We froze orchagent with `SIGSTOP` (inside the lab container only), announced the test prefix, waited 10 s, traced again.

- bgpd: route present. zebra: installed, **`offloaded=True`** — even though nothing reached the ASIC.
- APPL_DB `ROUTE_TABLE:10.99.0.0/24`: **absent**. Instead the route sat in **`_ROUTE_TABLE:10.99.0.0/24`** and its key in
  **`ROUTE_TABLE_KEY_SET`** — still there 10 s later.
- ASIC_DB: no route entry.
- After `SIGCONT`: `ROUTE_TABLE` after 0.104 s, ASIC_DB after 0.160 s.

What this teaches (two things I had wrong before the experiment):
1. SONiC's producer/consumer tables: fpmsyncd **writes a staging key** (`_ROUTE_TABLE:…` + `ROUTE_TABLE_KEY_SET`);
   the visible `ROUTE_TABLE:…` entry appears only when **orchagent consumes** it. So "it's in APPL_DB" means "orchagent has
   taken it", and **a stuck orchagent shows up as keys piling up in `ROUTE_TABLE_KEY_SET`** — a concrete check for an escalation.
2. In this image's configuration, zebra's **`offloaded` flag is not proof** that the route reached ASIC_DB.

## 5. The QoS auditor against the real CONFIG_DB (`results/qos_*`)
| Stage | What we wrote into CONFIG_DB | Auditor | What orchagent programmed (ASIC_DB, Ethernet0) |
|---|---|---|---|
| 1 default | nothing (image default) | `QOS-000` info: no port has PFC, nothing to audit | no PFC on the port |
| 2 PFC only | `PORT_QOS_MAP` with `pfc_enable 3,4` + the AZURE maps | **10 findings**: 4 × QOS-007 error (no WRED/ECN on lossless queues 3,4), 4 × QOS-006 warn (no lossless BUFFER_PG), 2 × QOS-008 warn (no PFC watchdog) | `SAI_PORT_ATTR_PRIORITY_FLOW_CONTROL = 24` (binary 11000 = priorities 3 and 4), QoS maps attached — **no orchagent error or warning** |
| 3 complete | + lossless ingress buffer profile and `BUFFER_PG 3-4`, `QUEUE 3-4` → `AZURE_LOSSLESS` WRED/ECN, `PFC_WD` | **no findings** | queue 3 gets a `WRED_PROFILE_ID`, priority group 3 gets the lossless `BUFFER_PROFILE` |

The point: the switch **silently accepted a half-done lossless configuration** (stage 2) — it programmed PFC with no
error — while the auditor flagged exactly the missing pieces. That is the kind of mistake a config auditor exists for.
Buffer sizes used in stage 3 are configuration values chosen for the test, not measurements.

## Caveats
- The "ASIC" is vslib on the Linux kernel; real hardware adds its own SAI behaviour, table limits and timing.
- Timings are polled through `docker exec` (resolution ≈ 0.05 s) on a shared CI runner, one run of N=10.
- `offloaded=True` without ASIC programming was observed in this image/config; I did not check whether enabling FRR's
  `bgp suppress-fib-pending` (route-response feedback) changes that.
- The QoS test checks configuration consistency and what orchagent programs; veth has no PFC, so no pause frame was sent.
