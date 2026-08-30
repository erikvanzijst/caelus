# ssh-auth — the SSH auth resolver

sshpiper's gRPC plugin. On every SSH connection the edge asks one question — may
this key open the deployment this username names, and where is that deployment's
sidecar — and this answers it from the platform's own rows, in one query.

Spec: [ssh-auth-resolver](../openspec/specs/ssh-auth-resolver/spec.md),
[sftp-edge-routing](../openspec/specs/sftp-edge-routing/spec.md) · Rationale:
[ssh-grpc-auth-plugin](../openspec/changes/archive/2026-08-30-ssh-grpc-auth-plugin/design.md),
[var/ssh_access.md](../var/ssh_access.md) (the spikes, and what sshpiperd
actually does)

## Coupling

This directory hardwires its query against the platform's schema, and knows a
deployment's sidecar is at `<name>-sftp.<namespace>.svc` as the user `<name>`.
That is deliberate; the design document argues it. The chart must therefore not
let a product choose a different sidecar user — see `sftp-chart-contract`.

It also treats `deployment.name` as globally unique, which the schema does not
guarantee — only `(namespace, name)`. That is a known wart being fixed at the
source, and `LIMIT 1` keeps the query deterministic until it is.

## Configuration

| Variable                                   | Default                         |                                                                                                                    |
|--------------------------------------------|---------------------------------|--------------------------------------------------------------------------------------------------------------------|
| `CAELUS_SSH_RESOLVER_DATABASE_URL`         | *required*                      | libpq URL for the `caelus_ssh_resolver` role. **Not** SQLAlchemy's `postgresql+psycopg://` form, which pgx rejects |
| `CAELUS_SSH_RESOLVER_LISTEN`               | `127.0.0.1:50051`               | Loopback. Binding it anywhere reachable means mTLS first — see the design document                                 |
| `CAELUS_SSH_RESOLVER_UPSTREAM_KEY_PATH`    | `/upstreamkey/ssh_upstream_key` | The environment's upstream private key, mounted from a Secret                                                      |
| `CAELUS_SFTP_SIDECAR_PORT`                 | `2222`                          |                                                                                                                    |
| `CAELUS_SSH_RESOLVER_POOL_SIZE`            | `4`                             |                                                                                                                    |
| `CAELUS_SSH_RESOLVER_STATEMENT_TIMEOUT_MS` | `2000`                          |                                                                                                                    |

It serves `grpc.health.v1` on the same port, answered from a real query. The
container's readiness probe is `ssh-auth -healthcheck`, which asks a running
server and reports it as an exit status; it must be an `exec` probe, because
Kubernetes dials a native `grpc` probe at the pod IP and this binds loopback.

## The database role

`tf/app/caelus/ssh-resolver-bootstrap.sql` creates `caelus_ssh_resolver` with
`SELECT` on `deployment` and `user_ssh_key` and nothing else, applied by an init
container on every rollout. `role_test.go` runs that same file, so the grant is
tested rather than described.

## Rotating the upstream keypair

Every sidecar trusts the public half, so this is a fleet-wide operation: publish
a chart carrying the new public key, roll every deployment onto it, then repoint
the Secret this reads. Nothing trusts both keys at once unless a chart version
carries both, so plan it as two chart changes rather than one.

## Working on it

```sh
go test ./...          # needs the migrated test database; see below
go build ./...
./gen.sh               # only when proto/plugin.proto changes
```

The tests read the platform's real tables, so they need the database
`api/tests/conftest.py` creates and migrates — `CAELUS_TEST_DATABASE_URL` is
already set inside the devcontainer, and one run of the API suite creates it.
They build and remove their own rows, so they can share it with that suite.

`gen.sh` fetches a pinned protoc and the two pinned Go plugins into `.tools/`
(gitignored). `proto_test.go` regenerates with the same pins and compares byte
for byte, so a re-vendor that skipped the regeneration fails the suite. The
proto's provenance is in `proto/UPSTREAM`.

## Releasing

`VERSION` is an immutable tag and the image is never re-pushed: rolling the edge
back means pointing Terraform at the previous version, which only works while
that version is still the image it was.

```sh
./scripts/build-images.sh --ssh-resolver
```

Then repoint `tf/app/sshpiper` and apply. `scripts/rollout.sh` does not touch
it — that is the point of it having its own version.
