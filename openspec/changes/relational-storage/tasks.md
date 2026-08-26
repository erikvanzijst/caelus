## 1. Plan allowance

- [x] 1.1 Add `database_bytes` (nullable `BigInteger`) to `PlanTemplateVersionORM` and its Create/Read models; verify `PlanTemplateVersionRead` round-trips the field in `api/tests/test_plan_and_subscription_api.py`
- [x] 1.2 Write the Alembic migration adding the column; verify `alembic upgrade head` then `downgrade -1` runs clean against a scratch database
- [x] 1.3 Add `--database-bytes` to the `caelus plan` template-version commands; verify the CLI test creates a template version carrying the value
- [x] 1.4 Add the field to the admin UI plan form; verify `cd ui && npm test` passes and the value survives a create/edit round trip
- [x] 1.5 Seed the Free (100 MB) and Basic (1 GB, EUR 3/month) tiers for the `custom` product; verify `caelus plan list` shows both allowances

## 2. Tenant database cluster

- [x] 2.1 Add PostgreSQL 18 to `tf/app` with its own PVC, per workspace, using design D13's `postgresql.conf` values (including `reserved_connections`) and resource bounds; verify `kubectl exec ... psql -c 'select version()'` reports 18 and the pod's limits match
- [x] 2.2 Write the idempotent bootstrap SQL script (guarded `DO $$` blocks for roles, `CREATE OR REPLACE FUNCTION`, `REVOKE`/`GRANT`): revoke `CONNECT` on `postgres` and `template1` from `PUBLIC`; create `caelus_admin` with `CREATEDB CREATEROLE` plus `pg_read_all_stats` and `pg_signal_backend`; create `pgbouncer_auth` and the superuser-owned `pgbouncer.user_lookup` `SECURITY DEFINER` function in the tenant cluster's `postgres` database, granting `pgbouncer_auth` `EXECUTE` on it and `pg_use_reserved_connections`; verify running it twice against a scratch cluster succeeds both times and leaves identical state
- [x] 2.3 Load the script into a ConfigMap and apply it from an ordered init container running `psql` from `postgres:18-alpine` on the reconcile worker Deployment, with the `pgbouncer_auth` password passed as a `psql` variable from a Terraform-generated Secret and a hash of the script on the pod template; verify `terraform apply` against an empty cluster produces a bootstrapped one with no manual step, that editing the script forces a rollout, and that an unreachable cluster crashloops the init container rather than starting the worker
- [x] 2.4 Verify `caelus_admin` needs no superuser by exercising the full lifecycle under it: create role and database owned by the tenant, read `pg_database_size` with `CONNECT` revoked, set and clear `default_transaction_read_only` via `SET ROLE`, terminate a tenant backend, and `DROP DATABASE WITH (FORCE)` then `DROP ROLE`
- [x] 2.5 Add PgBouncer >= 1.21 (2 replicas) behind a ClusterIP Service, transaction pooling, wildcard database routing, `auth_dbname` pinned to the tenant cluster's `postgres` database, `auth_user = pgbouncer_auth`, `max_prepared_statements` set, **no `admin_users`**, with design D13's resource bounds; verify `SHOW CONFIG` reports the intended pool mode and version, and that a tenant set to `NOLOGIN` is refused at the pooler
- [x] 2.6 Confirm a driver using prepared statements by default connects and queries through the pooler; verify with an asyncpg or SQLAlchemy round trip against a hand-provisioned test database
- [x] 2.7 Verify authentication still succeeds while the tenant cluster is at `max_connections`, confirming the reserved slot works; and record PgBouncer's observed `auth_query` cache-invalidation behavior for design.md's open question
- [x] 2.8 Add the admin connection settings and secret wiring to `CaelusSettings` and the API/worker deployments, following the Garage admin credential pattern; verify the API starts with them absent for products that have not opted in

## 3. Network isolation

- [x] 3.1 Add the pooler egress rule (namespaceSelector + podSelector, client port only) to `build_tenant_baseline_policy`; verify the rendered policy in `api/tests` matches the expected document
- [x] 3.2 Verify from a scratch pod in a tenant namespace that the pooler port is reachable and the PostgreSQL port is not
- [x] 3.3 Re-apply the policy fleet-wide with `caelus sync-network-policies`; verify every tenant namespace carries the new rule

## 4. Data model

- [x] 4.1 Add the `DeploymentDatabaseORM` model exactly as declared in design D12, following `deployment_var`'s column types; verify the model imports and `SQLModel.metadata` includes the table
- [x] 4.2 Write the Alembic migration for `deployment_database` including both indexes; verify `alembic upgrade head` then `downgrade -1` runs clean and the partial index predicate is present in `pg_indexes`
- [x] 4.3 Add a test asserting the row's absence means "not provisioned" and that `deployment_database` has no `deleted_at`

## 5. Keyring coverage for the new encrypted columns

- [x] 5.1 Refactor `var_crypto` so the encrypted-column set is a registry of `(model, ciphertext column, key_id column)` rather than a hardcoded reference to `DeploymentVarORM`; verify the existing var suite passes unchanged
- [x] 5.2 Expand `verify_keyring` to check stored `key_id`s across every registered table; verify that a `deployment_database` row naming an unconfigured key fails startup for both the API (`app/main.py`) and `caelus worker`, with an error naming the missing fingerprint
- [x] 5.3 Expand the rotation sweep to cover every registered table, preserving per-batch commit and resumability; verify a rotation across both tables leaves no row naming a non-current key, and that interrupting and re-running completes the sweep
- [x] 5.4 Extend the empty-keyring fatality check so an unconfigured keyring is also fatal when any `deployment_database` row exists, not only when a product template declares vars; verify startup fails in that case with an actionable message
- [x] 5.5 Rename `caelus vars-rotate` to reflect that it covers every encrypted column, and correct its help text, which currently tells operators the old key may be retired once it reports nothing left to rotate; verify the command rotates and reports under the new name

## 6. Provisioning service

- [x] 6.1 Add a PostgreSQL admin client module (connection handling, statement execution, autocommit for `CREATE`/`DROP DATABASE`), mirroring `garage.py`'s role as transport; verify its unit tests cover the non-transactional statements
- [x] 6.2 Add `relational_storage.py` with `is_enabled` reading the template's system values only; verify a tenant-supplied user value cannot enable it
- [x] 6.3 Implement `resolve_quota_bytes` fail-closed against `database_bytes`; verify it raises for a missing, zero or negative allowance
- [x] 6.4 Implement `database_name`/`role_name` from the deployment UUID with hyphens removed; verify the result is <= 63 bytes and valid unquoted in a real `CREATE ROLE`
- [x] 6.5 Implement `ensure_database` following design D6's ordered steps — including `GRANT <role> TO caelus_admin WITH SET TRUE, INHERIT FALSE` before the database is created — each reading before writing; verify tests cover a clean provision, a re-run, a role-without-database, and a database-without-role
- [x] 6.6 Store the password encrypted via `var_crypto` **before** applying it to the role; verify a test that interrupts after the store and asserts the next run repairs the credential
- [x] 6.7 Assert `SET ROLE <tenant>; REVOKE ALL ON DATABASE ... FROM PUBLIC` on every provision, followed by design D6 step 5b's post-condition — read `has_database_privilege('public', <db>, 'CONNECT')` back and raise when it is true, because the revoke fails without erroring when it is not owner-scoped; verify a test where a second provisioned role is refused connection to the first's database, and one that the post-condition raises when the revoke did not take effect
- [x] 6.8 Apply `temp_file_limit`, `statement_timeout` and `idle_in_transaction_session_timeout` on every provision; verify a test that clears them and asserts re-assertion on the next run
- [x] 6.9 Implement `teardown_database` as `NOLOGIN` plus `purge_after`, dropping nothing; verify it is idempotent and tolerates a deployment that never had a database
- [x] 6.10 Implement `evaluate_quota_state(deployment)` returning and applying the state, assuming the tenant role via `SET ROLE` for the owner-scoped `ALTER DATABASE`, with a flag to suppress notification; verify tests cover each threshold transition in both directions

## 7. Reconcile integration

- [x] 7.1 Add `_ensure_database` to `_reconcile_apply` after `ensure_tenant_isolation` and before Helm; verify ordering in `api/tests/test_reconcile_service.py`
- [x] 7.2 Publish the `<name>-database` Secret with `DATABASE_URL` and the discrete `PG*` variables; verify the Secret's contents and that it is updated in place across reconciles
- [x] 7.3 Add `_build_database_overrides` projecting only host, port, name, user and `secretName` under `caelus.database`; verify no password appears in merged values and that a non-opted-in product emits no block
- [x] 7.4 Call `evaluate_quota_state` as the final provisioning step with notification suppressed; verify a test that an over-quota deployment reconciling has read-only re-asserted rather than cleared
- [x] 7.5 Fail the reconcile when the tenant cluster is unreachable; verify no Helm release is attempted in that case
- [x] 7.6 Call `teardown_database` from `_reconcile_delete`; verify the role is `NOLOGIN`, `purge_after` is set, and the database still exists

## 8. Chart and catalog

- [x] 8.1 Add `relationalStorage.enabled` and `caelus.database` to `products/custom/chart/values.schema.json`; verify `helm template` accepts both and rejects an unknown sibling
- [x] 8.2 Render `envFrom` for the credentials Secret in the custom chart, gated on the opt-in flag; verify a rendered manifest carries the Secret reference only when enabled
- [x] 8.3 Set `relationalStorage.enabled: true` in `products/catalog/custom.yaml`; verify `caelus catalog lint` passes and `caelus catalog apply` produces a new template version
- [x] 8.4 Deploy a scratch `custom` app that reads `DATABASE_URL`, creates a table and writes a row; verify end to end that it succeeds

## 9. Housekeeping worker — quota tick

- [x] 9.1 Add the `caelus db-worker` entry point beside `caelus worker` and `caelus build-worker`, with per-tick guarding so one failing tick cannot stop another, and **no keyring verification at startup** per design D10 — it decrypts nothing; verify a test that raises in one tick and asserts the other still runs, and one that the process starts with an empty keyring while the API and `caelus worker` refuse to
- [x] 9.2 Implement the quota tick over the fleet using `evaluate_quota_state`, on a configurable interval defaulting to 60s; verify a test that walks a deployment from `ok` through `blocked` and back
- [x] 9.3 Send rate-limited threshold emails at 80%, 90% and 100% through the SMTP relay, recording suppression state; verify a deployment hovering above a threshold is not mailed twice
- [x] 9.4 Implement suspension as `NOLOGIN` plus backend termination, recording the transition in `quota_state`; verify that a client already connected to the pooler cannot execute a further query, that a fresh connection is refused, that no pooler admin credential is configured or used, and that lifting the suspension restores access
- [x] 9.5 Add the worker Deployment to `tf/app` with resource bounds; verify it comes up and logs a completed sweep

## 10. Housekeeping worker — purge and orphan ticks

- [ ] 10.1 Implement the purge tick: `SET ROLE <tenant>` then `DROP DATABASE ... WITH (FORCE)`, then `RESET ROLE` and `DROP ROLE`, past `purge_after`; verify a test that a due deployment is destroyed and one inside its grace period is not
- [ ] 10.2 Refuse to purge a null or future `purge_after`, cap purges per run, and log every drop with its deployment id; verify tests for each guard
- [ ] 10.3 Verify a purge succeeds while sessions are connected to the target database
- [ ] 10.4 Implement the orphan tick over both databases and roles, reporting cluster objects no row accounts for; verify a test that creates a role without a database and asserts it is reported

## 11. Documentation

- [ ] 11.1 Update `AGENTS.md`: three worker processes rather than two, `caelus db-worker` described as all database housekeeping, and the vars-vs-database channel distinction; verify the worker list matches the shipped entry points
- [ ] 11.2 Add a Relational Storage section to `api/README.md` mirroring Object Storage; verify it documents the Secret contract and the quota ladder
- [ ] 11.3 Update `tf/README.md` and `tf/app/README.md` with the tenant cluster and design D13's warning that `local-path` enforces no size and cannot expand
- [ ] 11.4 Update `products/custom/README.md` with the opt-in flag and the injected values
- [ ] 11.5 Rewrite the `deploy-to-freepod` skill's "there is no database" guidance, and add a migrations paragraph covering "run them at startup, beware the multi-replica race"; verify no remaining text tells users to port relational schemas onto S3
- [ ] 11.6 Update `legal/` to state that no tenant-reachable backups exist and to record the database retention period; verify it matches `deployment_bucket_expiry_days`
- [ ] 11.7 Update AGENTS.md's statement that "the API and `caelus worker` must both hold" the keyring, to reflect the third process and whichever way task 5.6 resolves; verify it names every process that requires a key and no process that does not
- [ ] 11.8 Extend AGENTS.md's REST-parity exemption to name `caelus db-worker` and the `caelus db` operator commands alongside `caelus catalog`; verify the wording covers both
