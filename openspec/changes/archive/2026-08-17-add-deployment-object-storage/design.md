## Context

See `proposal.md` § Why for motivation. What follows is only the state that shapes the
approach.

Garage v2.3.0 already runs as a `tf/deps` singleton, published at `https://blob.freepod.eu`,
holding the `dev` and `prod` artifact buckets for the build subsystem. It has no IAM: access
control is a per-`(access key, bucket)` permission grant, plus per-bucket quotas and lifecycle
rules, all reachable over a plain-HTTP admin API on port 3903 that is never routed by an
Ingress.

`DeploymentReconciler._build_system_overrides` is already a list of contributors, each
returning a `{"caelus": {...}}` fragment that is deep-merged and applied **last**, so a tenant
cannot shadow a system value. `KubeAdapter.apply_manifest` already performs an idempotent
`kubectl apply` of a single manifest. Both are the natural seams for this change.

Four facts were established empirically against the running cluster and against a throwaway
Garage v2.3.0 in Docker, rather than assumed. They are recorded because three of them are
load-bearing and one of them overturned an earlier design:

| Question | Result |
|---|---|
| Can a jailed tenant pod reach the object store? | **Yes, today, unchanged.** A live tenant pod under the baseline NetworkPolicy reached `https://blob.freepod.eu` and received a Garage S3 response. The in-cluster ClusterIP is blocked by the `10.0.0.0/8` egress exclusion and stays blocked. |
| Does an unmodified SDK work against a path-style-only endpoint? | **Yes for botocore.** With a custom `endpoint_url` it emits `…/bucket/key`, so a default client works with the endpoint variable alone. Not universal — see D7. |
| Is a bucket reachable only by its aliases? | **No.** Garage's S3 API accepts a bucket's raw internal identifier as a bucket name, bypassing aliases entirely. Access was still denied, by the permission grant. |
| Does a key-local alias survive its key? | **No.** It is deleted with the key. |

## Goals / Non-Goals

**Goals:**

- Provision, scope, quota and reclaim per-deployment object storage with no new process, no
  operator, no CRD and no subchart.
- Keep the secret access key out of every store that is not a Kubernetes Secret.
- Make an unmodified S3 SDK work in a tenant pod with zero application configuration.
- Leave a deleted deployment's bucket attributable to it without any platform-side bookkeeping.

**Non-Goals:**

- An empty-bucket reaper. Out of scope by design; see D6.
- Filesystem persistence (a PVC) or relational persistence (a `DATABASE_URL`). Both are real
  unmet needs and neither is addressed here; see `proposal.md` § Why.
- Public static hosting from a bucket. Closed off by this design; see Risks.
- Any change to tenant network isolation.
- A tenant-facing surface for reading the credentials back. Nothing here adds a REST endpoint,
  so no CLI/REST parity gap is introduced — the credentials only ever need to reach the pod.
  If a tenant later wants them for local development, `sftp-credentials-api` is the precedent
  to follow, and it is a separate change.

## Decisions

### D1. Provisioning lives in the reconciler

Terraform cannot do it: deployments are created and destroyed at runtime, not at apply time. A
chart-side pre-install Job cannot do it: it would require distributing an administrative token
into every tenant namespace, which inverts the entire trust boundary. An operator or CRD is
disproportionate to two API calls.

That leaves the reconciler, which is also where it belongs — it already owns namespace
creation, isolation and the Helm release, in that order, and this slots in beside them:

```
_reconcile_apply
    ensure_namespace
    ensure_tenant_isolation
    ensure_object_storage      ← new
    helm_upgrade_install
```

### D2. Credentials are written to a Secret directly, not passed as Helm values

The reconciler logs the fully merged values dict at INFO on every apply, and Helm persists the
values of every release into a `sh.helm.release.v1.*` Secret in the tenant's own namespace. A
credential routed through values is therefore written to the log aggregator and to a
tenant-namespace object on every reconcile, neither of which is treated as a credential store.

Only references travel through values: `caelus.objectStorage.{enabled,bucket,endpoint,region,
secretName}`. The chart does `envFrom: secretRef`. The Secret is applied before Helm runs, and
is destroyed with the namespace on delete, so it needs no separate cleanup path.

*Alternative considered:* passing the credential as a value and redacting the log line.
Rejected — it leaves the Helm release Secret, and a redaction list is a thing to forget.

### D3. A global alias `dep-<deployment-id>`, not a key-local alias

This decision was made, reversed, and is recorded with its reversal because the reasoning is
the point.

Garage supports **key-local aliases**: a bucket name scoped to one access key, so every tenant
could call their bucket `data` with no global namespace at all. That was the initial design,
justified as isolation-by-construction — no string a tenant could send would name another
tenant's bucket.

**That justification was false.** Garage's S3 API resolves a bucket by its raw internal
identifier as well as by alias, so any bucket is addressable by any caller who learns its
identifier. Access was still denied, but by the **permission grant**, not by the name. Once
that was established, key-local aliases were buying nothing that a random UUID does not
already buy, and they cost three things:

1. A local alias is deleted with its key. After the delete reconcile revokes access, the
   bucket becomes anonymous — precisely when reclamation needs to identify it. Recovering the
   association would require storing the bucket id on the deployment row.
2. Every deployment's objects would sit at the same URL path (`/data/…`), distinguished only
   by the credential in the query string. Attributable only by decoding it, and a cache keyed
   on path alone would confuse two tenants' objects.
3. Existence checks during provisioning need a key lookup followed by a walk of its buckets,
   rather than a direct lookup by name.

Naming the bucket `dep-<deployment-id>` as a **global** alias fixes all three. The deployment
id is a `uuid4` primary key: immutable, unique, unguessable, never reused, and already the
join key used everywhere else. The bucket becomes self-describing, so **no database column is
needed** — an earlier draft's `garage_bucket_id` on the deployment row is unnecessary.

The `dep-` prefix makes the selector explicit. Tooling asks "does this alias start with
`dep-`", not "does this string happen to parse as a UUID", which keeps the shared namespace
safe for anything added later.

*Cost accepted:* the deployment id appears in tenant-facing URLs. It is not a secret. It is
opaque, it reveals nothing about the owning user, and it is already the identifier the API and
CLI use.

### D4. Isolation rests on the permission grant, and the spec says so

Given D3, the honest statement is that two deployments are isolated because each key holds a
read+write grant on exactly one bucket. Name unguessability is defense in depth, not the
control. `deployment-object-storage` states this explicitly so that a future reader does not
re-derive the false version.

Two supporting properties, both verified: `ListBuckets` on a tenant key returns only its own
bucket, so other deployments' identifiers are not discoverable through the S3 API at all; and
addressing another bucket by either its alias or its raw identifier returns `AccessDenied`.

One consequence encoded as a naming rule: Garage distinguishes "exists but forbidden"
(`AccessDenied`) from "does not exist" (`NoSuchBucket`), so a bucket name is an existence
oracle. Worthless against a UUID, not worthless against `<user>-<product>` — hence the spec
forbids a guessable scheme rather than merely preferring the current one.

### D5. Quotas are enforced by Garage, and are fail-closed

`UpdateBucket` takes `quotas: {maxSize, maxObjects}`, so the cap is enforced at write time by
the store. No usage accounting, no reaper for overage, no billing surprise. `storage_bytes`
already exists on the plan template and is already populated for the `custom` product, so no
new field and no migration.

Two details that are easy to get wrong:

- The store requires `maxSize` and `maxObjects` to be set together or both cleared; one cannot
  be changed alone. `maxObjects` therefore needs a deliberate value, not `null` — millions of
  tiny objects would bloat the store's metadata volume, which is separately sized and small.
- `plan-storage-enforcement` treats an absent quota as "the chart falls back to its own
  default", which is safe because chart defaults are platform-written and bounded. Inheriting
  that here would make an absent quota mean an unbounded bucket on a shared 20 GiB volume.

**There is no platform default quota.** Every plan declares a storage allowance, so a
storage-enabled deployment always has one to read; a quota that cannot be resolved is a bug or
a misconfigured plan, and provisioning fails loudly rather than inventing an allowance no plan
authorized. A default would be a second, silent source of truth for a limit that is supposed
to come from the plan.

`PlanTemplateVersion.storage_bytes` is nullable in the schema today and is being made
non-nullable separately. This design does not depend on that migration: the resolution is
fail-closed in code, so it behaves correctly before and after. Verified against dev at design
time — zero live deployments lack a subscription, and the six plan rows with a null or zero
allowance all belong to products that do not enable object storage, so none of them reach this
path.

The same `UpdateBucket` call also sets **permissive `corsRules`**, so browser-direct uploads
work without the tenant doing anything. This is not a second round trip — `corsRules` is a
sibling key of `quotas` in one request.

Without a CORS rule, Garage answers a preflight `OPTIONS` with **403**, and a preflight must be
2xx or the browser abandons the request. Garage already emits `Access-Control-Allow-Origin: *`
on that 403, so the missing piece is the status, not the header — which is why this cannot be
fixed by injecting a header at the edge, and why doing so would also duplicate a header Garage
sends itself (browsers reject a response carrying two).

`*` is safe here because every request is authenticated by signature and there is no ambient
authority: no cookies, no session, and `*` cannot be combined with
`Access-Control-Allow-Credentials`. A caller still needs a valid presigned URL or signing key,
and CORS was never what stopped one that had it.

`ExposeHeader` must include `ETag`. Multipart uploads read the per-part ETag and CORS hides it
by default; omitting it fails silently in the browser.

*Alternative considered:* CORS middleware on the shared `tf/deps` Ingress, which Traefik can do
(its Headers middleware terminates preflights rather than forwarding them). Rejected — it is
equally invisible to tenants, but it applies to the artifact buckets too, risks the duplicate
header above, forecloses per-tenant origins, and puts a load-bearing rule in shared edge infra
to save one JSON key.

### D6. Deletion revokes synchronously and delegates reclamation; no reaper

`DeleteBucket` refuses a non-empty bucket, and enumerating an unbounded, tenant-controlled
object set inside the delete reconcile's fixed budget is not viable. So:

```
DeleteKey                                             revoke FIRST — synchronous and total
    └─ bucket keeps its dep-<id> alias, reachable by no credential
UpdateBucket {lifecycleRules: [Expiration: N days]}   admin token still works on a keyless bucket
       └─ Garage drains it on its own schedule
```

**Revocation comes first, deliberately.** A read+write key can call
`PutBucketLifecycleConfiguration` on its own bucket — that operation rides along with `write`
and Garage offers no finer grant to withhold it — and it *replaces* the whole configuration.
Setting the TTL before revoking would leave a window in which the tenant's still-live key could
strip it back off. Revoking first closes that window entirely.

Both orders have a crash failure mode and this one fails in the better direction: crashing
after `DeleteKey` leaves a bucket that never drains (a storage leak, converges on retry),
whereas crashing after `UpdateBucket` leaves a tenant holding live credentials to a deployment
they just deleted.

This is the same argument the existing bucket-provisioning capability already makes for the
artifact buckets: reclamation as a property of the bucket cannot be forgotten by a caller or
lost in a refactor.

Deleting the drained bucket is deliberately **not** in scope. An empty bucket is metadata
only, and its alias names the deployment, so a later sweep is a join against the deployments
table. Noting for whoever writes it: that makes the reaper a task needing a database session —
it cannot be a standalone CronJob holding only an admin token.

The window is **one day**, Garage's minimum granularity. It is chosen for prompt reclamation of
a constrained shared volume, and is explicitly *not* an undo for an accidental delete —
recovery of deleted tenant data relies on backups. Objects that have not yet expired are
technically still readable by an operator who grants a fresh key onto `dep-<id>`, but nothing
should be designed around that.

### D7. The public endpoint, and no network policy change

Tenant pods reach `https://blob.freepod.eu` today (verified). The path hairpins through the
router, HAProxy and Traefik rather than going direct to the in-cluster Service, which is
blocked by the baseline egress rules. Using the public endpoint means:

- **no NetworkPolicy change**, so no fleet-wide re-apply and no new hole in tenant isolation;
- one endpoint value that works identically in-pod and in a browser, which is what makes
  presigned URLs work without publishing a second internal endpoint.

*Alternative considered:* punching an egress rule to the in-cluster Service and publishing an
internal endpoint. Rejected for now — it is measurably faster but forces two endpoint values
(the internal one cannot appear in a presigned URL a browser will use) or split-horizon DNS
plus in-cluster TLS. Revisit if the hairpin proves to be a bottleneck.

Addressing is path-style, because `root_domain` is deliberately unset — vhost-style bucket
hostnames are two labels deep and fall outside the `*.freepod.eu` wildcard certificate.
botocore selects path style automatically for a custom endpoint; some SDKs do not, and that
is a documentation obligation rather than a design change (see Risks).

### D8. Opt-in on the product template, not on the deployment

The flag lives at `template.system_values.objectStorage.enabled` in the product's catalog
entry, and is a **first-class property of the chart's own `values.schema.json`**.

Two false starts are recorded because each taught something:

1. A top-level `object_storage` key that the chart's schema did not declare. Rejected outright
   by `helm upgrade` — `additional properties 'object_storage' not allowed` — because
   `system_values` is not a product-metadata bag: it *is* the chart's default Helm values,
   passed verbatim. Anything declared there must satisfy the chart's schema.
2. Moving it under `caelus`, whose `additionalProperties: true` makes it accepted by every
   chart without a schema bump. It worked, but it is a category error: `caelus` is for values
   the reconciler injects **per deployment**, and this is a static product declaration,
   identical across every deployment of the product. Being schema-open is not a reason to put
   something there.

So it is an ordinary system value, alongside `registry`, `placeholderImage` and
`containerPort` — chart inputs the platform sets and a tenant cannot, because they are absent
from the tenant-facing `values_schema`. A chart that consumes object storage is already being
edited to add the `envFrom` block, so declaring one more schema property costs nothing.

The per-deployment references stay under `caelus.objectStorage.*` (design D2). The split is
deliberate: the toggle is what the product declares, the references are what the platform
injected, and keeping them apart means "what did the platform inject?" is still answerable at
a glance.

*Alternative considered:* a tenant-facing toggle. Rejected — it adds a form field and a
user-values schema change to save provisioning one key and one empty bucket, which cost
essentially nothing.

### D9. Terraform mints a scoped, non-expiring admin token

`CreateAdminToken` accepts `neverExpires: true` with an explicit scope list, so `tf/deps`
mints one limited to the bucket and key operations provisioning performs and outputs it for
`tf/app` through the same gitignored handoff already used for the S3 credentials. The API
never holds the master token.

The scope must exclude `CreateAdminToken` and `UpdateAdminToken`, which Garage's own
documentation flags as trivially equivalent to unrestricted access.

## Risks / Trade-offs

- **The provisioning credential can read any key's secret.** → Inherent to automated
  provisioning; cannot be designed away. Bounded by D9 (no cluster status, no layout changes,
  no token minting) and stated in the spec as an accepted risk rather than implied away.

- **Sum of quotas can exceed the 20 GiB data volume,** which is shared with the artifact
  buckets. → Garage enforces per bucket and will not prevent oversubscription. Mitigated only
  by the default quota being small and by operator attention. This is the practical limit on
  how many storage-enabled deployments the instance holds, and it should be watched on a node
  with a history of disk pressure.

- **`AllowBucketKey` cannot narrow a grant.** Flags set true activate; flags set false are
  ignored, not revoked — Garage documents this as an unconventional semantic. → Code that
  tries to correct an over-broad grant by passing false will silently do nothing. Revocation
  is `DenyBucketKey`. Provisioning must only ever widen, never assume it can narrow.

- **Not every SDK selects path style automatically.** botocore does; JavaScript's v3 client
  defaults to virtual-host addressing with a custom endpoint and needs one flag. → A
  documentation obligation for tenants, not a platform change. Publishing a second endpoint or
  enabling vhost addressing would both be worse (per-bucket certificates and DNS).

- **The hairpin path puts every tenant object byte through HAProxy and Traefik.** → It is
  LAN-local rather than uplink-bound, and it costs no new network policy. If it becomes a
  bottleneck, D7 records the alternative and what it would cost.

- **Public static hosting from a bucket is closed off.** Garage's website access is
  unauthenticated and resolved by Host header, which requires a global alias *and* vhost-style
  addressing *and* a per-bucket certificate. → Not a regression (it was never available), but
  worth knowing the door is shut before someone proposes "serve my `dist/` from the bucket".

- **A tenant can rewrite the lifecycle rules on their own bucket.** `PutBucketLifecycle` is
  granted by `write` and cannot be withheld separately. → Never rely on a lifecycle rule as a
  platform control while the tenant's key is live. Quotas are the control that cannot be
  touched; the delete-time TTL is safe only because D6 revokes the key first.

- **Interrupted provisioning leaves an orphan key.** → Each step is verified independently
  (see the spec's idempotency requirement), so the next reconcile completes the rest rather
  than concluding it is done.

- **Self-service bucket creation would produce a second bucket shape.** Garage's
  `KeyPerm.createBucket` lets a key create its own buckets, which receive local aliases and no
  global one. → Not enabled by this change. Flagged so that a future reaper is not written
  assuming every bucket has a `dep-` alias.

## Migration Plan

1. `tf/deps` — mint the scoped admin token, output it. No effect on anything until consumed.
2. `tf/app` — pass the token and the endpoint into the API's configuration. Still inert:
   nothing reads them until step 4.
3. Publish the updated `custom` chart under a new chart version. Existing releases are pinned
   to their current version and are unaffected.
4. Ship the reconciler change, then flip `object_storage.enabled` in `products/catalog/custom.yaml`
   and roll out. The first reconcile of each existing `custom` deployment provisions its
   bucket and rolls its pod with the new environment.

Rollback is per-step and does not strand data: reverting step 4 stops provisioning new
buckets and drops the environment variables from pods on the next reconcile; existing buckets
and keys are left intact and reachable, and can be removed by hand if the change is abandoned.

## Open Questions

- The `maxObjects` companion cap, which the store requires to be set alongside `maxSize`.
  Plans declare a byte allowance but not an object count, so this one value is necessarily a
  platform constant rather than plan-derived. It exists to protect the separately-sized
  metadata volume from a very large number of very small objects, not to constrain normal use,
  so it can be raised on evidence without touching the specs.

*Settled during planning:* there is no default quota (see D5), and the delete expiry window is
one day (see D6).
