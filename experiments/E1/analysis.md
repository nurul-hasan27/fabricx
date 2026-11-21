# E1 analysis

Numbers come from `results.md` (generated from the raw probe files in `results/`). Method and limits: `method.md`.

## What the data says
1. **Carrier loss is nearly free in this lab.** Median outage 4.6 ms with BFD and 3.2 ms without (N=10 each), i.e. at the probe noise floor (3-9 ms). Occasional runs showed 34-100 ms. Reason: a veth drops carrier on both ends instantly, zebra removes the next-hop from the kernel ECMP group at once, and no protocol has to notice anything. BFD makes no difference here.
2. **Gray failure is where detection matters.**
   - BGP 3/9 s + BFD (300 ms x 3): median **812 ms** (min 702, max 970, N=10), roughly the 900 ms detection time.
   - BGP 3/9 s, no BFD: median **10.3 s** (min 7.8, max 11.3, N=10), i.e. the 9 s hold timer plus 1-2 s of processing.
   - BGP defaults 60/180 s, no BFD: **141 s, 192 s and at least 197 s** (N=3, one run did not recover before the 200 s run ended). Far too slow to call a recovery.
   - BFD cut the gray-failure outage by about 12x compared with the 9 s hold timer and by more than 150x compared with BGP defaults.
3. Packets lost track the outage almost 1:1 at a 1 ms probe interval (median 812 lost for a 812 ms outage).

## Surprises / mistakes found while doing it
- My first version of the analysis reported `longest gap` only; the 200 s runs showed that an outage still going when the sender stops leaves a *trailing* silence that this misses (run 1 reported 1.6 ms while 197 s of packets were lost). `aggregate.py` now includes the trailing gap and flags such runs as unrecovered. The result.json files written during the runs keep the old field; `results.md` is the authority.
- The default-timer cell has only N=3 because each run lasts 200 s; its spread (141-197 s) is wide. Treat it as order-of-magnitude.
- Hold-timer runs came out slower than the nominal 9 s (up to 11.3 s). Not investigated further.

## What this does NOT show
Real optics, ASIC forwarding, or a congested control plane. Software ECMP, shared CPUs, one shared clock. Only one flow (h1 -> h3 over the leaf1 uplink it hashes to) and one fault direction (leaf1 egress) were tested; the reverse direction and other leaves were not.
