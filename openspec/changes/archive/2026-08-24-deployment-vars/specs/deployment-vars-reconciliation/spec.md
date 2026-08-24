## Purpose

Defines how a release's frozen vars reach the running pod: one Kubernetes Secret per
deployment, referenced from the Helm values by name only, with the tenant's variables
never able to displace what the platform injects.

## ADDED Requirements

### Requirement: A release's vars are materialized into a Kubernetes Secret
When reconciling a deployment, the reconciler SHALL read the snapshot of the release it
is applying, decrypt it, and write a Kubernetes Secret in the deployment's own namespace
containing each var's key and plaintext value. The Secret SHALL be written before the
chart is installed or upgraded, so no pod ever starts expecting a Secret that is not
there.

The Secret's name SHALL identify the **release**, not merely the deployment, so that a
rollout which fails and is rolled back leaves the previous release's Secret untouched.

The Secret is written before the chart runs and is not part of the Helm release, so a
rollback does not revert it. Were one Secret shared across releases, a failed rollout
would leave the reverted pod specification paired with the failed release's values: no
running pod would change, because environment variables are resolved once at container
start, but the next pod created for any reason would silently start with configuration
the platform does not report as applied.

#### Scenario: A release with vars is applied
- **WHEN** the reconciler applies a release whose snapshot holds three vars
- **THEN** a Secret in the deployment's namespace holds those three keys and values
- **AND** it is written before the chart is applied

#### Scenario: A second release changes one var
- **WHEN** a later release changes one var's value
- **THEN** that release's vars are written to a Secret of its own
- **AND** the pod specification names it, so the rollout replaces the running pod

#### Scenario: A rollout fails and is rolled back
- **WHEN** applying a release with changed vars fails and the chart is rolled back
- **THEN** the Secret the restored pod specification names still holds the values of the
  release that is applied
- **AND** no pod started afterwards receives the failed release's values

### Requirement: Superseded var Secrets are removed after a successful apply
Once an apply succeeds, the reconciler SHALL delete every var Secret belonging to that
deployment except the one the applied release names, so that per-release naming does not
accumulate objects in the tenant's namespace without bound.

Removal SHALL happen only after a **successful** apply: a failed one is rolled back onto
the previous release, whose Secret the running pod specification still names.

Removal SHALL be scoped to the deployment rather than to the namespace, and a failure to
remove SHALL NOT fail the rollout — an unremoved Secret is unreferenced, and the next
successful apply removes it.

#### Scenario: A third release supersedes the second
- **WHEN** a release is applied successfully and earlier releases' var Secrets exist
- **THEN** only the applied release's var Secret remains

#### Scenario: An apply fails
- **WHEN** an apply fails
- **THEN** no var Secret is removed

#### Scenario: The applied release has no vars
- **WHEN** a release whose snapshot is empty is applied successfully
- **THEN** every earlier var Secret for that deployment is removed
- **AND** no new one is created

#### Scenario: Removal fails
- **WHEN** deleting a superseded Secret fails
- **THEN** the rollout still reports success

### Requirement: Var values never travel through the Helm values
The reconciler SHALL project only the **name** of the Secret into the merged Helm
values, under the platform-controlled `caelus` namespace. A var's value MUST NOT appear
in the Helm values document under any key.

Merged values are logged in full and are persisted by Helm into a release object inside
the tenant's own namespace, so a value routed through them would reach the log
aggregator and a tenant-visible object on every reconcile.

#### Scenario: Values are absent from the merged values
- **WHEN** the reconciler builds the merged values for a deployment with vars
- **THEN** the values contain the Secret's name
- **AND** they contain no var value

### Requirement: A deployment with no vars produces no Secret and no values block
When a release's snapshot is empty, the reconciler SHALL create no Secret and SHALL emit
no vars block into the merged values at all, rather than an empty Secret or an empty
block. A chart that requires vars then fails visibly rather than rendering an
environment that silently provides nothing.

#### Scenario: A deployment with no vars
- **WHEN** the reconciler applies a release whose snapshot is empty
- **THEN** no vars Secret exists for that deployment
- **AND** the merged values carry no vars block

### Requirement: Platform-injected environment variables take precedence over vars
A chart consuming the vars Secret SHALL do so in a way that platform-provided
environment variables win over a tenant's var of the same name: the vars Secret SHALL be
ordered ahead of any platform-provided source, and variables the platform sets
explicitly SHALL remain explicit.

This is defense in depth alongside the reserved-name rejection in `deployment-vars-api`;
neither is a privilege boundary, since a tenant shadowing their own pod's variables harms
only their own pod, but the failure it prevents is confusing and hard to diagnose.

#### Scenario: A var colliding with a platform credential
- **WHEN** a var somehow carries the same name as a platform-injected object-storage
  credential
- **THEN** the pod receives the platform's value

### Requirement: A reconcile that cannot decrypt a snapshot fails without writing
If any var in the release's snapshot cannot be decrypted, the reconciler SHALL fail the
reconcile with an error naming the missing key identifier, and SHALL NOT write a Secret,
partial or otherwise.

Starting a pod with only some of its variables is worse than not starting it, and far
harder to diagnose.

#### Scenario: An unavailable encryption key
- **WHEN** a snapshot names an encryption key the worker does not hold
- **THEN** the reconcile fails with an explicit error
- **AND** no Secret is written or updated
