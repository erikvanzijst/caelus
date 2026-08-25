## 1. Plan allowance

- [ ] 1.1 Add `database_bytes` (nullable `BigInteger`) to `PlanTemplateVersionORM` and its Create/Read models; verify `PlanTemplateVersionRead` round-trips the field in `api/tests/test_plan_and_subscription_api.py`
- [ ] 1.2 Write the Alembic migration adding the column; verify `alembic upgrade head` then `downgrade -1` runs clean against a scratch database
- [ ] 1.3 Add `--database-bytes` to the `caelus plan` template-version commands; verify the CLI test creates a template version carrying the value
- [ ] 1.4 Add the field to the admin UI plan form; verify `cd ui && npm test` passes and the value survives a create/edit round trip
- [ ] 1.5 Seed the Free (100 MB) and Basic (1 GB, EUR 3/month) tiers for the `custom` product; verify `caelus plan list` shows both allowances

## 2. Tenant database cluster

- [ ] 2.1 Add PostgreSQL 18 to `tf/app` with its own PVC, per workspace, using design D13's `postgresql.conf` values and resource bounds; verify `kubectl exec ... psql -c 'select version()'` reports 18 and the pod's limits match
- [ ] 2.2 Bootstrap the cluster: `REVOKE CONNECT` on `postgres` and `template1`, and create the platform admin role; verify a non-privileged role cannot connect to either maintenance database
- [ ] 2.3 Create the platform-owned `auth_dbname` database and the `auth_query` view that filters suspended deployments; verify the view returns a row for an active deployment and none for a suspended one
- [ ] 2.4 Add PgBouncer >= 1.21 (2 replicas) behind a ClusterIP Service, transaction pooling, wildcard database routing, `auth_dbname` pinned, `max_prepared_statements` set, with design D13's resource bounds; verify `SHOW CONFIG` reports the intended pool mode and version
- [ ] 2.5 Confirm a driver using prepared statements by default connects and queries through the pooler; verify with an asyncpg or SQLAlchemy round trip against a hand-provisioned test database
- [ ] 2.6 Add the admin connection settings and secret wiring to `CaelusSettings` and the API/worker deployments, following the Garage admin credential pattern; verify the API starts with them absent for products that have not opted in

## 3. Network isolation

- [ ] 3.1 Add the pooler egress rule (namespaceSelector + podSelector, client port only) to `build_tenant_baseline_policy`; verify the rendered policy in `api/tests` matches the expected document
- [ ] 3.2 Verify from a scratch pod in a tenant namespace that the pooler port is reachable and the PostgreSQL port is not
- [ ] 3.3 Re-apply the policy fleet-wide with `caelus sync-network-policies`; verify every tenant namespace carries the new rule

## 4. Data model

- [ ] 4.1 Add the `DeploymentDatabaseORM` model exactly as declared in design D12, following `deployment_var`'s column types; verify the model imports and `SQLModel.metadata` includes the table
- [ ] 4.2 Write the Alembic migration for `deployment_database` including both indexes; verify `alembic upgrade head` then `downgrade -1` runs clean and the partial index predicate is present in `pg_indexes`
- [ ] 4.3 Add a test asserting the row's absence means "not provisioned" and that `deployment_database` has no `deleted_at`

## 5. Provisioning service

- [ ] 5.1 Add a PostgreSQL admin client module (connection handling, statement execution, autocommit for `CREATE`/`DROP DATABASE`), mirroring `garage.py`'s role as transport; verify its unit tests cover the non-transactional statements
- [ ] 5.2 Add `relational_storage.py` with `is_enabled` reading the template's system values only; verify a tenant-supplied user value cannot enable it
- [ ] 5.3 Implement `resolve_quota_bytes` fail-closed against `database_bytes`; verify it raises for a missing, zero or negative allowance
- [ ] 5.4 Implement `database_name`/`role_name` from the deployment UUID with hyphens removed; verify the result is <= 63 bytes and valid unquoted in a real `CREATE ROLE`
- [ ] 5.5 Implement `ensure_database` following design D6's ordered steps, each reading before writing; verify tests cover a clean provision, a re-run, a role-without-database, and a database-without-role
- [ ] 5.6 Store the password encrypted via `var_crypto` **before** applying it to the role; verify a test that interrupts after the store and asserts the next run repairs the credential
- [ ] 5.7 Assert `REVOKE CONNECT ... FROM PUBLIC` on every provision; verify a test where a second provisioned role is refused connection to the first's database
- [ ] 5.8 Apply `temp_file_limit`, `statement_timeout` and `idle_in_transaction_session_timeout` on every provision; verify a test that clears them and asserts re-assertion on the next run
- [ ] 5.9 Implement `teardown_database` as `NOLOGIN` plus `purge_after`, dropping nothing; verify it is idempotent and tolerates a deployment that never had a database
- [ ] 5.10 Implement `evaluate_quota_state(deployment)` returning and applying the state, with a flag to suppress notification; verify tests cover each threshold transition in both directions

## 6. Reconcile integration

- [ ] 6.1 Add `_ensure_database` to `_reconcile_apply` after `ensure_tenant_isolation` and before Helm; verify ordering in `api/tests/test_reconcile_service.py`
- [ ] 6.2 Publish the `<name>-database` Secret with `DATABASE_URL` and the discrete `PG*` variables; verify the Secret's contents and that it is updated in place across reconciles
- [ ] 6.3 Add `_build_database_overrides` projecting only host, port, name, user and `secretName` under `caelus.database`; verify no password appears in merged values and that a non-opted-in product emits no block
- [ ] 6.4 Call `evaluate_quota_state` as the final provisioning step with notification suppressed; verify a test that an over-quota deployment reconciling has read-only re-asserted rather than cleared
- [ ] 6.5 Fail the reconcile when the tenant cluster is unreachable; verify no Helm release is attempted in that case
- [ ] 6.6 Call `teardown_database` from `_reconcile_delete`; verify the role is `NOLOGIN`, `purge_after` is set, and the database still exists

## 7. Chart and catalog

- [ ] 7.1 Add `relationalStorage.enabled` and `caelus.database` to `products/custom/chart/values.schema.json`; verify `helm template` accepts both and rejects an unknown sibling
- [ ] 7.2 Render `envFrom` for the credentials Secret in the custom chart, gated on the opt-in flag; verify a rendered manifest carries the Secret reference only when enabled
- [ ] 7.3 Set `relationalStorage.enabled: true` in `products/catalog/custom.yaml`; verify `caelus catalog lint` passes and `caelus catalog apply` produces a new template version
- [ ] 7.4 Deploy a scratch `custom` app that reads `DATABASE_URL`, creates a table and writes a row; verify end to end that it succeeds

## 8. Housekeeping worker — quota tick

- [ ] 8.1 Add the `caelus db-worker` entry point beside `caelus worker` and `caelus build-worker`, with per-tick guarding so one failing tick cannot stop another; verify a test that raises in one tick and asserts the other still runs
- [ ] 8.2 Implement the quota tick over the fleet using `evaluate_quota_state`, on a configurable interval defaulting to 60s; verify a test that walks a deployment from `ok` through `blocked` and back
- [ ] 8.3 Send rate-limited threshold emails at 80%, 90% and 100% through the SMTP relay, recording suppression state; verify a deployment hovering above a threshold is not mailed twice
- [ ] 8.4 Send an email at the 150% hard block — **drop this task if the open question in design.md resolves that way**; verify the message is sent once on transition to `blocked`
- [ ] 8.5 Implement suspension as `NOLOGIN` + the suspension flag + backend termination; verify a suspended deployment cannot authenticate through the pooler and that lifting it restores access
- [ ] 8.6 Add the worker Deployment to `tf/app` with resource bounds; verify it comes up and logs a completed sweep

## 9. Housekeeping worker — purge and orphan ticks

- [ ] 9.1 Implement the purge tick: `DROP DATABASE ... WITH (FORCE)` then `DROP ROLE` past `purge_after`; verify a test that a due deployment is destroyed and one inside its grace period is not
- [ ] 9.2 Refuse to purge a null or future `purge_after`, cap purges per run, and log every drop with its deployment id; verify tests for each guard
- [ ] 9.3 Verify a purge succeeds while sessions are connected to the target database
- [ ] 9.4 Implement the orphan tick over both databases and roles, reporting cluster objects no row accounts for; verify a test that creates a role without a database and asserts it is reported

## 10. Documentation

- [ ] 10.1 Update `AGENTS.md`: three worker processes rather than two, `caelus db-worker` described as all database housekeeping, and the vars-vs-database channel distinction; verify the worker list matches the shipped entry points
- [ ] 10.2 Add a Relational Storage section to `api/README.md` mirroring Object Storage; verify it documents the Secret contract and the quota ladder
- [ ] 10.3 Update `tf/README.md` and `tf/app/README.md` with the tenant cluster and design D13's warning that `local-path` enforces no size and cannot expand
- [ ] 10.4 Update `products/custom/README.md` with the opt-in flag and the injected values
- [ ] 10.5 Rewrite the `deploy-to-freepod` skill's "there is no database" guidance, and add a migrations paragraph covering "run them at startup, beware the multi-replica race"; verify no remaining text tells users to port relational schemas onto S3
- [ ] 10.6 Update `legal/` to state that no tenant-reachable backups exist and to record the database retention period; verify it matches `deployment_bucket_expiry_days`
- [ ] 10.7 Extend AGENTS.md's REST-parity exemption to name `caelus db-worker` and the `caelus db` operator commands alongside `caelus catalog`; verify the wording covers both
