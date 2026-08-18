## Why

A tenant on the `freepod` CLI has no way to see their application's output. When a `custom`
deployment comes up but misbehaves — an uncaught exception behind a 500, a wrong database
connection string, a config value read from the wrong place — the platform reports the deployment
as `ready` and the user has nothing to look at. The build log covers everything up to the image;
after that the trail goes cold.

The pieces to close this are already deployed, and nobody built them for this purpose. A Promtail
DaemonSet with `role: pod` service discovery and no namespace restriction is already scraping every
tenant pod on every node and shipping to Loki, and its relabel rules already emit `namespace` and
`instance` stream labels corresponding exactly to `deployment.namespace` and `deployment.name`.
Tenant application logs are being collected and stored **today**. What is missing is a way to ask
for them.

Reading from Loki rather than from the pod also settles the harder half. Helm runs with `--atomic`,
so a rollout whose pods crash on startup is rolled back and those pods deleted — the evidence
destroyed before anyone can ask for it. Promtail shipped those lines as they were written, seconds
earlier, so they survive the pod that produced them. A failed deploy's output is retrievable
*because* the read path does not go to the pod.

The one thing the log store cannot answer alone is **which release** a line belongs to. During a
rollout two pods write concurrently and `{namespace, instance}` returns both, interleaved and
unattributable. So this change also introduces a **release**: a record of one rollout, created by
the request that asks for it, whose identifier is stamped on the pod template before any pod exists.

## What Changes

- A new **`deployment_release`** row is created by `POST`/`PUT /deployments`, in the same
  transaction as the deployment write, and recorded as `deployment.desired_release_id`. The
  reconciler creates nothing: it applies that release, records the outcome, and on success sets
  `deployment.applied_release_id`.
- **No release column is ever revised.** The request writes identity and intent; the reconciler
  writes outcome. There is no status enum — status derives from `started_at`, `ended_at` and
  `error`, which removes the `superseded → live` transition an atomic rollback would otherwise
  require someone to notice and write.
- **The build belongs to the release.** `POST`/`PUT` accept an optional `build_id` that lands on
  the release and is never stored on the deployment and never passed to Helm. Builds exist only for
  products that deploy tenant-supplied code; deployments are general, and chart values carry what a
  chart renders. It rides as a plain request field, following `plan_template_id`, which is already
  accepted on create and never persisted on the deployment. Every write validates that the named
  build produced the effective image and belongs to the caller.
- The release's `uuid4` is injected as a system value and rendered by the chart as the
  `caelus.dev/release-id` pod label, reaching Loki as a stream label through one Promtail relabel
  rule. Because the id exists before any pod does, every pod of that release carries it — including
  one created hours later by an eviction, with nobody watching.
- **Only the `custom` chart renders it.** The value is offered to every product and rendering is
  each chart's decision, so the seven curated charts are untouched — 13 of 14 pod templates — and
  their logs stay readable at deployment granularity, without release pinning.
- A new **`GET /api/users/{user_id}/deployments/{deployment_id}/log`** endpoint streams a
  deployment's output from Loki. It follows the application across redeploys by default (Heroku
  semantics) and pins to one release when asked. It is **`async def`** — the first long-lived
  request the API serves, and a blocking stream on the existing 40-thread pool behind
  `--workers 1` would take the whole API down.
- Transport is **Server-Sent Events**, adding no CLI dependency. Not a WebSocket, because the
  traffic is unidirectional and a WebSocket cannot reuse `ApiClient`'s refresh contract; not an
  unframed body, because a long-lived stream must survive an idle application and SSE carries a
  keepalive idiom, per-line release attribution and mid-stream error signaling that plain text
  cannot express in band.
- **Every line carries the time it was written**, since many applications do not timestamp their own
  output and the store holds the only record. That field is also the resume point, so display and
  resumption cannot drift apart. `freepod log --timestamps` renders it, off by default.
- A new **`freepod log`** command streams it: lines to stdout, narration to stderr, reconnecting
  from the last timestamp rather than restarting at the present.
- On a failed apply the reconciler queries Loki for the failed release and attaches the tail to
  `last_error`, so `freepod deploy` reports *why* the application refused to start without a second
  command.
- **Loki gains a retention policy.** It currently has `compactor.replicas = 0` and no
  `limits_config.retention_period`, so nothing is ever deleted from a 10 GiB volume — tolerable for
  incidental operator observability, not once a user-visible feature depends on it.
- **Helm's `--atomic` is unchanged**, and the applied-release contract depends on it: a rollback
  restores the previously applied release, so leaving `applied_release_id` untouched on failure is
  correct rather than a missed update.

## Capabilities

### New Capabilities

- `deployment-release-ledger`: what a release is, how it is created by the request and completed by
  the reconciler, and how status and liveness are answered without revising a field.
- `release-log-labeling`: how a release identifier reaches a log line — system value, pod template
  (never a selector), stream label.
- `deployment-log-api`: the REST contract for reading a deployment's output — transport, resume
  point, keepalives, and the isolation rules that keep one tenant's request from reaching another's
  lines.
- `cli-log`: the `freepod log` command's behavior, output discipline and failure reporting.

### Modified Capabilities

- `pod-log-aggregation`: gains `instance` and `release_id` as a stated contract rather than an
  incidental consequence of shared relabel rules, and gains a retention requirement.

`deployment-network-isolation` is deliberately **not** modified: log collection is a node-local file
read by a DaemonSet, so no traffic leaves the tenant pod and the baseline NetworkPolicy is untouched.

## Impact

- **`api/app/models/core.py`** — the `deployment_release` table plus `desired_release_id` and
  `applied_release_id` on `deployment`, with an Alembic migration. The table is named
  `deployment_release` because RELEASE is a SQL keyword and this repo runs SQLite in tests and
  Postgres in production.
- **`api/app/services/deployments.py`** — create the release in the same transaction as the
  deployment write, accept an optional `build_id`, and enforce the build/image/ownership invariant.
- **`api/app/services/reconcile.py`** — apply the desired release, record its outcome, contribute
  `caelus.releaseId` to system overrides, and set `applied_release_id` on success.
- **`api/app/services/`** — a new Loki query client, a thin transport with no deployment or release
  concepts, following the Garage admin client's precedent.
- **`api/app/api/users.py`** — the streaming endpoint, alongside the existing deployment routes.
- **`api/app/config.py`** — Loki base URL, stream caps, keepalive interval, idle timeout.
- **`products/custom/chart/`** — a `custom.podLabels` helper on the pod template only, plus
  `caelus.releaseId` in `values.yaml` and `values.schema.json`.
- **Not affected: the seven curated charts.** Their pods carry no release label, which Promtail
  already tolerates. Adopting it later is a chart-only change.
- **`cli/`** — the `log` command, plus `freepod deploy` sending the `build_id` alongside the image
  it already sends, and a version bump; the client releases on its own cadence.
- **Migration backfills a release** for every existing non-deleted deployment, which is what lets
  `desired_release_id` be `NOT NULL` — a deployment without a release it wants to be running is not
  a state the system has. `applied_release_id` stays nullable and is backfilled only where
  `applied_template_id` shows something was actually applied.
- **`tf/deps/loki/`** — the relabel rule and a retention policy. This is the shared singleton with
  no workspaces, so it lands in dev and prod together and must precede the API emitting the label.
- **Availability.** Loki becomes a user-facing dependency: `SingleBinary`, `replicas = 1`,
  filesystem storage. The endpoint must fail as a clearly reported platform condition, never as a
  claim that the application produced no output.
- **Every deploy now cycles pods.** A fresh release id changes the pod template hash on every apply,
  so a redeploy with identical values is no longer a Helm no-op. This matches Heroku, Railway and
  Fly; at `replicas: 1` it costs a brief interruption. `custom` only.
