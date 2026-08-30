## 1. Spike: prove the round trip before anything else

Nothing below section 1 started until 1.4 passed. This section was the gate on the whole
change, and on deleting `ssh-pipe-key-auth`. **It passed on 2026-08-30**; the findings are
in `var/ssh_access.md` § gRPC plugin spike results and are folded into `design.md`.

- [x] 1.1 Stand up a minimal `SshPiperPlugin` gRPC server implementing only
      `ListCallbacks` and `PublicKeyAuth`, with one hard-coded account key and one
      hard-coded upstream. Verify sshpiperd connects to it with `SSHPIPERD_GRPC_ENDPOINT`
      and `SSHPIPERD_GRPC_INSECURE=true`. **`PLUGIN=grpc` does not work** — it names an
      executable and the image ships only `kubernetes` and `workingdir`; the plugin is
      selected by passing `grpc` as an argument.
- [x] 1.2 Verify `PublicKeyAuth` receives the SSH username in `ConnMeta.user_name` and the
      offered key in `public_key`, and record how many times it is called per connection.
      **Once per key the client offers**, not twice per connection; a failing upstream
      makes sshpiperd retry and re-call it.
- [x] 1.3 Verify an `Upstream` carrying `uri` and `UpstreamPrivateKeyAuth` both routes to a
      real deployment's SFTP sidecar and authenticates to it, with the sidecar's
      `authorized_keys` holding only the platform's public key. Confirm the sidecar logs
      `Accepted publickey`. Done against `hello-world-tyfim9` on dev; the key was removed
      afterwards and nothing else in the cluster was touched.
- [x] 1.4 Verify that advertising only `PublicKeyAuth` in `ListCallbacks` makes password
      authentication unavailable at the edge — a password attempt must fail regardless of
      the password supplied. Verified, and controlled for by advertising `PasswordAuth` as
      well and watching password authentication return.
      **Gate passed: `openspec/changes/ssh-pipe-key-auth/` is deleted.**
- [x] 1.5 Record the spike's findings in `var/ssh_access.md` beside D7's results, including
      anything that contradicts this design, and revise the design before continuing.
      Fifteen results recorded; four changed the design (invocation, call count, host-key
      handling, container start ordering).

## 2. The resolver

Implemented in Go, self-contained under `ssh-auth/` (design.md § *The resolver is Go, in
a self-contained `ssh-auth/`*). A first pass in Python was written, measured and
discarded; the reasoning is recorded in that section rather than lost.

- [x] 2.1 Vendor `plugin.proto` pinned to the deployed sshpiperd version and generate the
      stubs into the repo. Verify a regeneration from the pinned file reproduces the
      checked-in stubs byte for byte, so drift is a test failure rather than a surprise.
      `ssh-auth/gen.sh` fetches a pinned protoc and both plugins into a gitignored
      `.tools/`, so the comparison is against one toolchain rather than whichever one the
      machine happens to have.
- [x] 2.2 Implement `ListCallbacks` advertising `PublicKeyAuth` only. Verify by test that
      no other authentication callback is advertised, and that the edge offers only
      public-key authentication.
- [x] 2.3 Implement the resolution query — **one statement**, left-joining the offered
      key's fingerprint to the account owning the deployment named by the username
      (design.md § *One query, and it distinguishes every refusal*). Verify by test that the
      owner's key is admitted, another account's key is refused, an unregistered key is
      refused, and a username naming no deployment is refused.
- [x] 2.4 Gate on deployment status with an allowlist of `ready` and `error`
      (design.md § *Reachability is an allowlist that includes `error`*). Verify a
      crash-looping deployment in `error` is still reachable — this is the D17 defect and
      must be a test — and that `deleting`, `deleted`, `pending` and `provisioning` are not.
- [x] 2.5 Return the upstream as `uri` (scheme included — `tcp://host:port`) plus
      `UpstreamPrivateKeyAuth` from the mounted per-environment key, with
      `ignore_host_key: true` (design.md § *The upstream host key is not verified, as
      today*). Verify the key is read from the mount, that no client-supplied material
      reaches the upstream, and that a connection succeeds without `VerifyHostKey` being
      implemented.
- [x] 2.6 Implement `Logs` as a no-op stream so the edge does not log an error on every
      start (design.md Risks). Verify a clean startup log.
- [x] 2.7 Make every refusal uniform to the client whatever its cause, and log the cause
      server-side. Verify an unknown username and an unregistered key are indistinguishable
      to the client, and that the log distinguishes them.
- [x] 2.8 Fail closed: refuse when the database is unreachable, hold no cross-connection
      cache, and never reuse a prior answer. Verify with the database stopped that
      connections are refused, and that a previously admitted key is refused on a new
      connection.
- [x] 2.9 Bound the database dependency with a dedicated read-only role limited to the
      tables read, a short statement timeout, and a bounded pool. Verify the role cannot
      write, cannot read tables outside its grant, and that a slow query refuses rather
      than hangs.
      The narrow grant caught a real problem: `DeploymentORM` eagerly joins the user, both
      releases, both templates and the subscription, so selecting the entity would have
      needed seven more tables in the grant. The query selects columns instead.
- [x] 2.10 Package the resolver image, pinned and never re-pushed, and add its health to the
      platform's monitoring as a user-facing SSH dependency. Verify a failing resolver
      surfaces as an SSH edge outage distinguishable from clients presenting bad keys.
      A second image only earns its keep by being dramatically leaner than free-riding the
      API's, which already exists: 21.8 MB of static Go binary on `scratch` against 370 MB
      of Python. Immutable tag from `ssh-auth/VERSION`, never re-pushed.

## 3. Platform infrastructure

**Written now, applied in the window, and after section 6.** Applying this is the moment
the edge starts authenticating upstream with the platform's key, which a sidecar that has
not yet been given that key refuses — so every SFTP connection in the environment fails
until the chart catches up (design.md § Migration Plan). Nothing here is safe to apply on
its own.

The exception is 3.1's Secret, which nothing reads until 3.3 lands.

- [x] 3.1 Provision one SSH keypair per environment in `tf/app`, beside the edge's existing
      host key. Verify both environments have distinct keys and that neither private half
      appears in any tenant namespace. The keypair must be in `secrets.auto.tfvars`.
      Operator-supplied rather than Terraform-generated, because the chart carries the
      public half and Terraform does not own the chart; `terraform output -raw
      sshpiper_upstream_public_key` derives it so the two cannot drift. A variable
      validation rejects one key used for both environments.
- [x] 3.2 Run the resolver as a sidecar in the sshpiperd pod and point sshpiperd at it over
      loopback (design.md § *The resolver runs as a sidecar*). Ordering is not optional:
      sshpiperd calls `ListCallbacks` at startup and exits fatally if the resolver is not
      yet listening. A native sidecar (an init container with `restartPolicy: Always`)
      would express that best, but the pinned Kubernetes provider has no `restart_policy`
      on `init_container` and moving to 3.x for it is not this change's business — so the
      edge waits on the loopback port before exec'ing the daemon. Verify the pod starts
      cleanly from cold and that the gRPC endpoint is not reachable from outside the pod.
- [x] 3.2a Give the resolver container a `grpc` readiness probe against
      `grpc.health.v1`, which it answers from a real database query. This is what the
      `SshResolverNotReady` alert added in 2.10 keys on, so without the probe the alert
      can never fire. Deliberately no liveness probe: restarting fixes no database
      outage, and would take sshpiperd down with the pod.
      **An `exec` probe, not Kubernetes' native `grpc` one.** That is dialed at the pod
      IP, which a loopback-only listener can never answer — it failed exactly that way on
      the first dev apply. The bind is load-bearing: `PublicKeyAuth` returns the upstream
      private key to any caller naming a deployment and a public key registered on its
      owner, so pod-IP reachability would be an escalation to the fleet-wide credential.
      The binary answers `-healthcheck` for the probe to exec inside the container.
- [x] 3.3 Switch each environment to the gRPC plugin — container args `["grpc"]`, the
      `PLUGIN` entry removed from the ConfigMap — and drop the `pipes` and `secrets` rules
      from the proxy's ClusterRole. The ClusterRole and its binding are gone entirely, and
      the service account token is no longer mounted: the daemon needs nothing from the
      Kubernetes API now. Verify the proxy can no longer read Secrets or Pipes and that SSH
      still works end to end — **the end-to-end half is section 7, in the window.**

## 4. API and UI

- [ ] 4.1 Remove the password from the SFTP credentials read model and the endpoint, along
      with the namespace Secret read that served it. Verify no caller, administrator
      included, receives credential material, and that the endpoint reads no Secret.
- [ ] 4.2 Convey in the response that authentication is by registered key, and make it
      determinable whether the owning account has any key at all. Verify both an account
      with keys and one without.
- [ ] 4.3 Update the panel: no password field, a statement that access uses a registered SSH
      key, and a link to where keys are managed. Verify no masked-but-empty field remains
      and that nothing presents the absent password as a failure.
- [ ] 4.4 When the owning account has no registered key, make that the panel's prominent
      instruction. Verify against an account with none.
- [ ] 4.5 Update `caelus` parity for the changed read model.

## 5. Before the window

- [ ] 5.1 Query for accounts owning an SFTP-capable deployment that hold no registered SSH
      key — the accounts that will lose access. A one-off query, not a shipped command: the
      question expires with the rollout. Record the result.
- [ ] 5.2 If that population is large enough to make a hard cutover unacceptable, revisit
      the staged rollout the design keeps available (§ *The window stays*) before
      proceeding. Otherwise record the decision to proceed with the window.
- [ ] 5.3 Give affected users notice: passwords stop working, register a key, here is how.
      This is the gate on section 6.

## 6. In the window: the chart drops the password

- [ ] 6.1 In `products/_lib/caelus-sftp`, stop rendering the `Pipe` and stop generating a
      password: remove the `lookup`-stable password helper, the password field, and the
      password from the sidecar's user configuration. Verify the rendered output contains
      no `Pipe` and no password.
- [ ] 6.1a Remove the `internalUser` parameter, fixing the sidecar's user to the release
      name. The resolver derives the upstream username from `deployment.name` and reads no
      cluster object to learn it, so a chart that could name that user something else would
      produce a deployment the edge cannot log in to. No product overrides it today, so
      this removes an option rather than changing any behavior.
- [ ] 6.2 Carry the platform's public key into the credentials Secret and configure the
      sidecar for key-only authentication, mounting it through atmoz's
      `/home/<user>/.ssh/keys/*.pub` convention rather than writing `authorized_keys`
      directly — the entrypoint fixes the ownership sshd requires, and a root-owned file
      fails the login with nothing but `[preauth]` in the log
      (`var/ssh_access.md` § gRPC plugin spike results). Verify the sidecar refuses password
      authentication and that the Secret contains no private key and no user's key.
- [ ] 6.3 Bump the library chart, re-vendor into all six consuming products, bump and
      republish each. **Never re-push an existing version** — rollback depends on the old
      versions being intact. Verify each by pulling it back.
- [ ] 6.4 Repoint the recorded chart version for each product: catalog entries for the
      curated ones, and the `ProductTemplateVersion` for `helloworld`, `lemmy` and
      `mattermost` — an operator action that will not appear in the diff.
- [ ] 6.5 Extend the chart render test to assert the absence of a `Pipe` and of any
      password, so a future refactor cannot reintroduce either silently.

## 7. Verification

- [ ] 7.1 On dev, end to end: register a key, connect over SFTP with it, list and download a
      file. Verify the deployment's namespace holds no password and no private key.
- [ ] 7.2 Verify a key not registered on the owning account is refused, and that a key
      registered on a *different* account is refused against this deployment.
- [ ] 7.3 Verify revocation: remove the key, confirm the next connection is refused, with no
      deployment change, no reconcile and no cluster write in between.
- [ ] 7.4 Verify deletion: delete a deployment and confirm its username stops resolving,
      with no routing object having existed to remove.
- [ ] 7.5 Verify environment separation both ways: a prod username presented to the dev edge
      does not resolve, and the tenant NetworkPolicy still admits only its own environment's
      proxy.
- [ ] 7.6 Verify no tenant namespace holds a password, a private key, or any user's public
      key — sweep the namespaces rather than checking one.
- [ ] 7.7 Verify no `Pipe` exists anywhere in either environment and that nothing recreates
      one on the next reconcile of an existing deployment.

## 8. After the window settles

- [ ] 8.1 Remove the `Pipe` CRD install from `tf/deps/sshpiper`, once rollback is no longer
      wanted (design.md § *The `Pipe` CRD is removed after the window*). Verify the CRD is
      gone and SSH is unaffected.

## 9. Documentation

- [ ] 9.1 Update `AGENTS.md`: SSH authentication and routing are resolved per connection by
      the resolver from the platform database; no routing objects exist; SSH access is
      authenticated by account keys; the reconciler owns nothing for this feature. Add
      `caelus ssh-resolver` to the CLI-parity exception list beside the workers — it is a
      process, not a request, and has no REST equivalent by design.
- [ ] 9.2 Update the `sftp-edge-routing` main spec's `## Purpose`, which still describes
      `Pipe` custom resources and password relay — a delta cannot change it.
- [ ] 9.3 Update `products/_lib/caelus-sftp/README.md`: no `Pipe`, no password, the platform
      public key's role, and that the release now contains everything the deployment
      contributes to SSH access.
- [ ] 9.4 Update `tf/app/README.md` with the resolver, the upstream keypair, and the
      `grpc`-argument wiring (and why it is not `PLUGIN`); note the removed CRD in
      `tf/deps/`.
- [ ] 9.5 Update `api/README.md` and `ui/README.md` for the changed read model and panel.
- [ ] 9.6 Document the resolver in its own README: the proto pin and regeneration step, the
      fail-closed posture, the database role, and how to rotate the upstream keypair.
