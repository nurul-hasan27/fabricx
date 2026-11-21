#!/bin/bash
# Download the pinned official SONiC-VS image (x86 only), record size + sha256, load and tag it.
# Source: SONiC official build pipeline "Azure.sonic-buildimage.official.vs" (public artifacts).
set -euo pipefail
BRANCH=${SONIC_BRANCH:-202505}
BUILD=${SONIC_BUILD:-1238524}
TAG=docker-sonic-vs:${BRANCH}-${BUILD}
URL="https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=${BRANCH}&platform=vs&buildId=${BUILD}&target=target%2Fdocker-sonic-vs.gz"
OUT=${1:-/tmp/docker-sonic-vs.gz}
curl -sSL --fail --retry 3 -o "$OUT" "$URL"
echo "file: docker-sonic-vs.gz  branch: $BRANCH  build: $BUILD"
echo "size_bytes: $(stat -c %s "$OUT")"
echo "sha256: $(sha256sum "$OUT" | cut -d' ' -f1)"
loaded=$(sudo docker load -i "$OUT" | sed -n 's/^Loaded image: //p' | tail -1)
sudo docker tag "$loaded" "$TAG"
rm -f "$OUT"
sudo docker image inspect "$TAG" -f 'image: {{.Id}} arch: {{.Architecture}} size: {{.Size}}'
