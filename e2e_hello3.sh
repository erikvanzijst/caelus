#!/usr/bin/env bash
set -euo pipefail

# End-to-end deploy flow for hello-static chart via Caelus CLI + reconcile.
#
# Usage:
#   ./e2e_hello3.sh
#   DOMAIN=hello3.app.deprutser.be MESSAGE="Hello from script" ./e2e_hello3.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/api"
CHART_DIR="$ROOT_DIR/k8s/hello-static-chart"
CHART_YAML="$CHART_DIR/Chart.yaml"
REGISTRY_OCI="oci://registry.home:80/helm"
DOMAIN="${DOMAIN:-hello3.app.deprutser.be}"
MESSAGE="${MESSAGE:-Hello from codex e2e $(date +%F-%H%M%S)}"

log() {
  printf '\n==> %s\n' "$*"
}

chart_version() {
  awk '/^version:/{print $2; exit}' "$CHART_YAML"
}

bump_chart_patch() {
  python - "$CHART_YAML" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

def bump(v: str) -> str:
    parts = v.split(".")
    if len(parts) != 3:
        raise SystemExit(f"unsupported semver: {v}")
    parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)

m1 = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", text, flags=re.M)
m2 = re.search(r'^appVersion:\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', text, flags=re.M)
if not m1 or not m2:
    raise SystemExit("could not parse version/appVersion in Chart.yaml")

new_v = bump(m1.group(1))
new_app = bump(m2.group(1))

text = re.sub(r"^version:\s*[0-9]+\.[0-9]+\.[0-9]+\s*$", f"version: {new_v}", text, flags=re.M)
text = re.sub(r'^appVersion:\s*"[0-9]+\.[0-9]+\.[0-9]+"\s*$', f'appVersion: "{new_app}"', text, flags=re.M)
path.write_text(text)
print(new_v)
PY
}

push_chart() {
  local v pkg out rc
  while true; do
    v="$(chart_version)"
    pkg="/tmp/hello-static-${v}.tgz"
    rm -f "$pkg"
    log "Packaging chart version $v"
    helm package "$CHART_DIR" -d /tmp >/dev/null

    log "Pushing chart $v to $REGISTRY_OCI"
    set +e
    out="$(helm push "$pkg" "$REGISTRY_OCI" --plain-http 2>&1)"
    rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      printf '%s\n' "$out"
      break
    fi

    printf '%s\n' "$out"
    if grep -qi "already exists" <<<"$out"; then
      log "Version $v already exists. Bumping chart patch version."
      bump_chart_patch >/dev/null
      continue
    fi
    log "Chart push failed with non-recoverable error."
    exit 1
  done
  CHART_DIGEST="$(grep -Eo 'sha256:[0-9a-f]{64}' <<<"$out" | head -n1)"
  if [[ -z "${CHART_DIGEST:-}" ]]; then
    echo "Unable to parse chart digest from helm push output" >&2
    exit 1
  fi
}

log "Resetting DB file and migrating to head"
python - <<'PY'
from pathlib import Path
p = Path("api/caelus.db")
if p.exists():
    p.unlink()
PY
cd "$API_DIR"
uv run --no-sync alembic upgrade head >/dev/null
cd "$ROOT_DIR"

push_chart
CHART_VERSION="$(chart_version)"
log "Using chart digest: $CHART_DIGEST"

log "Creating product and user"
cd "$API_DIR"
uv run --no-sync python -m app.cli create-product hello-world "Hello world product"
uv run --no-sync python -m app.cli create-user codex@deprutser.be

log "Creating template and setting it on product"
SCHEMA_JSON='{"type":"object","properties":{"user":{"type":"object","properties":{"message":{"type":"string"}},"required":["message"],"additionalProperties":false}},"additionalProperties":true}'
uv run --no-sync python -m app.cli create-template \
  --product-id 1 \
  --chart-ref oci://registry.home:80/helm/hello-static \
  --chart-version "$CHART_VERSION" \
  --chart-digest "$CHART_DIGEST" \
  --values-schema-json "$SCHEMA_JSON"
uv run --no-sync python -m app.cli update-product 1 --template-id 1

log "Creating deployment for $DOMAIN with custom message"
dep_out="$(uv run --no-sync python -m app.cli create-deployment \
  --user-id 1 \
  --desired-template-id 1 \
  --domainname "$DOMAIN" \
  --user-values-json "{\"message\":\"$MESSAGE\"}")"
printf '%s\n' "$dep_out"
NS="$(grep -o "deployment_uid='[^']*'" <<<"$dep_out" | head -n1 | sed "s/deployment_uid='//;s/'$//")"
if [[ -z "${NS:-}" ]]; then
  echo "Unable to parse deployment_uid from create-deployment output" >&2
  exit 1
fi

log "Running reconcile"
uv run --no-sync python -m app.cli reconcile 1

cd "$ROOT_DIR"
log "Kubernetes resources in namespace: $NS"
kubectl get ns "$NS"
kubectl get all -n "$NS"
kubectl get ingress -n "$NS"

log "Verifying HTTPS endpoint response"
ok=0
for _ in $(seq 1 30); do
  body="$(curl -fsS "https://$DOMAIN" || true)"
  if grep -Fq "$MESSAGE" <<<"$body"; then
    ok=1
    break
  fi
  sleep 2
done

if [[ $ok -ne 1 ]]; then
  printf '\nExpected message not found from https://%s\n' "$DOMAIN" >&2
  printf 'Expected: %s\n' "$MESSAGE" >&2
  printf 'Last body: %s\n' "${body:-<empty>}" >&2
  exit 1
fi

printf '\nSUCCESS: %s serves expected content.\n' "$DOMAIN"
