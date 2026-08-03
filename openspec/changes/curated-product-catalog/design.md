## Context

Product templates are runtime rows in `product_template_version`, authored
through the admin UI or `caelus create-template`. The canonical template for a
product is the `product.template_id` pointer, moved with
`caelus update-product --template-id`. Nothing about this is version
controlled, so there is no diff to review, no audit trail, and no way to see
which upstream application version a product is pinned to without querying the
database.

This blocks an autonomous release-detection agent. A pull request proposing
"upgrade Immich to v3.1.0" would carry an empty diff, since the change is a
sequence of CLI calls rather than a file edit. Making the diff real requires
the desired catalog state to live in the repository.

Two existing properties shape the design. First, CI has no cluster access:
`.github/workflows/ci.yml` runs tests and pushes images to ghcr, and the k3s
cluster is homelab-internal. Second, `DeploymentORM` carries both
`desired_template_id` and `applied_template_id`, so template rows are
historical records referenced by running deployments and cannot be treated as
disposable.

The hands-on authoring loop — create a product, tweak system values, iterate on
a Helm chart — is how new products are onboarded today and is used routinely.
Any design that degrades it is a net loss.

## Goals / Non-Goals

**Goals:**
- Make product upgrades reviewable as a real diff, so a pull request is a
  meaningful approval gate.
- Preserve the interactive authoring loop for products under development.
- Keep template rows intact as history for deployments that reference them.
- Require no cluster credentials in CI and no runtime git access.
- Provide a boundary an autonomous agent provably cannot cross.

**Non-Goals:**
- Upgrading running deployments to a new canonical template. Merging affects
  new provisions only; existing deployments keep their applied template until
  an operator acts.
- Managing plans or plan templates through the catalog. Price and billing
  interval changes have live consequences via Mollie and existing
  subscriptions, and need their own approval policy.
- Building the release-detection agent itself, or any trial/smoke-test
  tooling it may later use.
- Replacing the `product` or `product_template_version` tables.

## Decisions

### Git holds desired state; the database remains the read path

The repository does not replace the tables. It becomes a desired-state input,
mirroring a pattern already present one level down:

| | Desired | Applied |
|---|---|---|
| Deployment | `desired_template_id` | `applied_template_id` |
| Catalog | `products/catalog/*.yaml` | `product_template_version` rows |

`DeploymentReconciler` closes the gap between a deployment's desired and
applied template; `CatalogReconciler` closes the gap between the repository's
desired catalog and the rows that realize it. Every column stays: each is read
at runtime by `reconcile.py`, `provisioner.py`, or the UI. Only the write path
moves.

*Alternative considered*: replace the tables with the YAML files as the runtime
source. Rejected because `applied_template_id` is a foreign key into
`product_template_version`; a deployment's applied template must remain a row
long after that version leaves the catalog.

### Curated and non-curated products, split by an explicit column

`product.curated` is the reconciler's selector, not a label. Non-curated
products are database-authored and behave exactly as they do today; curated
products are catalog-authored and read-only through the API, CLI, and UI, apart
from `visibility`. The flag is persisted rather than computed on demand: the
write guard, the reconciler's own queries, and the admin UI all need it without
consulting the filesystem.

*Alternative considered*: do not store the flag at all, and derive curation at
read time by matching a product's *name* against catalog filenames. Rejected
because renaming a product would silently un-curate it, and a scratch product
sharing a name with a catalog file would have undefined status. Persisting the
flag and joining on `slug` instead of `name` makes adoption a logged transition
and the boundary enforceable rather than conventional. Note this is a different
question from *where the value comes from*: the reconciler derives it from
catalog file presence, as described below.

### Two lifecycle stages, joined by curate

Non-curated is the staging stage: admin-only, tight iteration. Curated is the
published stage: reviewed, agent-upgradable. `catalog curate` is the graduation
step — it emits YAML from tuned database state, so the first pull request for a
product is a verified no-op: the reconciler matches the existing template by
spec equality, inserts nothing, and only flips the product to curated.

Round-trip fidelity is therefore load-bearing, and is the single most valuable
test in this change.

### Matching by computed spec hash, not a stored column

The reconciler hashes a canonical, sorted-key serialization of `chart_ref`,
`chart_version`, `chart_digest`, `system_values_json`, and `values_schema_json`,
computed from row contents at read time.

*Alternative considered*: a stored `spec_hash` column. Rejected on two grounds.
A stored hash is a cache that goes stale whenever the spec field set or the
serialization changes, whereas a computed hash is always self-consistent. And
if matching were filtered by provenance, graduation would break: the reconciler
would fail to see the hand-made template the YAML was generated from and would
insert an identical duplicate. Matching must ignore origin.

`catalog_commit` is stored instead, because it answers a different question —
how a row came to be, which is not derivable from its contents. It is written
once on insert from the `GIT_COMMIT` environment variable already present in
the image, and never read by application logic.

### Append-only template ledger

The reconciler has exactly two verbs: insert and repoint. It never updates a
template's spec fields and never sets `deleted_at` on one. This is what makes
it safe alongside the existing hand-made templates, and it makes re-running a
no-op. Removing a product from the catalog uncurates it and deletes nothing.

### Version pinned inside `system_values`, applied verbatim

The application image tag lives in `template.system_values` exactly as it will
be stored, with no templating engine. The file is what gets applied, so review
is WYSIWYG. `upstream.version_path` tells detection tooling where to write; it
is never applied to the cluster.

`upstream.match` carries a `version` capture group used only for ordering
candidates. The winning upstream tag is written verbatim, which is why no
`format` key is needed: for both seeded products the tag and the stored value
are identical (`v3.1.0`, `33.0.7-apache`).

*Alternative considered*: a `policy` block with a semver constraint and a
mirror-availability precondition. Dropped. The pull request is the policy — a
human reads every proposed bump, so a constraint duplicates review judgment and
can silently go stale. The residual problem is churn (an agent re-proposing a
rejected version), which is better solved as agent-side state than as catalog
schema. The mirror precondition was dropped because Caelus does not mirror
application images: the Matrix template pulls `ghcr.io/matrix-construct/tuwunel`
directly, and only charts live in `registry.home`.

### Apply by init container, not by CI or a polling loop

The catalog is baked into the API image and applied by an init container
running after the existing `migrate` container.

*Alternatives considered*: (a) CI applies on merge — rejected, since CI has no
cluster access and granting it would mean inbound access to a homelab cluster
plus long-lived credentials in GitHub secrets; (b) an in-cluster singleton
polling git — rejected as more machinery for little gain, since merge already
triggers a build and rollout, and it would require runtime git credentials and
leader election.

Baking the catalog into the image makes catalog-versus-code skew structurally
impossible and gives rollback for free: a bad catalog fails the init container,
new pods never become ready, and the old ReplicaSet keeps serving.

### Service-layer write guards

The curated guard lives in `api/app/services/products.py` and
`templates.py`, not in the UI. Per the repository convention that CLI and REST
stay in lockstep and all DB logic lives in services, a single guard covers the
REST API, the Typer CLI, and the React admin simultaneously. Guarding only in
the UI would leave `caelus update-product` as an unguarded back door.

Break-glass *modifications* are allowed via an explicit force option and leave
`catalog_commit` null, so drift is visible and self-heals on the next rollout.

Deletion is deliberately excluded from the override. The reconciler resolves a
curated product by slug among non-deleted rows, so a force-deleted product is
not found, is not adopted, and is recreated under a new id on the next rollout,
while existing deployments keep referencing templates on the old row. An
override whose outcome is "the product returns as a different product" is not a
useful escape hatch, and a supported path already exists: remove the catalog
file, let the rollout uncurate the product, then delete it normally. The same
reasoning excludes force-deleting a curated product's
templates, which the reconciler reinserts whenever the spec still matches.

### File presence is the sole carrier of curation

`curated` and `slug` are written only by the reconciler, derived from whether a
catalog file declares that slug. Adding a file curates a product; removing one
releases it. There is no CLI command to curate or uncurate.

An earlier draft had both a CLI `uncurate` command and a fail-closed rule that
aborted when a curated product had no catalog file. Those two rules deadlocked:
removing the file first blocked the rollout, and uncurating first was refused
because the file still existed. The deadlock existed only because `curated` had
two writers with different latencies — a database fact that changes instantly
and a git fact that arrives via merge and rollout. Collapsing it to one writer
removes the ordering problem rather than resolving it.

It is also the more consistent choice: an unreviewed CLI mutation that removes a
product from review-gated management inverts the premise of this change.
Deletion of a catalog file is a reviewable diff like every other catalog change.

*Alternative considered*: keep fail-closed, on the reasoning that an
accidentally dropped file is indistinguishable from a deliberate removal. The
concern is real but the damage is small and self-healing: an uncurated product
keeps its templates, canonical pointer, visibility, and deployments, and
restoring the file re-adopts it by name on the next rollout. What is *not*
tolerable is the systemic case — a mistyped `--dir`, or a build that fails to
read the catalog directory at all, which would present as zero documents and
uncurate every product at once. That case is guarded separately: a directory
that cannot be read is an error, because failing to read desired state is not
the same as desired state being empty. An *empty* directory is valid and simply
means nothing is catalog-managed — the state every environment is in before its
first product is curated.

### Visibility is runtime state, not catalog state

The catalog owns what a product *is*: name, description, category, replaces,
icon, chart reference, system values, and values schema. The database owns
whether it is *currently offered* to end users. `visibility` therefore does not
appear in the catalog document, and the curated write guard exempts it.

Putting it in the catalog would have meant a merge, build, and rollout to take a
product off the storefront — the wrong latency for what is often an incident
response, on a change that alters no deployment and is trivially reversible. It
would also have created a drift conflict the rest of the design avoids: an
administrator's toggle would be reverted on the next reconciliation.

The reconciler MAY initialize `visibility` when it creates a product and MUST
NOT write it afterwards. New products start hidden, so merging a catalog change
can never by itself expose a product to end users; publishing stays a deliberate
human act. This also matters for the future release-detection agent, which can
propose adding a product but cannot put it in front of users.

### Catalog CLI is exempt from REST parity

`catalog apply|curate|lint` are operator and build tooling, not
tenant-facing surface, and `apply` in particular is invoked by an init
container. They are CLI-only by design. The protections they depend on live in
the service layer, so no parity gap is introduced.

## Risks / Trade-offs

- **The hybrid is more code than either pure option** → Accepted deliberately.
  Adoption logic, uncuration, service guards, the curate command, and a
  dual-mode UI are the price of keeping the authoring loop fast while gaining
  review on published products.

- **Admin UI loses product-authoring for curated products** → The genuine cost
  of the design. Mitigated by the break-glass force path and by the fact that
  products under active development stay non-curated.

- **Prune logic could delete experimental products** → Every reconciler query
  filters `curated = true`. A test asserting non-curated products are untouched
  by a reconciliation run is required before the reconciler ships.

- **Concurrent init containers could double-insert** → A Postgres advisory lock
  wraps the apply transaction. Low exposure today at one replica, but cheap.

- **Curate/apply mismatch would churn template rows on graduation** → A
  round-trip test (curate all, apply, assert zero new rows) guards this. The
  recent removal of `version_label`, `capabilities_json`, and
  `health_timeout_sec` eliminated the known hazards, since every remaining spec
  field has a live consumer.

- **Renaming a product could orphan its catalog file** → `product.slug` is the
  join key, independent of `name`.

- **A dropped catalog file silently un-curates a product** → Accepted. The
  damage is small and self-healing: templates, canonical pointer, visibility,
  and deployments are untouched, and restoring the file re-adopts the product by
  name. The systemic case — a mistyped path or a build that copied nothing — is
  guarded separately by erroring when the catalog directory cannot be read.

- **A visibility toggle is not reviewed** → Accepted. It alters no deployment,
  is instantly reversible, and is logged with the acting user. Reviewing it
  would impose merge-and-rollout latency on what is often an incident response.

- **Catalog-only merges must still roll out** → The master CI build runs on
  every push regardless of changed paths. Adding path filters later would break
  catalog delivery; this constraint should be noted where CI is configured.

- **Drift is corrected at deploy boundaries, not continuously** → Accepted, and
  arguably preferable: reversions happen at a moment an operator is already
  watching.

## Migration Plan

Phased so that each step is independently useful and low risk.

1. **Visibility only.** Add `product.visibility`, backfilled to `public` to
   preserve today's behavior, and filter the end-user product list on it. Admin
   listings continue to filter on `deleted_at` alone. Useful standalone,
   independent of the catalog.
2. **Columns and guards.** Add `product.slug`, `product.curated`, and
   `product_template_version.catalog_commit`; add service-layer write guards
   and the read-only admin UI affordances. No behavior changes until a product
   is curated.
3. **Catalog tooling and seeding.** Implement `catalog curate`, `apply`, and
   `lint`, plus `CatalogReconciler`. Generate
   `products/catalog/*.yaml` for the existing products with `catalog curate`
   rather than authoring by hand, merge as a verified no-op, and confirm zero
   new template rows.
4. **Rollout wiring.** Bake `products/catalog/` into the image, add the
   `catalog` init container after `migrate`, and add `catalog lint` to CI on
   pull requests.

**Rollback**: each phase is a separate migration and can be reverted
independently. Because reconciliation is insert-and-repoint only, reverting the
rollout wiring leaves all template rows intact; repointing a product's canonical
template back is a single `update-product --template-id --force`. A bad catalog
never reaches a running pod, since the init container fails first.

## Open Questions

- Should `catalog curate` emit a stub `upstream` block with placeholders, or
  omit it and require the operator to add it? Omitting risks a curated product
  silently never being checked for updates.
- Should `catalog lint` verify that the pinned image tag exists upstream? It
  would require network access in CI and couples linting to third-party
  availability, but would catch a typo before merge rather than at rollout.
