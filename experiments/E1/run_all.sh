#!/bin/bash
# Runs the whole E1 matrix, then puts the lab back on the baseline (BFD) profile.
cd "$(dirname "$0")/../.."
P=.venv/bin/python
$P experiments/E1/run.py --profile bfd     --fault carrier --runs 10 --duration 8
$P experiments/E1/run.py --profile bfd     --fault gray    --runs 10 --duration 8
$P experiments/E1/run.py --profile nobfd   --fault carrier --runs 10 --duration 8
$P experiments/E1/run.py --profile nobfd   --fault gray    --runs 10 --duration 16
$P experiments/E1/run.py --profile default --fault gray    --runs 3  --duration 200
$P - <<'PY'
import sys; sys.path.insert(0, "experiments/E1"); sys.path.insert(0, "src")
import run; run.set_profile("bfd"); print("baseline restored")
PY
