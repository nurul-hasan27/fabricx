#!/bin/bash
# Deploys each underlay variant from the inventory, runs the failure matrix, then restores the eBGP baseline.
cd "$(dirname "$0")/../.."
F=.venv/bin/fabricx; P=.venv/bin/python
for proto in ospf isis; do
  $F destroy >/dev/null 2>&1
  $F deploy --inventory inventory/variants/$proto.yaml >/dev/null 2>&1
  sleep 70
  $F validate --inventory inventory/variants/$proto.yaml | tail -3
  $P experiments/E5/run.py $proto bfd carrier 10 8
  $P experiments/E5/run.py $proto bfd gray 10 8
  $P experiments/E5/run.py $proto nobfd gray 3 75
done
$F destroy >/dev/null 2>&1
$F deploy >/dev/null 2>&1
sleep 70
echo "baseline restored"
