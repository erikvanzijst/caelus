## Context

`DeploymentORM.deployment_uid` is an immutable slug (`{product_slug}-{user_slug}-{suffix6}`, max 40 chars) that serves as both the Helm release name and Kubernetes namespace. Because it encodes two variable-length components (product name + user email) into a single field, it can approach the 63-char DNS label limit after Kubernetes appends controller-revision-hashes and chart resource suffixes.

The `_resolve_identity()` method in `reconcile.py` currently returns `(uid, uid)` — the same value for both release name and namespace. The naming logic lives in `reconcile_naming.py` with `generate_deployment_uid()`, `slugify_token()`, and trimming helpers.

Downstream consumers: `reconcile.py` (helm install/uninstall, namespace create/delete), `deployments.py` (generation at create time), `models.py` (column + schema), `types.ts` (frontend), and tests.

## Goals / Non-Goals

**Goals:**
- Split the single `deployment_uid` into two fields: `name` (Helm release) and `namespace` (K8s namespace)
- Each field encodes only one variable input, giving tighter length budgets and clearer semantics
- Migrate existing data so the `namespace` column is populated for all existing rows
- Maintain backwards compatibility for already-deployed Kubernetes resources (no rewrite of live resources)

**Non-Goals:**
- Rewriting `name`/`namespace` for existing deployments in Kubernetes — the new format applies only to new deployments
- Changing how hostnames or user values work
- Adding a uniqueness constraint on `name` — release names are scoped to their namespace

## Decisions

### 1. Namespace formula: `"{slugify(email)[:20]}-{random9}"`

The namespace identifies ownership (user email) plus a random suffix for uniqueness.

- **Max length**: 20 + 1 + 9 = 30 chars (well under 63-char DNS label limit)
- **Random suffix**: 9 base36 chars → `36^9 ≈ 101 billion` possibilities, effectively zero collision risk
- **Why not use deployment.id?** The integer PK isn't available until after `session.flush()`, creating a chicken-and-egg problem with the NOT NULL column. A random suffix avoids this entirely.
- **Why email?** Namespaces in the cluster become human-scannable — `kubectl get ns` shows who owns what.
- **Alternative considered**: UUID-based namespace — rejected because it sacrifices human readability for no real benefit.

### 2. Name formula: `"{slugify(product_name)[:20]}-{random6}"`

The name identifies the product being deployed, with a random suffix.

- **Max length**: 20 + 1 + 6 = 27 chars → 36 chars of headroom for chart suffixes (up from 23)
- **Random suffix**: 6 base36 chars (unchanged from current suffix length)
- **Uniqueness**: Not enforced at DB level — the name is scoped to its namespace, so two deployments can share a release name as long as they're in different namespaces. This mirrors how Helm itself scopes releases.
- **Alternative considered**: Including user info in the name — rejected because it would bloat the name without adding information (the namespace already carries user identity).

### 3. Column rename: `deployment_uid` → `name`

- Aligns with Kubernetes terminology (Helm release "name")
- **BREAKING** for API consumers — `DeploymentRead` schema changes from `deployment_uid` to `name`
- The rename is mechanical across all layers: model, schema, service, API, TypeScript, tests

### 4. Reuse existing slugification logic

`slugify_token()` and `_trim_base_for_suffix()` already handle: lowercasing, non-alnum replacement, hyphen collapsing, trailing-hyphen stripping. The new generators compose these existing primitives with different truncation constants rather than writing new slug logic.

### 5. Migration strategy

Single Alembic migration that:
1. Adds `namespace` column as `String(), nullable=True` (temporary)
2. Seeds `namespace = deployment_uid` for all existing rows (existing K8s namespaces ARE the deployment_uid)
3. Alters `namespace` to `NOT NULL`
4. Renames `deployment_uid` column to `name`
5. Drops the old `ix_deployment_deployment_uid` index
6. Creates new indexes on `name` and `namespace`

This is safe because existing deployments will continue to use their original values — the reconciler reads whatever is in the DB columns.

## Risks / Trade-offs

- **[API breaking change]** → Clients must update from `deployment_uid` to `name` + `namespace`. Mitigation: coordinate frontend + backend deployment together. The TypeScript types are in the same repo, so this is a single PR.
- **[Namespace collision (theoretical)]** → Two users with similar email prefixes could collide on the 20-char slug, but the 9-char random suffix makes actual collision probability negligible (`~10^-16` per pair). Mitigation: the deployment creation code can retry with a new suffix on the astronomically unlikely `IntegrityError`.
- **[Existing deployments]** → Old deployments keep their original `name` (formerly `deployment_uid`) and `namespace` (seeded from `deployment_uid`). The reconciler uses the stored values directly, so no K8s resource rewrite is needed. Risk: none, but the naming pattern will differ between old and new deployments.
