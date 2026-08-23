## Context

See `proposal.md` § Why for the motivation. This section records only the existing
behavior that constrains the approach. The exploratory notes this design grew from are
kept at `var/vars.md`; this document supersedes them.

Four facts about the current system shape everything below.

1. **`user_values_json` is echoed and archived.** It is stored on the deployment row,
   snapshotted into `deployment_release.values_json`
   (`api/app/services/deployments.py:581`), and returned by both `DeploymentRead` and
   `DeploymentReleaseRead` (`api/app/models/core.py:665`). Anything routed through it is
   permanently readable.
2. **Merged Helm values are logged and persisted tenant-side.** The provisioner logs
   them in full at INFO and Helm writes them into a release object in the tenant's own
   namespace. `_ensure_object_storage` already documents this and routes the S3 secret
   key through a Kubernetes Secret instead (`api/app/services/reconcile.py:330`). That
   is the pattern to follow.
3. **Template versions are immutable.** `CatalogReconciler._resolve_template` matches a
   catalog document against existing rows by spec hash and **inserts a new template
   version** when the schema changes (`api/app/services/catalog.py:799`); it never edits
   one in place. A schema change therefore never rewrites what existing deployments are
   validated against.
4. **The user-values form is already flat.** `flattenSchema` collapses nested objects
   into dot-paths and the renderer emits a flat `Stack` of fields with no group heading
   (`ui/src/components/UserValuesForm.tsx:255`). Nesting in a schema buys nothing
   visually today. Its Ajv instance runs `strict: false`, so unknown keywords already
   pass through.

### Vocabulary

Used consistently in tables, endpoints, payloads and CLI. Prose that predates this change
mixes *var*, *config*, *param* and *secret*.

| Term | Meaning |
| --- | --- |
| **var** | One key/value pair destined for a pod's environment. The only noun. |
| **sensitive** | A var whose value is never returned. The adjective; not "secret". |
| **head** | The newest row per key, minus tombstones. A deployment's desired vars. |
| **snapshot** | The var rows bound to one release. Frozen at release creation. |
| **staged** | A var write not yet captured by any release. |
| **pending** | Head differs from the *applied* release's snapshot. |
| **release** | A `deployment_release` row. The Helm sense is always spelled **Helm release**; D10 depends on the distinction. |

"Secret" survives only as the name of the Kubernetes object.

## Goals / Non-Goals

**Goals:**

- One channel into a pod's environment, used by both the CLI and the UI.
- Sensitive values that are write-only end to end: never echoed, never logged, never
  stored in plaintext, not to the owner and not to an admin.
- Reproducible releases: a release records exactly the values it ran with.
- Curated products keep their schema-driven form, unchanged in look and behavior.
- Closed by default with no per-product boilerplate to author or forget.

**Non-Goals:**

- Hard deletion or crypto-shredding of rotated values. The store is append-only, so a
  rotated credential's ciphertext persists, pinned by the releases that referenced it.
  This has a GDPR/DPA angle and needs a retention policy; see *Deferred work*.
- Migrating existing curated products off `user_values_json`. D14 explains why not, and
  the mechanism is designed to make it possible property-by-property later.
- Access control below deployment ownership.
- Rollback to a previous release. The snapshot is the enabling structure; the verb is not
  in scope.

## Decisions

### D1. Routing is a per-property marker inside the existing schema

`values_schema_json` gains `x-caelus-target: chart | runtime` on top-level properties,
`x-caelus-sensitive` alongside it, and `x-caelus-vars-additional` at the root. The server
derives a **chart projection** and a **vars projection** by partitioning the root's
`properties` and `required`:

```
chart_projection = {
    **root_minus_properties_and_required,
    "properties": {k: v for k, v in properties.items() if target(v) == "chart"},
    "required":   [k for k in required if target(properties[k]) == "chart"],
}

vars_projection = {
    "$schema": root["$schema"],
    "type": "object",
    "additionalProperties": root.get("x-caelus-vars-additional", False),
    "properties": {k: v for k, v in properties.items() if target(v) == "runtime"},
    "required":   [k for k in required if target(properties[k]) == "runtime"],
}
```

Two consequences carry most of the weight of this design:

- **One namespace, not two.** `properties` is a single JSON object, so its keys are
  unique by construction and the two halves are disjoint partitions of one key space. A
  template author cannot create a chart/runtime collision even deliberately.
- **Closed by default is free.** A product with no runtime-marked properties derives
  `{"type": "object", "additionalProperties": false, "properties": {}}`, which rejects
  every var. No empty-schema boilerplate per product, and none to forget. A template with
  no schema rejects vars outright, mirroring `validate_user_values`, which already
  rejects values when a template declares no schema
  (`api/app/services/template_values.py:42`).

*Alternatives considered.* A reserved `vars:` container property inside the schema: it
bakes routing into the *shape* of the data, so moving one property between channels
changes the payload structure and every stored `user_values_json`, and it introduces the
second namespace the marker avoids. A separate `vars_schema_json` column on the template:
two documents to keep in sync, and no coherent way to render one form from two schemas —
which was the original open question this design set out to answer.

`x-` prefixes keep the keywords from colliding with a future JSON Schema draft.

### D2. Runtime markers only on top-level scalar properties

`x-caelus-target: runtime` is legal only on a root-level property of scalar type. The
schema property name **is** the environment variable name.

This removes an entire class of work. If runtime properties could nest, a flattening
convention (`signups.allowed` → `signups__allowed`) would have to be implemented in the
UI to build the payload and in the API to un-flatten it for validation — the same rule in
two languages, free to drift, and needed nowhere else in the system.

It costs nothing visually, because the form is already flat (Context, fact 4). A curated
product migrating later restructures a group into flat properties in its **new** template
version, which renders identically.

Enforced at meta-validation (`api/app/services/catalog.py`, `templates.py`): scalar type,
name matching `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, not a reserved name (D12),
`x-caelus-sensitive` only on a runtime property. A bad schema fails at rollout, not at
some tenant's next deploy.

### D3. The client splits the payload; the server never fans out `user_values_json`

The UI reads one schema, renders one form, and **partitions its own submission**: chart
properties into `user_values_json`, runtime properties into `vars`. The server validates
each half against its projection and writes each through its own code path.
`update_deployment` never derives vars from `user_values_json`.

This is the load-bearing decision, and the reason is not stylistic. For the server to
split one blob, sensitive plaintext would have to arrive **inside** `user_values_json` —
the field that is persisted on the deployment row, snapshotted into the release, and
echoed by two read models (Context, fact 1). The server would then have to strip secrets
before both persists, on every path, forever; one missed path puts an admin password in a
release record permanently. The design would reintroduce as its default the exact leak it
exists to close.

Secondarily, the two stores have incompatible update semantics: `update_deployment`
treats `user_values_json` as a full replace (`api/app/services/deployments.py:516`),
while vars are append-only with merge-and-tombstone. A payload that omits a key would
mean "delete" on one side and have no defensible meaning on the other.

*Alternative considered.* Server-side fan-out from a single submitted document. Rejected
for the above; it is attractive only because it keeps the client dumb.

### D4. Append-only rows, with a per-release snapshot table

```sql
create table deployment_var
(
    id              bigint generated always as identity primary key,
    deployment_id   uuid        not null references deployment (id) on delete cascade,
    key             varchar(64) not null,
    -- NULL is a tombstone: the key was deleted at this point in history.
    value_encrypted text,
    -- Fingerprint of the encryption key, not a position in the key list. See D5.
    key_id          char(8),
    sensitive       boolean     not null default false,
    created_by      integer     not null references "user" (id),
    created_at      timestamptz not null default now(),

    constraint ck_deployment_var_tombstone
        check ((value_encrypted is null) = (key_id is null))
);

create index ix_deployment_var_head
    on deployment_var (deployment_id, key, id desc);

-- Serves key retirement and the re-encryption sweep (D5).
create index ix_deployment_var_key_id
    on deployment_var (key_id);

create table release_var
(
    release_id uuid   not null references deployment_release (id) on delete cascade,
    var_id     bigint not null references deployment_var (id) on delete cascade,
    primary key (release_id, var_id)
);

create index ix_release_var_var on release_var (var_id);
```

Notes:

- `deployment_release.id` is a `uuid` (`api/app/models/core.py:585`), not an integer.
- `created_at` is a `timestamptz`. Head resolution orders by `id`; the timestamp is audit
  evidence, and a `date` would lose what makes it useful.
- A NULL `value_encrypted` is meaningful — it is the tombstone. The check constraint keeps
  it consistent with `key_id`.
- `sensitive` is per row, not per key, which is what allows the flip in E6.
- `release_var` carries no `key` column; it is derivable through the join, and
  denormalizing it would create a second place for a key name to be wrong.
- Both tables cascade from their parents, so deleting a deployment does not fail on a
  foreign key. `deployment_release` already cascades (`api/app/models/core.py:589`).

**Head resolution**, which belongs in exactly one function — the tombstone filter is easy
to omit and the omission is silent:

```sql
select *
  from (select distinct on (key) *
          from deployment_var
         where deployment_id = :deployment_id
         order by key, id desc) head
 where value_encrypted is not null;
```

**Write serialization.** `id` is monotonic per insert, but transactions can commit out of
order, so concurrent writers to one key could produce a head reflecting neither intent.
Every var mutation and every snapshot binding first takes `select id from deployment
where id = :deployment_id for update`. That gives a total order per deployment, and
serializes var writes against release creation so a write cannot land between head
resolution and the `release_var` insert.

*Alternatives considered.* A mutable one-row-per-key table: simpler reads, but it loses
the audit trail and cannot keep an old release's snapshot meaningful after a key is
deleted. Copying values into a column on `deployment_release` like `values_json`: it
would duplicate ciphertext per release and put secrets in the row that two read models
already echo.

*Accepted cost.* Reads are a `DISTINCT ON` rather than a plain select, and rotated
ciphertext is retained indefinitely (see *Deferred work*).

### D5. Key identity is a fingerprint of the key material

Each encrypted row stores `key_id`: the first 4 bytes of
`sha256(urlsafe_b64decode(fernet_key))`, lowercase hex.

It is **not** a position in the configured key list, and that is the point. A positional
identifier would be destroyed by the very operation it exists to support: rotation
introduces a key by **prepending**, so every stored index would silently come to name a
different key and every historical row would decrypt to garbage or fail. An identifier
invalidated by its own rotation procedure is worse than none, because it fails silently.

**Primitive: plain `Fernet`, one instance per key, in a dict keyed by fingerprint.**
`MultiFernet` is deliberately not used: its try-every-key decryption exists to work
around the absence of a key identifier in the token, and once a row carries one it buys
nothing and costs precision. Direct lookup is O(1) and fails with something actionable —
`row 8412 was encrypted with key 1a2b3c4d, which is not configured` — instead of an
undifferentiated `InvalidToken` that cannot tell a retired key from a corrupted row.

**Values are always encrypted, including non-sensitive ones.** One column, one code path,
no per-row branch on where the plaintext lives. Nothing needs to query on a value.

**Rotation.** The configured list is newest-first; the first entry is *current* and the
only one used to encrypt.

1. **Prepend** the new key. New writes use it. Nothing renumbers.
2. **Sweep** at leisure: `where key_id <> :current_id and value_encrypted is not null`,
   decrypt with the row's own key, re-encrypt with the current one, update
   `value_encrypted` and `key_id` in place. Batched, resumable, safe to interrupt — a
   half-swept table is fully readable because every row still names its own key.
3. **Retire** once `select distinct key_id ...` no longer contains the old fingerprint.

Step 2 rewrites the ciphertext of a row D4 calls immutable. That is consistent because
**immutability is defined at the plaintext level**: a row's plaintext never changes; its
representation may be rewritten as maintenance.

**Startup checks**, in both the API and the worker: fail on a fingerprint collision
between configured keys; fail if the list is empty while any reachable template declares
vars; fail if any `key_id` present in storage is not configured. The last is deliberately
fatal — a row whose key is gone can never be decrypted again, and that must surface in
front of whoever edited the key list, not months later inside a tenant's failed rollout.

*Alternative considered.* Explicit labels in the config (`3:<key>,2:<key>`). They survive
prepending, but depend on an operator assigning labels correctly and never reusing one,
across `secrets.auto.tfvars` in every environment, with nothing to detect a mistake. A
fingerprint travels with the key, cannot be misassigned, and is identical in dev and prod
for the same key.

### D6. A var is addressed by deployment, phase and key

```
GET | PATCH | PUT   /api/users/{u}/deployments/{d}/vars/{phase}
GET | DELETE        /api/users/{u}/deployments/{d}/vars/{phase}/{key}
```

`{phase}` is `runtime`, and nothing else until build vars exist. It is a path segment
because it is part of the resource's **identity**, not a filter: two vars may share a key
when their phases differ — `API_URL` is a public origin at build time and an in-cluster
address at runtime — so `(deployment, phase, key)` is the natural key. A query parameter
would be the wrong tool, and none of the comparable platforms uses one for this.

*Alternatives considered.* A flat `/vars` with a `?target=` filter: not RESTful, since it
selects rather than filters, and it bakes "a key is unique within a deployment" into the
response map — widening that later breaks every deployed client. Vercel's model (a list
of objects with a surrogate `id`, phase as a *field*) does not transfer: our store is
append-only, so a row id changes on every write and cannot identify a var; we would have
to mint a synthetic id that encodes `(phase, key)`, which is the natural key in disguise.
Heroku's precedent is the closest — when it needed to scope config vars by pipeline
stage, the stage went in the path.

**`{phase}` is a phase, never an environment.** It says *when* a value is consumed. It
must not grow `production` or `staging` values: those are a different axis, and we
already express it one segment earlier, since a staging app is its own deployment with
its own hostname, namespace, plan and release history. Collapsing the two axes into one
enum produces the unanswerable question "what are the build vars for staging?". The word
is pinned in the spec as *phase* for exactly this reason.

### D7. One wire shape; a sensitive read omits `value` entirely

```json
{
  "vars": {
    "SIGNUPS_ALLOWED": {"value": "false"},
    "ADMIN_TOKEN":     {"value": "hunter2", "sensitive": true}
  }
}
```

The same shape on create, update, the collection, a single var, and a release read — and
it is the shape of the Kubernetes Secret's `stringData`, which is where it ends up.
Nested under `vars` so envelope fields can be added later without colliding with a
caller-controlled key.

The map stays flat even though D6 gives the resource a phase segment, because every
place it appears is already single-phase. The collection and single-var routes are
phase-scoped by their path. `vars` on deployment create and update is runtime by nature:
a value consumed before the deployment exists cannot be supplied on the request that
creates it, since the image is built first. And a release only ever carries runtime vars
— a release rolls an image, and anything consumed at build time was consumed when that
image was built.

A read of a sensitive var returns `{"sensitive": true, "updated_at": ..., "updated_by": ...}`
with **no `value` key**:

- A mask (`"xxxxx"`) invites a caller to write it back verbatim as the new value.
- `null` is worse: null is the tombstone under PATCH, so a caller that round-tripped a
  read into a write would delete every secret it could not read.
- A digest of the *ciphertext* is useless — Fernet's IV is random, so it changes on every
  write of the same plaintext and cannot answer "did my value change". A useful
  fingerprint would have to be an HMAC of the plaintext under a separate key; not in
  scope.

Omission gives a clean third state and the rule that follows from it: **absent `value` on
write means "leave unchanged"**, which makes `freepod var list --json` output safely
writable.

**Values are strings on the wire**, coerced before validation against the projection:

| Declared type | Accepted | Coerced to |
| --- | --- | --- |
| `boolean` | `"true"`, `"false"` | `true` / `false` |
| `integer` | integer literal | `int` |
| `number` | number literal | `float` |
| `string` | anything | unchanged |

**`sensitive` is schema-authoritative** where the projection declares the property: filled
from `x-caelus-sensitive` when omitted, **400 when contradicted** rather than silently
overridden — that turns a client defect into an error instead of quietly downgrading a
password. Where the projection declares nothing (an open projection), the caller decides,
defaulting to `false`. The weak default is defensible because a non-sensitive value is
echoed only to the deployment's owner, who typed it.

### D8. Deployment reads report head; release reads report the snapshot

`DeploymentRead.user_values_json` is the deployment row — desired state. If
`DeploymentRead.vars` reported the applied release's snapshot, one response would mix
desired chart values with applied runtime values, which is exactly the confusion
`pending` exists to expose. So `DeploymentRead.vars` is head,
`DeploymentReleaseRead.vars` is that release's snapshot, and

> `pending` = runtime head ≠ **applied** release's snapshot

computed against `applied_release_id`, never `desired_release_id`. After a failed rollout
head equals the *failed* release's snapshot, so a diff against desired would report
"nothing pending" while the running pod carries none of the changes.

On the phase-scoped collection the path already fixes what `pending` refers to.
`DeploymentRead` spans the whole deployment, so its `pending` is pinned to the definition
above and stays a plain boolean — deliberately not widened into a per-phase object. Any
other staleness is a *different predicate*, not the same one scoped differently: a
build-time value would be compared against what the running image was built with, which
is a build record rather than a release snapshot, and answered by a rebuild rather than a
rollout. That deserves its own field with its own name, not a key in this one. What the
narrow definition prevents is the meaning silently widening under a UI that says
"redeploy to apply".

Vars are **not** inlined into the deployment list response: head resolution is a
`DISTINCT ON` per deployment, making the list an N+1 or one fiddly windowed query, and
fattening a payload no caller reads vars from.

### D9. Vars are desired state, including after a failed rollout

A request that creates a release writes its var rows whether or not the rollout later
succeeds, and they are captured by the next release. This is not a new hazard: it is
already how `user_values_json` behaves, written in the guarded UPDATE
(`api/app/services/deployments.py:522`) regardless of the reconcile's outcome.

Caelus is a desired-state system — `user_values_json`, `desired_template_id` and
`desired_release_id` record intent; `applied_release_id` records fact. Making vars
conditional on rollout success would mean the database stops recording what the user
asked for, and a retry would have to reconstruct intent from somewhere else.

Nothing is silent: the failed release keeps its own binding, so what that release meant
never changes retroactively, and `pending` (D8) reports correctly.

**The transaction**, in `create_deployment` / `update_deployment`:

1. Row-lock the deployment (or, on create, hold the insert).
2. Validate `user_values_json` against the chart projection (existing
   `_validate_user_values`).
3. Validate `vars` against the vars projection, coercing per D7 and scrubbing errors per
   D13.
4. Resolve head; **insert rows only where the value or `sensitive` actually differs**.
   Without this diff, every deploy appends a full copy of the configuration and the
   history becomes landfill.
5. Mint `release_id`, run the existing guarded status UPDATE, insert the release row.
6. Resolve head again — now including step 4 — and insert `release_var` for every
   non-tombstone row.
7. Enqueue the reconcile job.

Steps 4 and 6 sharing a transaction with 5 is what makes the snapshot atomic, and on
create it is what stops the first release's snapshot from being empty.

### D10. One Secret per deployment, referenced by name only

The reconciler reads the desired release's snapshot, decrypts, and upserts a Secret in
the tenant namespace, following the path `_ensure_object_storage` established
(`api/app/services/reconcile.py:320`):

```python
self._provisioner.upsert_secret(
    namespace=deployment.namespace,
    name=vars_secret_name(deployment),
    string_data={key: plaintext for key, plaintext in release_vars},
    labels={...},
)
```

`vars_secret_name(deployment)` returns `f"{deployment.name}-vars"` — derived from the
**deployment**, so stable across reconciles *and across releases*, updated in place
rather than churned.

> A caution for anyone working in the neighboring code: `storage_secret_name`'s docstring
> says it is "derived from the release name" (`api/app/services/reconcile.py:33`), where
> *release* means the **Helm release**, whose name is `deployment.name` — which is why
> the body is `f"{deployment.name}-object-storage"`. It does **not** mean
> `deployment_release`, which is what *release* means everywhere in this document.
> Carrying that phrase over would read as a per-`deployment_release` Secret name, which is
> not this design and would change the rollout semantics below.

Only the **name** is projected into the merged values:

```json
{"caelus": {"vars": {"secretName": "vw-abc123-vars"}}}
```

Values must never travel through the values document, for the reason recorded at
`api/app/services/reconcile.py:330`: merged values are logged in full at INFO and
persisted by Helm into a tenant-namespace object, so a value routed through them reaches
the log aggregator on every reconcile.

**No vars, no block.** An empty head emits no `caelus.vars` block and creates no Secret,
mirroring `_build_object_storage_overrides` returning `None`
(`api/app/services/reconcile.py:449`), so a chart that requires vars fails loudly instead
of rendering an empty `envFrom`.

**Reserved names and `envFrom` precedence** — two protections, because they fail
differently. The denylist (D12) rejects the name at the API. Independently, a later
`envFrom` source overrides an earlier one and an explicit `env` entry beats every
`envFrom`, so the vars Secret goes **first** in `envFrom` with platform sources after it.
`PORT` is already safe, being an explicit `env` entry
(`products/custom/chart/templates/deployment.yaml:65`).

**Rollout on a var-only change.** `helm upgrade` does not restart pods when only a
Secret's contents change — the rendered pod spec is identical. For `custom` this is
already solved: `caelus.releaseId` is projected on every reconcile
(`api/app/services/reconcile.py:405`) and the chart stamps it into the
`caelus.dev/release-id` pod label (`products/custom/chart/templates/_helpers.tpl:54`), so
a new release always changes the pod template. **The curated charts ignore `releaseId`**
and would take the new Secret while continuing to run the old configuration, silently —
which is why adopting `releaseId` or a Secret checksum annotation is a *prerequisite* for
D14, not a follow-up.

*Alternative considered.* A per-release Secret name (`{deployment.name}-vars-{number}`),
which would change the pod spec on every var change and force the rollout for free.
Rejected: it accumulates one Secret per release in the tenant namespace and needs a
garbage collector, while `releaseId` already does the job for `custom` with no litter.

### D11. `deploy --no-build` is the primitive; `var set` applies by default

Vars take effect on the next release, and today no verb mints a release without other
changes: `freepod deploy` re-uploads and rebuilds from source, and a curated product has
no deploy verb at all.

- **`freepod deploy --no-build`** — the primitive. Mints a release from the deployment's
  current image, skipping upload and build. Independently useful.
- **`freepod var set` / `rm` apply by default**, calling that primitive, with `--stage`
  to defer. This is Fly's ergonomics (`fly secrets set` deploys, `--stage` defers) and
  what users arriving from Heroku expect. Several vars in one invocation produce one
  release.

`freepod restart` is deliberately **not** added: the name promises "same configuration,
new pods" and would deliver the opposite.

**Carrying `build_id` forward.** A `--no-build` release runs an image a build produced, so
it must keep naming that build. It will not by default: `update_deployment` writes
`build_id=update.build_id` unconditionally (`api/app/services/deployments.py:580`), so a
payload omitting the field yields a release with a null `build_id` — running built code
with no link back to the build, breaking the association `AGENTS.md` describes and
emptying `DeploymentReleaseWithBuildRead.build`. The CLI therefore reads the applied
release and passes both its image and its `build_id` through explicitly, which makes the
CLI correct on its own.

The general fix is **out of scope here**: when `build_id` is omitted from an update and
the effective image is unchanged, the server should inherit the applied release's
`build_id` rather than writing null. That is not specific to `--no-build` — today *any*
update omitting it, such as a hostname edit through the UI, drops the build link while
the running image is unchanged. It changes behavior for existing clients and wants its own
change; vars merely make it conspicuous, because `var set` mints releases routinely.

### D12. Limits and reserved names

Enforced at the API so a bad var fails with a clear 400 rather than opaquely inside Helm.
A Kubernetes Secret tops out at 1 MiB, shared with the object-storage Secret.

| Limit | Value |
| --- | --- |
| Key name | `^[A-Za-z_][A-Za-z0-9_]{0,63}$` |
| Value size | 8 KiB (plaintext, UTF-8 bytes) |
| Total per deployment | 128 KiB (plaintext, summed over head) |
| Key count per deployment | 256 |

8 KiB per value rather than something tighter because injected JWTs and PEM-encoded
material routinely run to several kilobytes.

Reserved: the prefixes `CAELUS_`, `AWS_`, `S3_`, `RAILPACK_`, and the exact names
`BUCKET_NAME` and `PORT`. Most are what the platform injects today — the object-storage
Secret carries the `AWS_*`, `S3_BUCKET` and `BUCKET_NAME` names
(`api/app/services/reconcile.py:342`) and the `custom` chart sets `PORT`.

`RAILPACK_` is reserved ahead of need. It is Railpack's own namespace, it takes
precedence over the variables a plan declares, and `RAILPACK_CONFIG_FILE` redirects which
config file the builder reads. No var reaches a build today, so nothing enforces this
except the denylist — but adding a reserved prefix *later* breaks anyone who has already
set one, and adding it now costs a string in a list nobody has used.

### D13. Validation errors must not echo the value

`jsonschema`'s `ValidationError.message` **embeds the offending instance** — a bad
`ADMIN_TOKEN` produces `'hunter2' is not of type 'boolean'`. The existing chart-side
validator interpolates it directly (`api/app/services/template_values.py:57`), and that
message reaches the caller *and* the logs, which ship to Loki.

The vars validator must build its message from `exc.json_path` and `exc.validator` only:

```
vars.ADMIN_TOKEN: failed constraint "minLength"
```

Never `exc.message`, never the instance. This is a real leak and it is invisible if the
existing function is copied.

### D14. Curated products do not migrate in v1

There is **no curated product with a sensitive parameter today**: vaultwarden declares
`host`, `signups.allowed` and `signups.verify` (`products/catalog/vaultwarden.yaml:28`),
and nextcloud and immich are comparable. There is no leak to fix, so migrating buys
consistency and costs a chart change plus a backfill.

The rule going forward is **new sensitive parameters are born as vars**. A hypothetical
vaultwarden `ADMIN_TOKEN` must be a var from day one, because `user_values_json` would
write it into release records permanently.

The migration path, when a reason arrives, is in *Migration Plan*.

### Worked example: a curated schema with vars

Illustrative — this is what vaultwarden *would* look like, not what v1 ships (D14).

```yaml
values_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  properties:
    host:
      type: string
      title: Hostname
      description: The fully qualified domain name used to access Vaultwarden
        (e.g. password.freepod.eu)

    SIGNUPS_ALLOWED:
      type: boolean
      x-caelus-target: runtime
      title: Allow open registration
      description: 'Allow anyone who knows the address to create an account. Leave
        off unless you need it: your own account is created for you, and you can
        invite others from the web vault.'
      default: false

    SIGNUPS_VERIFY:
      type: boolean
      x-caelus-target: runtime
      title: Require email verification on signups
      description: New users must confirm their email address before they can log in.
      default: true

    ADMIN_TOKEN:
      type: string
      x-caelus-target: runtime
      x-caelus-sensitive: true
      title: Password for the admin interface
      description: Leave empty to keep the admin interface disabled.
  required:
    - host
```

`host` carries no marker and so defaults to `chart` — which is what makes every existing
catalog schema keep working with no edit at all.

Derived chart projection:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "host": {"type": "string", "title": "Hostname", "description": "..."}
  },
  "required": ["host"]
}
```

Derived vars projection:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "SIGNUPS_ALLOWED": {"type": "boolean", "title": "...", "default": false},
    "SIGNUPS_VERIFY":  {"type": "boolean", "title": "...", "default": true},
    "ADMIN_TOKEN":     {"type": "string",  "title": "...", "x-caelus-sensitive": true}
  },
  "required": []
}
```

The form renders four fields exactly as today; on submit the UI partitions them into
`user_values_json = {"host": ...}` and `vars = {"SIGNUPS_ALLOWED": ..., ...}`.

### Worked example: `custom`

`custom` is the one product whose vars half cannot be derived from the root's
`additionalProperties`: its chart half must stay closed (`hostname` and `image` are the
only chart values) while its vars half must accept anything. That is the entire reason
`x-caelus-vars-additional` exists, and `custom` is expected to be its only user.

```yaml
values_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  x-caelus-vars-additional: true
  properties:
    hostname:
      type: string
      title: hostname
      minLength: 1
      maxLength: 253
      description: The fully qualified hostname for the app.
    image:
      type: string
      description: User-built image as "{user_id}@{digest}" (a digest reference with
        the registry host stripped), or empty to serve placeholderImage.
      pattern: ^$|^[0-9]+@sha256:[a-f0-9]{64}$
  required:
    - hostname
```

Derived vars projection:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": true,
  "properties": {},
  "required": []
}
```

### Worked example: creating a deployment with vars

```json
POST /api/users/7/deployments
{
  "product_id": 3,
  "desired_template_id": 42,
  "user_values_json": {"host": "vault.example.eu"},
  "vars": {
    "SIGNUPS_ALLOWED": {"value": "false"},
    "SIGNUPS_VERIFY":  {"value": "true"},
    "ADMIN_TOKEN":     {"value": "hunter2", "sensitive": true}
  }
}
```

```json
GET /api/users/7/deployments/{id}/vars/runtime
{
  "vars": {
    "SIGNUPS_ALLOWED": {
      "value": "false", "sensitive": false,
      "updated_at": "2026-08-20T09:12:44Z", "updated_by": 7
    },
    "ADMIN_TOKEN": {
      "sensitive": true,
      "updated_at": "2026-08-21T16:03:02Z", "updated_by": 7
    }
  },
  "pending": true
}
```

`DeploymentCreate` and `DeploymentRead` are already separate models
(`api/app/models/core.py:476`, `:497`), so a write-only field costs no RESTfulness
concession and needs no envelope.

### UI

`UserValuesForm` renders one form from one schema, as today. Two changes:
`flattenSchema` carries `target` and `sensitive` through onto `SchemaField`; on submit
the flat field list is partitioned by `target` into the two payload fields.

A sensitive field renders as a `password` input. On an existing deployment it renders
empty with an "unchanged" affordance, and submitting the form untouched must send the
entry with **no `value` field** (D7) — an empty string is a real value and would wipe the
secret. There is no reveal control; the value was never sent.

### Edge cases

- **E1 — Setting a var on a deployment that has never rolled out.** Legal. Head is
  non-empty, `pending` is true, the first release picks them up.
- **E2 — Deleting a key that does not exist.** Idempotent no-op, 204, no tombstone
  written. `PATCH` with `"value": null` on an unknown key likewise writes nothing.
- **E3 — Setting a var to the value it already has.** Writes no row (D9 step 4). With
  auto-apply on, it still mints a release: the user asked to deploy, and suppressing that
  would be more surprising than an empty rollout.
- **E4 — A key whose newest row is a tombstone.** Excluded from head, never bound to a
  release, absent from every read. History remains for audit.
- **E5 — Re-creating a deleted key.** An ordinary insert; the new row wins on `id`, with
  the tombstone still between the two live rows.
- **E6 — Flipping `sensitive` on an existing key.** Allowed; writes a new row with the new
  flag and the same plaintext, re-encrypted. It protects **future reads only** — it does
  not scrub history and does not invalidate anything already read; the CLI says so when
  it happens. Forbidding it was rejected: it dead-ends the user into delete-and-recreate
  under a different name. The reverse flip requires a new value, because silently
  exposing a value the user had marked sensitive is worse than making them retype it.
- **E7 — A schema change that moves a property between halves.** Handled by template
  versioning, not mutation (Context, fact 3).
- **E8 — A template with no `values_schema_json`.** Accepts no vars, mirroring
  `user_values_json` (`api/app/services/template_values.py:42`).
- **E9 — A var write racing a rollout.** Ordered by the deployment row lock (D4). A staged
  write during a rollout is legal and applies to the next release; an auto-applying write
  returns 409.
- **E10 — Two clients writing one key concurrently.** Serialized by the same lock. Last
  writer wins on `id`; both are visible in history with distinct `created_by`.
- **E11 — Encryption key missing at reconcile time.** Should be unreachable, since startup
  refuses a keyring that cannot cover storage (D5). If it happens — a key dropped while
  the worker ran — the reconcile fails naming the missing fingerprint and writes nothing.
  A partial Secret would start a pod with some variables missing, which is worse than not
  starting it and far harder to diagnose.
- **E12 — Deleting a deployment.** Cascades through both tables (D4). The plaintext was
  never stored; the ciphertext goes with the rows.

## Risks / Trade-offs

- **A secret leaks through a path nobody audited** (validation messages, a new log line, a
  future read model) → the omission rule is enforced in one serializer used by every read
  (D7); D13 forbids propagating `exc.message`; tests assert that a known plaintext appears
  in no response body and no captured log record.
- **A curated product adopts vars and silently does not restart** → D10 makes `releaseId`
  adoption a prerequisite, and D14 keeps curated products out of v1 so the trap cannot be
  sprung by accident.
- **A key is dropped from the config and rows become unreadable** → the fatal startup check
  in D5, which surfaces the mistake in front of whoever made it; the two-phase rollout
  below prevents the reverse (a key present in one process and not the other).
- **Append-only history grows without bound** → the diff in D9 step 4 means a redeploy that
  changes nothing writes nothing; the 256-key and 128 KiB caps bound the live set. Growth
  is proportional to actual changes.
- **Head resolution is a `DISTINCT ON`** → indexed by `ix_deployment_var_head`, kept out of
  the list endpoint (D8), and confined to one function.
- **The UI now owns the split** → if it mis-routes a property, a chart value lands in the
  vars projection and is rejected by `additionalProperties: false` rather than silently
  ending up in the wrong store. The failure is loud.

### Deferred work

| Item | Why deferred | Why it matters |
| --- | --- | --- |
| Retention / hard deletion of rotated ciphertext | Needs a policy decision, not just code | Append-only means a leaked credential's ciphertext persists, pinned by old releases. GDPR/DPA angle; Freepod is EU-established. Likely shape: purge rows not referenced by the applied release or the last N releases. |
| `caelus.releaseId` adoption in curated charts | Not needed while only `custom` uses vars | Hard prerequisite for D14. Without it a curated var change writes a Secret and does not restart the pod. |
| Server-side `build_id` inheritance | Changes behavior for existing clients | D11. Any update omitting `build_id` drops the build link today. |
| Curated migration off `user_values_json` | No sensitive parameter exists to justify it | D14. |
| Plaintext HMAC fingerprint | No confirmed use case | Would let a client detect a changed sensitive value without reading it; a ciphertext digest cannot (D7). |
| Rollback to a previous release | Out of scope | `release_var` is the enabling structure. |

## Migration Plan

**Schema.** One Alembic migration adding two tables and three indexes. No existing table
is altered and no data moves — nothing migrates off `user_values_json`. Rolling back is
dropping the tables; nothing else references them.

**Keys.** Because the API and the worker share the keyring, introducing a key is
**two-phase**:

- **Phase A — distribute.** Append the new key to the *end* of the list everywhere and
  restart both processes. Every process can decrypt with it; none encrypts with it, so
  restart order does not matter.
- **Phase B — promote.** Move it to the front and restart both. Encryption switches over,
  and by now every process can read what any other writes.

Skipping phase A breaks the reconciler: the API would encrypt with a key the worker does
not hold, and every rollout would fail while building its Secret — *after* the release row
already exists. The initial rollout is phase B with an empty prior list, which is safe
only because no row exists yet; every subsequent key follows both phases.

**Order of deployment.** Migration → keyring (both processes) → API and worker → chart
version consuming `caelus.vars.secretName` → CLI release. The chart change is
backward-compatible: a deployment with no vars emits no block (D10), so the new chart runs
unchanged against deployments that have none.

**Rollback.** Reverting the API leaves rows unread and Secrets in place; reverting the
chart leaves the Secret unreferenced. Neither breaks a running deployment. Reverting past
the migration requires no vars to exist.

**Migrating a curated product later (not v1).** Ordered as:

1. Ship a chart version that reads the parameter via `envFrom` **and** stamps
   `caelus.releaseId` into the pod template (D10), so a var-only change restarts the pod.
2. Publish the new catalog schema with the marker set. This inserts a **new template
   version** (Context, fact 3); no deployment moves yet.
3. Backfill `deployment_var` rows for deployments still on the old version, as a
   **one-shot migration script** with a system `created_by`, before they upgrade.
4. Deployments pick up the new template on their next upgrade. Their current release keeps
   rendering the old way, which is correct — that release's `values_json` still holds the
   value.

The backfill is the only case where the platform writes vars on a user's behalf, and it
happens **once**, explicitly, and attributed. Detecting a marker change during a template
upgrade inside `update_deployment` and migrating inline was considered and rejected: it
puts a rare, hard-to-test branch in the hottest path in the service, firing exactly when
the deployment is mid-status-transition.
