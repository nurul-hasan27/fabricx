# FabricX — 6-minute demo script

A live walkthrough for an interview or a screen recording, with the real commands. Every command below was rehearsed on
the Mac; the outputs and timings are in [`artifacts/phase9/demo-rehearsal.txt`](../artifacts/phase9/demo-rehearsal.txt).
In that rehearsal each command took under 5 s except `diagnose` (~12 s, because it actively tests every link).

## Before you start (not on camera, ~3 min)
```bash
make up                      # fabric up; ends with "fabric healthy after N s" (exits 1 and names the problem if not)
scripts/monitoring.sh up     # Prometheus :9090 + Grafana :3000 in the lab VM
nohup .venv/bin/fabricx exporter > /tmp/fabricx-exporter.log 2>&1 &   # metrics on :9101; output to a file, or the shell may freeze it ("suspended (tty output)") and Grafana shows "No data"
export FABRICX_GRAFANA_URL=http://fabricx-lab.orb.local:3000   # so inject/restore pin notes on the dashboard
.venv/bin/fabricx run-fault F08   # ~1 min: leaves a complete evidence bundle in artifacts/runs/ to open at 3:45
```
Open these, each in its own tab:
- Grafana at <http://fabricx-lab.orb.local:3000> (dashboard "FabricX")
- [`inventory/fabric.yaml`](../inventory/fabric.yaml)
- [`experiments/telemetry/results/timeline.svg`](../experiments/telemetry/results/timeline.svg) (backup, in case Grafana misbehaves live)
- [`docs/limitations.md`](limitations.md)

Use a terminal with a large font.

## The script
| Time | Show | Say (short) |
|---|---|---|
| 0:00 | `inventory/fabric.yaml`, then `.venv/bin/fabricx generate` and `git status generated/` | "One file is the truth: 2 spines, 3 leaves, 2 tenant VRFs, 3 VLANs. Everything else is generated from it, so the lab can't drift from the design." |
| 0:45 | `.venv/bin/fabricx validate` → **PASS** | "It collects live state from every switch and compares it with the intent: every BGP and BFD session up, 2 ECMP paths, underlay MTU, and the EVPN Type-2/3/5 routes each leaf should have. The traffic classes and BLUE-RED isolation are checked by the lab tests and by `diagnose`." |
| 1:45 | `.venv/bin/fabricx faults` — let the interviewer pick, e.g. F08; then `.venv/bin/fabricx inject F08` | "Pick any fault; the diagnosis tool won't be told which one." |
| 2:15 | Customer view: `orb -m fabricx-lab sudo docker exec clab-fabricx-h1 ping -c2 -W1 10.10.10.103` fails; `... ping -c2 -W1 10.20.20.104` works | "Same-subnet traffic to leaf2 fails, but routed traffic works. Nothing is 'down'." |
| 2:45 | `.venv/bin/fabricx diagnose` (~12 s; exits 1 because it found a problem) → `Layer: EVPN routes, Cause: rt-mismatch`, "leaf1 imports ['65001:10010'] but leaf2 exports ['65002:99999']"; confirm by hand: `orb -m fabricx-lab sudo docker exec clab-fabricx-leaf2 vtysh -c 'show bgp l2vpn evpn vni 10010'` | "It works bottom-up — links, underlay, overlay, EVPN — and stops at the first broken layer. One vtysh command confirms it: leaf2 imports a different route target." |
| 3:45 | `.venv/bin/fabricx restore`, then `.venv/bin/fabricx validate` → **PASS**. Open a stored evidence bundle: `artifacts/runs/<time>_F08/report.md` and `timeline.json` | "Every fault run keeps a baseline, a during and an after snapshot, plus a timeline and a report, so the RCA is written from evidence." |
| 4:30 | Grafana: the inject/restore annotations just posted. Then `timeline.svg` from the F01 demo | "When the fault runner breaks something it pins a note on the dashboard. Here a link failure: BGP/BFD drop, traffic moves to the other uplink, no visible dip in throughput." |
| 5:15 | `docs/limitations.md` | "What this does not prove: no ASIC, no PFC, veth loses carrier instantly, and timings come from a shared CPU. On PowerSwitch + SONiC I'd start with the config audit and the RoCE test plan." |
| 6:00 | End | |

## If asked "show me more"
| Topic | One command or file |
|---|---|
| Gray failure vs BFD (E1) | [`experiments/E1/results.md`](../experiments/E1/results.md): 812 ms with BFD vs 10.3 s with 3/9 s BGP timers |
| MTU escalation (E3) | [`docs/rca/RCA-001-mtu-black-hole.md`](rca/RCA-001-mtu-black-hole.md) |
| ECMP polarisation (E2) | [`docs/rca/RCA-002-ecmp-polarisation.md`](rca/RCA-002-ecmp-polarisation.md) |
| SONiC route trace (E8) | [`experiments/E8/results/`](../experiments/E8/results/): bgpd → zebra → APPL_DB → ASIC_DB keys |
| QoS audit | `.venv/bin/fabricx audit-qos tests/fixtures/sonic_config_db_lossless_good.json` |
| Incast (E6) | [`experiments/E6/analysis.md`](../experiments/E6/analysis.md) |

## Recording notes (for the video)
- Record the screen at 1080p with the terminal font at 18 pt or larger; keep the Grafana tab at 125 % zoom.
- Run the "before you start" block, then `fabricx validate` once off camera, so caches are warm.
- If a step hangs on camera, cut to the stored file that shows the same thing (bundle, `timeline.svg`). Never re-run a
  fault on camera to "get a nicer number".
- Afterwards: `.venv/bin/fabricx restore` (if a fault is still active), `pkill -f "fabricx exporter"`,
  `scripts/monitoring.sh down`, `make down`.

## If something looks wrong before you start
| You see | Meaning | Do |
|---|---|---|
| `make up` ends with "fabric NOT healthy" and "restarted during deploy" | a container restarted while Containerlab was wiring it, so it lost its links | `make down && make up` |
| `[1] + suspended (tty output)` after starting the exporter | the shell froze the background job because it printed to the terminal | `kill %1`, then start it again with the `nohup ... > /tmp/fabricx-exporter.log 2>&1 &` line |
| Grafana says "No data" / "Data does not have a time field" | Prometheus has nothing from the exporter | check <http://fabricx-lab.orb.local:9090/targets> shows `fabricx` **up**; if not, see the line above |
| `run-fault` says "fabric did not return to healthy" | the fabric was already broken before the fault | `.venv/bin/fabricx validate` to see what, then `make down && make up` |
