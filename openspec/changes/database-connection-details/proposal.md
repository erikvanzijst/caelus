## Why

A `custom` deployment with relational storage gets a PostgreSQL database whose
credentials the tenant cannot see. The password is platform-generated, encrypted at rest,
and delivered straight into the pod as environment variables; it is deliberately not a
var, so no tenant-facing surface returns it. The result is a database the owner can use
only from code they have already deployed, and cannot inspect, migrate, seed, or reason
about at all.

`var/relational_storage_v2.md` records this as deferred work — *"Tenant-facing surface:
dashboard panel, `freepod status`, connection details"* — and the SSH access design
depends on it: a client cannot build a `postgresql://` URL, or know which host to forward
to, without being told. Reading it out of the running pod is not an option, since that
requires a healthy application container and a shell, and the whole point is to reach a
database whose application is broken.

There is a second, smaller reason that pays for itself immediately: a deployment whose
database has crossed its quota is switched to read-only, and later refused logins
entirely. Today that surfaces to the tenant as writes that mysteriously fail. The same
endpoint can say so plainly.

## What Changes

- A **deployment-scoped read endpoint** returning the deployment's database connection
  details as components: pooler host, port, database name, role name and password. No
  composed connection URL — see below.
- The same response reports **quota state and usage** — how much the database is using,
  against what allowance, when that was last measured, and whether the database is
  currently read-only or suspended.
- A **UI panel** on the deployment view, alongside the existing SFTP panel, showing the
  database name, role and a masked password with copy affordances, plus the quota figures.
- A **`freepod db status` command**, reporting the same from the client the developer
  already has open, with the password masked unless `--show-password` asks for it.
- **Neither surface shows an address or a connection URL.** The pooler is reachable only
  from inside the cluster, so a URL shown here would connect from nowhere the reader is
  standing. The endpoint returns the address because a forwarding client needs to know what
  to tunnel to; the surfaces a person reads report the database's identity, its credential
  and its health, which is the part that stays true on both sides of a future tunnel. The
  one URL that will ever connect is composed by `freepod db proxy`, around its own local
  address, in the SSH forwarding change.
- The endpoint's absence semantics mirror the existing SFTP credentials endpoint: a stable
  not-found the UI keys on to hide the panel when the product has no relational storage.
  A database is provisioned before its deployment reaches ready, so a settled deployment
  always has one, and the transient window is described by the deployment's own status.

**The address is in-cluster and not reachable from a developer's machine.** The pooler has
no public endpoint and this change does not give it one. What this delivers today is that a
tenant can finally *see* the credential they own and their database's health; connecting
from a laptop needs the SSH forwarding work, and both surfaces say so rather than showing
an address that invites an attempt that cannot succeed.

## Capabilities

### New Capabilities

- `database-credentials-api`: the deployment-scoped endpoint, what it returns, how it
  reports quota and usage, its absence semantics, and who may read which parts of it.
- `database-credentials-ui`: the deployment-view panel that presents those details,
  including how it handles a secret, an unreachable address, and a degraded database.
- `cli-database-status`: the `freepod db` command group and its first member, `db status`
  — what it prints, how it masks a live credential, and why it prints no address.

### Modified Capabilities

None. Provisioning, the quota ladder, the pooler, and the Secret delivered to the pod are
all unchanged; this change only reads what already exists.

## Impact

**API**

- A new read endpoint under the deployment, mirroring the existing SFTP credentials
  endpoint's shape and authorization pattern.
- A read model composed from the `deployment_database` record, the deployment's plan
  allowance, and platform pooler configuration. Components only; no URL is assembled
  anywhere in this change, so no percent-encoding rule is introduced by it either.
- Decrypting the stored password requires the encryption keyring, which the API already
  holds and refuses to start without.
- `caelus` CLI parity, per the API/CLI lockstep convention.

**UI**

- A new panel component under `ui/src/components/`, mounted on the deployment view beside
  the SFTP panel and following the same conditional-display pattern. It renders identity,
  credential and health — no host, port or URL.

**Client**

- A new `db` command group in `cli/`, holding `status` only. The group is the one
  `var/ssh_access.md` D10 reserves for `db proxy` and `db shell`; creating it here leaves
  the forwarding change its two members and nothing to invent about where they live.
- No new client machinery: the command is a read through the existing `ApiClient`,
  resolving its deployment from the project file like every other project-scoped command.

**Not affected**

- No chart, reconciler, worker, NetworkPolicy, Terraform, or edge configuration. Nothing
  is provisioned, rotated, or mutated by reading.
- Nothing about connecting. `freepod db status` reads and prints; the commands that open a
  connection — `db proxy`, `db shell` — remain the SSH forwarding change's work, and with
  them the sole connection URL in the product and the obligation to encode it correctly.
