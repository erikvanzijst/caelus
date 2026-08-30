# ssh-auth — the SSH auth resolver

sshpiper's gRPC plugin. On every SSH connection the edge asks one question —
may this key open the deployment this username names, and where is that
deployment's sidecar — and this answers it from the platform's own rows.

Nothing is projected into the cluster. There is no routing object, no copy of
anyone's keys, and so nothing for the reconciler to create, remove or sweep.
Revoking a key is deleting the row; the next connection is refused, with no
interval in between and nothing downstream to refresh.

See `openspec/changes/ssh-grpc-auth-plugin/` for the design and
`var/ssh_access.md` for the access model, including the spike that established
what sshpiperd actually does.

## What it does, in one query

```sql
SELECT d.name, d.namespace, d.status,
       d.name || '-sftp.' || d.namespace || '.svc' AS host,
       (k.id IS NOT NULL) AS key_registered
  FROM deployment AS d
  LEFT JOIN user_ssh_key AS k
         ON k.user_id = d.user_id AND k.fingerprint = $2
 WHERE d.name = $1 AND d.status <> 'deleted'
 LIMIT 1
```

Three things about it are deliberate:

- **The join is outer.** An inner join would answer "admit or not" in one row,
  but no rows would then mean either "no such deployment" or "that key is
  registered nowhere". Operators have to be able to tell those apart even
  though the client must not.
- **It does not go through `user`.** `deployment.user_id` and
  `user_ssh_key.user_id` are the same column; the extra hop returns identical
  rows and would put a table of email addresses into the grant of a service on
  the public SSH port.
- **`deployment.name` is treated as globally unique.** The schema guarantees
  only `(namespace, name)`. That is a wart being fixed at the source — the SSH
  username should be the namespace, which already is globally unique — and
  `LIMIT 1` keeps this deterministic until it is.

Reachability is an allowlist of `ready` and `error`. `error` is in it: file
access matters most when the application is broken, and the SFTP Service
publishes not-ready addresses for that same reason (`var/ssh_access.md` D17).

## Deliberate coupling

This directory hardwires the query above against the platform's schema, and
knows that a deployment's sidecar is reachable at `<name>-sftp.<namespace>.svc`
as the user `<name>`. Both are stable parts of the architecture, and paying a
schema-mapping layer for them would buy nothing.

The chart must therefore not let a product choose a different internal user; see
the `sftp-chart-contract` spec.

## Configuration

| Variable | Default | |
|---|---|---|
| `CAELUS_SSH_RESOLVER_DATABASE_URL` | *required* | libpq URL for the `caelus_ssh_resolver` role. **Not** SQLAlchemy's `postgresql+psycopg://` form |
| `CAELUS_SSH_RESOLVER_LISTEN` | `127.0.0.1:50051` | Loopback: the edge reaches it inside the pod, nothing else should |
| `CAELUS_SSH_RESOLVER_UPSTREAM_KEY_PATH` | `/upstreamkey/ssh_upstream_key` | The environment's upstream private key, mounted from a Secret |
| `CAELUS_SFTP_SIDECAR_PORT` | `2222` | |
| `CAELUS_SSH_RESOLVER_POOL_SIZE` | `4` | |
| `CAELUS_SSH_RESOLVER_STATEMENT_TIMEOUT_MS` | `2000` | A slow database must refuse connections, not hang the edge |

It serves `grpc.health.v1` on the same port, answered from a real query rather
than from being alive: a resolver that is running and cannot read the store
admits nobody, and the SSH edge's readiness probe has to say so.

## The database role

`tf/app/caelus/ssh-resolver-bootstrap.sql` creates `caelus_ssh_resolver` with
`SELECT` on `deployment` and `user_ssh_key` and nothing else, applied by an init
container on every rollout. `role_test.go` runs that same file.

## Rotating the upstream keypair

The private half lives only here and in Terraform state; every sidecar trusts
the public half. Rotating it is therefore a fleet-wide operation: publish a
chart carrying the new public key, roll every deployment onto it, then repoint
the Secret this reads. There is no window in which both keys are trusted unless
the chart carries both, so plan it as a two-step chart change.

## Working on it

```sh
go test ./...          # needs the migrated test database; see below
go build ./...
./gen.sh               # only when proto/plugin.proto changes
```

The tests read the platform's real tables, so they need the database
`api/tests/conftest.py` creates and migrates — `CAELUS_TEST_DATABASE_URL` is
already set inside the devcontainer, and one run of the API suite creates it.
They build and remove their own rows and can share that database with the API
suite.

`gen.sh` fetches a pinned protoc and the two pinned Go plugins into `.tools/`
(gitignored). `proto_test.go` regenerates with the same pins and compares byte
for byte, so a re-vendor that skipped the regeneration is a failed test.

## Releasing

`VERSION` is an immutable tag. The image is never re-pushed: rolling the SSH
edge back means pointing Terraform at the previous version, which only works
while that version is still the image it was.

```sh
./scripts/build-images.sh --ssh-resolver
```

Then repoint `tf/app/sshpiper` and apply. `scripts/rollout.sh` does not touch
it — that is the point of it having its own version.
