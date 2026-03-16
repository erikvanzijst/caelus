## 1. Naming Service

- [ ] 1.1 Add `generate_suffix9()` function to `reconcile_naming.py` (9-char base36 random string)
- [ ] 1.2 Add `generate_deployment_name(product_name, *, suffix=None)` — `"{slugify(product_name)[:20]}-{random6}"`, max 27 chars, valid DNS label
- [ ] 1.3 Add `generate_deployment_namespace(user_email, *, suffix=None)` — `"{slugify(email)[:20]}-{random9}"`, max 30 chars, valid DNS label
- [ ] 1.4 Update constants: add `MAX_NAME_LEN = 27`, `NAME_BASE_MAX_LEN = 20`, `MAX_NAMESPACE_LEN = 30`, `NS_BASE_MAX_LEN = 20`, `NS_SUFFIX_LEN = 9`
- [ ] 1.5 Remove `generate_deployment_uid()`, `namespace_name_for_deployment_uid()`, `release_name_for_deployment_uid()`, and old constants (`MAX_UID_LEN`, `BASE_MAX_LEN`)
- [ ] 1.6 Add unit tests for `generate_deployment_name` — format, length, truncation, DNS validity, fallback for non-alnum product names
- [ ] 1.7 Add unit tests for `generate_deployment_namespace` — format, length, truncation, DNS validity, special email characters

## 2. Database Migration

- [ ] 2.1 Create Alembic migration: add `namespace` column as `String(), nullable=True`
- [ ] 2.2 In migration: seed `namespace = deployment_uid` for all existing rows via `UPDATE`
- [ ] 2.3 In migration: alter `namespace` to `NOT NULL`
- [ ] 2.4 In migration: rename `deployment_uid` column to `name`
- [ ] 2.5 In migration: drop old `ix_deployment_deployment_uid` index, create new indexes on `name` and `namespace`
- [ ] 2.6 In migration: add partial unique index `uq_deployment_ns_name_active` on `(namespace, name)` where `status <> 'deleted'`

## 3. Model & Schema Updates

- [ ] 3.1 Update `DeploymentORM`: rename `deployment_uid` field to `name`, add `namespace` field (`String(), nullable=False, index=True`), add partial unique index `uq_deployment_ns_name_active` on `(namespace, name)` where `status <> 'deleted'`
- [ ] 3.2 Update `DeploymentRead` schema: replace `deployment_uid` with `name` and `namespace`
- [ ] 3.3 Update `_validate_input_state()` in `reconcile.py`: check `deployment.name` and `deployment.namespace` instead of `deployment.deployment_uid`

## 4. Service Layer

- [ ] 4.1 Update `create_deployment()` in `deployments.py`: call `generate_deployment_name()` and `generate_deployment_namespace()`, set both on the ORM instance
- [ ] 4.2 Update import in `deployments.py`: replace `generate_deployment_uid` with new functions
- [ ] 4.3 Update `_resolve_identity()` in `reconcile.py`: return `(deployment.name, deployment.namespace)`

## 5. Frontend

- [ ] 5.1 Update `Deployment` interface in `ui/src/api/types.ts`: replace `deployment_uid` with `name` and `namespace`
- [ ] 5.2 Update any UI components that reference `deployment_uid`

## 6. Tests

- [ ] 6.1 Update `test_reconcile_contracts.py`: replace `deployment_uid` references with `name`/`namespace` tests
- [ ] 6.2 Update `test_reconcile_service.py`: update deployment fixture factories and assertions
- [ ] 6.3 Update `test_models_v2.py`: update deployment model tests
- [ ] 6.4 Update `test_hostnames.py`: update deployment fixtures that set `deployment_uid`
- [ ] 6.5 Update `e2e_hello3.sh` if it references `deployment_uid` in assertions or output

## 7. Documentation

- [ ] 7.1 Update `k8s/architecture.md`: document new `name`/`namespace` identity model
- [ ] 7.2 Update `api/README.md` if it documents the `deployment_uid` field
