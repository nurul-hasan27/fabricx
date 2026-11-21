#!/bin/bash
# Dump facts about a running SONiC-VS container. Usage: sonic_probe.sh <container>
C=$1
x() { echo; echo "### $*"; sudo docker exec "$C" bash -c "$*" 2>&1 | head -${N:-60}; }
x "cat /etc/sonic/sonic_version.yml"
x "supervisorctl status"
x "ps -eo pid,args | grep -E 'bgpd|zebra|bfdd|fpmsyncd|orchagent|syncd|redis|bgpcfgd|frrcfgd|gnmi|telemetry' | grep -v grep"
x "vtysh -c 'show version' | head -3"
x "ls /usr/lib/frr/ | tr '\n' ' '"
x "sonic-db-cli PING; for d in APPL_DB ASIC_DB COUNTERS_DB CONFIG_DB STATE_DB; do echo \$d \$(sonic-db-cli \$d DBSIZE); done"
x "sonic-cfggen -d --var-json DEVICE_METADATA"
x "sonic-cfggen -d --print-data | python3 -c 'import sys,json; d=json.load(sys.stdin); print(sorted(d))'"
x "cat /usr/share/sonic/hwsku/port_config.ini | head -8; ls /usr/share/sonic/hwsku/"
x "cat /usr/share/sonic/hwsku/lanemap.ini 2>/dev/null | head -6"
x "ip -br link | head -20; ip -br addr | head -12"
x "show interfaces status 2>/dev/null | head -8"
x "sonic-db-cli APPL_DB keys 'PORT_TABLE:*' | head -5; sonic-db-cli APPL_DB HGETALL PORT_TABLE:Ethernet0"
x "sonic-db-cli ASIC_DB keys 'ASIC_STATE:SAI_OBJECT_TYPE_*' | cut -d: -f2 | sort | uniq -c | sort -rn | head -15"
x "cat /etc/sonic/frr/bgpd.conf 2>/dev/null | head -20; ls /etc/sonic/frr/"
x "which config show sonic-db-cli sonic-cfggen redis-cli; ss -ltnp | head -20"
