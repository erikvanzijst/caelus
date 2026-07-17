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

REGISTRY=ghcr.io/$(gh repo view --json nameWithOwner -q .nameWithOwner)

# Function to display help
usage() {
  cat <<'EOF'
Usage: ./scripts/build-images.sh [TAG] [--api|--ui|--keycloak|--all|--help]

If TAG is not provided, the current git SHA will be used.

Options:
  --api        Build only the API image.
  --ui         Build only the UI image.
  --keycloak   Build only the Keycloak image (Freepod theme baked in).
  --all        Build all images (API, UI, Keycloak).
  --help       Show this help message and exit.
EOF
}

# Parse arguments
TAG=""
TARGET="both"  # possible values: both, api, ui, keycloak, all
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
    --all)
      TARGET="all"
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

GIT_COMMIT=$(git rev-parse --short HEAD)

GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BRANCH_TAG=$(echo "$GIT_BRANCH" | sed -E 's/[^A-Za-z0-9_.-]+/-/g; s/^[.-]+//')

if [ -z "$TAG" ]; then
  TAG="$GIT_COMMIT"
fi

echo "=============================================="
echo "Building Caelus Images"
echo "Registry: ${REGISTRY}"
echo "Tag: ${TAG}"
echo "Branch tag: ${BRANCH_TAG}"
echo "Target: ${TARGET}"
echo "=============================================="

if [[ "$TARGET" == "both" || "$TARGET" == "all" || "$TARGET" == "api" ]]; then
  echo ""
  echo "[1/$(if [[ "$TARGET" == "both" ]]; then echo "2"; elif [[ "$TARGET" == "all" ]]; then echo "3"; else echo "1"; fi)] Building and pushing API image..."
  docker buildx build \
    --push \
    --build-arg GIT_COMMIT="${GIT_COMMIT}" \
    --tag "${REGISTRY}/api:${TAG}" \
    --tag "${REGISTRY}/api:${BRANCH_TAG}" \
    --tag "${REGISTRY}/api:latest" \
    ./api
fi

if [[ "$TARGET" == "keycloak" || "$TARGET" == "all" ]]; then
  echo ""
  echo "[$(if [[ "$TARGET" == "all" ]]; then echo "2/3"; else echo "1/1"; fi)] Building and pushing Keycloak image (Freepod theme baked in)..."
  docker buildx build \
    --push \
    --tag "${REGISTRY}/keycloak:${TAG}" \
    --tag "${REGISTRY}/keycloak:${BRANCH_TAG}" \
    --tag "${REGISTRY}/keycloak:latest" \
    ./tf/deps/keycloak
fi

if [[ "$TARGET" == "both" || "$TARGET" == "all" || "$TARGET" == "ui" ]]; then
  echo ""
  echo "[1/$(if [[ "$TARGET" == "both" ]]; then echo "2"; elif [[ "$TARGET" == "all" ]]; then echo "3"; else echo "1"; fi)] Building and pushing UI image..."
  docker buildx build \
    --push \
    --build-arg GIT_COMMIT="${GIT_COMMIT}" \
    --tag "${REGISTRY}/ui:${TAG}" \
    --tag "${REGISTRY}/ui:${BRANCH_TAG}" \
    --tag "${REGISTRY}/ui:latest" \
    ./ui
fi

echo ""
echo "=============================================="
echo "Build Complete!"
echo "=============================================="

echo "Images pushed:"
if [[ "$TARGET" == "both" || "$TARGET" == "all" || "$TARGET" == "api" ]]; then
  echo "  ${REGISTRY}/api:${TAG}"
  echo "  ${REGISTRY}/api:${BRANCH_TAG}"
  echo "  ${REGISTRY}/api:latest"
fi
if [[ "$TARGET" == "both" || "$TARGET" == "all" || "$TARGET" == "ui" ]]; then
  echo "  ${REGISTRY}/ui:${TAG}"
  echo "  ${REGISTRY}/ui:${BRANCH_TAG}"
  echo "  ${REGISTRY}/ui:latest"
fi
if [[ "$TARGET" == "keycloak" || "$TARGET" == "all" ]]; then
  echo "  ${REGISTRY}/keycloak:${TAG}"
  echo "  ${REGISTRY}/keycloak:${BRANCH_TAG}"
  echo "  ${REGISTRY}/keycloak:latest"
fi

echo ""


