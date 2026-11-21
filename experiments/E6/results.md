### results_ci  (kernel 7.0.0-1016-aws, bottleneck leaf2:eth3 at 100mbit, 20 s per run)

| scenario | runs | total Mbit/s | Jain fairness | queue drops | ECN marks | ping RTT median ms | ping RTT p99 ms | TCP mean RTT ms | retransmits | ping loss % | start skew s (max) | connections without ECN | connections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A tail-drop, cubic | 5 | 95.59 (95.56-95.69) | 0.961 (0.915-0.984) | 112 (96-118) | - | 111 (110-112) | 121 (121-121) | 108.78 (107.44-110.12) | 111 (95-116) | 0.4 (0-1.1) | 0 | 12 (12-12) | 12 (12-12) |
| B RED+ECN, cubic | 5 | 100.31 (94.7-100.49) | 0.98 (0.967-0.999) | 1597 (6-1716) | 21338 (20695-27961) | 2.06 (1.95-2.06) | 3.75 (3.61-4.32) | 2.88 (2.8-2.94) | 1590 (0-1703) | 0 (0-0) | 2 | 2 (1-3) | 12 (12-12) |
| C RED+ECN, DCTCP | 5 | 95.61 (95.51-95.61) | 1 (1-1) | 0 (0-1) | 100337 (100244-100462) | 2.67 (2.66-2.68) | 3.73 (3.52-3.87) | 3.06 (2.99-3.12) | 0 (0-1) | 0 (0-0) | 0 | 0 (0-0) | 12 (12-12) |

Idle RTT (ping, before load): median 0.056 ms.

### results_mac  (kernel 7.2.12-orbstack-00394-gbecdd6130068, bottleneck leaf2:eth3 at 100mbit, 20 s per run)

| scenario | runs | total Mbit/s | Jain fairness | queue drops | ECN marks | ping RTT median ms | ping RTT p99 ms | TCP mean RTT ms | retransmits | ping loss % | start skew s (max) | connections without ECN | connections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A tail-drop, cubic | 5 | 94.08 (92.24-94.37) | 0.942 (0.736-0.973) | 74 (59-1197) | - | 110 (105-113) | 128 (124-136) | 110.25 (98.51-113.97) | 147 (119-2311) | 0 (0-0.7) | 0 | 12 (12-12) | 12 (12-12) |
| B RED+ECN, cubic | 5 | 94.44 (93.64-98.72) | 0.987 (0.963-0.992) | 72 (52-839) | 20099 (17709-20505) | 2.29 (2.19-2.4) | 7.01 (6.56-8.48) | 3.27 (3.18-3.37) | 452 (366-1241) | 0 (0-0) | 2 | 2 (1-3) | 12 (12-12) |

Idle RTT (ping, before load): median 0.2375 ms.

