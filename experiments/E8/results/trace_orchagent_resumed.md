# Route trace after orchagent resumed (ROUTE_TABLE after 0.104 s, ASIC_DB after 0.16 s; poll period 0.053 s) for 10.99.0.0/24

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

## 3. fpmsyncd -> orchagent consumed -> APPL_DB
`ROUTE_TABLE:10.99.0.0/24`

- ifname = Ethernet0,Ethernet4
- nexthop = 10.1.1.4,10.1.2.4
- protocol = bgp
- weight = 1,1

## 4. orchagent (routeorch) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY:{"dest":"10.99.0.0/24","switch_id":"oid:0x21000000000000","vr":"oid:0x3000000000004"}`

- SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID = oid:0x50000000005e2

## 5. orchagent (routeorch ECMP group) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP:oid:0x50000000005e2`

- SAI_NEXT_HOP_GROUP_ATTR_TYPE = SAI_NEXT_HOP_GROUP_TYPE_DYNAMIC_UNORDERED_ECMP

## 6. orchagent (ECMP member) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER:oid:0x2d0000000005e4`

- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID = oid:0x50000000005e2
- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_ID = oid:0x40000000005dd
- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_WEIGHT = 1

## 7. orchagent (neighorch) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:oid:0x40000000005dd`

- SAI_NEXT_HOP_ATTR_IP = 10.1.2.4
- SAI_NEXT_HOP_ATTR_ROUTER_INTERFACE_ID = oid:0x60000000005b9
- SAI_NEXT_HOP_ATTR_TYPE = SAI_NEXT_HOP_TYPE_IP

## 8. orchagent (ECMP member) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER:oid:0x2d0000000005e3`

- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID = oid:0x50000000005e2
- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_ID = oid:0x40000000005de
- SAI_NEXT_HOP_GROUP_MEMBER_ATTR_WEIGHT = 1

## 9. orchagent (neighorch) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP:oid:0x40000000005de`

- SAI_NEXT_HOP_ATTR_IP = 10.1.1.4
- SAI_NEXT_HOP_ATTR_ROUTER_INTERFACE_ID = oid:0x60000000005b8
- SAI_NEXT_HOP_ATTR_TYPE = SAI_NEXT_HOP_TYPE_IP
