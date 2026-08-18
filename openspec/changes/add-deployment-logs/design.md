## Context

See `proposal.md` § Why for motivation. What follows is the state that shapes the approach.

**The collection half already exists.** `tf/deps/loki/` runs Loki 6.41.1 in `SingleBinary` mode on
a 10 GiB filesystem volume with schema `v13`, and a Promtail 6.17.0 DaemonSet whose
`kubernetes_sd_configs` use `role: pod` with **no namespace restriction**. Its `relabel_configs`
already emit the stream labels this change needs:

| Loki stream label  | Source                       | Corresponds to                                  |
|--------------------|------------------------------|-------------------------------------------------|
| `namespace`        | pod namespace                | `deployment.namespace` (per-**user** namespace) |
| `instance`         | `app.kubernetes.io/instance` | `deployment.name` (the Helm release name)       |
| `app`              | `app.kubernetes.io/name`     | `custom`                                        |
| `pod`, `container` | pod / container name         | —                                               |

`{namespace="…", instance="…"}` already selects exactly one deployment's logs, live and
historical, including pods deleted minutes ago. No new collection infrastructure is required.

**Facts established against the codebase, each load-bearing below:**

| Question                                                  | Result                                                                                                                                                                                                                                                           |
|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Does the API have a Kubernetes client?                    | **No.** `provisioner.py`, `build_jobs.py` and `network_policy.py` shell out to `kubectl` via `app/proc.py`, whose only primitive is `subprocess.run(capture_output=True)`. It cannot express a follow.                                                           |
| How many API workers?                                     | **One.** `api/Dockerfile:29` — `uvicorn … --workers 1`. Every endpoint is a sync `def` on a 40-thread pool.                                                                                                                                                      |
| Precedent for id-labeled pods?                            | **Yes.** `build_jobs.py:28` — `BUILD_ID_LABEL = "caelus.dev/build-id"`: mint an id, stamp the pod, select logs by it.                                                                                                                                            |
| Can a tenant forge a system value?                        | **No.** `merge_values_scoped` applies system overrides last, which the chart's `caelus.owner.id` check already rests on.                                                                                                                                         |
| Do reconciles serialize per deployment?                   | **Yes.** `enqueue_job` rejects a second queued-or-running job (`jobs.py:66-70`), and `update_deployment` requires status `ready`/`error`.                                                                                                                        |
| Are failed reconciles retried?                            | **No.** `mark_job_failed` is terminal. Only a lease-expired *running* job is reclaimed — a worker that died mid-flight.                                                                                                                                          |
| Which paths enqueue an apply?                             | `deployments.py:270` (create), `:435` (update), and `webhooks.py:199`, which only unblocks a `pending` deployment created earlier. All trace to a POST or PUT.                                                                                                   |
| Is `--atomic` in use?                                     | **Yes.** `reconcile.py:141-142` — `atomic=True, wait=True`. But see D15: until `minReadySeconds` was added, `--wait` could not *detect* an application that crashed on startup, so `--atomic` never fired for the case this change exists to serve.               |
| Does Loki enforce retention?                              | **No** — but not for the stated reason. The compactor already runs in-process (`-target=all`; `/services` reports `compactor => Running`) and `compactor.replicas = 0` is inert in `SingleBinary` mode. What is missing is `compactor.retention_enabled` and `limits_config.retention_period`. Enabling the first without `compactor.delete_request_store` is a hard `CONFIG ERROR` on Loki 3.5.5.                                                                                                                                                                  |
| What kills an idle connection first?                      | **The client, at 30s** (`cli/src/freepod/config.py:36`), applied per read on a stream. Behind it the homelab HAProxy, whose timeouts are **not in this repo**. Traefik takes defaults — `writeTimeout: 0`, `idleTimeout: 180s` — and is the least likely killer. |
| Can a new `caelus.*` value reach a chart that ignores it? | **Yes, by design.** Every curated chart sets `caelus.additionalProperties: true`; `mattermost` has no schema at all.                                                                                                                                             |

## Goals / Non-Goals

**Goals:** let a tenant read their running application's output from the CLI; make a *failed*
rollout's output retrievable after `--atomic` deleted the pods; attribute every line to exactly
one release even while two pods write concurrently; add no dependency to the client package.

**Non-Goals:**

- Log search, level filtering or structured-log parsing. LogQL is never exposed to a client.
- Retention as a product promise. It is configured because it must be, not because it is sold.
- `freepod exec` or any interactive session — the one thing that would justify a WebSocket.
- Streaming logs *during* `freepod deploy`; see D12.
- Surfacing Kubernetes Events or pod status. Helm's failure output already covers image-pull, OOM
  and crash-loop, and reaches the user through `last_error`.
- Release labeling for the seven curated charts, and any `_lib` helper for it; see D8.
- Reworking `freepod history`, which infers the running build by matching
  `user_values_json["image"]` — the best available before this change. A natural follow-up.
- Removing `deployment.applied_template_id` and `deployment.generation`, both made redundant by
  the ledger. `applied_template_id` has live UI consumers; removal is a separate change.
- Any change to `--atomic`, to the provisioner, or to tenant network isolation.

## Data model

```sql
-- Named deployment_release, not release: RELEASE is a SQL keyword (SAVEPOINT
-- syntax) and this repo runs SQLite in tests and Postgres in production.
-- Matches the existing deployment_reconcile_job naming.
CREATE TABLE deployment_release (
    id             UUID        PRIMARY KEY,          -- uuid4; also the pod label value
    number         INTEGER     NOT NULL,             -- per-deployment, 1..N; the human handle
    deployment_id  UUID        NOT NULL REFERENCES deployment(id) ON DELETE CASCADE,
    template_id    INTEGER     NOT NULL REFERENCES product_template_version(id),
    build_id       UUID        NULL     REFERENCES build(id),
    values_json    JSON        NULL,                 -- user-values snapshot, not merged values
    created_at     TIMESTAMPTZ NOT NULL,             -- written by the API ─┐
    started_at     TIMESTAMPTZ NULL,                 -- ─┐                  │ request txn
    ended_at       TIMESTAMPTZ NULL,                 --  │ written by       │
    error          TEXT        NULL,                 --  │ the reconciler   │
    helm_revision  INTEGER     NULL,                 -- ─┘                  │
    CONSTRAINT uq_release_number UNIQUE (deployment_id, number)
);
CREATE INDEX ix_release_deployment_id ON deployment_release (deployment_id);
CREATE INDEX ix_release_build_id      ON deployment_release (build_id);

ALTER TABLE deployment
    -- NOT NULL: every deployment is created together with its first release, and
    -- the migration backfills one for every pre-existing deployment. DEFERRABLE
    -- because the reference is mutual -- see below.
    ADD COLUMN desired_release_id UUID NOT NULL
        REFERENCES deployment_release(id) DEFERRABLE INITIALLY DEFERRED,
    -- Nullable: a deployment has no applied release until a rollout succeeds.
    ADD COLUMN applied_release_id UUID NULL
        REFERENCES deployment_release(id) DEFERRABLE INITIALLY DEFERRED;
```

```
        build ──0..1──┐
                      │                    ┌── desired_release_id ──┐
   deployment ──1..N──┴─► deployment_release ◄─┤                    │
        ▲                                      └── applied_release_id
        └──────────────────────────────────────────┘
```

`deployment_id` is a not-null many-to-one. `desired_release_id` is not-null one-to-one:
a deployment without a release it wants to be running is not a state the system has.
`applied_release_id` is nullable, because a deployment that has never rolled out successfully —
awaiting payment, or whose first rollout failed — is running nothing.

The reference is **mutual**, and under immediate constraints neither row could be inserted first:

```
  deployment first  →  desired_release_id NOT NULL violated
  release first     →  deployment_id FK violated (deployment absent)
```

Both primary keys are `uuid4` generated in Python, so both ids are known before either INSERT.
The deployment is therefore inserted with `desired_release_id` already set, the release second,
and the constraint is `DEFERRABLE INITIALLY DEFERRED` so it is checked at commit. Deferred
`NO ACTION` also replaces `ON DELETE SET NULL`, which would contradict `NOT NULL`; a hard delete
drops both rows in the same transaction and the deferred check sees neither.

**`api/app/db.py` never sets `PRAGMA foreign_keys=ON`, so SQLite enforces no foreign keys.**
Postgres enforces all of this; the test suite does not. An insert-order mistake passes green
locally and fails in production, so the ordering wants an explicit test against Postgres.

Alembic creates both tables before adding the constraints, for the same circularity reason.

**There is no `image` column.** For `custom` the image lives in `values_json`, and `build_id`
reaches it too. **There is no `status` column**; see D3.

## Decisions

### D1. Loki is the read path, not the Kubernetes API

`kubectl logs` cannot answer the case that motivates this change: with `--atomic`, a rollout whose
pods crash on startup is rolled back and its pods deleted, so reading from the pod races the thing
it wants to observe. Promtail shipped those lines as they were written, seconds earlier, so a
query issued *after* the rollback still finds them.

```
  reconciler applies release R7
        ├─► helm upgrade --atomic --wait
        │      pod(R7) starts ─► crashes ─► promtail ─► Loki {…, release_id="R7"}  ← durable
        │      helm times out, rolls back, pod(R7) deleted
        └─◄ returns failure ─► query Loki for release_id=R7 ─► the crash output
```

It also avoids a process per viewer: `app/proc.py` cannot express a follow at all, so `kubectl`
would mean either a new asyncio-subprocess mechanism or the first direct apiserver client in the
codebase. Loki is an HTTP query over the `httpx` that `api/` already has.

### D2. A release is created by the request that asks for it

`POST` and `PUT /deployments` create the `deployment_release` row **in the same transaction** as
the deployment write, and set `deployment.desired_release_id` to it. The reconciler creates
nothing; it reads that pointer, applies it, records the outcome, and on success sets
`applied_release_id`.

This is what makes the rest fall out. The release id exists before Helm runs, so it can be stamped
on the pod template. The build reference lands directly on the release, so nothing build-shaped
has to travel through the deployment row or through Helm values (D4). And a redeploy with
byte-identical values is still a distinct release, because identity comes from the row rather than
from the content.

Every apply-reconcile has a desired release: the three enqueue sites are create, update, and the
Mollie webhook, and the webhook only unblocks a `pending` deployment whose release the original
POST already created.

The reconciler remains **level-triggered** — it reads `deployment.desired_release_id` when it runs,
not what was true when the request landed. `update_deployment`'s status guard
(`WHERE status IN (ready, error)`) already prevents a second intent stacking on an in-flight one.

### D3. Rows are written once, by two actors; status derives, liveness is a pointer

No column is ever revised. The API writes identity and intent at request time; the reconciler
writes outcome later. `started_at` is write-if-null, so a lease-reclaim retry after a worker died
mid-Helm records when work *first* began — the job's `attempt` counter records that there was more
than one. `ended_at` and `error` cannot be rewritten because a failed reconcile is terminal
(`mark_job_failed` never re-enqueues) and a reclaimed job is one that never wrote them.

**Status is derived, never stored:**

```
  started_at IS NULL                      → queued        (incl. awaiting payment)
  started_at set, ended_at NULL           → in flight     (abandoned once stale)
  ended_at set, error set                 → failed
  ended_at set, error NULL                → succeeded
  id = deployment.applied_release_id      → live
```

A stored status enum would need a transition written when *something else* changes — notably
`superseded → live` when an atomic rollback restores an earlier release, by code that is not
watching. Deriving it removes that class of bug entirely.

**Liveness is the opposite case and is stored.** `applied_release_id` is written by the reconciler
in the same transaction as `deployment.status`, recording an action it has just completed rather
than tracking a system it observes. On failure it is left unchanged, which is *correct* rather than
a missed update: `--atomic` has already restored the release it still names. It costs one column
and no subquery, where deriving liveness would cost a query per row on a listing.

### D4. The build belongs to the release — not to the deployment, not to Helm values

`POST`/`PUT` accept an optional `build_id` in the request body. It is written to
`deployment_release.build_id` and is **not** persisted on `DeploymentORM`. A deployment therefore
has no build-shaped column, which matters because builds exist only for developer applications
while deployments are general.

It is also never passed as a Helm value. Values carry what a chart renders and nothing else —
`caelus.releaseId` qualifies because `custom.podLabels` renders it as a pod label; a build
reference never would.

Validation happens at the write, where a 400 is still available, and **ownership is the only
condition**:

```
  build_id absent   →  accepted; the release records no build
  build_id present  →  the build must exist and build.user_id must be the caller
```

Ownership stops a client claiming another user's build as provenance — the same concern the
chart's `caelus.owner.id` assertion answers on the image path.

**Nothing is validated against the deployment's values.** An earlier draft required the named
build to have produced exactly the effective `image`, and required a build whenever an image was
present. Both were dropped deliberately. `image` is a value of the `custom` chart, not a platform
concept: most products build nothing, another chart may name the field differently or carry
several, and a build or release may come to reference more than one image. Tying the ledger to one
chart's value key would make the release record an artifact of `custom`'s schema and would have to
be unpicked the first time either model grows. The literal rule also had an immediate cost:
`ui/src/api/endpoints.ts`'s `updateDeployment` sends no build reference, so the admin UI's
template-upgrade button — which re-sends the deployment's stored values, image included — would
have been rejected for every `custom` deployment, as would any write against a deployment created
before this change.

The image reference could not have identified the build on its own in any case: it is
`{user_id}@{digest}` and digests are content-addressed, so image → build is many-to-one.

### D5. The release id is stamped on the pod template before any pod exists

The reconciler injects `deployment.desired_release_id` as the `caelus.releaseId` system value; the
chart renders it as the `caelus.dev/release-id` pod label. Because the id exists before any pod
does, every pod of that release carries it — including one created hours later by a node eviction
or a kubelet restart, with nobody watching. Timestamps and pod names cannot do this: both are
learned by observation and both mislabel a pod born after the observer stopped looking.

A `uuid4` is a valid label value: 36 characters against a 63-character limit, `[0-9a-f-]`, starting
and ending alphanumeric. It arrives as a system override under `caelus.*`, so
`merge_values_scoped`'s system-last precedence prevents a tenant claiming another release's id.

**Consequence, accepted:** a fresh id changes the pod template hash on every apply, so a redeploy
with identical values genuinely cycles pods rather than being a Helm no-op. This matches Heroku,
Railway and Fly, and at `replicas: 1` it means every redeploy costs a brief interruption.

### D6. `release_id` is a Loki stream label, not structured metadata

`pod` is already a stream label, and the release id is constant within a pod — it is functionally
dependent on a label that already exists, so promoting it creates **no new streams**. It widens
each series by one label rather than multiplying them, and makes a release-pinned query an index
lookup. One `relabel_config`, the same mechanism already used for `instance`.

The structured-metadata rule applies to fields that vary *within* a stream, which is exactly where
this repo already applies it: the Traefik stage promotes `remote_addr`, `path` and `duration`
because those would multiply streams without bound.

### D7. The label goes on the pod template only, never a selector

`custom.selectorLabels` is included in three places and only one may carry a per-release value:

```
  deployment.yaml:16 → spec.selector.matchLabels      ← IMMUTABLE; second apply fails
  deployment.yaml:20 → spec.template.metadata.labels  ← the label belongs here
  service.yaml:10    → Service spec.selector          ← would blackhole traffic mid-rollout
```

So the chart gains a separate `custom.podLabels` helper, used at the pod template and nowhere else.

### D8. Only the `custom` chart renders the label; the value is offered to all

The reconciler injects `caelus.releaseId` for every product with no per-product condition;
rendering it is each chart's decision. Only `custom` renders it here, across 8 charts and 14 pod
templates.

The need is specific to tenant-supplied code — a curated deployment runs an image the platform
pinned. Universal labeling is not obviously desirable either: immich's `postgres`, `valkey` and
`machine-learning` would acquire release ids for database and cache output, which the existing
`app` and `container` labels already separate. And degradation is clean: a pod with no release
label collects exactly as before, so a curated deployment's logs stay fully readable at
`{namespace, instance}` granularity — only release pinning is unavailable, and the API reports
that rather than returning an empty stream.

Adopting it later in any chart is a chart-only change: the value is already supplied and the Loki
contract is identical. A `_lib` helper would centralize the definition but not the call, so it is
worth adding when a second chart wants it, not before.

### D9. Server-Sent Events — not a WebSocket, and not raw chunked text

The traffic is unidirectional, so a WebSocket buys a return channel nothing would use, at the cost
of a client dependency (`cli/pyproject.toml` is `click`, `httpx`, `pathspec`; `httpx` has no
WebSocket support) and of reimplementing `ApiClient._request`'s refresh-at-most-once contract for
one endpoint.

But a long-lived stream must survive silence, and every hop treats a quiet connection as dead:

```
  freepod CLI ─────► homelab HAProxy ─────► k3s Traefik ─────► caelus-api
  httpx read: 30s    timeout client/server   writeTimeout: 0
  (config.py:36)     NOT in this repo        idleTimeout: 180s
  breaks first       unknown, commonly 30–60s
```

Plus NAT and firewalls outside the platform. A bare `text/plain` body has no heartbeat and every
improvisation is bad — a blank line pollutes output that must survive `freepod log > app.log`, a
zero-length chunk terminates the response. SSE carries a heartbeat as a first-class idiom (a line
beginning with `:` is a comment clients must ignore) and settles three more things plain text
cannot express in band: per-line release attribution, `event: error` before a mid-stream close,
and `id:` for resumption. It costs nothing that made chunked HTTP attractive — still plain HTTP,
still `iter_lines()`, still zero new client dependencies, still `curl`-able.

Loki's own `/loki/api/v1/tail` is a WebSocket; the API terminates it and re-emits SSE. Polling
`/query_range` with an advancing `start` is an acceptable and simpler alternative server-side.

SSE's UTF-8 requirement costs nothing: Loki's HTTP API carries log lines as JSON strings, so the
collection pipeline normalized invalid UTF-8 long before the API reads them. There is no
byte-accurate original left to preserve, unlike `build_jobs.read_log`.

### D10. The resume point is the line's timestamp

Every event carries its line's Loki nanosecond timestamp as an explicit field, and that field is
also the resume point. There is no separate cursor token; two representations of one fact drift.
The timestamp earns its place independently — many applications do not timestamp their own output,
and the store holds the only record of when a line was written.

```
  first connect   direction=backward, limit=N   ← newest N, reversed before emitting
  resume          start=<timestamp> INCLUSIVE, direction=forward   ← not Loki's default
```

Inclusive resume **is** the mechanism. Every undelivered line is at or after the cursor, so it
cannot leave a gap; its only cost is re-delivering lines sharing the boundary nanosecond, normally
one. Resuming at `+1ns` would drop them. Resumption is therefore **at-least-once**: a duplicated
line is cosmetic, a missing one is the one being looked for.

**The timestamp travels as a JSON string, never a number.** A nanosecond value is ~1.76×10¹⁸
against a `Number.MAX_SAFE_INTEGER` of ~9.01×10¹⁵, so a numeric encoding is silently rounded by any
JavaScript consumer — corrupting both the displayed time and the resume point with no error
raised. `ui/` makes that concrete. The same value is mirrored into SSE `id:` so a stock
`EventSource` consumer gets `Last-Event-ID` for free; the contract names the timestamp field.

Keepalives carry no cursor: they are comments describing the connection, not the log, and advancing
from one would permanently skip a line arriving late with an earlier timestamp.

The client treats the timestamp as a value it may render but SHALL NOT reason about — it stores the
last one and returns it. The API parses and validates it as a `uint64` before it becomes `start`;
it is the only client-supplied value reaching the query (D14's sole exception), and the client
knowing it legitimately does not make it trusted.

`freepod log -f` follows the **deployment**, not a release — Heroku's semantics. The selector names
no release, so a rollout's new pods are picked up and the handover appears live.

### D11. Rendering the timestamp is the client's choice, defaulting off

`freepod log --timestamps` / `-t`, off by default, matching `kubectl logs`: many applications
already timestamp their output and a second prefix yields a line with two dates. The default must
not differ between followed and bounded reads — differently shaped lines per mode is exactly what a
downstream pipe depends on not happening. Where both optional prefixes are enabled they compose as
`<timestamp> <release> <line>`.

### D12. The deploy path reports failures; it does not stream

`--atomic` makes the deploy request block for the whole rollout, so streaming would need a second
concurrent request against a pod whose start and lifetime the client cannot predict, and on the
common successful deploy it would dump startup noise into a terminal that wanted one line.

Instead the reconciler's `except` branch queries Loki for the failed release and attaches the tail
to `last_error` — possible only because the lines outlive the rolled-back pod (D1). Deploy stays a
single blocking request, success exits quietly, failure needs no second command.

`AdapterCommandError._build_message` truncates detail at 400 characters (`app/proc.py`) and that
string becomes `last_error`; the failure tail must not be eaten by it.

### D13. The endpoint is `async def`

Every existing endpoint is a sync `def` on Starlette's 40-thread pool, behind `--workers 1`. A
blocking stream would hold a thread for the life of the connection, so 40 readers would stop the
API answering anything — including `GET /api/me`. The endpoint must also not hold the sync
`get_session` open across the stream: authorize, release the session, then stream. A per-user
concurrent-stream cap and an idle timeout bound what one tenant can do to the single worker.

### D14. LogQL is constructed server-side, always

Loki runs `auth_enabled = false` — one tenant holding every user's logs and the platform's own,
including `caelus-api`, which logs full Helm values at INFO (`provisioner.py`). A client-influenced
selector would be a cross-tenant read and a platform-secret read at once. The selector is built
from the deployment row fetched under `require_self`; no client string is interpolated. A
deployment belonging to another user answers 404, matching the build endpoint.

### D15. `--atomic` only helps if Helm can tell the rollout failed

Verified against dev, after the rest of this change was in place: deploying an image that exits on
startup produced `Deployed. Live at …`, a release recorded with `error = NULL` and marked
`applied_release_id`, and a pod in `CrashLoopBackOff` behind a deployment the platform reported as
`ready`. The Deployment itself said
`Available: False — Deployment does not have minimum availability`.

The cause is not `--atomic` and not the reconciler. The `custom` chart declares **no readiness
probe**, so a container is Ready the instant it runs. A container that starts, prints and dies is
therefore briefly Ready, Kubernetes marks the new ReplicaSet available, and `helm upgrade --wait`
returns success. No exception is raised, so the reconciler's `except` branch — and with it the
failure tail of D12 — is never reached.

`minReadySeconds: 10` on the pod template closes it: a pod must hold Ready for ten seconds before
counting as available, so a process that exits soon after starting fails the rollout and `--atomic`
does what the rest of this design assumes.

It is a floor, not a health check, and deliberately so. Binding `$PORT` is a convention most
applications follow rather than a requirement — headless workloads are a stated future use and
would have nothing to probe — so a TCP or HTTP readiness probe would refuse to deploy applications
the platform means to support. An application that stays alive without ever serving anything still
passes. **Liveness wants designing on its own terms and is not attempted here.**

This is a pre-existing platform defect rather than one this change introduces, but every claim
about `--atomic` in D1 and D12 depends on it, so it is fixed here rather than noted and left.

## Risks / Trade-offs

- **Loki becomes a user-facing dependency** — `SingleBinary`, `replicas = 1`, filesystem storage,
  no HA. When it is down `freepod log` is down, and the endpoint must say so; the one unacceptable
  outcome is an empty stream, which reads as "your app printed nothing".
- **Retention is now mandatory.** With no compactor and no retention period the 10 GiB volume
  fills and takes the feature with it. Configuring it is part of this change.
- **Promtail is end-of-life** in the Loki 3.x line, superseded by Alloy. This change adds one
  relabel rule and no new capability, but the migration is a known future cost.
- **`tf/deps` is a shared singleton with no workspaces**, so the relabel rule lands in dev and prod
  together and must precede the API emitting the label. Ordering, not breakage.
- **A heartbeat does not survive a buffering proxy.** `X-Accel-Buffering: no` and
  `Cache-Control: no-store` are hints; the only real check is an idle stream against the live edge —
  the same unverified hop as the HAProxy timeout.
- **Log bytes are tenant-controlled and now reach a user's terminal**, which the build path never
  had to consider — terminal escape sequences in output the platform relays.
- **A very fast crash plus a very fast rollback could outrun Promtail**, whose guarantee is "within
  seconds". `--wait` holds a crashing pod for the whole Helm timeout first, so the window is narrow
  and accepted rather than engineered around.
