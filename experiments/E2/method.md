# E2 — Does ECMP actually spread traffic, and what controls it?

**Method** (`run.py`): 64 parallel TCP flows (`iperf3 -P 64`, distinct source ports) h1 -> h3 for 5 s, run with
`net.ipv4.fib_multipath_hash_policy` = 0 (L3 only) and 1 (L3+L4) on every switch, each twice. Read TX packet counters on leaf1's two
uplinks and on the spines' downlinks to leaf2; sample the VXLAN outer UDP source ports leaving leaf1 with tcpdump.
**Control:** 64 plain UDP flows (distinct source ports) from leaf1's loopback to leaf2's loopback, no VXLAN, under both policies.

**Limits:** software (kernel) hashing, one source/destination pair, a single 5 s window per run; ASIC hash functions differ.
