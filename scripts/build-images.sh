#!/bin/bash
#
# Build and push production container images to ghcr.io
#
# Usage:
#   ./scripts/build-images.sh           # Builds with git SHA tag
#   ./scripts/build-images.sh v1.2.3    # Builds with custom tag
#

set -euo pipefail

REGISTRY=ghcr.io/$(gh repo view --json owner -q .owner.login)/caelus

if [ -n "${1:-}" ]; then
    TAG="$1"
else
    TAG=$(git rev-parse --short HEAD)
fi

echo "=============================================="
echo "Building Caelus Images"
echo "Registry: ${REGISTRY}"
echo "Tag: ${TAG}"
echo "=============================================="

echo ""
echo "[1/4] Building API image..."
docker build \
    --tag "${REGISTRY}-api:${TAG}" \
    --tag "${REGISTRY}-api:latest" \
    ./api

echo ""
echo "[2/4] Building UI image..."
docker build \
    --tag "${REGISTRY}-ui:${TAG}" \
    --tag "${REGISTRY}-ui:latest" \
    ./ui

echo ""
echo "[3/4] Pushing API image..."
docker push "${REGISTRY}-api:${TAG}"
docker push "${REGISTRY}-api:latest"

echo ""
echo "[4/4] Pushing UI image..."
docker push "${REGISTRY}-ui:${TAG}"
docker push "${REGISTRY}-ui:latest"

echo ""
echo "=============================================="
echo "Build Complete!"
echo "=============================================="
echo "Images pushed:"
echo "  ${REGISTRY}-api:${TAG}"
echo "  ${REGISTRY}-api:latest"
echo "  ${REGISTRY}-ui:${TAG}"
echo "  ${REGISTRY}-ui:latest"
echo ""
