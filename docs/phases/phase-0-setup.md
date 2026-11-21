# Phase 0 — Setup (the workshop)

## The goal, in kid words
Before building a pretend school network we need a workshop: a safe room on the Mac where we can build and break things without messing up the Mac itself.

## What I did, step by step
1. **Checked the Mac.** Apple M1 chip (arm64), 8 GB RAM, ~40 GB free disk. No Docker yet. Homebrew (the Mac app installer) was present.
2. **Installed OrbStack** (`brew install --cask orbstack`). OrbStack runs Linux machines inside your Mac very lightly. Network switch software (FRR, SONiC) needs Linux, and macOS isn't Linux.
3. **Created a Linux VM** named `fabricx-lab` (Ubuntu 24.04, arm64) with `orbctl create ubuntu:noble fabricx-lab`. A VM is a computer pretending to live inside another one.
4. **Installed Docker inside the VM.** Docker runs *containers*: tiny isolated programs-with-their-own-network, much lighter than VMs. Each switch and host in our lab will be one container.
5. **Installed Containerlab 0.83.0** (from the official `.deb` file; I pinned the version so results are repeatable). Containerlab reads a YAML file describing nodes and links, then creates the containers and connects them with virtual cables (veth pairs).
6. **Checked image architecture** with `docker manifest inspect`. The FRR image (`quay.io/frrouting/frr:10.2.1`) has an arm64 build, so it runs natively on the M1 (no slow emulation).
7. **Built a "hello" lab** (`labs/hello/hello.clab.yml`): 1 FRR router + 1 Alpine host, one link. Gave each end an IP (a /31), pinged: 3/3 replies.
8. **Destroyed it cleanly** (0 containers left) and recorded versions in `versions.lock.md`, notes in `docs/BUILD_LOG.md`, shortcuts in the `Makefile`.

## Key terms
- **FRRouting (FRR):** open-source routing software (BGP, OSPF, EVPN...). It is the same routing brain used inside SONiC switches.
- **Containerlab:** tool that turns a YAML "topology as code" file into a running virtual network.
- **veth pair:** a virtual Ethernet cable with two ends; one end goes in each container.
- **/31:** a 2-address subnet, perfect for a point-to-point link.
- **arm64 vs amd64:** CPU families. M1 is arm64; most servers are amd64 (x86). Images must match or run slowly in emulation.
- **Pinning versions:** fixing exact versions so anyone can rebuild the same lab.

## Results (real)
- Ping 3/3, 0% loss. Hello lab RAM ~15 MiB total. Mac free disk 40 GB -> 36 GB.
- Found: OrbStack's kernel has **no /dev/kvm** and **no tcp_dctcp** module. So SONiC-VM and the DCTCP congestion experiment must run on GitHub CI or the Azure VM later.

## What went wrong / lessons
- The Containerlab "quick setup" script failed with my arguments; I used the official `.deb` instead.
- The FRR container printed a config error at start: expected, it had no config yet.
- GitHub Actions part of Phase 0 was moved to Phase 5 (no GitHub repo yet).

## How to explain it in an interview
"I run the lab in an arm64 Linux VM on my Mac using Containerlab and FRR containers, pinned versions, and I verified image architectures up front. I found my kernel lacks DCTCP and KVM, so I planned those experiments for CI/cloud from the start."
