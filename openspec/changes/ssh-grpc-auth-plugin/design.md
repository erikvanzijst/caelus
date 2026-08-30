## Context

See `proposal.md` § Why for motivation, and `var/ssh_access.md` D7–D9 for the access design
this implements. This change supersedes `ssh-pipe-key-auth`, which reached the same
authentication outcome by materializing it as cluster objects and has been deleted.

**This ships in a maintenance window**, and nothing here exists solely to smooth the
cutover — the same trade `ssh-pipe-key-auth` made, for the same reason.

Six facts, each read from the code or verified against the pinned release, shape the rest.

1. **sshpiperd dials an external gRPC service when `grpc` is passed as an argument.**
   `createNetGrpcPlugin` takes `--endpoint` / `SSHPIPERD_GRPC_ENDPOINT`, with either mTLS
   (`--cert` / `--key` / `--cacert`) or `--insecure`. Verified in
   `cmd/sshpiperd/grpc.go` at tag **v1.5.4** — the release already deployed
   (`farmer1992/sshpiperd:v1.5.4`), so nothing here implies an upgrade.

   **Not** `PLUGIN=grpc`. `PLUGIN` names an *executable* under the daemon's plugin
   directory or `$PATH`, and the image ships only `kubernetes` and `workingdir`; setting
   it to `grpc` exits with `no plugins found`. The gRPC plugin is reached by argument, and
   the environment variables above still apply. The spike found this first
   (`var/ssh_access.md` § gRPC plugin spike results, #1–2).
2. **One RPC carries the whole decision.** `PublicKeyAuth(PublicKeyAuthRequest) returns
   (PublicKeyAuthResponse)` receives `ConnMeta{user_name, from_addr, uniq_id}` plus
   `bytes public_key`, and returns an `Upstream{user_name, uri, ignore_host_key,
   oneof auth{...}}`. Authentication and routing are answered together, per connection
   (`libplugin/plugin.proto`, v1.5.4). `public_key` is the SSH wire blob — the base64 body
   of an `authorized_keys` line — so matching it against a stored key needs no parsing, and
   `uri` is parsed by `url.Parse`, so it must carry a scheme: `tcp://host:port`.
3. **The upstream credential is supplied inline, per connection.**
   `UpstreamPrivateKeyAuth{private_key}`, `UpstreamPasswordAuth{password}` and
   `UpstreamRemoteSignerAuth` are alternatives in the same `oneof`. Nothing about the
   credential has to exist as a cluster object.
4. **`ListCallbacks` advertises which RPCs the plugin implements**, and sshpiperd installs
   handlers only for those. A plugin that advertises only `PublicKeyAuth` makes password
   authentication structurally absent rather than merely unconfigured — confirmed by spike,
   both ways: advertising `PasswordAuth` as well brings password authentication back from
   the same binary and the same configuration.
5. **The decision is already two indexed rows.** `deployment.name` is the SSH username and
   `deployment.user_id` its owner (`api/app/models/core.py`); `user_ssh_key` carries
   `(user_id, fingerprint)` under a unique index (`api/app/models/ssh_key.py:23`). No
   schema change is required.
6. **The sidecar's usefulness peaks when the application is broken.** The SFTP Service
   sets `publishNotReadyAddresses: true` for exactly this reason, and `var/ssh_access.md`
   D17 records a live defect where a crash-looping pod lost file access. Whatever decides
   whether a deployment is reachable must not repeat it.

## Goals / Non-Goals

**Goals:**

- No password anywhere in the SSH path.
- The authorization answer has exactly one source, so no projection, sweep, or repair can
  be behind it.
- Revocation is the deletion of the row, with nothing downstream to refresh.
- No object whose lifecycle the reconciler has to own, and therefore no reaper.

**Non-Goals:**

- Continuity of access across the cutover. Passwords stop working; keys start working.
- Any mechanism whose only purpose is the transition.
- The `dev` profile, the shell, or database forwarding. This change swaps authentication
  for the access that exists today; `ssh-session-dispatcher` and `ssh-sidecar-image` build
  on the resolver later without changing it.
- SSH certificates, which would remove per-user resolution entirely and are unavailable to
  us (`var/ssh_access.md` D8).

## Decisions

### The resolver is consulted per connection and holds no state

The plugin answers from the platform database at the moment sshpiperd asks. There is no
projection to write, no cache to invalidate, and no object to garbage-collect, because
there is no second representation of the answer.

This is the decision the change exists for. The alternative — `ssh-pipe-key-auth`'s
`Pipe` objects plus per-account key projections — reaches the same authentication outcome
but has to keep two hand-rolled lifecycles in repair, and needs a periodic unconditional
rewrite of every projection whose sole purpose is catching a revocation that silently
failed to land. That backstop is not incidental: with a copy, a *surviving revoked key* is
the one failure nothing announces. Removing the copy removes the failure and the backstop
together.

### The resolver runs as a sidecar in the sshpiperd pod, over loopback

`SSHPIPERD_GRPC_ENDPOINT=127.0.0.1:<port>` with `SSHPIPERD_GRPC_INSECURE=true`. The
insecure flag is safe here precisely because the connection never leaves the pod's network
namespace.

This makes the resolver's availability *identical* to the edge's rather than merely
correlated with it, which is the honest shape of the dependency: the pod is up with both
containers or it is not serving SSH. It also removes a network hop from every
authentication, needs no NetworkPolicy, and needs no certificate management for a
credential-bearing service.

The alternative — a separate Deployment — buys independent scaling and restarts that the
edge does not need, and costs mTLS (sshpiperd supports client certs, so this is
configuration rather than code, but it is configuration that can be got wrong on an
internet-facing auth path) plus a NetworkPolicy plus a second thing to be down.

**The resolver must be listening before sshpiperd starts.** `ListCallbacks` is called at
startup and sshpiperd exits fatally if it fails — the spike hit this — so the resolver
runs as a native sidecar (an init container with `restartPolicy: Always`), which
Kubernetes starts to completion before the main container. Left as two ordinary
containers, an unlucky start order is a `CrashLoopBackOff` that resolves itself only by
restart, which is a poor way to learn about it.

### The resolver is Go, in a self-contained `ssh-auth/`

The contract is `plugin.proto` over plain gRPC, so the implementation language is free.
Go answers it in 386 lines with three direct dependencies — grpc, protobuf, pgx — and
ships as a static binary on `scratch`: **21.8 MB**, against 370 MB for the Python
equivalent even after trimming it to its own dependency group. The component sits in the
pod that terminates the platform's public SSH port, so what is in that pod matters more
here than anywhere else in the platform.

**This was decided the other way first, and the reasoning that overturned it is worth
keeping.** The original argument was that Python could import `api/app/models` and avoid a
second, independently-maintained description of the same two tables — the kind of second
copy this whole change exists to remove. That is a real cost, and it is paid: `ssh-auth`
hardwires one SQL statement against the platform's schema.

It is the right trade because the two cases are not alike. The projections this change
deletes were *derived state*, copied ahead of time and able to drift silently while
nothing announced it. A hardwired query is a *direct read* of the one source: when it
disagrees with the schema it fails immediately and loudly, and the tests run against the
real migrated database, so drift is a failed build rather than a revoked key that still
works. The schema it depends on — `deployment.name`, `deployment.namespace`,
`deployment.user_id`, `user_ssh_key.fingerprint` — is among the most stable in the
platform.

The alternative that made Python cheap was to stop shipping a second image and run the
resolver from the API's, which already exists and is already built. That is genuinely free
of new packaging machinery, and it is the reason not to take on a second image *unless*
the second image is dramatically leaner. At 21.8 MB against 370 MB, on the SSH edge's own
pod, it is.

### One upstream keypair per environment, held only by the resolver

The edge authenticates to every sidecar with a single per-environment key, provisioned in
Terraform beside the existing `tls_private_key.host_key`, mounted into the resolver, and
returned as `UpstreamPrivateKeyAuth`. The chart carries the public half.

Two alternatives were considered:

- **The chart's per-deployment password**, returned as `UpstreamPasswordAuth`. Now viable
  again — with no `Pipe`, nothing constrains where the credential lives, so Helm could go
  on owning it with nothing to reap. Rejected for cost, not for principle: the resolver
  would have to read a Secret from the tenant's namespace on every connection, which adds
  a Kubernetes API call to the authentication path and gives an internet-facing service
  cluster-wide secret-read permission. A per-environment key needs neither.
- **A per-deployment keypair.** Narrower blast radius, but reintroduces exactly the
  per-deployment credential lifecycle this change removes.

The single key's blast radius is bounded by what it reaches: sidecars, which hold no secret
material. Anyone holding it has what a tenant already has, for every tenant — which is why
it stays in the resolver's own pod and in Terraform state, and why rotating it is a
first-class operation rather than an afterthought (see Risks).

`UpstreamRemoteSignerAuth` would let the resolver sign for the upstream without the key
ever reaching sshpiperd's process. Not adopted now — within one pod it protects little —
but it is the reason this decision is cheap to tighten later.

### Reachability is an allowlist that includes `error`

A username resolves when its deployment's status is `ready` or `error`, and not when it is
`deleting`, `deleted`, `pending` or `provisioning`.

`error` is in the list deliberately. Fact 6: file access exists most urgently when the
application is broken, and excluding `error` would re-create D17's defect in a new place.
An allowlist rather than a denylist so that a status added later fails closed by default.

### The upstream host key is not verified, as today

The resolver sets `ignore_host_key: true` on every `Upstream`. This is not a new
concession: the chart's `Pipe` sets `ignore_hostkey: true` today, for the reason recorded
there — the sidecars regenerate their host keys on every start, so there is no stable key
to pin, and `SSHPIPERD_DROP_HOSTKEYS_MESSAGE` exists precisely so clients pin the edge's
key and never a sidecar's.

It has to be stated rather than left implicit, because the alternative is not "verify" but
"fail". The spike found that with `ignore_host_key: false` sshpiperd calls `VerifyHostKey`,
and a resolver that does not implement it fails the handshake outright. So the resolver
either sets the flag or implements the RPC; there is no third behavior, and the flag is
what preserves today's semantics exactly.

The upstream leg runs pod-to-pod inside the cluster under the tenant NetworkPolicy, which
admits only this environment's edge — the same containment that makes it acceptable now.

### One query, and it distinguishes every refusal

The resolution is a single statement: the deployment by username, left-joined to the
offered key's fingerprint on the owning account. One round trip, and the join key is a
unique index on both sides.

The join is *outer* rather than inner. An inner join answers "admit or not" in one row,
but no rows would then mean either "no such deployment" or "that key is registered
nowhere" — and the spec requires an operator to tell those apart even though the client
must not. `(k.id IS NOT NULL)` carries that distinction back without a second query.

It joins `deployment` straight to `user_ssh_key` on `user_id` rather than through `user`.
The extra hop returns identical rows and would put a table of email addresses into the
grant of a service on the public SSH port.

**The username is `deployment.name`, treated as globally unique.** The schema guarantees
only `(namespace, name)`, which is a defect in the username construction rather than
something the edge should paper over: an earlier draft of this component carried a
candidate-set loop and an `ambiguous_username` refusal, which is a lot of machinery to
handle a state that should not exist. The fix belongs at the source — the SSH username
should be the deployment's namespace, which already *is* globally unique — and is tracked
outside this change. Until then the query takes `LIMIT 1`, which is deterministic rather
than merely usually right.

### The resolver fails closed, and never caches

A resolver that cannot read the database refuses. It does not serve a previous answer, and
it holds no cache between connections — a cached admission is a revocation that has not
taken effect, which is the property this whole change buys.

The spike measured what not caching actually costs. sshpiperd invokes the callback **once
per key the client offers** — not twice per connection: the query and the signed attempt
for the same key resolve once. So the cost is one indexed lookup per offered key, and a
user whose agent holds several keys pays for each one sshpiperd is asked about before the
right one. That is an argument for logging refusals well, not for a cache.

One case multiplies it: when the *upstream* leg fails, sshpiperd retries and re-calls the
callback each time — seven calls for one connection during the spike, while the sidecar's
`authorized_keys` was unreadable. A broken upstream is therefore also a load event on the
database, which the statement timeout and bounded pool below already have to survive.

The resolver connects with a dedicated database role holding read-only access to just the
two tables it reads. It never decrypts anything and so never needs the keyring — the same
reasoning that keeps `caelus db-worker` out of it (`AGENTS.md` § Encrypted columns).

Building that grant minimally caught a real defect before it shipped. The obvious
implementation selects the deployment *entity*, which in the API's ORM eagerly joins the
user, both releases, both templates and the subscription — seven more tables in the grant,
to answer a question about five columns. A generous grant would have hidden it
indefinitely.

### The window stays, even though a staged rollout is now possible

Unlike `ssh-pipe-key-auth`, a coherent intermediate state *does* exist here: the sidecar
could trust the platform's public key while still accepting its generated password, and the
edge could be flipped to the gRPC plugin before or after. There is no racing pair of routing
objects to make it incoherent.

We take the window anyway. Staging it costs a transitional chart version, published across
six products and then republished to remove it — machinery built to be deleted, which is
the thing this repo's SSH work has consistently refused. Recorded here because it is a real
option: if the affected-user query in section 5 comes back large, staging is available and
does not require redesign.

### The `Pipe` CRD is removed after the window, not during it

Rollback from the window is repointing every product to its previous chart version and
setting `PLUGIN=kubernetes` back, which needs the CRD still installed. So `tf/deps/sshpiper`
is torn down in a later, separate step once the new path has settled.

## Risks / Trade-offs

- **A new component sits on the authentication path of every SSH connection** → mitigated
  by making it a sidecar, so it cannot be independently down, and by fail-closed behavior.
  It is a genuine addition to what must work; the offsetting deletion is two reconciler
  lifecycles and a periodic sweep.
- **The database becomes an SSH dependency** → a short statement timeout and a bounded
  pool, so a slow database refuses connections quickly instead of hanging the edge. The
  platform database being down already means the API and the reconciler are down; SSH
  joining that set is a widening of one outage, not a new one.
- **We now own an authorization decision in our own code** → previously it was expressed
  declaratively by which Secret a `Pipe` referenced. A bug in the query is a cross-tenant
  authorization bug. Mitigated by it being one query with adversarial tests for the
  cross-account and unowned-deployment cases, which is materially easier to test than a
  distributed projection was.
- **Rotating the upstream key is a fleet-wide reconcile** → every sidecar's trusted key
  changes, so a compromised key cannot be retired quickly. Mitigated by the key living only
  in the resolver's pod and Terraform state, and by `UpstreamRemoteSignerAuth` being
  available if that is later judged insufficient.
- **`plugin.proto` is versioned with sshpiper and visibly evolves** (`Upstream.host` and
  `Upstream.port` are already deprecated in favor of `uri`) → pin the sshpiperd image,
  vendor generated stubs, and regenerate as an explicit step of any upgrade. The proto is
  read at the pinned tag and nowhere else: an earlier draft of this document described
  fields from a later revision that v1.5.4 does not have.
- **sshpiperd calls `Logs`, a streaming RPC the resolver has no use for** → unimplemented,
  it is non-fatal but logs an error on every start. Implement it as a no-op stream, so the
  edge's log stays readable and a real error is not lost in a recurring one.
- **`kubectl get pipes -A` stops being a debugging affordance** → replaced by structured
  logging of every resolution decision and its cause, which the spec requires anyway so
  that operators can distinguish refusal causes clients cannot.
- **Six charts to republish and their recorded versions to repoint** → the same fan-out the
  reachability change went through, with the same trap: the three non-curated products are
  updated through operator action rather than a repository edit, so nothing in the diff
  shows if it is forgotten.
- **All SFTP passwords stop working at the window** → intended, and the reason the account
  key store shipped first. Mitigated by notice, by registering a key being self-service and
  effective without a redeploy, and by staging being available if the affected population
  turns out to be large.

## Migration Plan

The spike gates everything. Nothing else starts until the round trip is proven on dev, the
way D7 was proven for the `Pipe` path.

**Ahead of the window**, in any order, each safe on its own:

1. **Spike** a minimal resolver against sshpiperd v1.5.4 and a real deployment's sidecar,
   with one hard-coded account. Confirm `PublicKeyAuth` receives the username and key,
   that `Upstream` routes and authenticates, and that `ListCallbacks` suppresses password
   authentication. **Done** — `var/ssh_access.md` § gRPC plugin spike results; four
   findings are folded into the decisions above, and `ssh-pipe-key-auth` is deleted.
2. **Resolver**, complete and tested, and its read-only database role, which is additive
   and reaches nothing until something connects as it.
3. **Publish the resolver image**, and run the query for accounts that will lose access.
   Give those users notice.

**In the window**, and this is one switchover rather than three:

4. **Terraform**: the upstream keypair, the resolver as a container in the edge's pod, the
   `grpc` argument, and the `pipes`/`secrets` cluster role rules dropped.
5. **Chart**: drop the password, carry the platform public key, configure the sidecar for
   keys only. Version bump, re-vendor, republish, repoint every product — **and then move
   every existing deployment onto the new template**. A product's `template_id` governs
   new deployments only; `deployment.desired_template_id` pins a version and does not
   follow it. Publishing and repointing therefore change nothing about a running
   deployment, and a deployment left on the old chart has no platform key in its sidecar,
   so the edge cannot log in to it after step 4.
6. **API and UI**: password removed from the read model and the panel.

**Steps 4, 5 and 6 do not have a safe interval between them, and the order within the
window is 5 then 4 then 6.** An earlier draft of this plan had the Terraform ahead of the
window, which is wrong: the moment the edge switches to the resolver it authenticates
upstream with the platform's key, and a sidecar that has not yet been given that key
refuses it — every SFTP connection in the environment fails until the chart catches up.
Taking the chart first inverts that, because a sidecar trusting the platform key while it
still accepts its own password is a coherent state that breaks nothing. Removing the
password from the API before the edge stops accepting passwords would likewise strand
anyone who had not already saved theirs.

**After it settles**

7. Remove the `Pipe` CRD from `tf/deps/sshpiper`.

**Rollback**: repoint every product to its previous chart version, move every deployment
back onto it, and restore the `kubernetes` plugin, which returns the tenant-rendered
`Pipe` and its password on the next reconcile. A whole-fleet operation in a window, like the rollout. It depends on old chart
versions never having been overwritten, and on step 7 not having run yet.

## Open Questions

- **Whether refused attempts should be rate-limited at the edge.** sshpiperd chains plugins
  with `--`, so `failtoban` can sit in front of the resolver without either knowing about
  the other. Deferrable: it changes no requirement here and can be added later.
- **What the resolver's decision log retains, and for how long.** The spec requires
  operators be able to tell refusal causes apart; the retention window is an operational
  choice that does not affect the approach.
