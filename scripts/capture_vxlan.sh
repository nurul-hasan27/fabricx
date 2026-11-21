#!/bin/bash
# Capture VXLAN (UDP 4789) on a lab node while pinging. Usage: capture_vxlan.sh <node> <out.pcap> <src_host> <dst_ip>...
# Runs from the Mac; commands go through the OrbStack VM.
NODE=$1; OUT=$2; SRC=$3; shift 3
V="${FABRICX_EXEC:-orb -m fabricx-lab sudo}"
PID=$($V docker inspect -f '{{.State.Pid}}' clab-fabricx-$NODE)
$V nsenter -t "$PID" -n timeout 7 tcpdump -i any -nn -U -w "$OUT" udp port 4789 >/dev/null 2>&1 &
sleep 2
for ip in "$@"; do $V docker exec clab-fabricx-$SRC ping -c2 -W2 "$ip" | grep transmitted; done
wait
