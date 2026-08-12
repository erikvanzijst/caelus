#!/bin/sh
# Applies the bucket lifecycle configuration. Second step of the
# `garage-provision` Job, in an S3-client image.
#
# This is a separate step from provision.sh because lifecycle is an S3-API
# operation (`PutBucketLifecycleConfiguration`), not a Garage admin-API or CLI
# one — so it needs an S3 client and the bucket's own access key rather than an
# admin token.
#
# Both of the lifecycle actions Garage implements are used, and they reclaim
# different things:
#
#   Expiration                       completed objects past their age
#   AbortIncompleteMultipartUpload   parts of uploads that never completed
#
# The second is not optional. Abandoned multipart parts consume disk while never
# appearing in a bucket listing — exactly the kind of invisible growth that
# produced this node's earlier disk-pressure incident.
#
# Declarative expiry is why this design needs no reaper CronJob and no cleanup
# code: reclamation is a property of the bucket, so it cannot be forgotten by a
# caller, skipped by a failed job, or lost in a refactor.
set -eu

: "${S3_ENDPOINT:?}"
: "${AWS_DEFAULT_REGION:?}"
: "${ENVIRONMENTS:?}"
: "${OBJECT_EXPIRY_DAYS:?}"
: "${CREDS_DIR:?}"

log() { echo "[lifecycle] $*" >&2; }

umask 077
cat >/tmp/lifecycle.json <<EOF
{
  "Rules": [
    {
      "ID": "expire-objects",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "Expiration": { "Days": ${OBJECT_EXPIRY_DAYS} }
    },
    {
      "ID": "abort-incomplete-multipart-uploads",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": ${OBJECT_EXPIRY_DAYS} }
    }
  ]
}
EOF

for env in $ENVIRONMENTS; do
  # Each bucket is configured with its own environment's key, so this step
  # needs no additional credential and holds no cross-environment authority.
  set -a
  # shellcheck disable=SC1090
  . "${CREDS_DIR}/${env}.env"
  set +a

  # Idempotent by nature: PutBucketLifecycleConfiguration replaces the whole
  # configuration, so re-running converges rather than accumulating rules.
  aws --endpoint-url "$S3_ENDPOINT" s3api put-bucket-lifecycle-configuration \
    --bucket "$env" \
    --lifecycle-configuration file:///tmp/lifecycle.json

  log "applied lifecycle to bucket '${env}' (expiry ${OBJECT_EXPIRY_DAYS}d)"
  aws --endpoint-url "$S3_ENDPOINT" s3api get-bucket-lifecycle-configuration --bucket "$env"
done

log "done."
