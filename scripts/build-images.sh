#!/bin/bash
#
# Build and push production container images to ghcr.io
#
# Usage:
#   ./scripts/build-images.sh               # Builds both images with git SHA tag
#   ./scripts/build-images.sh v1.2.3        # Builds both images with custom tag
#   ./scripts/build-images.sh --api          # Build only API image (tag = git SHA)
#   ./scripts/build-images.sh --ui           # Build only UI image (tag = git SHA)
#   ./scripts/build-images.sh --keycloak     # Build only Keycloak image (Freepod theme)
#   ./scripts/build-images.sh v1.2.3 --api   # Build only API image with custom tag
#   ./scripts/build-images.sh v1.2.3 --ui    # Build only UI image with custom tag
#   ./scripts/build-images.sh --help         # Show this help message
#
# Note: the Keycloak image (deps) is not part of the default "both" build; it
# rarely changes and is built explicitly with --keycloak.

set -euo pipefail

REGISTRY=ghcr.io/$(gh repo view --json owner -q .owner.login)/caelus

# Function to display help
usage() {
  cat <<'EOF'
Usage: ./scripts/build-images.sh [TAG] [--api|--ui|--keycloak|--help]

If TAG is not provided, the current git SHA will be used.

Options:
  --api        Build only the API image.
  --ui         Build only the UI image.
  --keycloak   Build only the Keycloak image (Freepod theme baked in).
  --help       Show this help message and exit.
EOF
}

# Parse arguments
TAG=""
TARGET="both"  # possible values: both, api, ui, keycloak
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api)
      TARGET="api"
      shift
      ;;
    --ui)
      TARGET="ui"
      shift
      ;;
    --keycloak)
      TARGET="keycloak"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [ -z "$TAG" ]; then
        TAG="$1"
        shift
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      ;;
  esac
done

if [ -z "$TAG" ]; then
  TAG=$(git rev-parse --short HEAD)
fi

echo "=============================================="
echo "Building Caelus Images"
echo "Registry: ${REGISTRY}"
echo "Tag: ${TAG}"
echo "Target: ${TARGET}"
echo "=============================================="

if [[ "$TARGET" == "both" || "$TARGET" == "api" ]]; then
  echo ""
  echo "[1/$(if [[ "$TARGET" == "both" ]]; then echo "2"; else echo "1"; fi)] Building API image..."
  docker build \
    --tag "${REGISTRY}-api:${TAG}" \
    --tag "${REGISTRY}-api:latest" \
    ./api

  echo ""
  echo "[2/$(if [[ "$TARGET" == "both" ]]; then echo "2"; else echo "1"; fi)] Pushing API image..."
  docker push "${REGISTRY}-api:${TAG}"
  docker push "${REGISTRY}-api:latest"
fi

if [[ "$TARGET" == "keycloak" ]]; then
  echo ""
  echo "[1/1] Building Keycloak image (Freepod theme baked in)..."
  docker build \
    --tag "${REGISTRY}-keycloak:${TAG}" \
    --tag "${REGISTRY}-keycloak:latest" \
    ./tf/deps/keycloak

  echo ""
  echo "[1/1] Pushing Keycloak image..."
  docker push "${REGISTRY}-keycloak:${TAG}"
  docker push "${REGISTRY}-keycloak:latest"
fi

if [[ "$TARGET" == "both" || "$TARGET" == "ui" ]]; then
  echo ""
  echo "[1/$(if [[ "$TARGET" == "both" ]]; then echo "2"; else echo "1"; fi)] Building UI image..."
  docker build \
    --tag "${REGISTRY}-ui:${TAG}" \
    --tag "${REGISTRY}-ui:latest" \
    ./ui

  echo ""
  echo "[2/$(if [[ "$TARGET" == "both" ]]; then echo "2"; else echo "1"; fi)] Pushing UI image..."
  docker push "${REGISTRY}-ui:${TAG}"
  docker push "${REGISTRY}-ui:latest"
fi

echo ""
echo "=============================================="
echo "Build Complete!"
echo "=============================================="

echo "Images pushed:"
if [[ "$TARGET" == "both" || "$TARGET" == "api" ]]; then
  echo "  ${REGISTRY}-api:${TAG}"
  echo "  ${REGISTRY}-api:latest"
fi
if [[ "$TARGET" == "both" || "$TARGET" == "ui" ]]; then
  echo "  ${REGISTRY}-ui:${TAG}"
  echo "  ${REGISTRY}-ui:latest"
fi
if [[ "$TARGET" == "keycloak" ]]; then
  echo "  ${REGISTRY}-keycloak:${TAG}"
  echo "  ${REGISTRY}-keycloak:latest"
fi

echo ""


