## 1. Terraform: the collection contract

- [ ] 1.1 In `tf/deps/loki/`, add a `relabel_config` promoting the `caelus.dev/release-id` pod label
      to a `release_id` stream label, following the existing `instance` rule. Pods without the label
      must collect exactly as they do now.
- [ ] 1.2 Enable retention: set `limits_config.retention_period` and run the compactor with
      `retention_enabled`. Today it is `compactor.replicas = 0` with no period, so nothing is ever
      deleted from the 10 GiB volume. Pick the period from measured ingest, not a round number.
- [ ] 1.3 Deploy `tf/deps` **before** the API emits the label. It is the shared singleton with no
      workspaces, so this lands in dev and prod together; until it does, release-pinned queries
      return empty.
- [ ] 1.4 Verify on the running cluster that a tenant pod's lines arrive carrying `namespace`,
      `instance` and `release_id`, and record the observed write-to-queryable delay. Section 6
      depends on it being short relative to the Helm timeout.

## 2. The release ledger

- [ ] 2.1 Add the `deployment_release` table and Alembic migration per design § Data model. Name it
      `deployment_release`, **not** `release`: RELEASE is a SQL keyword and this repo runs SQLite in
      tests and Postgres in production. Matches `deployment_reconcile_job`.
- [ ] 2.2 Add `deployment.desired_release_id` **NOT NULL** and `deployment.applied_release_id`
      nullable, both `DEFERRABLE INITIALLY DEFERRED`. Applied stays nullable because a deployment
      that has never rolled out successfully is running nothing. Create both tables before adding
      the constraints — the reference is mutual and the migration will not otherwise order.
- [ ] 2.2a Insert the deployment with `desired_release_id` **already set**, then the release. Both
      PKs are Python-generated `uuid4`, so both ids are known up front; the deferred constraint is
      checked at commit. **`api/app/db.py` never sets `PRAGMA foreign_keys=ON`, so SQLite enforces
      no FKs** — an insert-order mistake passes the test suite and fails on Postgres. Test this
      ordering against Postgres specifically.
- [ ] 2.3 No `status` column and no `image` column. Status derives (2.5); the image lives in
      `values_json` and is reachable through `build_id`. If either seems needed, re-read D3.
- [ ] 2.4 Unique `(deployment_id, number)`; index `deployment_id` and `build_id`.
- [ ] 2.4a **Backfill a release for every existing non-deleted deployment** in the migration and
      point `desired_release_id` at it, which is what makes the NOT NULL in 2.2 possible. Without
      it, a deployment predating the migration has no desired release and the first reconcile it
      gets — a Mollie webhook unblocking a `pending` row, or a lease reclaim of a job enqueued
      before the deploy — has nothing to apply.
- [ ] 2.4b Set `applied_release_id` to the same release **only where `applied_template_id IS NOT
      NULL`**, which is the existing record that something was actually applied. Blanket-setting it
      would have a `pending` deployment claiming to run something it never ran.
- [ ] 2.5 Add derivation helpers for release status — queued / in flight / abandoned / failed /
      succeeded — over `started_at`, `ended_at` and `error`. Liveness is **not** derived: it is
      `deployment.applied_release_id`.

## 3. Creating releases on the write path

- [ ] 3.1 Create the release in `create_deployment` and `update_deployment`, in the **same
      transaction** as the deployment write, and set `deployment.desired_release_id`. On update,
      the guarded `UPDATE … WHERE status IN (ready, error)` must roll the release back with it when
      `rowcount == 0`.
- [ ] 3.2 On create, generate both `uuid4`s first and insert the deployment with
      `desired_release_id` already populated, then the release. See 2.2a — there is no
      insert-null-then-update step.
- [ ] 3.3 Assign `number` as `max(number) + 1` per deployment. Safe because `enqueue_job` rejects a
      second open job and `update_deployment` requires `ready`/`error`; the unique constraint makes
      it structural rather than incidental.
- [ ] 3.4 Snapshot the **user** values onto the release, not the merged values — system overrides
      do not exist yet at request time, and the user values are the intent worth keeping.
- [ ] 3.5 Accept an optional `build_id` as a plain field on `DeploymentCreate` and
      `DeploymentUpdate`, store it on the release, and **do not** add any build field to
      `DeploymentORM`. No envelope and no query parameter: `plan_template_id` is already a
      request-only field on `DeploymentCreate`, dropped at `deployments.py:229` via
      `model_dump(exclude={...})`. Follow that, and extend the exclusion set.
- [ ] 3.6 Validate the pair against the **effective** values (`new_user_values`, not just what was
      submitted): no image ⇒ no build; image present ⇒ the build produced exactly that image and
      belongs to the caller. Reject with 400 at the write; never defer to the reconciler.
- [ ] 3.7 Test the partial-update hole specifically: an update that changes
      `user_values_json["image"]` while naming no build must be rejected, not stored with a build
      that did not produce the running image.
- [ ] 3.8 Test that a rejected update leaves no release behind, and that two identical updates
      produce two distinct releases.

## 4. Applying releases in the reconciler

- [ ] 4.1 In `_reconcile_apply`, read `deployment.desired_release_id`. The reconciler creates no
      releases.
- [ ] 4.2 Write `started_at` **only if null**, so a lease-reclaim retry records when work first
      began. Attempt counting belongs to the reconcile job.
- [ ] 4.3 Add a `caelus.releaseId` contributor to `_build_system_overrides` carrying the desired
      release's id, alongside the existing owner and object-storage contributors, so system-last
      precedence applies. Pass nothing else release-related through Helm values — no build
      reference, no numbers.
- [ ] 4.4 Record the outcome on **both** paths, writing `ended_at`, `error` and `helm_revision`
      exactly once. Leave `--atomic` and `--wait` unchanged.
- [ ] 4.5 On success only, set `deployment.applied_release_id`, in the same transaction as
      `deployment.status`. On failure leave it untouched — the atomic rollback already restored the
      release it names, so unchanged is correct rather than a missed update.
- [ ] 4.6 Verify a worker killed mid-Helm leaves `ended_at` null, that the lease reclaim re-runs the
      reconcile against the **same** release, and that `started_at` is not rewritten.
- [ ] 4.7 Expose the applied release on `DeploymentRead` so callers can read what is running without
      deriving it.

## 5. Chart — `custom` only

Scope decision, not an oversight: `caelus.releaseId` is offered to every product and rendering it is
each chart's choice. Do **not** touch the seven curated charts, and do **not** add a `_lib` helper
for a single consumer — see D8.

- [ ] 5.1 Add a `custom.podLabels` helper carrying `caelus.dev/release-id`, applied **only** at
      `deployment.yaml`'s pod template metadata. Do not touch `custom.selectorLabels`: it feeds
      `spec.selector.matchLabels` (immutable) and the Service's `spec.selector` (drops traffic
      mid-rollout).
- [ ] 5.2 Add `caelus.releaseId` to `values.yaml` and `values.schema.json`.
- [ ] 5.3 Bump the chart version and publish. Do not re-push an existing version.
- [ ] 5.4 Test that a second apply with a new release id succeeds — the regression that catches the
      id leaking into a selector, which fails with `field is immutable`.
- [ ] 5.5 Confirm the accepted consequence: a redeploy with identical values now cycles pods rather
      than being a Helm no-op, costing a brief interruption at `replicas: 1`. Note it in the CLI's
      user-facing docs. Curated charts keep their existing no-op behavior.
- [ ] 5.6 Verify a curated product still applies while being handed a `caelus.releaseId` it does not
      render. Schema rejection is already ruled out — every curated chart sets
      `caelus.additionalProperties: true`, `mattermost` has no schema — so this confirms the render
      path, not the schema.

## 6. Loki client and the log endpoint

- [ ] 6.1 Add a Loki query client under `api/app/services/` over the existing `httpx`. Keep it a
      thin transport with no deployment or release concepts, following the Garage admin client.
- [ ] 6.2 Add Loki settings to `api/app/config.py` (base URL, default tail size, stream caps,
      keepalive interval, idle timeout). Absent settings must fail only on the path that needs them,
      so migrations, tests and the local CLI still construct settings.
- [ ] 6.3 Add `GET /api/users/{user_id}/deployments/{deployment_id}/log` in `api/app/api/users.py`
      as **`async def`**. Every other endpoint is a sync `def` on a 40-thread pool behind
      `--workers 1`; a blocking stream there takes down the whole API.
- [ ] 6.4 Authorize the deployment, then release the session **before** streaming. Do not hold
      `get_session` open across the stream.
- [ ] 6.5 Build the LogQL selector server-side from the deployment row only. Accept no query,
      selector, matcher or namespace parameter under any name. Test that such a parameter has no
      effect on the query issued.
- [ ] 6.6 Emit SSE. Each log event carries the line, its timestamp, and the release id where the
      pods are labeled. Mirror the timestamp into `id:` so a stock `EventSource` gets
      `Last-Event-ID` free.
- [ ] 6.7 Send the timestamp as a **JSON string, never a number** — ~1.76e18 against a
      `Number.MAX_SAFE_INTEGER` of ~9.01e15, so a number is silently rounded by any JS consumer with
      no error raised. Loki returns it as a string; keep it one.
- [ ] 6.8 Resume with `start = <timestamp>` **inclusive** and `direction=forward`. Inclusive is the
      at-least-once mechanism: no gap, at the cost of re-delivering lines sharing the boundary
      nanosecond. Never resume at `+1ns`.
- [ ] 6.9 Mind that `direction` differs: the **first** connect is `backward` with `limit=N` and its
      batch must be reversed before emitting; every **resume** is `forward`. Loki defaults to
      `backward`, so the resume path is the one that breaks silently.
- [ ] 6.10 Validate a client-supplied resume timestamp as a `uint64` in a sane range before it
      becomes `start`. It is the only client-supplied value reaching the query — the sole exception
      to 6.5, and the client knowing it legitimately does not make it trusted.
- [ ] 6.11 Guard the pathological case: if a batch returns `limit` lines all bearing the cursor's
      timestamp, the cursor cannot advance and the poll loop spins. Raise the limit or fail loudly.
- [ ] 6.12 Emit a configurable keepalive on open follow-mode streams as an SSE **comment**, so it
      carries no `id:` and cannot be mistaken for output. A quiet period must not advance the resume
      point. Set `X-Accel-Buffering: no` and `Cache-Control: no-store`.
- [ ] 6.13 **Measure the real edge before picking the keepalive interval.** The tightest timeout is
      not in this repo: client → homelab HAProxy → Traefik → API, and HAProxy's
      `timeout client`/`timeout server` are operator-configured. Hold an idle stream against the live
      edge, find where it dies, set the interval below that with margin. Do not assume 30s.
- [ ] 6.14 Confirm nothing in the path buffers the response — a buffering proxy swallows the
      keepalives too. Same unverified hop as 6.13, checked the same way.
- [ ] 6.15 Implement release pinning by `number`, resolved against the addressed deployment. On a
      product whose pods carry no release label, report that attribution is unavailable rather than
      returning an empty stream.
- [ ] 6.16 Distinguish store-unavailable from empty-result on the initial response and mid-stream.
      Mid-stream this is an `event: error` before close — the reason SSE was chosen over an unframed
      body. An unreachable store must never produce an empty 200.
- [ ] 6.17 Enforce the per-user concurrent-stream cap and the idle timeout. The idle timeout bounds
      total stream lifetime and is unrelated to 6.12's keepalive — a quiet application must never
      trip it, or the two mechanisms fight.
- [ ] 6.18 Decide between Loki's `/tail` WebSocket and polling `/query_range` with an advancing
      `start`, and record which and why. Polling is simpler server-side and avoids `/tail`'s
      boundary-loss caveats; the client contract is identical either way.

## 7. Deploy failure reporting

- [ ] 7.1 In the reconciler's `except` branch, query Loki for the failed release and attach the tail
      of its output to `last_error`. This works only because the lines outlive the rolled-back pod —
      do not reach for the pod.
- [ ] 7.2 Check the truncation path: `AdapterCommandError._build_message` cuts detail at 400
      characters (`app/proc.py`) and that string becomes `last_error`. Carry the tail so truncation
      does not eat it.
- [ ] 7.3 Verify end to end: deploy an image that crashes on startup, confirm `--atomic` rolls back,
      and confirm the user sees the application's actual error without a second command.
- [ ] 7.4 Confirm the previous release still serves after the rollback and that
      `applied_release_id` still names it.

## 8. `freepod log`

- [ ] 8.1 Add the `log` command, resolving the deployment from the project file and environment like
      the other project-scoped commands. Say so plainly outside a project; do not guess from the
      account's other deployments.
- [ ] 8.2 Stream over the existing `ApiClient` with `httpx`'s streaming request, parsing SSE with
      `iter_lines()`. Add **no** package dependency and do not reimplement the refresh contract
      documented in `api.py`.
- [ ] 8.3 Do **not** apply `DEFAULT_HTTP_TIMEOUT` (30s, `cli/src/freepod/config.py:36`) to a followed
      stream — httpx applies it per read, disconnecting any application quiet for 30 seconds. Treat
      missing *keepalives* as the disconnect signal, never missing application output. Discard
      keepalives without printing them.
- [ ] 8.4 Log lines to **stdout**, client narration to **stderr** — the opposite split from
      `freepod deploy`, because here the lines are the result and must survive a redirect and a pipe.
- [ ] 8.5 Retain the last event's timestamp and reconnect from it on an interrupted follow, with
      bounded backoff, reported on stderr. Resume from the same field `--timestamps` renders, so
      display and resumption cannot disagree. Do not restart at the present: that loses exactly the
      output written during the outage. `ApiClient`'s `MAX_ATTEMPTS` retry is the precedent.
- [ ] 8.6 Parse the timestamp from its string without going through a float at any point. Round-trip
      a real nanosecond value in a test — this corrupts silently.
- [ ] 8.7 Add `--timestamps` / `-t`, **off by default**. Keep the default identical for followed and
      bounded reads — differing shapes between modes breaks downstream pipes. Fix prefix order as
      `<timestamp> <release> <line>`.
- [ ] 8.8 Add release pinning by number, including a failed release whose pods are gone.
- [ ] 8.9 Report store-unavailable distinctly from a genuinely silent application; say the
      application was silent rather than exiting with no output.
- [ ] 8.10 Test a followed stream across a quiet period longer than the default timeout, asserting no
      keepalive residue in redirected output; and that output written while disconnected is printed
      after reconnecting.
- [ ] 8.0 Make `freepod deploy` send the `build_id` alongside the image it already sends
      (`cli/src/freepod/deploy.py`, the same call site as `IMAGE_KEY`). Without it every custom
      release records a null build and the provenance chain this change exists to close stays
      broken. Behavior change to `cli-deploy`, small but not invisible.
- [ ] 8.11 Bump `__version__` in `cli/src/freepod/__init__.py` and tag `freepod-v*` — no commit to
      `master` publishes the client.
- [ ] 8.12 Document the command in `cli/README.md` for end users and the internals in
      `cli/DEVELOPMENT.md`.

## 9. Documentation

- [ ] 9.1 Update `api/README.md` with the release ledger: created by the request, completed by the
      reconciler, no column revised, status derived, liveness a pointer. Someone will otherwise add
      a status column.
- [ ] 9.2 Record in `tf/deps/README.md` that `namespace`, `instance` and `release_id` are a contract
      the API depends on, not just operator convenience.
- [ ] 9.3 Note in the deployment skill (`cli/`) that application logs are readable, so an agent
      debugging a deployment reaches for `freepod log` instead of guessing.
