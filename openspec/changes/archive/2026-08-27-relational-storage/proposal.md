## Why

Freepod auto-provisions object storage for every `custom` deployment, but there is no
relational storage: the platform tells developers in bold that "there is no database"
and to port relational schemas onto S3. That rules out most real applications, and it
is the single largest gap between Freepod and every comparable platform.

The object-storage subsystem already established the pattern — provision on reconcile,
publish credentials through a Kubernetes Secret, bound by the plan, reclaim on delete.
This change applies that same pattern to PostgreSQL, giving each `custom` deployment
its own database on a shared cluster with a `DATABASE_URL` in its environment.

## What Changes

- **Each `custom` deployment gets a PostgreSQL database and a login role** on a new
  shared tenant cluster, provisioned during reconcile and owned by the deployment.
- **`DATABASE_URL` and the discrete `PG*` variables appear in the pod environment**,
  delivered through a Kubernetes Secret. Helm values carry references only, never the
  password.
- **A new `database_bytes` plan field** bounds each deployment's database, separately
  from the existing `storage_bytes`, which already means two different things.
- **A quota ladder** warns by email at 80% and 90%, degrades the database to read-only
  at 100%, and refuses login at 150%.
- **A new `caelus db-worker` process** performs all database housekeeping: measuring
  quotas, purging deleted deployments' databases after the grace period, and sweeping
  orphans.
- **A new tenant PostgreSQL cluster and PgBouncer pair** deployed per Terraform
  workspace, so dev and prod tenants never share a cluster.
- **The tenant NetworkPolicy gains one egress rule** so pods can reach the pooler.
  Direct PostgreSQL access remains denied, which is what makes the pooler
  unbypassable.
- **BREAKING (documentation):** the `deploy-to-freepod` skill's "there is no database"
  guidance becomes wrong and must be rewritten.

Deliberately out of scope: curated products (which keep their embedded PostgreSQL),
external database access, tenant-facing UI or CLI, schema migration tooling, backups
that a tenant can reach, plan downgrades, and per-plan connection tiering.

## Capabilities

### New Capabilities

- `deployment-relational-storage`: how a PostgreSQL database and role are provisioned,
  isolated, credentialed and reclaimed for one deployment on the shared tenant cluster
  — and what the isolation between two deployments actually rests on.
- `relational-storage-chart-contract`: how database credentials reach a pod, which
  environment variables an application may rely on, and how a product opts in.
- `plan-database-enforcement`: the `database_bytes` allowance, the quota state machine,
  what each threshold does to a database, and which enforcement is exact rather than
  advisory.
- `tenant-database-cluster`: the shared PostgreSQL and PgBouncer pair — versions,
  pooling mode, authentication, resource bounds, and the capacity limits it operates
  under.
- `database-housekeeping-worker`: the process that measures quotas, applies quota
  state, purges deleted deployments' databases, and sweeps orphaned cluster objects.

### Modified Capabilities

- `deployment-network-isolation`: tenant egress gains the pooler; every other internal
  destination, including PostgreSQL directly, stays denied.
- `plan-data-model`: `plan_template_version` gains a `database_bytes` field alongside
  `storage_bytes`.

## Impact

**Code**

- New `api/app/services/relational_storage.py` (policy) and a PostgreSQL admin client,
  mirroring `object_storage.py` and `garage.py`.
- `api/app/services/reconcile.py`: provisioning and credential publication on apply,
  teardown on delete, `caelus.database` value overrides.
- `api/app/network_policy.py`: one egress rule; fleet re-apply via
  `caelus sync-network-policies`.
- New `deployment_database` table and a `database_bytes` column, with Alembic
  migrations.
- New `caelus db-worker` entry point beside `caelus worker` and `caelus build-worker`.
- `api/app/services/plans.py`, the plans API, and the admin UI plan form.

**Charts and catalog**

- `products/custom/chart` gains `relationalStorage.enabled` and `caelus.database`;
  `products/catalog/custom.yaml` opts in.

**Infrastructure**

- `tf/app`: PostgreSQL 18 and PgBouncer, per workspace, with their own PVC.

**Documentation**

- `AGENTS.md` (a third worker process), `api/README.md`, `tf/README.md`,
  `products/custom/README.md`, the `deploy-to-freepod` skill, and `legal/` — which
  must state plainly that no tenant-reachable backups exist.

**Dependencies**

- The only exit from an exhausted quota is a plan upgrade, and no operation currently
  changes a deployment's plan. That work is tracked separately; this change is built so
  the exit works the day it lands.
