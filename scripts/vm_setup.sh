#!/usr/bin/env bash
# Prepare a fresh Ubuntu 24.04 machine (the OrbStack VM on a Mac, or a CI runner) to run the lab.
# Idempotent: anything already at the right version is left alone. Run as root:
#   Mac:  make vm-setup                (= orb -m fabricx-lab sudo bash scripts/vm_setup.sh)
#   CI:   make vm-setup RUN=sudo
set -euo pipefail
CLAB_VERSION=0.83.0
ARCH=$(dpkg --print-architecture)          # arm64 on an M1 Mac VM, amd64 on GitHub runners

if ! command -v docker >/dev/null; then
  echo "[vm-setup] installing Docker (Ubuntu docker.io package)"
  apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io
fi
if ! command -v tcpdump >/dev/null; then
  echo "[vm-setup] installing tcpdump"
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q tcpdump
fi
have=$(containerlab version 2>/dev/null | awk '/version:/ {print $2; exit}' || true)
if [ "$have" != "$CLAB_VERSION" ]; then
  echo "[vm-setup] installing Containerlab $CLAB_VERSION ($ARCH), found '${have:-none}'"
  deb="containerlab_${CLAB_VERSION}_linux_${ARCH}.deb"
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/$deb" "https://github.com/srl-labs/containerlab/releases/download/v${CLAB_VERSION}/${deb}"
  dpkg -i "$tmp/$deb"
  rm -rf "$tmp"
fi
echo "[vm-setup] ready: $(uname -m), kernel $(uname -r), docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)," \
     "containerlab $(containerlab version | awk '/version:/ {print $2; exit}')"
