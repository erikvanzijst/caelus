## Context

See `proposal.md` § Why for motivation.

Six facts about the current system shape everything here.

1. **Merged Helm values are logged and persisted tenant-side.** The provisioner logs
   them in full at INFO and Helm writes them into a release Secret in the tenant's own
   namespace. `_ensure_object_storage` already documents this and routes the S3 secret
   key through a Kubernetes Secret instead (`api/app/services/reconcile.py:360`). A
   database password must take the same route.
2. **`vars` is the tenant-writable channel.** A deployment's vars become its pod
   environment and a tenant can set them, so platform-injected credentials cannot
   travel that way.
3. **Tenant egress is default-deny.** `build_tenant_baseline_policy`
   (`api/app/network_policy.py`) permits only in-namespace traffic, DNS, the SMTP relay
   and internet-minus-internal-CIDRs. A tenant pod cannot reach any in-cluster service
   today. The policy is byte-identical fleet-wide and re-applied by
   `caelus sync-network-policies`.
4. **`plan_template_version.storage_bytes` is already double-booked** — the Garage
   bucket quota (`object_storage.resolve_quota_bytes`) and the chart's PVC size
   (`caelus.plan.storageBytes`). It cannot take a third meaning.
5. **Reconcile is re-entrant and its jobs can be stranded.** A worker restart leaves
   jobs in `running` with no lease expiry, so every step added to the reconcile path
   must be re-runnable and nothing on the delete path may be irreversible.
6. **`local-path` is the only storage class; it enforces no volume size and cannot
   expand one.** Verified: `ALLOWVOLUMEEXPANSION: false`, and every PV is a plain
   directory under `/var/lib/rancher/k3s/storage/`. This is the most consequential
   infrastructure constraint in the change.

## Goals / Non-Goals

**Goals**

- Isolation that is enforced rather than assumed.
- Provisioning that is a live operation — no PostgreSQL or pooler restart, ever.
- One credential path, identical in shape to object storage's.
- Enforcement that survives a tenant who reads the PostgreSQL manual.
- A physical-safety mechanism independent of the customer-facing quota.

**Non-Goals** (beyond the proposal's scope boundaries)

- Exactness in client-connection accounting. See D9.
- Any recovery from an exhausted quota other than raising the allowance. See D8.
- Backups reachable by a tenant, in any form.

## Decisions

### D1. Isolation requires an explicit REVOKE

PostgreSQL grants `CONNECT` to `PUBLIC` on every new database, so database-per-tenant
is not isolation by itself. Verified on PostgreSQL 16: a freshly provisioned tenant
connected to another tenant's database *and* to the control-plane database, enumerated
the other tenant's tables (system catalogs are world-readable), and — with a
`CONNECTION LIMIT` set — exhausted the owner's own connection allowance, producing
`FATAL: too many connections for database "dpl_b"` for the legitimate owner. Row data
was protected by ordinary table privileges.

Provisioning therefore runs `REVOKE ALL ON DATABASE <db> FROM PUBLIC` on every tenant
database, and the same revocation is applied to the cluster's `postgres` and
`template1` at bootstrap. Verified: afterwards the cross-tenant connection is refused
and the owner is unaffected.

`ALL` rather than `CONNECT`, which is tidiness rather than a hole: revoking only
`CONNECT` leaves `PUBLIC` holding `TEMPORARY` — `datacl` reads `=T/dpl_x` — which is
inert once `CONNECT` is gone, and which the owner keeps regardless through ownership
(verified: the owner still creates temporary tables afterwards). Revoking `ALL` leaves
one entry in the ACL instead of two, so a reader has nothing to reason about.

The role is created with every attribute negated —
`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`. `NOCREATEDB` is what
stops a tenant provisioning around its own quota.

*Residual, accepted:* `pg_stat_activity` still exposes other tenants' `usename` and
`datname`. Query text is redacted for non-superusers. Not worth a custom view.

### D2. Identifiers are `dpl_` plus the deployment UUID with hyphens removed

`DeploymentORM.id` is a `uuid4`. Rendered naively the identifier does not parse —
`CREATE ROLE dpl_8f31c2-aaaa-...` is a syntax error — and quoting would infect every
SQL statement, pooler config line and operator query permanently. Removing the hyphens
yields 36 characters, inside the 63-byte `NAMEDATALEN` limit and valid unquoted.

Database and role share one name. That is what keeps a deployment attributable across
`pg_database`, `pg_roles`, `pg_stat_activity`, the pooler and the control plane with no
mapping table.

### D3. The tenant owns its database

The honest model: normal ownership, trusted extensions, clean `pg_dump` semantics.

Two accepted consequences. The tenant can drop their own database (verified) — the
reconciler re-provisions it empty, which it must be able to do anyway. And ownership is
what makes eager role cleanup expensive; see D11.

### D4. The password is platform-held and re-asserted every reconcile

`ensure_object_storage` is re-runnable because Garage lets a secret key be read back.
PostgreSQL stores only a SCRAM verifier, so the platform must hold the password. It is
stored encrypted under the existing `var_crypto` keyring, which the API and workers
already refuse to start without.

**Write order is load-bearing: persist the ciphertext, then `ALTER ROLE`.** A crash
between the two leaves a stored password that does not yet work, which the next
reconcile fixes. The reverse order leaves a live credential nobody holds.

**This is the keyring's second encrypted column, and the keyring machinery is written
for one.** `verify_keyring` checks stored `key_id`s only in `deployment_var`, and the
rotation sweep re-encrypts only that table — so without expanding both, a retired key
still named by `deployment_database` rows passes startup and surfaces inside a reconcile
instead, and `caelus vars-rotate` reports nothing left to rotate while telling the
operator it is safe to retire a key that is still in use. Following the documented
rotation procedure correctly would then leave every tenant password unreadable: not
permanent loss, since this decision's repair path covers an unreadable stored password
as well as a missing one, but a fleet-wide outage that clears only as each deployment
next rolls out. Both functions become generic over a registry of encrypted columns
rather than gaining a second hardcoded branch — this is the second such column and will
not be the last, and the registry is what makes "what is encrypted under this keyring"
answerable in one place before an operator retires a key.

Reconcile re-asserts unconditionally. A tenant *can* change their own password
(verified), which desynchronizes the stored copy — and since the credential reaches the
app as an environment variable, a tenant who rotates has already broken their own app
at the next pod restart. Re-assertion makes the stored value authoritative and the
drift self-healing. Tenant-side rotation is documented as unsupported.

**Alternative rejected:** repair-only, matching `ensure_object_storage`. It preserves a
tenant's rotation while handing their pod a credential that no longer works — a more
confusing failure than silent reversion.

### D5. Credentials travel in a Secret; values carry references only

A mechanical mirror of object storage. The reconciler writes
`<deployment.name>-database` into the tenant namespace with `DATABASE_URL` and the
discrete `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` / `PGDATABASE`. The URL covers
every ORM; the discrete variables are what libpq, `psql` and `pg_dump` read unaided. No
further aliases — object storage ships eight because S3 SDKs disagree; libpq does not.

Helm values receive host, port, database name, role name and the Secret's name under
the reconciler-owned `caelus.database` namespace. The chart consumes the Secret with
`envFrom`. Both `relationalStorage.enabled` (static product declaration) and
`caelus.database` (per-deployment runtime facts) are added to
`products/custom/chart/values.schema.json`, keeping the same separation the schema
already documents for object storage.

### D6. Provisioning order, and failing closed

Placement matches `_ensure_object_storage`: after `ensure_namespace` and
`ensure_tenant_isolation`, before `helm_upgrade_install`, so no pod starts expecting a
Secret that is not there.

```sql
--  1. resolve the allowance first; a misconfigured plan provisions nothing
--  2. CREATE ROLE ...          (if absent) NOSUPERUSER NOCREATEDB NOCREATEROLE ...
--  2b. GRANT <role> TO caelus_admin WITH SET TRUE, INHERIT FALSE   (see below)
--  3. ALTER ROLE ... PASSWORD  (always; D4)
--  4. CREATE DATABASE ... OWNER ...   (if absent; cannot run in a transaction)
--  5. SET ROLE <tenant>; REVOKE ALL ON DATABASE ... FROM PUBLIC; RESET ROLE
--       (always; D1 -- owner-scoped, see below)
--  5b. assert has_database_privilege('public', <db>, 'CONNECT') IS FALSE,
--       and raise if it is not (see below)
--  6. ALTER ROLE ... SET temp_file_limit = '64MB'  (always)
--  7. ALTER ROLE ... SET statement_timeout = '30s'
--  8. ALTER ROLE ... SET idle_in_transaction_session_timeout = '60s'
--  9. upsert the deployment_database row
-- 10. evaluate_quota_state(deployment)
```

Each step reads before it writes and is verified independently, so a run interrupted
between any two is finished by the next rather than mistaken for complete. Steps 5–8
are re-asserted every time so a tenant's `RESET` or a settings change takes effect
without a migration.

Step 10 keeps quota state correct on every apply: a deployment now under its allowance
has read-only cleared before Helm runs, one still over it has its state re-asserted. It
calls the *same* `evaluate_quota_state` the housekeeping worker uses (D10) — one
implementation. Unconditionally *clearing* read-only would let any over-quota tenant
buy a write window by redeploying.

**Fail-closed:** an unreachable tenant cluster fails the reconcile rather than
deploying a pod without a database, matching `resolve_quota_bytes`, which refuses to
invent an allowance.

#### Bootstrap

Cluster-level setup — `REVOKE CONNECT ON DATABASE postgres/template1 FROM PUBLIC`, the
platform admin role with its role grants and its `SET` grant on `temp_file_limit`, and
the `pgbouncer_auth` role with its
`SECURITY DEFINER` `user_lookup` function is infrastructure setup, so it is expressed as infrastructure: an
idempotent SQL script held in the repo, loaded into a ConfigMap by Terraform, and
applied by an init container running `psql` from a stock `postgres:18-alpine` image.

The bootstrap is readable as plain SQL in review, and is verified the way
it actually matters — run it twice against a scratch cluster and assert identical state.

PostgreSQL has no `CREATE ROLE IF NOT EXISTS`, so idempotency is explicit: `DO $$ ... $$`
guards around role creation, `CREATE SCHEMA IF NOT EXISTS`, `CREATE OR REPLACE
FUNCTION`, and `REVOKE`/`GRANT`, which are naturally repeatable. The `pgbouncer_auth`
password is generated by Terraform, stored in a Secret consumed by both this container
and the pooler, and passed to `psql` as a variable rather than interpolated into the SQL
text.

It runs as an ordered init container on the **reconcile worker**, following the pattern
`alembic upgrade head` and `caelus catalog apply` already establish on the API Deployment
(`tf/app/caelus/deployment-api.tf:40`): a non-zero exit fails the init container, the pod
never becomes ready, and the previous ReplicaSet keeps serving. The worker rather than
the API, because it is the first process to write to the tenant cluster and because
putting it on the API would couple control-plane startup to tenant-cluster availability
— the opposite of D14's intent. The pod template carries a hash of the SQL so that
changing the script forces a rollout; without that a ConfigMap edit would sit unapplied
until the next unrelated restart.

Three alternatives rejected.

**`/docker-entrypoint-initdb.d/`** is the obvious candidate and is wrong for one
decisive reason: it fires exactly once. The image's entrypoint guards it with

```sh
# only run initialization on an empty data directory
if [ -z "$DATABASE_ALREADY_EXISTS" ]; then
    ...
    docker_process_init_files /docker-entrypoint-initdb.d/*
```

and `DATABASE_ALREADY_EXISTS` is set as soon as `$PGDATA/PG_VERSION` exists. So the
bootstrap could never be changed or repaired without emptying the data directory —
destroying every tenant database — and a script that is skipped produces no error and no
log line, so the failure surfaces somewhere else entirely. (`conf.d` is a different
thing again: `postgresql.conf`'s `include_dir`, for `.conf` settings, not SQL.)

**A Terraform-managed Job** would not gate the worker: a failed bootstrap would let the
worker start and fail every reconcile instead. It also needs its own readiness wait,
since `depends_on` orders creation rather than readiness, and it leaves completed objects
to reap.

**A Terraform PostgreSQL provider** would need network reach to a ClusterIP service from
the operator's machine, which means a port-forward or an exposed endpoint, and D15 exists
precisely to avoid adding one.

#### The platform admin role needs no superuser

Only the bootstrap connects as superuser — it must, to install a `SECURITY DEFINER`
function over `pg_authid` and to create the admin role. **Every runtime process uses a
non-superuser `caelus_admin`**, and the full lifecycle was verified to work under it:

| Operation                                              | What makes it work                                              |
|--------------------------------------------------------|-----------------------------------------------------------------|
| `CREATE ROLE` / `DROP ROLE`                            | `CREATEROLE` (which confers `ADMIN OPTION` on roles it creates) |
| `CREATE DATABASE ... OWNER <tenant>`                   | `CREATEDB`, **plus `SET` on the tenant role**                   |
| `pg_database_size` with `CONNECT` revoked              | `pg_read_all_stats`                                             |
| `pg_terminate_backend` on a tenant backend             | `pg_signal_backend`                                             |
| `ALTER DATABASE ... SET default_transaction_read_only` | `SET ROLE <tenant>` first — the tenant owns the database        |
| `DROP DATABASE ... WITH (FORCE)`                       | `SET ROLE <tenant>` first, same reason                          |
| `REVOKE CONNECT ON DATABASE ... FROM PUBLIC`           | `SET ROLE <tenant>` first, same reason                          |
| `ALTER ROLE <tenant> SET temp_file_limit`              | `GRANT SET ON PARAMETER temp_file_limit TO caelus_admin` (PG15+) |

Two of those rows were established by running the lifecycle against a real
non-superuser admin on 18.6, and each is a trap that does not announce itself:

- **`REVOKE CONNECT` is owner-scoped like the other two.** Run by the admin
  without `SET ROLE` it does not error — it emits
  `WARNING: no privileges could be revoked` and leaves `PUBLIC` holding
  `CONNECT`. Verified: `datacl` kept `=Tc/dpl_x` without the `SET ROLE` and
  dropped to `=T/dpl_x` with it. Since D1's cross-tenant isolation *is* this
  revocation, a silently skipped step 5 would leave every tenant database
  reachable by every other role while provisioning reported success.

  **Hence step 5b.** The lesson is not that a `SET ROLE` was missed once; it is
  that this security property can fail *without erroring*, so nothing downstream
  would notice. `caelus_admin` can read the property back directly —
  `SELECT has_database_privilege('public', 'dpl_x', 'CONNECT')`, which needs no
  `CONNECT` of its own on that database (verified: `t` before the revoke, `f`
  after) — and raising when it comes back true turns a silent isolation failure
  into a loud provisioning failure. That is the same fail-closed posture as
  `resolve_quota_bytes` refusing to invent an allowance, and it costs one query
  on a path that already issues nine statements.
- **`temp_file_limit` cannot be set by a non-superuser at all**, not even on
  another role: `ERROR: permission denied to set parameter "temp_file_limit"`.
  The grant above is what lets the bootstrap hand that one parameter to
  `caelus_admin` without handing it superuser. Enforcement is unaffected —
  verified after the grant that the admin can set the limit on a tenant role
  and the tenant is still refused `SET temp_file_limit` in its own session.

The `SET ROLE` requirement is the non-obvious one and it is load-bearing for both
enforcement mechanisms. `CREATEROLE` alone is not enough: creating a role confers
`admin_option = t` but `set_option = f` (verified), and without `SET`,
`CREATE DATABASE ... OWNER` fails with `must be able to SET ROLE "dpl_x"` and the
owner-scoped statements fail with `must be owner of database`. Hence the explicit grant
in the provisioning sequence above, with **`INHERIT FALSE`** so the admin never silently
acquires tenant privileges and must assume the role deliberately for the two operations
that need it.

This keeps superuser credentials confined to a single init container that runs at pod
start and holds no long-lived process, which is a materially smaller blast radius than
handing them to the reconcile worker and the housekeeping worker for the lifetime of the
platform.

*Of note:* `temp_file_limit` is superuser-only to raise (verified) so it is real
enforcement; `statement_timeout` is tenant-overridable (verified) so it guards against
buggy tenants, not hostile ones. Temporary files also live outside the per-database
directory and so are invisible to the logical quota, which is why the limit matters.

### D7. Read-only is advisory, re-asserted, and that is the design

Every lever was tested against a tenant that owns its database:

| Lever | Tenant can undo it? |
| --- | --- |
| `ALTER DATABASE ... SET default_transaction_read_only` | **Yes** — per session, and `RESET` permanently |
| `REVOKE INSERT, UPDATE ON ALL TABLES` | **Yes** — `GRANT` it back; new tables never covered |
| `ALTER DATABASE ... CONNECTION LIMIT` | **Yes** — the owner may change their own |
| `ALTER ROLE ... NOLOGIN` | **No** — `permission denied to alter role` |

**Role attributes are the only lever a database owner cannot defeat.**

`REVOKE INSERT/UPDATE` was considered and rejected: equally soft, misses tables created
after the revoke, and unlike one boolean it destroys state — undoing it correctly would
mean snapshotting and replaying the tenant's exact ACLs.

So `default_transaction_read_only` is the 100% mechanism, re-asserted on every
evaluation. Because the tenant owns the database, the worker must `SET ROLE` to it
before the `ALTER DATABASE` — see *The platform admin role needs no superuser* under
D6. **Its softness is deliberate.** At 100% an honest tenant's ORM sees a
read-only transaction and degrades gracefully with no platform involvement; a tenant who
defeats it keeps growing and trips 150%. That makes the second threshold an abuse
signal rather than an arbitrary number.

The hard block is **two** actions, both against PostgreSQL and neither touching the
pooler:

1. `ALTER ROLE ... NOLOGIN`, which also makes the pooler's lookup resolve nothing on a
   cache miss (D9).
2. Terminate the role's backends, which empties its pool.

`NOLOGIN` alone does not bite promptly under transaction pooling — the pooler's server
connections are already authenticated and get reused, and it caches credentials from
`auth_query`, so a client whose credential is already cached may still authenticate *at
the pooler*. Terminating the backends closes that gap: every subsequent query needs a
fresh server connection, and the server refuses it.

**No pooler eviction, and therefore no pooler admin credential.** Every path ends with
the tenant unable to execute queries: an existing client's next query finds an empty
pool and a refused server connection; a new client with a cached credential
authenticates and then hits the same refusal; a new client without one is rejected at
connect time because `auth_query` returns no row. Issuing `KILL` would change only
*which* error the tenant sees and how quickly idle client connections are reaped —
which is not worth a fourth credential, replicated per pooler instance, on the one code
path that would otherwise need fanning out.

### D8. The ladder, and the absent recovery path

| Threshold | State | Email |
| --- | --- | --- |
| 80% | `warned` | yes, rate-limited |
| 90% | `warned` | yes, rate-limited |
| 100% | `readonly`, re-asserted each evaluation | yes — states the database is read-only and the exit is support or a higher plan |
| 150% | `blocked` | see *Open Questions* |

**There is no recovery path.** Verified: read-only blocks `DELETE`, `DROP TABLE` and
`VACUUM`, and with no external access an over-quota tenant cannot delete data by any
means. `DELETE` alone would not help regardless — measured, a table stayed at 112 MB
after deleting every row and only fell to 7.6 MB after `VACUUM`.

Compounding this, **no operation currently changes a deployment's plan**:
`plan_template_id` is create-only (`api/app/services/deployments.py:266,288`),
`DeploymentUpdate` sets `extra="forbid"` with no plan field
(`api/app/models/core.py:568`), `subscriptions.py` has no change-plan function, and
nothing there enqueues a reconcile. That work is tracked separately and is **not part
of this change**; D6 step 10 means the exit begins working the day it lands. Until
then, crossing 100% is terminal for that deployment's data.

### D9. Suspension needs no custom auth machinery — `pg_shadow` already filters it

PgBouncer's documented default `auth_query` is:

```sql
SELECT rolname, CASE WHEN rolvaliduntil < now() THEN NULL ELSE rolpassword END
FROM pg_authid WHERE rolname=$1 AND rolcanlogin
```

`AND rolcanlogin` is already in the stock query, and `pg_shadow` carries the same filter
(`... FROM pg_authid WHERE pg_authid.rolcanlogin`, verified with `pg_get_viewdef`). A
role set to `NOLOGIN` therefore resolves to nothing — verified: the lookup returned one
row for an active tenant, **zero** once suspended, and one again when lifted.

**So PgBouncer's standard `auth_query` already refuses suspended tenants.** No custom
view, no filtered projection of control-plane state, and no replication of the
suspension bit onto the tenant cluster. `NOLOGIN` — already the exact backstop from D7,
and the one lever a database owner cannot defeat — *is* the state, and the stock
authentication path already reads it.

The authentication setup is therefore the ordinary PgBouncer recipe: a `pgbouncer_auth`
login role plus a `SECURITY DEFINER` `pgbouncer.user_lookup` function — in a `pgbouncer`
schema owned by the superuser, the function being necessary because a non-superuser
cannot read `pg_shadow` directly (verified: `permission denied for view pg_shadow`). Both are created by the bootstrap in D6's
migration step.

**Where it lives: the tenant cluster's own `postgres` maintenance database.** Two
constraints pin it there.

- `auth_query` runs against the PostgreSQL server the pooler proxies to. `auth_dbname`
  can name a `[databases]` entry with its own host, so pointing it at the control-plane
  database is technically possible — and is the wrong trade. It would make every tenant
  application's ability to authenticate depend on `caelus-postgres`, which is a single
  replica with a `Recreate` strategy in a 256Mi limit, and it would put
  tenant-traffic-driven query load on the platform's own database. That partly undoes
  D14's separation.
- It must not be a database a tenant owns. Without a pinned `auth_dbname` the pooler
  runs `auth_query` inside the client's *target* database, which the tenant owns and can
  create objects in — a pooler-wide authentication problem. The `postgres` maintenance
  database already has `CONNECT` revoked from `PUBLIC` by the bootstrap (D1), so no
  tenant can reach it.

No new database is created for this. Pinning also avoids a second problem the PgBouncer
documentation names: without `auth_dbname` the query runs in the target database, so a
`SECURITY DEFINER` function "needs to be installed into each database". Pinned, it is
installed once.

**Alternative rejected:** an earlier draft of this design had the pooler resolve
`auth_query` against a platform-owned view filtered by `deployment_database.suspended`.
It works, but it is redundant with `rolcanlogin`, and it would have required either a
cross-instance lookup or a copy of the suspension state on the tenant cluster kept in
sync by the worker. Both problems vanish once `NOLOGIN` is recognised as sufficient.

#### Keeping authentication out of the tenants' way

Running the lookup on the tenant cluster means it competes for that server's connection
slots. The lookup lives in its own `(pgbouncer_auth, auth_dbname)` pool, so no tenant's
full pool can starve it, and results are cached so the query rate is not proportional to
the connection rate. The remaining risk is server-wide `max_connections` exhaustion,
which PostgreSQL 16+ addresses directly: `reserved_connections` plus the
`pg_use_reserved_connections` predefined role (both verified present). `pgbouncer_auth`
is granted that role and a small reserve is configured, so authentication retains a slot
even when the cluster is otherwise full.

**Alternative rejected:** resolving `auth_query` against the control-plane database.
`auth_dbname` names a `[databases]` entry, which may carry its own host, so this is
possible — but `pg_authid` on `caelus-postgres` holds no `dpl_*` roles, so it would
require storing a SCRAM verifier per tenant in a control-plane table and keeping it in
sync with D4's password re-assertion. It would also extend every control-plane outage
into the data plane, including the *planned* ones: `caelus-postgres` runs a `Recreate`
strategy and so restarts on every update, and running tenant applications currently
survive that untouched.

#### Consequences for the pooler's high availability

The pooler runs two instances behind a Service, and its admin commands (`RELOAD`,
`KILL`, `RECONNECT`) are per-process with per-instance `auth_query` caches. **Nothing in
this design issues one.** Suspension is enforced entirely by role state on the server
(D7), provisioning needs no configuration write (D8), and no platform process holds a
pooler admin credential at all.

That is what makes scaling the pooler a pure capacity decision: there is no operation
whose correctness depends on reaching every instance, so adding or losing one changes
throughput and the arithmetic below, and nothing else.

Two further consequences of two instances, recorded because each is a trap later:
server connections multiply by instance count, so `default_pool_size × instances` is
what lands on `max_connections`; and every client-side limit is per-instance, so a limit
of 25 permits 50. That second point is why there is one global `max_user_connections`
and no per-plan tiering — a per-plan number would not mean what the plan says. **If
exact connection enforcement is ever needed it must be `ALTER ROLE ... CONNECTION
LIMIT`**, which is instance-agnostic, at the cost of being in backend rather than client
units.

### D10. One `caelus db-worker`, three ticks

A third long-running worker beside `caelus worker` and `caelus build-worker`. Every
periodic job here is the same shape of work — a sweep over `deployment_database`
holding one privileged connection — so they share a process and differ only in cadence.
Named `db-worker` rather than `quota-monitor` because quotas are not all it does.

| Tick | Default | Work |
| --- | --- | --- |
| quota | 60s, configurable | Measure and apply quota state fleet-wide |
| purge | daily | Drop database then role past `purge_after` |
| orphan | daily | Cluster objects no row accounts for |

**Ticks share a process but not a `try`.** The purge tick performs the only
irreversible operation in the change and a bug there must not stop quota enforcement,
or the reverse. Purge additionally refuses a null or future `purge_after`, caps how
many deployments it will purge per run so a bad clock cannot cascade, and logs every
drop with its deployment id.

What the quota poll is *for* is worth stating: customer-facing quota state, not cluster
safety. A tenant can write gigabytes inside any interval, so the poll is not and cannot
be what protects the volume — D13 is.

**The db-worker does not verify the keyring at startup**, unlike the API and
`caelus worker`. All three ticks connect as `caelus_admin` and act on cluster state; not
one of them decrypts a tenant password, so the check would gate quota enforcement,
purges and orphan sweeps on a keyring problem this process has no stake in. The two
processes that *do* read ciphertext already fail loudly, and both must be running for
the platform to function at all, so a third gate adds a failure mode without adding
coverage. If a tick ever needs a stored password — connecting *as* a tenant, which
nothing here does — it gains the check then.

**Alternative rejected:** folding quota work into the reconcile worker, which would
couple enforcement to Helm timeouts.

### D11. Deletion revokes now; destruction is deferred

Delete reconcile: `ALTER ROLE <role> NOLOGIN`, terminate the role's backends, record
`purge_after`. Bounded, fast, and tenant data untouched during the grace window.

The termination is there for the same reason it is part of the hard block (D7):
`NOLOGIN` does not close connections that are already authenticated, and under
transaction pooling the pooler reuses them — so without it a lingering pod could keep
writing to a deleted deployment's database through the grace window. Two statements
rather than one, both cheap, neither irreversible.

A second consequence of the row outliving the deployment: `evaluate_quota_state` returns
early once `purge_after` is set. Its below-threshold branch re-asserts `LOGIN`, so a
quota sweep over a deleted deployment's row would otherwise hand back the access this
step just took away. The purge tick later
runs `DROP DATABASE ... WITH (FORCE)` — which takes every object with it — then
`DROP ROLE`, by then dependency-free. The drop is owner-scoped, so it runs under
`SET ROLE <tenant>`; the subsequent `DROP ROLE` runs after `RESET ROLE`. Order matters
twice over: the role must still exist for the admin to assume it.

**Eager role-drop was tested and rejected.** `DROP ROLE` fails while the tenant owns
anything, and PostgreSQL checks across databases via `pg_shdepend`:
`ERROR: role "dpl_del" cannot be dropped because some objects depend on it / DETAIL: 2
objects in database dpl_del`. Making it work requires connecting into the tenant
database and running `REASSIGN OWNED BY ... ; DROP OWNED BY ...` — which does succeed,
and conveniently transfers the database itself — but it is an unbounded per-object
ownership rewrite inside the delete reconcile's budget, on a database whose object
count the platform does not control, and it mutates tenant data mid-grace.

Nothing irreversible runs on the delete path, per Context (5). `DROP DATABASE` cannot
run in a transaction and fails while sessions are connected, which is exactly why it
belongs in a separately re-runnable tick.

The orphan sweep is not guarding against vanished control-plane rows — those never
vanish (D12) — but against **partial provisioning**: D6 creates the role and database
at steps 2–4 and writes the row at step 9, so a worker killed in between leaves cluster
objects no row points at. It must cover roles as well as databases, since step 2
precedes step 4.

### D12. `deployment_database`, and `database_bytes`

`storage_bytes` cannot take a third meaning (Context 4), so `plan_template_version`
gains a nullable `database_bytes`, resolved fail-closed exactly as
`resolve_quota_bytes` does. Tiers: Free 100 MB, Basic 1 GB at EUR 3/month.

One `deployment_database` row per provisioned deployment. **Its absence means not
provisioned** — no nullable-column conventions on `deployment`, and nothing added to
the platform's hottest, most-joined table.

```sql
CREATE TABLE deployment_database (
    id                 BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id      UUID         NOT NULL UNIQUE REFERENCES deployment(id),

    -- D2. Same string. Stored rather than derived so a future change to the
    -- derivation rule cannot orphan existing databases, and so operator SQL
    -- joins without recomputing a hex transform.
    db_name            VARCHAR(63)  NOT NULL,
    role_name          VARCHAR(63)  NOT NULL,

    -- D4. Same shape as deployment_var: ciphertext as text, 8-char key id.
    password_encrypted TEXT         NOT NULL,
    key_id             VARCHAR(8)   NOT NULL,

    -- D7/D8. 'ok' | 'warned' | 'readonly' | 'blocked'
    quota_state        VARCHAR(16)  NOT NULL DEFAULT 'ok',

    size_bytes         BIGINT,                               -- last measurement
    measured_at        TIMESTAMP,
    warned_threshold   SMALLINT,                             -- 80 | 90 | 100; suppression
    warned_at          TIMESTAMP,
    readonly_at        TIMESTAMP,                            -- transition audit
    blocked_at         TIMESTAMP,

    purge_after        TIMESTAMP,                            -- D11
    created_at         TIMESTAMP    NOT NULL
);

CREATE INDEX ix_deployment_database_quota_state
    ON deployment_database (quota_state);

CREATE INDEX ix_deployment_database_purge_after
    ON deployment_database (purge_after)
    WHERE purge_after IS NOT NULL;
```

Column types follow `deployment_var`: `BigInteger` + `Identity(always=True)` for the
key, `Uuid` for the deployment reference, `Text` for ciphertext, `String(8)` for
`key_id`, and naive `DateTime` throughout.

**No `deleted_at` of its own.** `deployment` rows are never hard-deleted — deletion
sets `status = deleted` and `deleted_at` (`api/app/models/core.py:127`), and the only
`session.delete` in the codebase is a duplicate-job cleanup (`jobs.py:268`). This row
always has a live parent to read deletion state from, and duplicating the timestamp
would only create somewhere for the two to disagree. `purge_after` stays because it is
not a deletion record but a *schedule*, and nothing on `deployment` carries it.

Quota state is not projected onto `deployment`: no new column, no new status enum
value. `deployment.status` keeps meaning "is the rollout healthy", and an over-quota app
is still deployed and serving. Readers join this table, which also avoids two
independent writers contending for one column.

### D13. Physical safety, capacity, and resource bounds

Per Context (6), a PVC's declared size is metadata. Every PV is a plain directory on
the node filesystem, and the cluster today carries 41 PVs declaring 550 Gi against a
61.3 GB disk. Three consequences: filling the tenant volume takes down the node rather
than only PostgreSQL; the reserve must be enforced by monitoring node disk, not by the
PVC; and growth is a dump/restore migration, not a resize.

Response to crossing the reserve is **alert only** — a human decides. No automated
global read-only, no automatic suspension.

Storage budget: a **10 GB** self-imposed ceiling, of which roughly 4 GB is
infrastructure reserve (WAL, temporary files, maintenance headroom) and ~6 GB is
available to tenant databases. An empty tenant database costs 7,425 kB measured, which
with always-on provisioning is a per-deployment floor rather than a per-user cost;
capacity should be tracked against a fleet ceiling in the low hundreds and crossing it
treated as the trigger for the migration above.

**Resource bounds.** Under-dimensioning CPU makes things slow; under-dimensioning
memory has the OOM killer destroy the database pod. So PostgreSQL's own memory ceiling
sits well below the container limit, and the limit is set with headroom rather than
tuned tight.

| Component | CPU request / limit | Memory request / limit |
| --- | --- | --- |
| PostgreSQL | 100m / 400m | 512Mi / **2Gi** |
| PgBouncer (×2) | 10m / 50m each | 32Mi / 128Mi each |

Total CPU limit 500m; total memory limit ~2.25 Gi.

PostgreSQL configuration, worst case ~1.3 GB against the 2 Gi limit:

```
shared_buffers = 256MB
max_connections = 100          # superuser_reserved_connections = 5
reserved_connections = 3       # PG16+; pgbouncer_auth holds pg_use_reserved_connections
work_mem = 4MB
maintenance_work_mem = 64MB
autovacuum_max_workers = 3
```

Pooler, per instance — remembering D9's doubling:

```
pool_mode = transaction
max_prepared_statements = 100  # PgBouncer >= 1.21
max_client_conn = 500
default_pool_size = 3
max_db_connections = 5
max_user_connections = 25
server_idle_timeout = 60
```

`max_prepared_statements` and the version floor are not optional: asyncpg, SQLAlchemy,
Prisma and node-postgres all use prepared statements by default, and without
protocol-level support the failure is a confusing runtime error.

### D14. PostgreSQL 18, in `tf/app` per workspace

PostgreSQL 18 (18.6, supported to 2030-11-14) — the current stable. The tenant cluster
does not track `caelus-postgres`, which is on 16; pinning low costs an upgrade later.

Deployed from `tf/app` per workspace so dev and prod tenants never share a cluster,
deliberately unlike Garage, which is a shared singleton in `tf/deps`. It is a separate
instance from `caelus-postgres` without exception: a tenant sharing the control-plane
database could take down the platform with one query, and `caelus-postgres` runs in a
256Mi limit with a `Recreate` strategy.

Extensions are PostgreSQL's trusted set, which requires no platform work — it is what
D3's ownership already permits. Verified: `CREATE EXTENSION pgcrypto` succeeded as the
tenant, `file_fdw` was refused with `Must be superuser`. `pgvector` is not in the stock
image; a base image shipping it would make it tenant-installable with no code change.

### D15. No external access, no in-cluster TLS

Tenants reach their database only from their own pods, through the pooler. No public
endpoint, no tunnel. The NetworkPolicy is the boundary, and no TLS is terminated
between pod and pooler in V1.

Accepted: credentials and query data cross the pod network in cleartext. Revisit if the
DPA makes claims about encryption in transit.

Worth recording for whenever this is reopened: an authenticated short-lived tunnel is
the likelier shape than a public endpoint, because it is the one primitive that also
resolves migrations, seeding, debugging and self-service dumps. Two facts that will
matter then — PostgreSQL is not SNI-routable by default (the protocol starts in
cleartext and upgrades via `SSLRequest`), for which `sslnegotiation=direct` in
PostgreSQL 17+ is the mechanism; and the edge is two hops, homelab HAProxy in front of
k3s Traefik, so any TCP exposure needs a port at both.

## Risks / Trade-offs

- **The volume has no enforced size and shares the node's disk** → alerting on node
  free space, `temp_file_limit`, and a self-imposed budget well under the disk. Filling
  it takes down k3s, not just PostgreSQL, and the response is human-in-the-loop.
- **Fail-closed reconcile makes the tenant cluster a platform-wide dependency (D6)** →
  its outage blocks every `custom` deploy, including apps that never touch a database.
  This raises the cluster's availability bar above what `caelus-postgres` meets today.
  Accepted for V1; revisit if it bites.
- **Until plan change is implemented, no tenant at 100% can recover (D8)** → tracked
  separately; D6 step 10 means the exit starts working the day it lands. Meanwhile an
  over-quota tenant's data is stranded until purge.
- **One email is the entire tenant surface** → if it is filtered, the app goes
  read-only with nothing in the product to explain why. Mitigation deferred with the
  dashboard.
- **Read-only is defeatable (D7)** → by design; the real ceiling for anyone who reads
  the manual is 150%, which is what makes crossing it an abuse signal.
- **Tenants can drop their own database (D3)** → the reconciler re-provisions it empty.
  Recoverable, surprising, a support conversation.
- **Backfill is lazy, so the fleet stays mixed** → some `custom` apps have
  `DATABASE_URL` and some do not until each next reconciles. Documentation will say
  "always" before it is true everywhere.
- **No tenant-reachable backups exist** → an accidental `DROP TABLE` is unrecoverable
  for the tenant. `legal/` must state this plainly rather than implying a restore
  capability.
- **A retired encryption key would strand every tenant password** → the keyring's
   coverage checks and rotation sweep are made generic before the column is populated
   (migration step 5). Untreated, the failure is triggered by following the documented
   rotation procedure correctly, which is the worst way to find a gap.
- **The pooler is a new shared dependency** → two instances reduce blast radius but do
  not eliminate reconnects, since PgBouncer has no connection handoff. Applications
  must tolerate reconnects, which every client pool already does.
- **PgBouncer has no global cap on server connections** → the sum of per-pool sizes can
  exceed `max_connections`, and the failure lands on whoever connects last. Small pool
  sizes and a short `server_idle_timeout` are the mitigation; "server connection
  failures" must be alerted.
- **Autovacuum's launcher cycles every `autovacuum_naptime / database count`** → raise
  `autovacuum_naptime` once the fleet passes roughly 200 databases.

## Migration Plan

Ordered so each step is independently verifiable and separately revertable.

1. **Plan field** — migration for `database_bytes`, `caelus plan` options, admin UI
   field, read models. Ships alone and changes no behavior.
2. **Infrastructure** — `tf/app` PostgreSQL 18 and PgBouncer ×2 per workspace with
   D13's configuration. Cluster bootstrap — the `PUBLIC` revocations, the platform
   admin role and its grants, and the `pgbouncer_auth` role with its `SECURITY DEFINER`
   lookup — is an idempotent SQL script applied by an init container, not a `caelus`
   command and not a manual step; see D6 *Bootstrap*.
3. **NetworkPolicy** — the egress rule plus a fleet-wide re-apply via
   `caelus sync-network-policies`. Safe before anything consumes it.
4. **Data model** — the `deployment_database` migration.
5. **Keyring coverage** — make `verify_keyring` and the rotation sweep generic over the
   registry of encrypted columns, before any `deployment_database` row exists. Ships
   alone, changes no behavior for vars, and is a prerequisite for the next step being
   safe to operate rather than merely correct.
6. **Provisioning service** — `relational_storage.py` beside `object_storage.py`, over
   a PostgreSQL admin client, with `is_enabled`, `resolve_quota_bytes`,
   `ensure_database`, `teardown_database`, `evaluate_quota_state`.
7. **Reconcile integration** — provisioning and Secret publication on apply, teardown
   on delete, `caelus.database` overrides, chart schema and catalog opt-in.
8. **`caelus db-worker`, quota tick** — thresholds, email with suppression, read-only
   assert and lift, suspension. Shipping the process with one tick keeps its first
   deployment small.
9. **`caelus db-worker`, purge and orphan ticks** — same process, added once the quota
   tick is proven.
10. **Documentation** — see `tasks.md`.

**Rollback.** Steps 1–4 are additive and safe to leave in place. From step 6 onward,
reverting means removing the catalog opt-in, which stops new provisioning; existing
databases are then untouched and unreferenced, and the purge tick will not act on them
because no `purge_after` is set. Nothing in this change destroys tenant data on
rollback.

## Open Questions

- **An email at the 150% hard block.** The ladder decided in review covers 80%, 90% and
  100%. Suspending a database with no notification seems wrong, but adding one is a
  product decision rather than a design consequence — confirm or drop before step 7.
- ~~**PgBouncer's `auth_query` cache-invalidation semantics.**~~ Observed on 1.25.2
  during step 2 and no longer open: a suspended tenant is rejected **at connect**, with
  `bouncer config error` reaching the client (asyncpg surfaces it as
  `ProtocolViolationError`). The block took effect on the very next connection despite
  that tenant having connected successfully moments earlier, so a cached credential does
  not hold a suspension open; lifting it was equally immediate (0.10s to reconnect). No
  pooler command was issued in either direction.
- **Whether `db_name` / `role_name` are stored at all.** They are derivable from
  `deployment_id` via D2, and `object_storage.py` computes such names rather than
  storing them. Kept here for derivation-change insurance and operator ergonomics;
  dropping them changes nothing else.
