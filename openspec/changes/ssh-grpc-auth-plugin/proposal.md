## Why

SSH access to a deployment is authenticated today by a password the Helm chart generates
and stores in the tenant's own namespace. That has to end: the SSH design
(`var/ssh_access.md` D7) puts every form of access behind a public key the user registers
once, which the account key store already provides. Nothing consumes those keys yet.

The question is what carries the decision. sshpiper's `kubernetes` plugin reads it from
`Pipe` custom resources, and resolves every Secret a `Pipe` names from the `Pipe`'s own
namespace — so a key-based swap built on that plugin has to materialize the answer as
cluster state: a routing object per deployment and a projection of each account's keys,
both owned by the reconciler because Helm cannot own an object outside the release's
namespace. That is two hand-rolled lifecycles, each needing a create path, a delete path
and a sweep for when the delete path fails, and a periodic rewrite of every projection
whose sole purpose is to catch a revocation that silently failed to land.

None of that state is necessary. sshpiper's plugin interface is gRPC, and a plugin is free
to answer from anywhere. `PublicKeyAuth` hands the plugin the SSH username and the public
key the client offered, and takes back the upstream address and the credential to present
there. Both halves of the decision are already rows in our database: `deployment.name` is
the SSH username, and `user_ssh_key` holds the account's keys. A plugin that answers from
those rows needs no `Pipe`, no projection, and no sweep, because there is no second copy
of the answer to fall out of step with the first.

This also settles revocation, which is the operation the whole design exists to get right.
Deleting the row is the revocation; there is nothing downstream of it to refresh, and no
window in which a removed key still opens a session.

**This change superseded `ssh-pipe-key-auth`,** which reached the same authentication
outcome through `Pipe` objects and key projections. The spike in section 1 of `tasks.md`
confirmed this approach, so that change has been deleted rather than archived — it was
never implemented.

## What Changes

- **A new platform component, the SSH auth resolver**, implements sshpiper's plugin gRPC
  service. On each connection it resolves the offered public key and the SSH username
  against the database and returns the upstream sidecar's address, or refuses.
- **sshpiperd runs its gRPC plugin** against that resolver instead of the `kubernetes`
  plugin. The plugin is selected by passing `grpc` as an argument, not through `PLUGIN` —
  see design.md fact 1.
- **Both authentication legs become key-based.** The client authenticates to the edge with
  a key registered on the owning account; the edge authenticates to the sidecar with a
  platform-held key. Password authentication leaves the path entirely.
- **The `Pipe` CRD leaves the platform.** No routing objects are created, by the chart or
  by the reconciler; the CRD install and the proxy's cluster-wide `pipes` RBAC are removed.
- **No key material is projected into the cluster.** An account's registered keys are read
  from the database at connection time and are never copied into a Secret.
- **The chart stops rendering the `Pipe` and stops generating a password.** The credentials
  Secret keeps the username, the sidecar's user configuration, and the platform's public
  key.
- **The SFTP credentials endpoint and panel stop returning a password**, and instead point
  the user at their registered keys.
- **The reconciler owns no new state.** It gains no object to create, delete, or sweep.
  It does gain one line: the platform's public key joins the `caelus.*` values it already
  injects, alongside `caelus.owner` and `caelus.plan`.

**BREAKING for existing users, and rolled out in a maintenance window.** Every SFTP
password stops working at once. A user with no registered public key loses file access to
every deployment until they register one. The passwords are deleted, not migrated.

## Capabilities

### New Capabilities

- `ssh-auth-resolver`: the component that answers sshpiper's per-connection authentication
  and routing question — what it resolves, from what, what it refuses, how it behaves when
  its dependencies are unavailable, and what its availability means for the SSH edge.

### Modified Capabilities

- `sftp-edge-routing`: the edge resolves routing and authentication through the plugin
  rather than from `Pipe` resources; password relay is removed and replaced by public-key
  authentication downstream and a platform-held key upstream.
- `sftp-chart-contract`: the chart no longer renders the `Pipe`, no longer generates a
  password, and the credentials Secret changes shape.
- `sftp-credentials-api`: the endpoint no longer returns a password.
- `sftp-credentials-ui`: the panel no longer shows a password and directs the user to their
  registered keys.

## Impact

**New component**

- The resolver: a gRPC service implementing `libplugin.SshPiperPlugin`, deployed per
  environment. It sits on the authentication path of every SSH connection, so its
  availability is the SSH edge's availability. It reads the platform database and holds the
  environment's upstream private key.

  It lives in `ssh-auth/`, self-contained and written in Go — the first Go in this
  repository. It couples to the platform's schema through one hardwired SQL statement
  rather than through the API's models; see design.md for why that trade goes this way
  here and not elsewhere.

**Platform infrastructure**

- `tf/app/sshpiper`: the container's args become `["grpc"]`, `PLUGIN` is dropped, and
  `SSHPIPERD_GRPC_ENDPOINT` is added; the `pipes` and
  `secrets` cluster role rules are dropped. One SSH keypair per environment for the
  upstream leg, beside the edge's existing host key.
- `tf/deps/sshpiper`: the `Pipe` CRD install is removed.

**Charts**

- `products/_lib/caelus-sftp` drops the `Pipe` and the generated password and carries the
  platform's public key. Version bump, re-vendor, and republish across the six consuming
  products, with the recorded chart version repointed for each — the same fan-out the
  reachability change went through.

**API and UI**

- The SFTP credentials read model loses its password field; the panel changes accordingly.

**Reconciler**

- One new values contributor, `caelus.sftp.platformPublicKey`, injected per environment
  from settings the way `caelus.owner` and `caelus.plan` already are. No new object, no
  new lifecycle, no reaper — which is the property this change is about.

**Operational**

- A one-off query, before the window, for users who would lose access — a question that
  expires with the rollout, so not a shipped command.

**Depends on**

- The account SSH key store, which is shipped and must be populated before this rolls out.

**Supersedes**

- `ssh-pipe-key-auth`, deleted after the spike confirmed this approach.
