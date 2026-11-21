# E6 — What does incast do to a switch queue, and how much do ECN and DCTCP help?

**Tier: EMULATED + MEASURED.** Linux queues on a veth port stand in for a switch buffer; DCTCP (a TCP sender) stands
in for DCQCN (what RoCE NICs do). The *mechanisms* are real; the numbers say nothing about a switch ASIC.

## Question and hypothesis
When several hosts send to one host at once (**incast**, the normal pattern of AI all-reduce/all-to-all), the switch
port toward the receiver becomes the bottleneck and its queue fills.
Hypothesis: (A) with a plain tail-drop queue the queue stays full, so every packet waits the full buffer time;
(B) ECN marking at a low threshold keeps the queue short without losing throughput; (C) DCTCP, which reacts to *how
many* packets are marked rather than halving, keeps it short **and** avoids loss.

## Method (`run.py`, `inventory/variants/e6-incast.yaml`)
- 4 senders → 1 receiver: h1, h2, h6 (leaf1) and h4 (leaf2) → h3 (leaf2). Each sender runs iperf3 with 2 TCP
  streams for 20 s (12 TCP connections incl. iperf3's control connections). Traffic from leaf1 crosses the VXLAN
  fabric; marking happens on the inner packet after decapsulation.
- Bottleneck: leaf2's port to h3, shaped to **100 Mbit/s with TBF**; under it either
  **A** tail-drop `pfifo` of 1000 packets (≈121 ms when full), or
  **B/C** `red` with ECN marking from ~30 KB queued (≈20 packets ≈ 2.4 ms) — same queue for B and C.
  Hosts: A cubic + ECN off, B cubic + ECN on, C DCTCP (needs the kernel's `tcp_dctcp`).
- Measured per run: throughput (receiver bytes over the common time span), Jain fairness over the 4 senders, queue
  drops and ECN marks (`tc -s` of the child queue, unit-tested parser), RTT through the queue by ping every 50 ms
  **sent as ECN-capable** (`-Q 2`) and TCP's own smoothed RTT, retransmits, and a packet capture of every handshake at
  the receiver (which connections negotiated ECN). N = 5 runs per scenario.
- **Where:** all three scenarios on one GitHub x86 runner (kernel 7.0.0-1016-aws; `results_ci/`), because the Mac's VM
  has no `tcp_dctcp`. A and B were also run on the Mac as a cross-check (`results_mac/`).

## Results (x86, N=5; median and range — `results.md`, raw JSON in `results_ci/`)
| | A tail-drop, cubic | B RED+ECN, cubic | C RED+ECN, DCTCP |
|---|---|---|---|
| throughput (Mbit/s) | 95.6 (95.6–95.7) | 100.3 (94.7–100.5)* | 95.6 (95.5–95.6) |
| RTT through the queue, median (ping) | **111 ms** | **2.06 ms** | **2.67 ms** |
| RTT p99 (ping) | 121 ms | 3.75 ms | 3.73 ms |
| TCP's own mean RTT | 108.8 ms | 2.88 ms | 3.06 ms |
| queue drops per run | 112 (96–118) | 1597 (6–1716) | **0** (0–1) |
| retransmits per run | 111 (95–116) | 1590 (0–1703) | **0** (0–1) |
| ECN marks per run | – | 21 338 | 100 337 |
| Jain fairness | 0.961 | 0.980 | **1.000** |
| connections without ECN (of 12) | 12 (ECN off) | **1–3 in every run** | 0 |

Idle RTT before load: 0.056 ms. *B's totals above 100 are within the ±5 % resolution of the total (iperf3 start
times are whole seconds).

## What the data says
1. **Tail-drop = the queue is always full.** Median RTT 111 ms against 0.056 ms idle — ~2000× — and the p99 (121 ms) is
   exactly the full 1000-packet buffer at 100 Mbit/s. Throughput is fine; latency is terrible ("bufferbloat"). For an
   AI job, every collective step would wait that long.
2. **ECN marking keeps the queue ~50× shorter at the same throughput** (2.06 ms vs 111 ms median).
3. **But classic ECN (cubic) still lost packets in 3 of 5 runs — and the capture shows why.** In every B run 1–3 of the
   12 connections did **not** negotiate ECN: their first SYN (which is never ECN-capable) was dropped at the RED queue,
   and Linux retries a SYN **without** ECN (RFC 3168). Those connections' data is then *dropped* by RED instead of
   marked. Every B run had such a fallback, yet drops split into two groups: ~1600 drops and retransmits in 3 runs,
   6–7 in the other 2. That is consistent with the fallback hitting a data connection in some runs and only iperf3's
   nearly idle control connection in others — but I did not record which connection fell back, so this part is a
   hypothesis.
4. **DCTCP: no loss, perfect fairness.** All 12 connections negotiated ECN in every run, 0 drops and 0 retransmits in
   4 of 5 runs (1 in the fifth), Jain 1.000. It accepts ~5× more marks than cubic (100 k vs 21 k per run) because it
   cuts its window in proportion to the *fraction* of marked packets instead of halving at the first mark.
5. **Surprise:** DCTCP's median queue delay (2.67 ms) is slightly *higher* than cubic+ECN's (2.06 ms), with the same
   p99. DCTCP deliberately holds the queue at the marking threshold (~2.4 ms here); cubic's halving sawtooth drains it
   lower on average. DCTCP's gain in this setup is **no loss and fairness**, not lower median latency.

## Mac cross-check (`results_mac/`, A and B only)
Same picture: tail-drop median 110 ms, RED+ECN 2.29 ms; B again had 1–3 connections without ECN per run.
Two VM-specific findings (`shaper_check_mac.txt`): **HTB could not shape in the Mac's VM** — a 100 Mbit/s class
delivered 16–56 Mbit/s to one flow, so E6 uses TBF (92–95 Mbit/s); and an earlier Mac batch reported totals above the
shaper rate in some runs. That batch was computed with a since-fixed throughput formula (summing per-sender averages),
so I cannot separate a VM timing effect from my own bug for it; the final Mac batch stays below 100 Mbit/s.

## How this maps to RoCE / AI fabrics
RED+ECN on a switch queue + a sender that reacts to the marked fraction is the same control loop as **ECN + DCQCN**
in RoCE NICs: mark early, slow down gently, keep the lossless queue short so **PFC** rarely fires. Finding 3 is the
TCP version of a real deployment rule: anything that is not ECN-capable on a marking queue gets dropped — on a
lossless RoCE class that means pauses instead of drops, which is why DSCP/ECN consistency is audited
(`fabricx audit-qos`) and why the hardware test plan (`docs/roce-test-plan.md`) starts with configuration.

## Limitations
- Linux qdiscs on veth are not switch buffers (no shared buffer, no headroom, no PFC); 100 Mbit/s instead of
  100–400 Gbit/s; one bottleneck; 4 senders × 2 streams; 20 s runs.
- DCTCP is a TCP algorithm in the host kernel, not DCQCN in a NIC; ping and TCP RTT include host-stack time.
- RED uses an averaged queue, so its "step" marking is approximate.
