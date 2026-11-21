#!/bin/bash
# Evidence about the SONiC leaf and its spine neighbour. Usage: sonic_diag.sh <sonic-node> <spine-node> <spine-ip> <spine-if>
S=clab-fabricx-$1; P=clab-fabricx-$2; PIP=$3; PIF=$4
x() { local c=$1; shift; echo; echo "### ${c#clab-fabricx-}: $*"; sudo docker exec "$c" bash -c "$*" 2>&1 | head -${N:-40}; }
x $S "vtysh -c 'show bgp summary' | sed -n '1,14p'"
x $S "supervisorctl status | grep -E 'bgpd|zebra|bfdd|staticd'; ps -eo args | grep -E '/usr/lib/frr/' | grep -v grep"
x $S "grep -B1 -A3 'program:bgpd' /etc/supervisor/conf.d/supervisord.conf"
x $S "ip -br link | grep -E '^(eth|Ethernet0 |Ethernet4 |Loopback)'; ip -br addr | grep -E '^(Ethernet0 |Ethernet4 |Loopback)'"
x $S "show interfaces status | head -4"
x $S "sonic-db-cli STATE_DB HGETALL 'PORT_TABLE|Ethernet0'; sonic-db-cli APPL_DB HGETALL 'PORT_TABLE:Ethernet0'"
x $S "sonic-db-cli APPL_DB keys 'INTF_TABLE:*'; sonic-db-cli ASIC_DB keys 'ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE:*' | wc -l"
x $S "ping -c2 -W1 $PIP; ip neigh"
x $P "ip -br link show $PIF; ip -br addr show $PIF; ip neigh"
N=25 x $P "vtysh -c 'show bgp neighbors' | grep -A22 'BGP neighbor is ${PIP%.*}.$(( ${PIP##*.} + 1 ))' | grep -i -E 'state|reset|bfd|connect|timer|error'"
x $P "vtysh -c 'show bfd peers brief'"
x $S "vtysh -c 'show bfd peers brief'; cat /var/log/bfdd.log | tail -5; ss -ltn | grep -E ':179|:3784'"
echo; echo "### capture 6 s on both ends while leaf pings"
sudo timeout 15 nsenter -t $(sudo docker inspect -f '{{.State.Pid}}' $S) -n tcpdump -c 12 -nn -i eth1 'tcp port 179 or udp port 3784 or icmp' 2>&1 | head -12 &
sudo timeout 15 nsenter -t $(sudo docker inspect -f '{{.State.Pid}}' $P) -n tcpdump -c 12 -nn -i $PIF 'tcp port 179 or udp port 3784 or icmp' 2>&1 | head -12 &
sleep 1; sudo docker exec $S ping -c3 -W1 $PIP >/dev/null 2>&1; wait
x $S "tail -n 30 /var/log/syslog 2>/dev/null | grep -i -E 'bfdd|bgpd|syncd|vs|error' | tail -15"
