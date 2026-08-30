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
      Operator-supplied rather than Terraform-generated, so the same key survives a lost
      state file. A variable validation rejects one key used for both environments.
      The public half is derived at the root with `tls_public_key` and passed to both
      modules — the edge for the private half, the caelus module for the value the
      reconciler injects into charts. Derived at the root rather than inside the sshpiper
      module because that module already depends on `module.caelus` for the resolver's
      database URL, so passing it back would be a cycle.
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

- [x] 4.1 Remove the password from the SFTP credentials read model and the endpoint, along
      with the namespace Secret read that served it. Verify no caller, administrator
      included, receives credential material, and that the endpoint reads no Secret.
      The username now comes from `deployment.name` — the Helm release name the chart
      configures the sidecar with — so the only cluster question left is whether the
      product exposes files at all, answered by the SFTP Service rather than the Secret.
- [x] 4.2 Convey in the response that authentication is by registered key, and make it
      determinable whether the owning account has any key at all. Verify both an account
      with keys and one without. `auth_method: "publickey"` and `account_has_ssh_key`,
      the latter reporting the *owner's* keys rather than the reader's — an administrator
      is asking whether this deployment can be connected to.
- [x] 4.3 Update the panel: no password field, a statement that access uses a registered SSH
      key, and a link to where keys are managed. Verify no masked-but-empty field remains
      and that nothing presents the absent password as a failure.
- [x] 4.4 When the owning account has no registered key, make that the panel's prominent
      instruction. Verify against an account with none. It sits above the details as a
      warning; the details stay visible because they are correct, just unusable yet.
- [x] 4.5 Update `caelus` parity for the changed read model. It echoes the same model, so
      parity is structural; the command gained the docstring that says why there is no
      credential to report.

## 5. Before the window

- [x] 5.1 Query for accounts owning an SFTP-capable deployment that hold no registered SSH
      key — the accounts that will lose access. A one-off query, not a shipped command: the
      question expires with the rollout. Record the result. Do this for both dev and prod.

      Run 2026-08-30, taking SFTP-capability from the cluster (namespaces holding a
      `caelus.dev/component=sftp` Service) rather than from product names:

      | | SFTP deployments | owners | with a key | **losing access** |
      |---|---|---|---|---|
      | dev | 5 | 2 | 2 | **0** |
      | prod | 5 | 2 | 1 | **1** |

      One account, `mail@timberkelaar.nl`, owning `immich-7tgixq` on prod. A hard cutover
      is fine at this size.

      Two namespaces hold an SFTP Service with no deployment row in either database —
      `erik-van-zijst-gmail-z2okvsizf` (`hello-world-kca6uu`) and `user-example-com-pfxg97ifx`
      (`hello-world-w8ngu6`), both with running pods. Pre-existing orphans, unrelated to
      this change and the kind `orphan_tick` reports. They stop being routable at the
      cutover, since the resolver refuses a username naming no deployment.

## 6. In the window: the chart drops the password

- [x] 6.1 In `products/_lib/caelus-sftp`, stop rendering the `Pipe` and stop generating a
      password: remove the `lookup`-stable password helper, the password field, and the
      password from the sidecar's user configuration. Verify the rendered output contains
      no `Pipe` and no password.
- [x] 6.1a Remove the `internalUser` parameter, fixing the sidecar's user to the release
      name. The resolver derives the upstream username from `deployment.name` and reads no
      cluster object to learn it, so a chart that could name that user something else would
      produce a deployment the edge cannot log in to. No product overrides it today, so
      this removes an option rather than changing any behavior.
- [x] 6.2 Carry the platform's public key into the credentials Secret and configure the
      sidecar for key-only authentication, mounting it through atmoz's
      `/home/<user>/.ssh/keys/*.pub` convention rather than writing `authorized_keys`
      directly — the entrypoint fixes the ownership sshd requires, and a root-owned file
      fails the login with nothing but `[preauth]` in the log
      (`var/ssh_access.md` § gRPC plugin spike results). Verify the sidecar refuses password
      authentication and that the Secret contains no private key and no user's key.
      Verified by building a sidecar from the chart's own rendered output: the platform
      key logs in, another key is refused, and sshd offers only `publickey`. The empty
      password field is what disables password login — `usermod -p "*"` — and `:e:` would
      **not** have worked: `e` is atmoz's *encrypted* flag, so it would have set a literal
      password of `"e"`. `PasswordAuthentication no` is appended to the sshd config as
      well, so password auth is unavailable rather than merely unusable.
      The key reaches the chart as `caelus.sftp.platformPublicKey`, injected per
      environment by the reconciler beside `caelus.owner` and `caelus.plan`, since it is
      per-environment and the catalog is shared. Rendering fails without it.
      `CAELUS_SFTP_PLATFORM_PUBLIC_KEY` is set in `tf/app/caelus`'s ConfigMap from the
      root's derived public key, so the value the charts render is the same one the edge
      holds the private half of, by construction rather than by copying.
- [x] 6.3 Bump the library chart, re-vendor into all six consuming products, bump and
      republish each. **Never re-push an existing version** — rollback depends on the old
      versions being intact. Verify each by pulling it back.
      Library `0.2.0` → `0.3.0`, re-vendored into all six, each product bumped and pushed
      to `oci://registry.home/helm`: helloworld `0.1.13`, immich `0.1.6`, lemmy `0.4.2`,
      mattermost `1.0.14`, nextcloud `0.1.11`, vaultwarden `3.3.2`. The push checked the
      registry's tag list first and would have refused an existing version. Each was
      pulled back and confirmed to bundle `caelus-sftp 0.3.0` with no `Pipe`.

- [x] 6.4 Repoint the recorded chart version for each product: catalog entries for the
      curated ones, and the `ProductTemplateVersion` for `helloworld`, `lemmy` and
      `mattermost` — an operator action that will not appear in the diff.
      Catalog entries repointed in the repo (immich `0.1.6`, nextcloud `0.1.11`,
      vaultwarden `3.3.2`), applied to each environment by the API image's catalog init
      container. **Dev** non-curated products done by hand: new template rows inserted and
      `product.template_id` repointed — Hello World → 69 (`0.1.13`), Mattermost → 68
      (`1.0.14`), Lemmy → 67 (`0.4.2`). Insert-and-repoint rather than mutating a row,
      matching `CatalogReconciler._resolve_template`. **Prod not done.**
- [x] 6.4a Move every existing SFTP deployment onto its product's new template.
      Repointing a product only affects *new* deployments: `deployment.desired_template_id`
      pins a version and does not follow `product.template_id`. All five SFTP deployments
      on dev are on older charts — and `vaultwarden-zus6ha` was already one version behind
      before this change, so this is a standing property of the platform rather than
      something this change introduced.
      Until each is moved, its sidecar still has the old password-based configuration and
      no platform key, so the edge cannot log in to it once section 3 is applied. Each
      needs `caelus update-deployment --user-id … --deployment-id … --desired-template-id …`
      (the API's `PUT` equivalent) to queue a reconcile onto the new chart.
      **This is part of the window, and the whole fleet must be moved before section 3.**

- [x] 6.5 Extend the chart render test to assert the absence of a `Pipe` and of any
      password, so a future refactor cannot reintroduce either silently. Also asserts the
      key is mounted through atmoz's queue directory, that password auth is disabled in
      the sshd config, and that a render without the platform key fails.

## 7. Verification

Run against dev on 2026-08-30, after the cutover. Prod is still on the `kubernetes`
plugin, which is the only reason 7.7 and section 8 remain open.

- [x] 7.1 On dev, end to end: register a key, connect over SFTP with it, list and download a
      file. Verify the deployment's namespace holds no password and no private key.
      A key registered seconds earlier opened `immich-8ha8qg` with no reconcile and no
      redeploy; listed the library tree and downloaded an 18.7 MB backup that verified as
      valid gzip. A write was refused, so read-only holds. **The namespace does still hold
      a password — see 7.6.**
- [x] 7.2 Verify a key not registered on the owning account is refused, and that a key
      registered on a *different* account is refused against this deployment.
      Both refused, `Permission denied (publickey)`, logged as `cause=key_not_registered`.
- [x] 7.3 Verify revocation: remove the key, confirm the next connection is refused, with no
      deployment change, no reconcile and no cluster write in between.
      Refused on the next attempt. Across the revocation the Helm revision (9), the
      credentials Secret's `resourceVersion` (6078227), the reconcile-job count (156) and
      the deployment's `generation` (8) were all unchanged.
- [x] 7.4 Verify deletion: delete a deployment and confirm its username stops resolving,
      with no routing object having existed to remove.
      Verified in the stronger form the cluster happened to offer: `hello-world-kca6uu` has
      no deployment row but still has a live `Pipe` **and** a live Service. It is refused
      with `cause=unknown_username` — the routing object is present and irrelevant, which
      is the property this change is really about. A create-and-destroy cycle on dev was
      not run: it provisions and then destroys real tenant resources, and the above
      establishes the same thing without doing so.
- [x] 7.5 Verify environment separation both ways: a prod username presented to the dev edge
      does not resolve, and the tenant NetworkPolicy still admits only its own environment's
      proxy.
      Four prod usernames (`immich-uqjcqc`, `nextcloud-yu50v2`, `lemmy-1c4lsj`,
      `immich-7tgixq`) all refused at the dev edge as `unknown_username`. A dev tenant's
      NetworkPolicy admits `sshpiper-dev` on 2222; a prod tenant's admits `sshpiper`.
- [~] 7.6 Verify no tenant namespace holds a password, a private key, or any user's public
      key — sweep the namespaces rather than checking one.
      No private key and no user key anywhere. **Every SFTP Secret still holds a
      `password`, including the four dev deployments already upgraded to the new charts.**
      This is a `stringData` merge trap, not a chart error: the API server folds
      `stringData` into `data`, so Helm's three-way merge computes "remove
      `stringData.password`" against a live object that has no `stringData` field, and
      `data.password` survives. Proven in a scratch namespace, along with the fact that
      neither switching the template to `data`/`b64enc` nor `helm upgrade --force` fixes
      it; only renaming the Secret does, because Helm deletes an object dropped from the
      manifest. The leftover is inert — sshd has `PasswordAuthentication no` and the
      account's password is disabled — but it is stale credential material in a tenant
      namespace, which the `sftp-chart-contract` spec says must not be there. Fix pending
      a decision: see 7.6a.
- [x] 7.6a Decided not to remove the stale `password` key from already-upgraded Secrets.
      It is inert — sshd refuses password authentication and the account's password is
      disabled — and the two ways to clear it are a chart rename with another six-product
      fan-out, or a one-off patch across tenant namespaces. Neither buys anything a reader
      of the Secret could use. Left in place deliberately; new deployments never get one,
      so the population only shrinks.

- [~] 7.7 Verify no `Pipe` exists anywhere in either environment and that nothing recreates
      one on the next reconcile of an existing deployment.
      **Dev holds none.** Every dev deployment is on a new chart, and Helm deleted each
      `Pipe` as it went — the object leaves the manifest, so Helm removes it, which is
      exactly what does *not* happen for a key inside a Secret (7.6). Nothing recreates
      one: an upgraded release's manifest contains no `Pipe`.
      Seven remain cluster-wide, all outside dev's control: five in prod, which has not
      been cut over, and the two orphans with no deployment row, which nothing manages.
      Closes when prod does.

## 8. After the window settles

- [x] 8.1 Remove the `Pipe` CRD install from `tf/deps/sshpiper`, once rollback is no longer
      wanted (design.md § *The `Pipe` CRD is removed after the window*). Verify the CRD is
      gone and SSH is unaffected.
      Applied after 8.1a. `pipes.sshpiper.com` no longer exists and the resource cannot be
      listed at all; the three remaining `Pipe` objects went with it by cascade. Both edges
      run the resolver and no ClusterRole grants `pipes` anywhere.
- [x] 8.1a Repoint the Lemmy product to chart `0.4.2` on prod and move `lemmy-1c4lsj` onto
      it. Lemmy is database-authored, not curated, so the catalog init container never
      touched it and it was missed when the curated products were updated — the only
      product in either environment still on a pre-cutover chart, and its SFTP was broken
      from the cutover until this landed. Now on `0.4.2`, with `authorized_keys` owned by
      the SFTP user and the account's password disabled.

## 9. Documentation

Follows `AGENTS.md` § Documentation Layering: terse orientation plus links, no
restating what a spec or design document already carries.

- [x] 9.1 Update `AGENTS.md`: link to the appropriate openspec files regarding
      authentication, routing, account keys. The account-keys bullet no longer says
      nothing consumes them; a new bullet covers per-connection resolution.
- [x] 9.2 Update the `sftp-edge-routing` main spec's `## Purpose`, which still describes
      `Pipe` custom resources and password relay — a delta cannot change it.
      The requirements below it still describe `Pipe`s, correctly: the deltas replace them
      on archive, and only `## Purpose` is unreachable by one.
- [x] 9.3 Update `products/_lib/caelus-sftp/README.md`: no `Pipe`, no password, the platform
      public key's role, and that the release now contains everything the deployment
      contributes to SSH access.
- [x] 9.4 Update `tf/app/README.md` with openspec links for the resolver, the upstream keypair, and the
      `grpc`-argument wiring.
- [x] 9.5 Update `api/README.md` and `ui/README.md` for the changed read model and panel.
      `api/README.md` documents no SFTP endpoint of its own, so the account-keys section
      was the only thing to correct. `ui/README.md` gained a file-access panel section and
      the three SFTP components in its map, which it had never listed.
- [x] 9.6 Document the resolver in its own README: the proto pin and regeneration step, the
      fail-closed posture, the database role, and how to rotate the upstream keypair.
      Rewritten: the first draft argued the design — why the join is outer, why `error` is
      reachable, why loopback — which is design.md's job. It now orients and links, and
      keeps the operational half (configuration, the role, rotation, codegen, releasing).
