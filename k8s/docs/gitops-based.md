# GitOps‑Based Architecture for Caelus

## Overview
This design leverages **Argo CD** as a GitOps engine. Caelus stores the desired state for each user‑deployed instance as a folder of Helm values in a Git repository. When a user creates, upgrades, or deletes an instance, Caelus writes the appropriate files (instance manifest and an Argo CD Application CR) and commits them. Argo CD continuously syncs the repository to the cluster, ensuring drift‑free deployments.

---

### 1. Assumptions
| Item | Detail |
|------|--------|
| Backend | FastAPI (Python) – we will use `gitpython` or the `git` CLI to manipulate the repo. |
| Template format | Helm chart (admin authored). Values are stored as JSON/YAML blobs in the DB. |
| Scale | Hundreds of concurrent instances – Argo CD can handle thousands of Applications. |
| Cluster | Dedicated to Caelus – Argo CD can be granted cluster‑wide permissions to create namespaces and resources. |
| Secrets | Not defined yet – we can use **SOPS‑encrypted** secret files in the repo; Argo CD can decrypt them at sync time. |
| Source of truth | Git repository – the repo is the canonical desired state; Caelus only writes to it. |
| Upgrade path | Admin updates the values or chart reference and commits; Argo CD performs a Helm upgrade. |
| Drift handling | Argo CD continuously reconciles the live cluster with the Git repo; any drift triggers a sync. |

---

### 2. Data‑Model Extension
**`product_template_version`** (extends the existing table)
- `helm_chart_repo_url: str` – URL or filesystem path to the Helm chart repository that contains the chart for this product version.
- `chart_version: str` – Optional explicit chart version (e.g., `1.2.3`). If omitted the latest version in the repo is used.
- `default_values: TEXT` – JSON/YAML string containing the default `values.yaml` for the chart. This is merged with any per‑instance overrides when rendering the final manifest.

**`deployment`** (the existing `deployment` table gains additional columns; no separate table is required)
- `git_path: str` – Relative path inside the GitOps repository where this instance’s folder lives (e.g., `instances/<uuid>/`).
- `argo_app_name: str` – Name of the Argo CD `Application` custom resource that manages this deployment. Typically matches the instance UUID.
- `last_synced_at: datetime` – Timestamp of the most recent successful sync performed by Argo CD.
- `sync_status: str` – Current synchronization status (`Synced`, `OutOfSync`, `Error`).
- `status: str` – High‑level lifecycle state from Caelus’s perspective (`Pending`, `Running`, `Failed`, `Deleting`).

These fields allow Caelus to:
1. Record the exact Helm source and default values for each product version (immutable once created).\
2. Track the location of the instance’s manifests in the Git repo and the corresponding Argo CD Application.\
3. Observe and surface the sync health reported by Argo CD, enabling automated drift detection and manual troubleshooting.

**Migrations**
- Add the new columns with `NULL` defaults (or appropriate defaults) to keep existing deployments functional.
- Populate `helm_chart_repo_url` for existing product versions via an admin migration script.
- Back‑fill `git_path` and `argo_app_name` for existing deployments when they are first reconciled by Caelus.

The DB schema changes are purely additive; they do not break existing API contracts because all new fields are optional for reads and writes unless explicitly set by the admin.

The `git_path` points to the folder in the Git repo that holds the per‑instance manifest.

---

### 3. Repository Layout
```
/gitops-repo/
├─ charts/
│   └─ nextcloud/            # shared chart repo (admin‑maintained)
│       ├─ Chart.yaml
│       └─ templates/...
├─ instances/
│   ├─ 123e4567‑89ab‑cdef/   # instance UUID
│   │   ├─ values.yaml        # merged default + overrides
│   │   └─ kustomization.yaml   # optional overlay
│   └─ 89ab1234‑56cd‑ef78/
│       └─ values.yaml
└─ argo‑cd/
    └─ applications/
        ├─ 123e4567‑89ab‑cdef.yaml   # Argo CD Application manifest
        └─ 89ab1234‑56cd‑ef78.yaml
```
Each instance gets its own **Argo CD Application** manifest that points to its folder and its dedicated namespace.

---

### 4. High‑Level Flow
```
+-------------------+          +-------------------+          +-------------------+
|   Caelus API      |  POST /  |   DB (Postgres)   |  writes   |   Git Repo (bare) |
| (FastAPI)         |--------->| deployment_inst  |--------->|  instances/<id>/  |
+-------------------+          +-------------------+          +-------------------+
        |                               |                               |
        |   Create Application CR      |   Argo CD watches repo        |
        +------------------------------>------------------------------+
                                     |
                               +-------------------+
                               |   Argo CD (controller)   |
                               |  - syncs Helm releases   |
                               +-------------------+
```
Argo CD continuously reconciles the **Application** CRs with the live cluster, guaranteeing drift‑free state.

---

### 5. Detailed Steps per Operation
| Operation | Caelus actions | Argo CD actions |
|-----------|----------------|-----------------|
| **Create instance** | 1. Insert row in `deployment_instance`.<br>2. Render `values.yaml` (default + overrides).<br>3. Commit new folder under `instances/<uuid>/`.<br>4. Generate an **Application** manifest (`applications/<uuid>.yaml`) that references the folder, sets `destination.namespace = <uuid>`, `source.helm.chart = <chart repo>`. Commit. | Detects new Application CR → creates namespace → runs Helm install. |
| **Delete instance** | 1. Mark row as deleted.<br>2. Remove folder & Application manifest (commit). | Detects deletion → deletes namespace (if `syncPolicy.prune=true`). |
| **Upgrade instance** | 1. Admin creates a new `ProductTemplateVersion` (new chart version).<br>2. Admin calls `PATCH /instances/{id}` with new `template_version_id`.<br>3. Caelus updates `values.yaml` (or `chart` reference) and commits. | Argo CD sees change → performs Helm upgrade. |
| **Drift correction** | N/A – source of truth is Git. | Argo CD detects drift → auto‑sync (or alerts). |

---

### 6. Upgrade Process
1. **New template version** → admin adds chart version to repo (or updates chart reference).
2. **Instance upgrade** → Caelus updates the `Application` CR’s `source.helm.chart.version` (or updates values).
3. **Argo CD** performs a Helm upgrade; PVCs are retained automatically because Helm charts typically set `helm.sh/resource-policy: keep` on PVC resources.

*If you want to gate upgrades by tier, add a label `tier=stable|beta` on the `Application` CR and let Argo CD sync only those with a specific `syncPolicy` (or use Argo CD’s `sync windows`).*

---

### 7. Security & Secrets
* **Secrets handling** – Caelus can generate a Kubernetes `Secret` object (base64‑encoded) and write it into the instance folder as a **Helm secret** (`templates/secret.yaml`). The secret file can be encrypted with **SOPS**; Argo CD has built‑in SOPS decryption support.
* **RBAC** – Argo CD runs with a ServiceAccount that has cluster‑wide `create/delete` rights for namespaces it creates. Namespace‑level `NetworkPolicy` can be added later.

---

### 8. Scalability & Performance
* **Stateless Caelus** – only writes to Git (fast, cheap).
* **Argo CD** scales horizontally; each Application CR is independent, allowing parallel syncs.
* **No per‑instance controller** – the heavy lifting is done by Argo CD, which already handles thousands of applications efficiently.
* **Deployment time** is O(1) – Helm install/upgrade time depends only on chart size, not on total instances.

---

### 9. Pros / Cons
| Pros | Cons |
|------|------|
| **Zero custom controller** – rely on battle‑tested Argo CD. | Requires **Git repo management** (permissions, backup). |
| **Strong drift detection** – Argo CD continuously reconciles. | Slightly more indirect – Caelus must write to Git, then wait for Argo CD. |
| **Easy to audit** – all desired state lives in Git history. | Secrets need extra handling (SOPS, external secret stores). |
| **Scales** – Argo CD handles many applications in parallel. | If Git repo becomes a bottleneck, you need scaling (e.g., Git server clustering). |
---

### 10. Next Steps
1. Create the **Git repo** layout & initial `charts/` directory.
2. Add `helm` chart repository configuration (local or remote).
3. Implement FastAPI routes to **generate/commit** instance folders and Application manifests (use `gitpython` or CLI).
4. Deploy **Argo CD** into the cluster (helm install) and configure it to watch the repo.
5. Add **SOPS** integration for encrypted secrets (optional).
6. Write **integration tests** that simulate instance creation, upgrade, and deletion, asserting the corresponding resources appear/disappear in the cluster.

---

*This document is saved as `ai/architecture/gitops‑based.md`.*