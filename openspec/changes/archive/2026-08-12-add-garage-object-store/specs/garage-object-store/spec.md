## Purpose

The shared, cluster-wide S3-compatible object store for the Freepod platform: a single Garage
instance in `tf/deps`, sized and bounded to coexist with every other workload on the one k3s
node, and serviceable from the moment it is installed.

## ADDED Requirements

### Requirement: Garage is deployed as a shared singleton in tf/deps

The platform SHALL run exactly one Garage instance, provisioned by Terraform from
`tf/deps/garage/` and wired into `tf/deps/main.tf` alongside the other shared singletons
(Keycloak, mailer, monitoring). It SHALL live in its own dedicated Kubernetes namespace.

`tf/deps` is workspace-less, so this single instance serves **both** the dev and prod Caelus
environments. The deployment MUST NOT be duplicated per environment; environment separation is
provided by bucket and access-key naming (see the `garage-bucket-provisioning` capability), not
by a second Garage.

Garage SHALL be pinned to an explicit version in Terraform — never a floating `latest` tag — so
an upgrade is a reviewed code change rather than a pod restart.

#### Scenario: Garage namespace and workload exist

- **WHEN** `kubectl get statefulset -n garage` is run after `terraform apply` in `tf/deps`
- **THEN** a Garage StatefulSet exists in the `garage` namespace
- **AND** its pod reaches `Running` and passes its readiness probe

#### Scenario: One instance serves both environments

- **WHEN** the cluster is inspected for Garage workloads
- **THEN** exactly one Garage StatefulSet exists cluster-wide
- **AND** no Garage resources are created by the workspace-multiplexed `tf/app` root module

#### Scenario: Version is pinned

- **WHEN** the Garage Terraform module is inspected
- **THEN** the Garage container image (and the Helm chart, if one is used) is pinned to an
  explicit version
- **AND** no reference resolves to a mutable `latest` tag

### Requirement: Garage runs single-node with replication factor 1

The cluster is a single k3s node, so Garage SHALL be configured with one replica and a
replication factor of `1`. Any replication factor above `1` on a single node leaves Garage
unable to satisfy its own quorum and it will refuse writes.

#### Scenario: Single replica, replication factor 1

- **WHEN** the rendered Garage configuration and StatefulSet spec are inspected
- **THEN** the replica count is `1`
- **AND** the configured replication factor is `1`

#### Scenario: Writes succeed on the single node

- **WHEN** an object is written to a provisioned bucket
- **THEN** the write is accepted and the object is subsequently readable
- **AND** Garage does not report a quorum or layout error

### Requirement: Metadata and object data are on separate persistent volumes

Garage SHALL persist its metadata and its object data on **two separate**
PersistentVolumeClaims. Metadata is small, latency-sensitive and access-heavy while object data
is bulk storage; keeping them apart means metadata can be placed on faster storage if the
cluster ever offers a choice of storage class, without resizing or moving the bulk volume.

Both PVCs SHALL have an explicit, capped size. The data PVC size is the hard ceiling on how
much node disk this dependency can consume, and it is the primary defense against a repeat of
the node's prior disk-pressure incidents. The chart or module default MUST NOT be relied upon —
upstream Garage chart defaults are far too small for real object data and would silently fill.

Both volumes MUST survive pod restarts and rescheduling: object data and the cluster layout
outlive the pod.

#### Scenario: Two distinct PVCs are bound

- **WHEN** `kubectl get pvc -n garage` is run
- **THEN** a metadata PVC and a data PVC exist as separate claims
- **AND** both are `Bound`

#### Scenario: Sizes are explicit and capped

- **WHEN** the Terraform module is inspected
- **THEN** both the metadata and the data PVC sizes are set from explicit module variables
- **AND** neither falls back to an upstream chart default

#### Scenario: Data survives a pod restart

- **WHEN** an object is written, the Garage pod is deleted, and the pod is rescheduled
- **THEN** the pod rejoins with its existing cluster layout intact
- **AND** the previously written object is still readable

### Requirement: Garage has hard CPU and memory bounds

Garage SHALL declare explicit CPU and memory **requests and limits** on its container.

This is a functional requirement, not boilerplate. The k3s node is a single libvirt VM whose
RAM was raised from 16 GB to 24 GB following out-of-memory events, and which runs Postgres,
Keycloak, Traefik, the monitoring stack and every tenant workload on the same kernel. An
unbounded storage daemon absorbing a burst of large multipart uploads can push the node into
the OOM killer and take unrelated tenant workloads down with it. Limits convert that failure
into a slow or failed upload, which is recoverable.

The limits MUST be set from module variables so they can be tuned without editing resource
definitions.

#### Scenario: Requests and limits are present

- **WHEN** the Garage pod spec is inspected
- **THEN** the container declares both `requests` and `limits` for `cpu` and `memory`
- **AND** no resource field is left unset

#### Scenario: Bounds are configurable

- **WHEN** the Terraform module is inspected
- **THEN** the CPU and memory requests and limits are supplied by module variables with
  documented defaults

### Requirement: The cluster layout is assigned and committed as a bootstrap step

A freshly installed Garage node holds **no cluster layout** and rejects all S3 operations until
a layout assigning capacity to the node is applied and committed. This step is a documented
one-time operator action, not something Terraform performs.

The change SHALL document the exact commands, and the operator SHALL verify the node reports a
healthy layout before any bucket is provisioned. The documentation MUST state that the step
recurs whenever the Garage node identity changes (for example, if the metadata volume is
recreated).

#### Scenario: Layout is applied on first install

- **WHEN** Garage is installed for the first time and the documented layout commands are run
- **THEN** `garage status` reports the node as part of the cluster with assigned capacity
- **AND** `garage layout show` reports no pending layout changes

#### Scenario: S3 operations before layout are understood to fail

- **WHEN** an S3 request is made against a Garage node that has no committed layout
- **THEN** the request fails
- **AND** the operator documentation identifies the missing layout as the cause and points at
  the bootstrap procedure

### Requirement: The admin interface is not exposed outside the cluster

Garage's admin API and its CLI grant unrestricted control over buckets, access keys and cluster
layout. Only the S3 API is externally reachable (see the `garage-s3-edge` capability). The admin
endpoint SHALL NOT be published through any Ingress or otherwise routed from outside the
cluster; it is reached in-cluster or via `kubectl port-forward` / `kubectl exec`.

Any admin token SHALL be stored as a Kubernetes Secret sourced from a gitignored
`secrets.auto.tfvars` value, never committed to the repository.

#### Scenario: No ingress routes the admin endpoint

- **WHEN** all Ingress and IngressRoute resources in the cluster are inspected
- **THEN** none routes to the Garage admin port

#### Scenario: Admin credentials are not in version control

- **WHEN** the repository is searched for the Garage admin token and RPC secret
- **THEN** neither value appears in tracked files
- **AND** both are declared as Terraform variables supplied via the gitignored
  `tf/deps/secrets.auto.tfvars`
