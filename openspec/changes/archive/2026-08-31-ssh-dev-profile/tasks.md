## 1. Disambiguate the two `_lib` artifacts, then rename the convention

`products/_lib` holds two different kinds of thing whose names are about to converge: a
Helm library chart and a container image build context. Both directory names are made to
say which is which before anything else changes.

- [x] 1.1 Rename the **image build context** `products/_lib/ssh-sidecar` to
      `products/_lib/ssh-sidecar-image`, updating the `--ssh-sidecar` target in
      `scripts/build-images.sh`, the CI step that publishes it, and every path reference in
      its README and in the docs. The image's own name and published tag are unchanged —
      only the directory holding its build context moves. Verify a clean build and that CI
      still publishes exactly when `VERSION` names an unpublished version.
- [x] 1.2 Rename the **library chart** `products/_lib/caelus-sftp` to
      `products/_lib/ssh-sidecar-chart`, setting the chart's `name:` to `ssh-sidecar` and
      renaming its named templates `caelus-sftp.*` → `ssh-sidecar.*`. Update the
      `dependencies:` entry, the `repository: file://` path and the vendored archive in each
      of the six consumers. Verify `helm lint` passes on the library and every consumer
      renders.
- [x] 1.3 Move rendered resource names from `-sftp` to `-ssh`: the Service, the credentials
      Secret and the scripts ConfigMap. Verify the rendered output names, and note that the
      Secret rename is what clears the inert `password` key the previous change could not
      remove (design.md § *The naming convention moves to `-ssh`*).
- [x] 1.4 Split the library into two helper sets, `ssh-sidecar.sftp.*` and
      `ssh-sidecar.dev.*`, sharing one `ssh-sidecar.service` helper. There is no `profile`
      parameter and no profile string anywhere: a product chart calls the set it was
      written for (design.md § *The profile is which helpers a chart calls*). Verify a
      product calling the `sftp` set emits no `dev` resource and vice versa, and that the
      Service is emitted by the shared helper in both cases.
- [x] 1.5 Keep the `sftp` profile byte-identical to today apart from the renamed resources.
      Verify by diffing rendered output before and after for all six consumers, with only
      name changes present.
- [x] 1.6 Move the "nothing to expose renders nothing" rule into the `sftp` profile, so it
      constrains that profile rather than the chart contract. Verify an `sftp` product with
      no exposable PVC still renders nothing.

## 2. Library chart: the `dev` profile

- [x] 2.1 Render the `dev` sidecar from the platform SSH sidecar image, pinned to an exact
      version supplied as a system value. Verify a tenant value cannot change the image
      reference.
- [x] 2.2 Supply every required runtime input from platform-projected values: the trusted
      public key from `caelus.sftp.platformPublicKey`, the forward allowlist from
      `caelus.database.host`/`.port`, the database variables via `envFrom` on
      `caelus.database.secretName`, and the release identity from the
      `caelus.dev/release-id` pod label through the Downward API. Verify the rendered
      sidecar carries all of them and that the pod starts.
- [x] 2.3 Verify the sidecar exits with a clear error when an input is missing, by
      rendering with one omitted — the failure must be a pod that will not start, not one
      that starts misconfigured.
- [x] 2.4 Render no SFTP subsystem, no chroot, and no tenant volume mount on this profile.
      Verify the sidecar's volume mounts include no tenant data volume.
- [x] 2.5 Emit the Service from the **shared** `ssh-sidecar.service` helper, not a
      dev-specific copy, so the two profiles cannot drift apart on the one thing the edge
      depends on. Verify the Services rendered for a `sftp` product and for `custom` are
      identical but for their names.

## 3. `custom` adopts the `dev` profile

- [x] 3.1 Add the `ssh-sidecar` chart dependency and call the `ssh-sidecar.dev.*` helpers
      from `products/custom/chart` — unconditionally, with no profile branch, since `custom`
      is only ever on this profile. Verify the rendered output contains the sidecar and the
      Service — and no Secret or ConfigMap, which this profile defines none of — and that
      every call site uses the `dev` set.
- [x] 3.2 Set `shareProcessNamespace: true` on the pod. Verify the application container's
      security context gains nothing, that no container is privileged, and that `hostPID`
      is not set. **`CAP_SYS_PTRACE` is deferred**: tenant namespaces enforce Pod Security
      `baseline`, which refuses non-default capabilities at admission, so the pod would
      never schedule (design.md § *Pod Security `baseline` refuses `CAP_SYS_PTRACE`*).
      Verify no container requests an added capability.
- [x] 3.3 Declare the new values in `values.schema.json` rather than relying on the
      permissive `caelus` block. Verify Helm accepts the reconciler's projected values and
      rejects a tenant attempt to set the sidecar image or the trusted key.
- [x] 3.4 Verify both containers run under the same AppArmor profile, and record the
      invariant in the chart where the security context is defined: giving the application
      container its own profile breaks tracing with an error that mentions only permissions
      (design.md § *The pod grants `CAP_SYS_PTRACE`*).

## 4. Resolver

- [x] 4.1 Move the upstream address expression from `-sftp` to `-ssh`. Verify against the
      resolver's existing tests, and add one asserting the rendered convention matches what
      the chart produces for the same deployment.
- [x] 4.2 Document the convention on both sides as shared and unchangeable alone — in the
      resolver's README and in the library chart's. Verify each names the other.
- [x] 4.3 Bump the resolver version and publish. **Do not deploy yet**; it is unroutable
      against the current charts by design.

## 5. In the maintenance window

The resolver and the charts must agree; between these steps the fleet is unroutable.

- [x] 5.1 Deploy the resolver to the environment.
- [x] 5.2 Re-vendor, bump, republish and repoint all six existing consumers on the `sftp`
      profile. **Never re-push an existing version** — rollback depends on the old ones.
- [x] 5.3 Publish `custom` and repoint its catalog entry.
- [x] 5.4 Repoint the `ProductTemplateVersion` for `helloworld`, `lemmy` and `mattermost` —
      operator action that will not appear in the diff, and the step most likely to be
      forgotten.
- [x] 5.5 Verify the whole fleet is routable again before closing the window: connect over
      SFTP to one deployment of each existing product.

## 6. Verification

- [x] 6.1 On a `custom` deployment: `ssh <deployment>@<edge>` opens a shell **in the
      application container** — verify by reading a file the application wrote and an
      environment variable it was started with.
- [~] 6.2 ~~Attach `strace` to the application's process from the session.~~ **Deferred
      with the capability** — blocked by Pod Security `baseline`, not by this chart. To be
      verified when the namespace enforcement level is decided (design.md § *Pod Security
      `baseline` refuses `CAP_SYS_PTRACE`*).
- [x] 6.3 Forward a local port to the database and connect with a local client. Verify the
      forwarded address is spelled exactly as the platform documents it.
- [x] 6.4 Verify a forward to any other destination is refused.
- [x] 6.5 Run the database client through the session with the application container
      stopped, and verify it still connects.
- [x] 6.6 Copy a file to the deployment with a standard file-copy tool and verify it lands
      in the application container's filesystem. **Verified two ways.** `scp` is covered by
      the image harness against an application image that ships `sftp-server`. On the
      cluster the tenant image ships `tar` but not `sftp-server`, which is the documented
      limitation — file transfer needs its helper in the tenant's own image, exactly as
      `kubectl cp` needs `tar` — so the on-cluster check streamed a tar over the session
      and confirmed the file landed in the application container and not the sidecar.
- [x] 6.7 Verify the session reports the release it landed on, and that the reported value
      matches the pod's `caelus.dev/release-id` label.
- [x] 6.8 Verify a `custom` deployment in `error` state is still reachable — the state this
      profile exists to debug.
- [x] 6.9 Verify the six `sftp` products behave exactly as before: connect, list, download,
      and confirm no shell and no forwarding is available on that profile.
- [x] 6.10 Verify the credentials Secret rename cleared the stale `password` key on an
      upgraded deployment.

## 7. Documentation

- [x] 7.1 Rewrite `products/_lib/ssh-sidecar-chart/README.md` around the two profiles, scoping the
      existing "no shell, no writes" promise explicitly to `sftp`.
- [x] 7.2 Update `AGENTS.md`: two access profiles, chosen per product; `custom` runs `dev`;
      the naming convention is shared between the charts and the resolver.
- [x] 7.3 Document the forward address for users, byte-identical to what the chart renders.
- [x] 7.4 Update `products/custom/README.md` with what SSH access to a `custom` deployment
      offers, including that debugging a broken deployment is supported and that no
      separate file-transfer configuration exists.
- [x] 7.5 Update `var/ssh_access.md` noting which decisions this change delivered.

## 8. Decouple the profile from relational storage

Added after section 7, before the branch merged: the first draft made the sidecar's `PG*`
variables required and recorded the resulting coupling as a stated precondition. A shell in
the application container is worth having with or without a database, so the coupling was
removed rather than documented.

- [x] 8.1 Make `FREEPOD_PERMIT_OPEN` optional in the image, rendering `PermitOpen none`
      when it is absent — never omitting the directive, whose default is to permit
      forwarding anywhere.
- [x] 8.2 Make the `PG*` variables optional as a set and all-or-nothing individually: none
      is a deployment without a database, some is a broken projection and still aborts
      startup naming both halves.
- [x] 8.3 Have the dispatcher decline the database tools by name when there is no database,
      rather than run them into a connection error.
- [x] 8.4 Render the allowlist and the database environment in `_dev.tpl` only when the
      product has a database.
- [x] 8.5 Extend the image harness with a sidecar configured with no database and no
      allowlist, asserting the shell, the explicit forward refusal, the declined tools and
      that no credential is staged for the session.
- [x] 8.6 Add the `custom` render test for a deployment with no relational storage.
- [x] 8.7 Sidecar image 0.2.0 → 0.3.0, library chart 0.4.2 → 0.4.3, `custom` 0.8.2 → 0.8.3
      and its catalog entry. The six `sftp` charts take the new library pin only; their
      rendered output is unchanged, verified by diffing every one against `HEAD`.
- [x] 8.8 Update the specs, both READMEs and the design note.
