# Telemetry demo: F01 (leaf1 eth1 down) seen on the pipeline

- annotations posted: ['restore F01: Leaf-spine link down', 'inject F01: Leaf-spine link down']
- iperf3 mean 10 s before inject: 200.0 Mbit/s; first 3 s after inject: [197.3, 201.1, 201.9]
- first Prometheus sample showing a leaf1 BGP session down: +4.6 s after inject
- first sample with it back up after restore: +4.4 s after restore
- iperf3 retransmits (whole run): 99
- resolution: Prometheus 5 s scrape (exporter collects on each scrape); iperf3 1 s intervals
