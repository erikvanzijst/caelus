# Caelus Kubernetes Architecture (Native Reconciler + Helm SDK)

Date: 2026-02-14
Status: Proposed V1

## Scope

This document defines the V1 deployment architecture for Caelus using:

- Helm-only product templates
- Caelus-native reconciliation worker
- Admin-only upgrades
- Hard deletion of instance Kubernetes resources
- Single-cluster operation
- Shared cluster ingress/TLS/load-balancing stack (provided externally)

Caelus DB remains the only source of truth.

---

## 1. Reconciler Worker Design

## 1.1 Responsibilities

The reconciler converges Kubernetes state to the desired state stored in the Caelus DB, per deployment.

Per deployment, it ensures:

- Namespace exists (or is deleted when deployment is deleted)
- Helm release exists and matches desired template + values
- Deployment status in DB reflects current outcome
- Drift is corrected automatically

## 1.2 Identity model (domain is mutable)

Use immutable identity fields, never domain name, for Kubernetes naming:

- `deployment.deployment_uid` (immutable slug id, not a UUID)

`deployment.domainname` is mutable config injected into Helm values.

### 1.2.1 Naming contract

Requested format for `deployment_uid`:

`{product_slug}-{user_slug}-{suffix6}`

Where:

1. `product_slug`: product name slugified to lowercase `[a-z0-9-]`.
2. `user_slug`: user email slugified to lowercase `[a-z0-9-]` (replace non-alnum with `-`).
3. `suffix6`: six random base36 chars (`[0-9a-z]{6}`) for uniqueness.

Kubernetes DNS-label constraints require:

- max length 63
- charset `[a-z0-9-]`
- must start/end with alphanumeric

So generation must enforce:

1. Build base: `{product_slug}-{user_slug}`.
2. Reserve 7 chars for `-{suffix6}`.
3. Truncate base to at most 56 chars.
4. Trim leading/trailing `-` after truncation.
5. If base is empty after trimming, fallback to `dep`.
6. Final value: `{base}-{suffix6}`.

V1 rule:

- `namespace_name = deployment_uid`

## 1.3 Reconciler pseudocode

```text
main():
  start N workers
  start periodic scanner (every 60s):
    enqueue all deployments where:
      - deleted_at is null and status in (pending, provisioning, upgrading, error)
      - or deleted_at is not null and status != deleted
      - or last_reconcile_at older than drift_interval

worker_loop(worker_id):
  while true:
    job = dequeue_next_job_with_skip_locked()
    if no job:
      wait on notify/poll
      continue

    deployment_id = job.deployment_id
    try:
      reconcile_one(deployment_id)
      mark_job_done(job)
    except RetryableError as e:
      reschedule_job(job, backoff(e.attempt))
      record_error(deployment_id, e)
    except FatalError as e:
      mark_job_failed(job)
      set_deployment_status(deployment_id, "error", e.message)

reconcile_one(deployment_id):
  with db_transaction:
    dep = load_deployment_for_update(deployment_id)
    if dep missing:
      return

    desired = build_desired_state(dep)  # template, values, namespace, release

  if dep.deleted_at is not null:
    reconcile_delete(dep)
    return

  reconcile_apply(dep, desired)

reconcile_apply(dep, desired):
  ensure_namespace(desired.namespace_name)

  chart = resolve_chart(desired.template.chart_ref, desired.template.chart_version, desired.template.chart_digest)
  values = merge_values_scoped(
    defaults         = desired.template.default_values,
    user_scope_delta = dep.user_values_json,    # merged only under values.user
    system_overrides = system_overrides(dep)    # domain, namespace, ingressClass, etc.
  )
  validate_against_schema(values, desired.template.values_schema)

  result = helm_upgrade_install(
    release_name = desired.release_name,
    namespace    = desired.namespace_name,
    chart        = chart,
    values       = values,
    atomic       = true,
    wait         = true,
    timeout      = desired.template.health_timeout
  )

  if result.success:
    set_deployment_status(dep.id, "ready")
    set_applied_template(dep.id, dep.desired_template_id)
    set_last_reconcile(dep.id, now)
  else:
    raise RetryableError(result.error)

reconcile_delete(dep):
  helm_uninstall(
    release_name = dep.release_name,
    namespace    = dep.namespace_name,
    wait         = true,
    timeout      = delete_timeout
  )

  delete_namespace(dep.namespace_name)

  if namespace_still_terminating(dep.namespace_name):
    raise RetryableError("namespace terminating")

  set_deployment_status(dep.id, "deleted")
  set_last_reconcile(dep.id, now)
```

## 1.4 `build_desired_state()` pseudocode

```text
build_desired_state(dep):
  # dep contains desired_template_id, domainname, user_values, identity fields
  tmpl = get_template(dep.desired_template_id)
  if tmpl is null or tmpl.deleted_at is not null:
    raise FatalError("desired template missing")

  # Ensure immutable identity fields exist
  deployment_uid = dep.deployment_uid or generate_deployment_uid(
    product_name = dep.template.product.name,
    user_email   = dep.user.email
  )
  namespace_name = dep.namespace_name or deployment_uid

  # Build values in deterministic precedence
  # 1) template defaults
  # 2) user-provided values under "user" scope only
  # 3) system overrides
  defaults = tmpl.default_values_json or {}
  uservals = dep.user_values_json or {}
  sysvals  = {
    "ingress": {
      "host": dep.domainname,
      "className": platform_ingress_class
    },
    "caelus": {
      "deploymentId": dep.id,
      "deploymentUid": deployment_uid,
      "namespace": namespace_name
    }
  }

  # Merge only into defaults.user to clearly isolate user-editable values
  merged = deep_copy(defaults)
  merged["user"] = deep_merge(defaults.get("user", {}), uservals)
  merged = deep_merge(merged, sysvals)

  # Validate final values against immutable template schema
  validate_json_schema(merged, tmpl.values_schema_json)

  return DesiredState(
    deployment_id      = dep.id,
    namespace_name     = namespace_name,
    chart_ref          = tmpl.chart_ref,
    chart_version      = tmpl.chart_version,
    chart_digest       = tmpl.chart_digest,
    values             = merged,
    health_timeout_sec = tmpl.health_timeout_sec or 600
  )
```

## 1.5 Command/service decomposition (CLI + worker share same functions)

To avoid monolithic worker code, split reconciliation into service functions in `api/app/services/` and expose operator-style admin commands in `api/app/cli.py`.

Recommended modules:

- `api/app/services/jobs.py`
  - `enqueue_job(...)`
  - `list_jobs(...)`
  - `claim_next_job(...)`
  - `mark_job_done(...)`
  - `requeue_job(...)`
  - `mark_job_failed(...)`
- `api/app/services/reconciler.py`
  - `build_desired_state(...)`
  - `reconcile_deployment(...)`
  - `reconcile_apply(...)`
  - `reconcile_delete(...)`
  - `run_worker_once(...)`
  - `run_drift_scan(...)`

Recommended CLI commands (examples):

- `reconcile <deployment_id>`
- `enqueue-reconcile <deployment_id> --reason <reason>`
- `list-reconcile-jobs [--status queued|running|failed]`
- `run-worker-once`
- `run-worker-loop --concurrency 4 --poll-seconds 2`
- `requeue-job <job_id>`
- `fail-job <job_id> --error \"...\"`
- `scan-drift`

Command naming convention: use `kebab-case` for all CLI commands to match existing Typer style.

Worker loop then becomes a thin orchestrator:

```text
run_worker_loop():
  while true:
    job = reconcile_jobs.claim_next_job(session)
    if no job:
      sleep(poll_interval)
      continue
    try:
      reconcile.reconcile_deployment(session, deployment_id=job.deployment_id)
      reconcile_jobs.mark_job_done(session, job.id)
    except RetryableError as e:
      reconcile_jobs.requeue_job(session, job.id, e.message)
    except FatalError as e:
      reconcile_jobs.mark_job_failed(session, job.id, e.message)
```

This gives parity between automation and manual admin replay in terminal.

## 1.6 Reconciliation semantics

- Idempotent: every reconcile can be rerun safely.
- Per-instance isolation: one failed deployment does not block others.
- Bounded retries: exponential backoff with max delay.
- Drift correction: periodic requeue + event-triggered requeue.

## 1.7 Status model (deployment table)

Recommended statuses:

- `pending`
- `provisioning`
- `ready`
- `upgrading`
- `deleting`
- `deleted`
- `error`

And fields:

- `desired_template_id`
- `applied_template_id`
- `last_reconcile_at`
- `last_error`
- `generation`

---

## 2. Queue/Event Strategy

## 2.1 Should the reconciler read from a queue?

Yes. Use a queue so reconciliation is:

- asynchronous from API writes
- retryable with backoff
- horizontally scalable across workers

## 2.2 Recommended V1 queue: Postgres-backed job table + `SKIP LOCKED`

Given simplicity and DB-as-source-of-truth, use Postgres as both state store and work queue.

Recommended table (conceptual): `deployment_reconcile_job`

- `id`
- `deployment_id`
- `reason` (`create`, `update`, `delete`, `drift`, `retry`)
- `run_after`
- `attempt`
- `status` (`queued`, `running`, `done`, `failed`)
- `locked_by`, `locked_at`
- `last_error`
- `created_at`

Dequeue pattern:

```sql
WITH picked AS (
  SELECT id
  FROM deployment_reconcile_job
  WHERE status = 'queued' AND run_after <= now()
  ORDER BY run_after, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE deployment_reconcile_job j
SET status='running', locked_by=$1, locked_at=now()
FROM picked
WHERE j.id = picked.id
RETURNING j.*;
```

## 2.3 Triggering jobs

Enqueue on:

- deployment created
- deployment updated (domain, user values, desired template)
- deployment soft-deleted
- template-related compatibility migrations (if needed)
- periodic drift scan

Optional optimization: `LISTEN/NOTIFY` to wake idle workers immediately after enqueue.

## 2.4 Why not Redis/Rabbit/Kafka in V1?

They are valid, but not necessary for current scale and simplicity goals.

Start with Postgres queue. Revisit external broker only if:

- enqueue/dequeue throughput becomes bottleneck
- strict cross-service event contracts are required
- multi-cluster orchestration is introduced

## 2.5 Runtime topology (API vs worker)

Deploy reconciliation runtime as a separate Kubernetes Deployment (same image/codebase as API, different command/entrypoint).

Recommended:

- `caelus-api` Deployment: serves REST API/CLI-facing behavior
- `caelus-worker` Deployment: runs `run-worker-loop`

Optional:

- `caelus-drift-scan` CronJob: periodically runs `scan-drift` and exits

This keeps long-running reconciliation independent from request-serving API pods.

---

## 3. Example App from Scratch (Hello World)

Goal: deploy an app where nginx serves a static HTML file from a PVC; HTML content comes from Helm value `user.message`.

## 3.1 Chart structure

```text
hello-static/
  Chart.yaml
  values.yaml
  values.schema.json
  templates/
    _helpers.tpl
    pvc.yaml
    deployment.yaml
    service.yaml
    ingress.yaml
```

### `Chart.yaml`

```yaml
apiVersion: v2
name: hello-static
description: Nginx serving a generated static HTML file from PVC
type: application
version: 0.1.0
appVersion: "1.0.0"
```

### `values.yaml`

```yaml
image:
  repository: nginx
  tag: "1.27"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: traefik
  annotations: {}
  host: ""

storage:
  size: 1Gi
  accessModes:
    - ReadWriteOnce
  storageClassName: ""

user:
  message: "Hello from Caelus"
```

### `values.schema.json`

`values.schema.json` defines which values are valid and is used by:

- Helm at render/upgrade time
- Caelus API validation
- UI form generation (see dynamic values section below)

### `templates/pvc.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "hello-static.fullname" . }}-data
spec:
  accessModes: {{ toYaml .Values.storage.accessModes | nindent 2 }}
  resources:
    requests:
      storage: {{ .Values.storage.size }}
  {{- if .Values.storage.storageClassName }}
  storageClassName: {{ .Values.storage.storageClassName }}
  {{- end }}
```

### `templates/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "hello-static.fullname" . }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ include "hello-static.name" . }}
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ include "hello-static.name" . }}
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      initContainers:
      - name: write-index
        image: busybox:1.36
        command:
        - sh
        - -c
        - |
          cat > /data/index.html <<'HTML'
          <html><body><h1>{{ .Values.user.message }}</h1></body></html>
          HTML
        volumeMounts:
        - name: data
          mountPath: /data
      containers:
      - name: nginx
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: 80
        volumeMounts:
        - name: data
          mountPath: /usr/share/nginx/html
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: {{ include "hello-static.fullname" . }}-data
```

### `templates/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "hello-static.fullname" . }}
spec:
  type: {{ .Values.service.type }}
  selector:
    app.kubernetes.io/name: {{ include "hello-static.name" . }}
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
  - port: {{ .Values.service.port }}
    targetPort: 80
```

### `templates/ingress.yaml`

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "hello-static.fullname" . }}
  annotations:
    {{- toYaml .Values.ingress.annotations | nindent 4 }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  rules:
  - host: {{ .Values.ingress.host | quote }}
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {{ include "hello-static.fullname" . }}
            port:
              number: {{ .Values.service.port }}
{{- end }}
```

The full demo chart is committed at `k8s/hello-static-chart/`.

## 3.2 Admin registration flow in Caelus

1. Admin creates `Product`:
   - `name = "Hello Static"`
   - `description = "Nginx static page from PVC"`

2. Admin publishes `ProductTemplateVersion` (immutable):
   - `package_type = "helm-chart"`
   - `chart_ref = "oci://registry.example.com/caelus/hello-static"`
   - `chart_version = "0.1.0"`
   - `chart_digest = "sha256:..."` (preferred)
   - `default_values_json` from chart defaults
   - `values_schema_json` including `user.message` as configurable string
   - `capabilities_json` with `requires_admin_upgrade=true`

3. Admin marks product canonical template (`product.template_id = <new_template_id>`).

## 3.3 User deployment creation flow

1. User creates deployment via API/CLI:
   - `POST /users/{user_id}/deployments`
   - payload includes:
     - `template_id` (canonical template)
     - `domainname` (e.g., `hello.userdomain.example`)
     - optional `user_values = { "message": "Hello Alice" }` (this maps to `values.user`)

2. API transaction:
   - validates user exists
   - validates template exists and is active
   - allocates immutable `deployment_uid` using `{product_slug}-{user_slug}-{suffix6}` contract
   - sets `namespace_name = deployment_uid`
   - sets `release_name = deployment_uid`
   - sets `desired_template_id = template_id`, `status = pending`
   - inserts deployment row
   - enqueues reconcile job (`reason=create`)

3. Worker reconciliation:
   - dequeues job
   - creates namespace (if missing)
   - merges values:
     - template defaults
     - user-scope overrides (`user.message`)
     - system overrides (`ingress.host = domainname`, namespace-specific labels)
   - runs Helm install/upgrade
   - waits for health
   - updates deployment status to `ready`

4. Resulting Kubernetes objects in namespace:
   - Deployment (nginx)
   - Service
   - Ingress for user domain
   - PVC with generated `index.html` content

## 3.4 Update and drift examples

- Domain change:
  - user/admin updates `deployment.domainname`
  - enqueue `reason=update`
  - reconciler runs Helm upgrade with new `ingress.host`

- Message change:
  - update `user_values.message`
  - enqueue `reason=update`
  - reconciler upgrades release; initContainer rewrites `index.html`

- Drift:
  - if someone edits/deletes Deployment manually, periodic drift reconcile reruns Helm and restores expected state

## 3.5 Dynamic application values and UI integration

Application-specific values (example: `user.message`) are modeled as user-overridable fields constrained by template schema.

Data model split:

- `ProductTemplateVersion.values_schema_json`: immutable full JSON schema for chart values
- `ProductTemplateVersion.default_values_json`: immutable default values
- `Deployment.user_values_json`: per-instance overrides entered by user/admin

### 3.5.1 User-overridable fields under `user` scope

V1 decision: user-editable fields are only those declared under `values.user` in `values_schema_json`.

Practical extraction algorithm:

1. Read `values_schema_json.properties.user`.
2. If missing, user input is disabled for that template (valid and expected for templates with no dynamic user values).
3. Include leaf fields with simple input semantics:
   - `type` in `{string, integer, number, boolean}`
   - or explicit `enum`
4. Exclude fields marked `readOnly: true` if present.
5. For arrays/objects under `user`:
   - include only when schema is bounded and can be rendered safely in UI
   - otherwise hide in V1
6. UI uses schema metadata (`title`, `description`, `default`, `enum`, `minimum`, `maximum`, `pattern`) to render controls.

This gives a clear ownership boundary without introducing a second schema field in V1.

### 3.5.2 Validation path

Recommended flow:

1. Admin publishes template with full `values_schema_json`.
2. UI fetches template metadata before rendering deployment form.
3. API/UI derive editable fields from `values_schema_json.properties.user`.
4. User submits `user_values_json`.
5. API validates `user_values_json` against the `user` subschema.
6. Reconciler merges `user_values_json` into `default_values_json.user`, applies system overrides, and validates final merged payload against full `values_schema_json`.

For `hello-static`, expose:

- `user.message` (string, editable)

Keep these system-managed and non-editable by users:

- `ingress.host` (derived from deployment domain)
- platform/internal labels and namespace metadata

## 3.6 Delete flow (V1 hard delete)

1. User/admin deletes deployment (soft delete in DB via `deleted_at`).
2. API enqueues `reason=delete`.
3. Worker:
   - Helm uninstall release
   - delete namespace
   - retry until namespace fully removed (or flagged error)
4. DB status set to `deleted` on success.

---

## 4. Minimal implementation plan

1. Extend `product_template_version` and `deployment` schema with required fields.
2. Add enqueue-on-write behavior in deployment/template services.
3. Implement Postgres job table + worker process.
4. Implement Helm adapter (`install_or_upgrade`, `uninstall`, `get_status`).
5. Add periodic drift scanner.
6. Add deployment status API fields for UI visibility.
7. Add integration test with kind/k3s: create, update, delete lifecycle.

---

## Clarifying decisions applied

1. `values_schema_json.properties.user` is optional.
2. Templates without user-editable fields omit `user` entirely; UI shows no dynamic input fields.

---

## 5. Non-goals for V1

- User-initiated upgrades
- Multi-cluster scheduling
- Non-Helm templates
- Built-in cert-manager/ingress provisioning (cluster provides these)

---

## 6. Manual Validation Checklist (hello-static)

Use this checklist to validate a new chart/template manually before wiring it into automated reconciliation.

1. Cluster connectivity:

```bash
export KUBECONFIG=/workspace/k8s/kubeconfigs/dev-k3s.yaml
kubectl config current-context
kubectl get nodes -o wide
```

2. Create test namespace:

```bash
kubectl create namespace hello-manual
kubectl get ns hello-manual
```

3. Install chart:

```bash
helm upgrade --install hello-manual ./k8s/hello-static-chart \
  --namespace hello-manual \
  --set ingress.enabled=true \
  --set ingress.className=traefik \
  --set ingress.host=hello.app.deprutser.be \
  --set user.message="Hello from manual deploy"
```

4. Verify resources:

```bash
kubectl -n hello-manual get pods,deploy,svc,ingress,pvc
kubectl -n hello-manual rollout status deploy/hello-manual-hello-static --timeout=120s
```

5. Verify HTTP response through ingress:

```bash
curl -ik https://hello.app.deprutser.be
```

Expected body:

```html
<html><body><h1>Hello from manual deploy</h1></body></html>
```

6. Cleanup:

```bash
helm uninstall hello-manual -n hello-manual
kubectl delete namespace hello-manual
```
