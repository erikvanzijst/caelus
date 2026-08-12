#!/bin/sh
# Idempotent bucket, access-key and permission provisioning for the shared
# Garage singleton. Runs as the first step of the `garage-provision` Job.
#
# WHY THIS TALKS TO THE ADMIN API AND NOT THE `garage` CLI
# -------------------------------------------------------
# The obvious implementation — run `garage bucket create` in the Garage image —
# is not available:
#
#   * `dxflrs/garage` is a FROM-scratch image whose only file is `/garage`.
#     There is no shell and no coreutils, so a script cannot run in it.
#   * The `garage` CLI speaks the internal RPC protocol and needs
#     `<full-node-id>@host:port`. The node ID does not exist until the pod has
#     run, so a second pod cannot address it without discovering it first.
#
# The admin API has neither problem: it is plain HTTP on :3903, addressed by
# Service name. Design D2 anticipates this ("where the admin API is used rather
# than the CLI, use a scoped, expirable admin token").
#
# EVERY STEP READS BEFORE IT WRITES, so a re-run is a no-op and an existing
# access key is never rotated. Terraform re-runs this Job whenever the script or
# its inputs change, which also repairs hand-made drift.
set -eu

: "${GARAGE_ADMIN_URL:?}"
: "${GARAGE_ADMIN_TOKEN:?}"
: "${ENVIRONMENTS:?}"
: "${KEYS_SECRET_NAME:?}"
: "${NAMESPACE:?}"
: "${CREDS_DIR:?}"
: "${HEALTH_TIMEOUT_SECONDS:?}"

log() { echo "[provision] $*" >&2; }

# --------------------------------------------------------------------------
# 1. Wait for a committed cluster layout.
#
# A freshly installed Garage node holds NO cluster layout and rejects every S3
# and data operation until an operator assigns and commits one; `/health`
# returns 503 until then. Polling rather than failing immediately means an
# operator can run the one-time bootstrap in another terminal while
# `terraform apply` waits here, instead of having the apply fail and be re-run.
# --------------------------------------------------------------------------
waited=0
while [ "$(curl -s -o /dev/null -w '%{http_code}' "$GARAGE_ADMIN_URL/health" || echo 000)" != "200" ]; do
  if [ "$waited" -ge "$HEALTH_TIMEOUT_SECONDS" ]; then
    log "FATAL: Garage still reports unhealthy after ${HEALTH_TIMEOUT_SECONDS}s."
    log ""
    log "On a fresh install the overwhelmingly likely cause is that the cluster"
    log "layout has never been assigned and committed. Garage cannot serve any"
    log "request without one. See tf/deps/README.md -> 'Cluster-layout"
    log "bootstrap' for the two commands, then re-run 'terraform apply'."
    log ""
    log "Current health:"
    curl -s "$GARAGE_ADMIN_URL/health" >&2 || true
    echo >&2
    exit 1
  fi
  log "waiting for Garage to report healthy (${waited}s/${HEALTH_TIMEOUT_SECONDS}s)..."
  sleep 5
  waited=$((waited + 5))
done
log "Garage is healthy; cluster layout is committed."

# --------------------------------------------------------------------------
# 2. Mint a scoped, expiring admin token and do the real work with that.
#
# Required by the garage-bucket-provisioning spec: the working credential is
# limited to the six endpoints below and expires on its own. Honest caveat —
# this pod still holds the master token, because minting a scoped token is
# itself a master-token operation. What this buys is that the credential
# actually used for the provisioning calls cannot read cluster status, cannot
# touch the layout, and cannot mint further tokens (Garage rejects
# `CreateAdminToken`/`UpdateAdminToken` in a scope as trivial privilege
# escalation), and that it is revoked on exit and expires regardless.
# --------------------------------------------------------------------------
TOKEN="$GARAGE_ADMIN_TOKEN"

api() { # api <METHOD> <PATH> [JSON_BODY]
  _method="$1"
  _path="$2"
  _body="${3:-}"
  if [ -n "$_body" ]; then
    _code=$(curl -sS -o /tmp/api.out -w '%{http_code}' -X "$_method" \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d "$_body" "${GARAGE_ADMIN_URL}${_path}")
  else
    _code=$(curl -sS -o /tmp/api.out -w '%{http_code}' -X "$_method" \
      -H "Authorization: Bearer $TOKEN" "${GARAGE_ADMIN_URL}${_path}")
  fi
  if [ "$_code" -lt 200 ] || [ "$_code" -ge 300 ]; then
    log "admin API $_method $_path failed with HTTP $_code:"
    cat /tmp/api.out >&2
    echo >&2
    return 1
  fi
  cat /tmp/api.out
}

SCOPED_TOKEN_ID=""
revoke_scoped_token() {
  [ -n "$SCOPED_TOKEN_ID" ] || return 0
  TOKEN="$GARAGE_ADMIN_TOKEN"
  api POST "/v2/DeleteAdminToken?id=${SCOPED_TOKEN_ID}" >/dev/null 2>&1 ||
    log "WARNING: could not revoke scoped admin token ${SCOPED_TOKEN_ID}; it expires on its own."
  SCOPED_TOKEN_ID=""
}
trap revoke_scoped_token EXIT INT TERM

expires_at=$(date -u -d "@$(($(date +%s) + 3600))" +%Y-%m-%dT%H:%M:%SZ)
token_response=$(api POST /v2/CreateAdminToken "$(
  cat <<EOF
{"name":"caelus-provisioning-$(date +%s)",
 "expiration":"${expires_at}",
 "scope":["ListBuckets","CreateBucket","ListKeys","CreateKey","GetKeyInfo","AllowBucketKey"]}
EOF
)")
SCOPED_TOKEN_ID=$(echo "$token_response" | jq -r '.id')
TOKEN=$(echo "$token_response" | jq -r '.secretToken')
log "using scoped admin token ${SCOPED_TOKEN_ID}, expiring ${expires_at}"

# --------------------------------------------------------------------------
# 3. Per environment: bucket, access key, permission grant.
#
# Naming convention, single-sourced from var.environments in Terraform:
#   bucket      <env>              (the bucket namespace is private to this
#                                   instance, so a prefix would carry no
#                                   information)
#   access key  caelus-api-<env>   (mirrors freepod-dev / freepod-prod)
# --------------------------------------------------------------------------
mkdir -p "$CREDS_DIR"
set --

for env in $ENVIRONMENTS; do
  key_name="caelus-api-${env}"

  bucket_id=$(api GET /v2/ListBuckets |
    jq -r --arg b "$env" 'map(select(.globalAliases | index($b))) | .[0].id // empty')
  if [ -z "$bucket_id" ]; then
    bucket_id=$(api POST /v2/CreateBucket "{\"globalAlias\":\"${env}\"}" | jq -r '.id')
    log "created bucket '${env}' (${bucket_id})"
  else
    log "bucket '${env}' already exists (${bucket_id})"
  fi

  access_key_id=$(api GET /v2/ListKeys |
    jq -r --arg n "$key_name" 'map(select(.name == $n)) | .[0].id // empty')
  if [ -z "$access_key_id" ]; then
    # Garage mints the key material; it cannot be pre-generated by Terraform
    # because `ImportKey` rejects keys Garage did not generate (the access key
    # ID carries a checksum). This is the only moment the secret is returned by
    # a create call, but GetKeyInfo?showSecretKey can read it back later, which
    # is what makes the re-run path below possible without rotating anything.
    key_response=$(api POST /v2/CreateKey "{\"name\":\"${key_name}\",\"neverExpires\":true}")
    access_key_id=$(echo "$key_response" | jq -r '.accessKeyId')
    secret_access_key=$(echo "$key_response" | jq -r '.secretAccessKey')
    log "created access key '${key_name}' (${access_key_id})"
  else
    log "access key '${key_name}' already exists (${access_key_id}) - not rotating"
    secret_access_key=$(api GET "/v2/GetKeyInfo?id=${access_key_id}&showSecretKey=true" |
      jq -r '.secretAccessKey')
  fi

  # Read and write on THIS environment's bucket only. `owner` is deliberately
  # omitted: AllowBucketKey activates the flags set to true and leaves the rest
  # untouched, so omitting it neither grants nor is needed — bucket lifecycle
  # configuration (the next Job step) is accepted by Garage on a read+write key.
  api POST /v2/AllowBucketKey \
    "{\"bucketId\":\"${bucket_id}\",\"accessKeyId\":\"${access_key_id}\",\"permissions\":{\"read\":true,\"write\":true}}" \
    >/dev/null
  log "granted read+write on '${env}' to '${key_name}'"

  # Handed to the lifecycle step through a memory-backed emptyDir, so the
  # credentials never touch this node's disk.
  umask 077
  cat >"${CREDS_DIR}/${env}.env" <<EOF
AWS_ACCESS_KEY_ID=${access_key_id}
AWS_SECRET_ACCESS_KEY=${secret_access_key}
EOF

  set -- "$@" \
    --from-literal="${env}_access_key_id=${access_key_id}" \
    --from-literal="${env}_secret_access_key=${secret_access_key}"
done

# --------------------------------------------------------------------------
# 4. Publish the credentials as a Secret in this namespace.
#
# Terraform reads this back through a `kubernetes_secret` data source and
# exposes it as outputs, which the operator pastes into the gitignored
# tf/app/secrets.auto.tfvars — the same handoff ritual as the Keycloak client
# secrets. The Job deliberately does NOT write into tf/app's namespaces: that
# would need cross-namespace write RBAC and would invert the ownership boundary
# between the two root modules.
# --------------------------------------------------------------------------
kubectl create secret generic "$KEYS_SECRET_NAME" \
  --namespace "$NAMESPACE" "$@" \
  --dry-run=client -o yaml | kubectl apply -f - >&2

log "wrote Secret ${NAMESPACE}/${KEYS_SECRET_NAME}"
log "done."
