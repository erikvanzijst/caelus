# Operator‑Based Architecture for Caelus

## Overview
This design uses a **dedicated Kubernetes Operator** that watches a custom resource representing each user‑deployed instance. The operator reconciles the desired state stored in the Caelus database into a Helm release inside a dedicated namespace.

---

### 1. Assumptions
| Item | Detail |
|------|--------|
| Backend | FastAPI (Python) – we will use the official `kubernetes‑python` client and a Helm SDK wrapper. |
| Template format | Helm chart (admin authoring). Values are stored as JSON/YAML blobs in the DB. |
| Scale | Hundreds of concurrent instances – the operator can handle thousands; each instance lives in its own namespace. |
| Cluster | Dedicated to Caelus – we can safely grant the operator permissions to create namespaces, resources, and secrets. |
| Secrets | Not defined yet – the operator will create a `Secret` per instance from values supplied in the template. |
| Source of truth | Caelus DB – the operator treats the DB as the canonical state and mirrors it via a CRD. |
| Upgrade path | Admin‑only for now – a new template version is linked to an existing instance via an API call, the operator performs a Helm upgrade. |
| Drift handling | Operator continuously watches the CRD and the live cluster; any drift triggers a re‑apply. |

---

### 2. Data‑Model Extension
**`product_template_version`**
- `helm_chart_path` (string – path or URL to the chart)
- `default_values` (JSON/YAML)
- `created_at`

**`deployment_instance`** (new table)
- `id`
- `user_id`
- `product_template_version_id`
- `namespace`
- `domain_name`
- `status`
- `created_at`
- `updated_at`

The `deployment_instance` row is the **source of truth** for a running instance.

---

### 3. CRD – `CaelusInstance`
```yaml
apiVersion: caelus.io/v1
kind: CaelusInstance
metadata:
  name: <instance‑uuid>
spec:
  userId: <uuid>
  productTemplateVersion: <uuid>
  namespace: <k8s‑ns>
  domainName: <fqdn>
  values: {}          # merged default + overrides
status:
  phase: Pending|Running|Failed|Upgrading
  lastReconcile: <timestamp>
```
The operator creates one CRD per row in `deployment_instance`. The CRD is **owner‑referenced** to the namespace it creates, enabling automatic garbage‑collection when the instance is deleted.

---

### 4. High‑Level Flow
```
+-------------------+          +-------------------+          +-------------------+
|   Caelus API      |  POST / |   DB (Postgres)   |  Sync →  |   Operator (Pod) |
| (FastAPI)         |--------->|  deployment_inst  |<--------|  watches CaelusInst|
+-------------------+          +-------------------+          +-------------------+
        ^                               ^                         |
        |                               |                         |
        |   DELETE /instance/:id        |   Create/Update CRD     |
        +-------------------------------+-------------------------+

Operator Reconcile Loop (per CaelusInstance):
  1️⃣ Ensure Namespace exists (create if missing)
  2️⃣ Load Helm chart from chart_path (local FS or remote repo)
  3️⃣ Render values = default_values ⊕ overrides
  4️⃣ Run `helm upgrade --install` into the instance's namespace
  5️⃣ Persist status back to CRD → DB (via API call or direct DB client)
  6️⃣ Watch for drift (Pod/Deployment changes) → repeat if needed
```
---

### 5. Detailed Reconciliation Steps
| Step | Action | Tool / Library |
|------|--------|----------------|
| **Namespace** | `kubectl create namespace $NS` (idempotent) | `kubernetes‑client` |
| **Chart fetch** | Pull chart from object storage or local chart repo (cached) | `helm‑sdk` |
| **Values merge** | Deep‑merge default values with per‑instance overrides stored in DB | Python `deepmerge` |
| **Helm install/upgrade** | `helm upgrade --install $release $chart --namespace $NS --values $merged.yaml` | `helm‑sdk` |
| **PVC preservation** | Helm chart marks PVCs with `persistentVolumeClaim: { retain: true }`; operator ensures `helm.sh/resource-policy: keep` annotation | Helm |
| **Status update** | Set `status.phase=Running` and `lastReconcile` | CRD status patch → DB sync |
| **Drift detection** | Periodic `kubectl get all -n $NS` compare with Helm release manifest; if diff, re‑run upgrade | `helm diff` plugin (optional) |
---

### 6. Upgrade Process
1. **Admin creates a new `ProductTemplateVersion`** with a new Helm chart version.  
2. **Admin calls** `POST /instances/{id}/upgrade` with the new template version UUID.  
3. Caelus updates the `deployment_instance` row (`product_template_version_id`).  
4. The Operator sees the CRD spec change → **performs a Helm upgrade**.  
5. PVCs retain data because the chart uses `helm.sh/resource-policy: keep`.  

*If a user‑initiated upgrade is later allowed, the same endpoint can be exposed with proper RBAC.*
---

### 7. Security & Secrets
* Secrets are stored in the DB encrypted (e.g., using Fernet) and injected as Kubernetes `Secret` objects during Helm rendering.  
* The Operator runs with a **ServiceAccount** that has:
  - `create/delete` namespaces
  - `get/list/watch` all resources in those namespaces
  - `create/update` Secrets, ConfigMaps, Deployments, PVCs
* NetworkPolicies can be added later to isolate each namespace.
---

### 8. Scalability & Performance
* Each instance lives in its own namespace → **no resource contention**.  
* Operator is **stateless**; we can run multiple replicas behind a leader‑election (Lease API) for high availability.  
* Helm releases are cached locally; chart fetch is O(1) per instance, independent of total instances.  
* No Terraform‑style planning phase – each reconcile is O(1).
---

### 9. Pros / Cons
| Pros | Cons |
|------|------|
| **Strong drift correction** – Operator continuously reconciles. | Adds a **new runtime component** (Operator) to the cluster. |
| **Helm native** – leverages existing charts, values, and upgrade semantics. | Requires **CRD & controller** development/maintenance. |
| **Per‑namespace isolation** – easy to enforce quotas, RBAC. | Slightly higher operational surface (RBAC for Operator). |
| **Upgrade safety** – Helm handles rolling upgrades, PVC retention. | Operator must be kept in sync with DB schema changes. |
---

### 10. Next Steps
1. Add `deployment_instance` table & migrations.  
2. Implement FastAPI endpoints for create/delete/upgrade of instances.  
3. Create the `CaelusInstance` CRD (YAML).  
4. Scaffold an **Operator** (Python `kopf` or Go `controller-runtime`).  
5. Write the reconciliation logic (namespace, helm install/upgrade).  
6. Deploy Operator as a Deployment in the cluster, give it the ServiceAccount.  
7. Add unit & integration tests (mock k8s client, DB).  

---

*This document is saved as `ai/architecture/operator‑based.md`.*