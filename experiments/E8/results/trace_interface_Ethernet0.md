# Interface trace for Ethernet0

## 1. config (intent) -> CONFIG_DB
`PORT|Ethernet0`

- admin_status = up
- alias = fortyGigE0/0
- index = 0
- lanes = 25,26,27,28
- mtu = 9100
- speed = 100000
- subport = 0

## 2. portmgrd / portsyncd -> APPL_DB
`PORT_TABLE:Ethernet0`

- admin_status = up
- alias = fortyGigE0/0
- flap_count = 3
- index = 0
- lanes = 25,26,27,28
- last_down_time = Sat Nov 21 16:15:13 2026
- last_up_time = Sat Nov 21 16:15:13 2026
- mtu = 9100
- oper_status = up
- speed = 100000
- subport = 0

## 3. portsyncd (kernel state) -> STATE_DB
`PORT_TABLE|Ethernet0`

- admin_status = up
- fec = N/A
- host_tx_ready = true
- mtu = 9100
- netdev_oper_status = up
- speed = 10000
- state = ok
- supported_speeds = 

## 4. orchagent (portsorch) -> ASIC_DB
`ASIC_STATE:SAI_OBJECT_TYPE_PORT:oid:0x1000000000002`

- NULL = NULL
- SAI_PORT_ATTR_ADMIN_STATE = true
- SAI_PORT_ATTR_AUTO_NEG_MODE = true
- SAI_PORT_ATTR_MTU = 9122
- SAI_PORT_ATTR_SPEED = 100000

## 5. syncd (flex counters) -> COUNTERS_DB
`COUNTERS:oid:0x1000000000002`

- SAI_PORT_STAT_IF_IN_DISCARDS = 0
- SAI_PORT_STAT_IF_IN_OCTETS = 419816
- SAI_PORT_STAT_IF_IN_UCAST_PKTS = 4808
- SAI_PORT_STAT_IF_OUT_OCTETS = 62826
- SAI_PORT_STAT_IF_OUT_UCAST_PKTS = 851
