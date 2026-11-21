# Route trace with orchagent frozen (staged after 0.215 s, checked again 10 s later: still staged=True, ROUTE_TABLE_KEY_SET=['10.99.0.0/24']) for 10.99.0.0/24

## 1. bgpd (best path) -> FRR bgpd
`show bgp ipv4 unicast 10.99.0.0/24`

- path1 = as-path [65000 65001] via 10.1.1.4 best
- path2 = as-path [65000 65001] via 10.1.2.4 multipath

## 2. zebra (RIB -> FPM) -> FRR zebra
`show ip route 10.99.0.0/24`

- installed = True
- nexthop1 = 10.1.1.4 dev Ethernet0 fib=True
- nexthop2 = 10.1.2.4 dev Ethernet4 fib=True
- offloaded = True
- protocol = bgp
- selected = True

## 3. fpmsyncd (written, NOT yet consumed by orchagent) -> APPL_DB
`_ROUTE_TABLE:10.99.0.0/24`

- ifname = Ethernet0,Ethernet4
- nexthop = 10.1.1.4,10.1.2.4
- protocol = bgp
- weight = 1,1

## 4. fpmsyncd -> orchagent consumed -> APPL_DB
`ROUTE_TABLE:10.99.0.0/24`

- (nothing found here)

## 5. orchagent (routeorch) -> ASIC_DB
`(no route entry for 10.99.0.0/24)`

- (nothing found here)
