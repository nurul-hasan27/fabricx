#!/bin/bash
# Why E6 shapes with TBF and not HTB: single TCP flow h1 -> h3 through leaf2's port to h3 under different shapers.
# Usage (from the Mac): experiments/E6/shaper_check.sh > experiments/E6/shaper_check_mac.txt
R="${FABRICX_EXEC:-orb -m fabricx-lab sudo}"
L="clab-fabricx-leaf2"; DST=$(cd "$(dirname "$0")/../.." && .venv/bin/python -c "from fabricx import model; print(model.load('inventory/variants/e6-incast.yaml').hosts_by_name()['h3'].ip)")
$R docker exec clab-fabricx-h3 sh -c 'pkill iperf3; sleep .3; iperf3 -s -D -p 5201'
t() { $R docker exec clab-fabricx-h1 iperf3 -c "$DST" -p 5201 -t 6 2>&1 | grep receiver | awk '{print $7, $8}'; }
q() { $R docker exec $L sh -c "tc qdisc del dev eth3 root 2>/dev/null; $1" 2>/dev/null; }
echo "kernel: $($R uname -r)"
q "true";                                                                         echo "no shaper: $(t)"
for cb in 1600 15k 60k; do
  q "tc qdisc add dev eth3 root handle 1: htb default 10; tc class add dev eth3 parent 1: classid 1:10 htb rate 100mbit ceil 100mbit burst 15k cburst $cb; tc qdisc add dev eth3 parent 1:10 handle 10: pfifo limit 1000"
  echo "htb 100mbit cburst $cb + pfifo: $(t)"
done
q "tc qdisc add dev eth3 root handle 1: tbf rate 100mbit burst 60k limit 1000000; tc qdisc add dev eth3 parent 1:1 handle 10: pfifo limit 1000"; echo "tbf 100mbit + pfifo: $(t)"
q "tc qdisc add dev eth3 root handle 1: tbf rate 100mbit burst 60k limit 1000000; tc qdisc add dev eth3 parent 1:1 handle 10: red limit 400000 min 30000 max 31500 avpkt 1500 burst 21 bandwidth 100mbit probability 1.0 ecn"; echo "tbf 100mbit + red: $(t)"
q "true"
