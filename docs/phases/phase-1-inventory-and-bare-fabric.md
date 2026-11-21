# Phase 1 — Inventory, config generation, bare fabric (the blueprint and the empty school)

## The goal, in kid words
Draw the school plan on **one page**, then have a robot build the whole school from that page. Nobody ever types an address by hand, so nobody can make a typo twice.

## What I did, step by step
1. **Python workspace** on the Mac (`.venv`, with pydantic, Jinja2, Typer, PyYAML, pytest). Python code runs on the Mac; only the lab runs in the VM.
2. **Wrote `inventory/fabric.yaml`** — the single source of truth: 2 spines (AS 65000 shared), 3 leaves (AS 65001-65003), loopbacks, 3 VLANs with VNIs (10010/10020/10030), 2 VRFs (RED, BLUE) with L3VNIs (50001/50002), 5 hosts, MTU 9100 (fabric) and 1500 (hosts).
3. **Wrote `src/fabricx/model.py`** with **pydantic**: it loads the YAML, checks it (unique names, host IP inside its subnet, unique leaf ASNs...) and *derives* things: the 6 spine-leaf /31 links by a formula (spine1-leaf2 = 10.1.1.2/31), which port each host plugs into, etc.
4. **Wrote Jinja2 templates** (`templates/`) for the Containerlab file and each node's `frr.conf`, `daemons`, `vtysh.conf`. `fabricx generate` fills them in and writes `generated/`. Generating the same inventory twice gives byte-identical output (a unit test checks this).
5. **Generated a diagram** (`docs/topology.md`, Mermaid) from the same model.
6. **Wrote tests:** 8 unit tests (run on the Mac, no lab) and 17 lab tests (`tests/lab`) that run commands inside containers via `docker exec` through the VM.
7. **Deployed the 10 nodes** (`make fabric-up`) and ran the lab tests: all passed.
8. **Sanity check:** I put one link down; its test failed; I put it back; it passed. This proves the tests are not fake.
9. **Tore it down** and recorded everything.

## Key terms
- **Inventory / source of truth:** one file that defines intent; everything else is generated from it.
- **Spine-leaf (Clos):** leaves connect to servers, spines connect leaves. Every leaf links to every spine.
- **Loopback:** a virtual interface that is always up; used as the router's identity (router-ID) and later the VXLAN tunnel address (VTEP).
- **VLAN / VNI / VRF:** VLAN = a Layer-2 segment; VNI = its VXLAN number across the fabric; VRF = a separate routing table per tenant (RED, BLUE).
- **Jinja2 template:** text file with blanks filled from data.
- **MTU 9100:** big-frame size on fabric links so VXLAN's 50 extra bytes fit around 1500-byte host packets.
- **Idempotent/deterministic generation:** same input -> same output.

## Results (real)
- 8/8 unit tests, 17/17 lab tests passed. All 6 links UP, MTU 9100, ping works both ends of each /31.
- Whole idle fabric ~70 MiB RAM.
- h1 -> h3 ping fails: **expected**, there is no routing or gateway yet.

## What went wrong / lessons
- Typer collapsed a single command into the root command; fixed with an explicit app callback.
- A rule test forbids IP literals in code/templates, which keeps the inventory honest.

## How to explain it in an interview
"The fabric is generated from one pydantic-validated inventory; links, ports and expected state are derived, never hand-listed. Tests prove both the generator (unit) and the live lab (integration), and I verified they can fail."
