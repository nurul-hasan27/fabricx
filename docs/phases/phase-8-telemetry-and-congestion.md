# Phase 8 — Telemetry and the congestion study

## The idea in simple words
**Telemetry** = a nurse who checks every patient every few seconds and writes it on a big chart on the wall.
Here the "patients" are the switches: is each BGP and BFD session up, how many EVPN routes are there, how many bytes
and drops on each port. **Prometheus** keeps the chart (a time-series database), **Grafana** draws it, and every time
our naughty helper breaks something it pins a red note on the chart (an **annotation**), so you can see the cause next
to the effect.

**E6** answers the "traffic jam" question. Four classrooms send notes to one classroom through one narrow door
(**incast**). Either the queue at the door grows until notes fall on the floor (**tail-drop**), or the monitor stamps
"slow down!" on notes early (**ECN**), and the senders slow down — gently and in proportion with **DCTCP**. AI clusters
care about this because collective operations are incast by nature; RoCE does the same thing with ECN + DCQCN.

## Step by step
1. **Exporter** (`src/fabricx/exporter.py`, `fabricx exporter`): one `docker exec` per switch per scrape collects BGP
   summary, BFD peers, EVPN routes and `ip -s link` counters, parsed with the same parsers as `validate`, served in
   Prometheus text format with the standard library only. Metrics: `fabricx_bgp_peer_up`, `fabricx_bfd_peer_up`,
   `fabricx_evpn_routes{type}`, `fabricx_iface_{rx,tx}_{bytes,dropped}_total`, `fabricx_up`, `fabricx_poll_seconds`.
2. **Monitoring stack** (`scripts/monitoring.sh up|down`, `monitoring/`): Prometheus v3.1.0 and Grafana 11.4.0 in the
   lab VM, one provisioned dashboard (health, BGP/BFD timelines, leaf-uplink throughput = ECMP balance, drops, EVPN
   routes) and a "Fault injection" annotation layer.
3. **Annotations** (`src/fabricx/annotate.py`): the fault runner posts one on every inject and restore.
4. **Acceptance demo** (`experiments/telemetry/run_demo.py`): 200 Mbit/s h1 → h3, F01 (leaf1 eth1 down) at +30 s,
   restore at +60 s; evidence pulled back from Prometheus and Grafana into `experiments/telemetry/results/`.
5. **E6** (`experiments/E6/`): incast study, on the Mac (A, B) and on GitHub x86 (A, B, C) via `.github/workflows/e6.yml`.
6. **RoCE test plan** (`docs/roce-test-plan.md`).

## What went wrong (and what it taught)
| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | Inject annotation missing in the first demo | first request to a fresh Grafana took > 3 s; the failure was silent | 5 s timeout, one retry, failures printed (unit-tested) |
| 2 | Uplink graph showed 280 Mbit/s for a 200 Mbit/s flow, then 0/double values with `irate` | **my exporter design**: it polled on its own 5 s timer while Prometheus scraped on another, so scrapes saw stale or doubled counters | exporter now **collects on scrape** (the standard pattern); numbers became consistent and the dashboard lag is at most one scrape (the old design could add a second 5 s stage) |
| 3 | HTB shaper gave 16–56 Mbit/s of 100 in the Mac's VM | VM timer behaviour | TBF shaper (92–95 Mbit/s), measured in `experiments/E6/shaper_check_mac.txt` |
| 4 | RED scenario: 36 % of pings lost, RTT looked too good | ping is not ECN-capable, RED drops it; survivors were the lucky ones | ping sent as ECT(0) (`-Q 2`) + TCP's own RTT as a second source; both agree |
| 5 | "114.5 Mbit/s through a 100 Mbit/s shaper" | I summed per-sender averages over different time windows | total over the common time span; raw per-sender bytes kept |
| 6 | `tc` parser missed the ECN marks | text-format detail | parser moved into `parsers.py` with a unit test on real output |
| 7 | DCTCP scenario failed on CI: "congestion control is cubic" | containers may only select algorithms on the host's *allowed* list | runner adds `dctcp` to `net.ipv4.tcp_allowed_congestion_control` |
| 8 | B runs split into "almost no drops" and "~1600 drops" | (found, not a bug) some connections fall back to non-ECN after a dropped SYN | evidence via handshake capture at the receiver |

## Results
**Telemetry** (`experiments/telemetry/results/summary.md`, `timeline.svg`): both annotations posted; leaf1's eth1 uplink
went to 0 and eth2 carried the whole ~213 Mbit/s while the link was down, then traffic shared both uplinks again; the
dashboard showed the BGP change 4.6 s after inject and 4.4 s after restore (≤ one 5 s scrape); iperf3's 1-second
throughput showed **no visible dip** (≈ 200 Mbit/s before and after) — consistent with E1, where carrier-loss failover
takes milliseconds.

**E6** (`experiments/E6/analysis.md`, x86, N=5):
| | tail-drop | RED+ECN, cubic | RED+ECN, DCTCP |
|---|---|---|---|
| queue delay (median ping RTT) | 111 ms | 2.06 ms | 2.67 ms |
| drops per run (median) | 112 | 1597 (6–1716) | 0 |
| Jain fairness | 0.961 | 0.980 | 1.000 |
Plus the surprise: classic ECN lost packets because some connections never negotiated ECN; DCTCP kept ECN on every
connection and lost nothing.

## Honest status (tiers)
| Item | Tier |
|---|---|
| FRR exporter → Prometheus → Grafana with fault annotations | BUILT + MEASURED (demo with real timestamps) |
| E6 incast: tail-drop vs RED+ECN vs DCTCP | EMULATED + MEASURED (Linux queues, x86 CI, N=5) |
| gNMI streaming from SONiC | NOT POSSIBLE with the pinned SONiC-VS image (no gNMI service; Phase 7 probe) |
| RoCE on real hardware | STUDIED (test plan only) |
| Soft-RoCE spike | NOT DONE (stretch) |

## How to explain it in an interview
"I wrote a small Prometheus exporter for the FRR fabric and had the fault injector annotate Grafana, so a link failure
shows up as a BGP/BFD state change and an uplink shift right next to its cause. A first version polled on its own timer
and produced impossible rates — fixing it to collect on scrape was a nice lesson in how Prometheus counters work. Then I
built an incast experiment: four senders into one shaped port. Tail-drop kept the queue full — 111 ms of queueing for
a link that idles at 0.06 ms. ECN marking cut that to about 2 ms, but classic ECN still dropped packets, and a capture
showed why: connections whose SYN was dropped retried without ECN, so RED dropped their data. DCTCP kept ECN on every
connection, lost nothing and shared perfectly — the same reason RoCE fabrics pair ECN with DCQCN and keep PFC as the
last resort."
