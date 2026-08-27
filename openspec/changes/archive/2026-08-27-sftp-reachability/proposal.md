## Why

A deployment whose application container is in `CrashLoopBackOff` is `NotReady`, and a
Kubernetes Service excludes `NotReady` pods from its endpoints. The SFTP sidecar in that
pod is running perfectly well, but the SFTP Service stops routing to it, so **the edge
cannot reach it and the tenant cannot get at their files — at exactly the moment they
are most likely to want them.** This was measured on the dev cluster, not inferred: with
a crash-looping app container beside a healthy sidecar holding a listener, a connection
through a Service as the chart renders it today fails outright, while an otherwise
identical Service with `publishNotReadyAddresses: true` succeeds.

This is a defect in shipped behavior. It is also a prerequisite for the broader SSH
access work (`var/ssh_access.md` D17), which depends on the sidecar being reachable
precisely when the application is broken — but it stands on its own and ships first.

## What Changes

- The SFTP Service rendered by the `caelus-sftp` library chart sets
  `publishNotReadyAddresses: true`, so the edge can reach the sidecar regardless of the
  application container's readiness.
- The SFTP sidecar gains a **liveness probe** on its SSH port. With readiness no longer
  gating traffic, nothing else would stop connections being routed to a wedged `sshd`;
  the probe makes a broken sidecar restart rather than silently accept connections that
  go nowhere.
- The library chart version is bumped, re-vendored into all six consuming product
  charts, and each product chart is bumped and republished.
- Each product's recorded chart version is repointed at the new release: the catalog
  entry for curated products, the `ProductTemplateVersion` row for non-curated ones.

Not a breaking change: no interface, credential, or routing behavior changes. A tenant
who could reach SFTP before can still reach it, identically.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sftp-chart-contract`: the Service requirement gains the obligation to publish
  not-ready addresses, and a new requirement states that SFTP reachability is
  independent of application-container health and that the sidecar is liveness-probed.

## Impact

**Charts**

- `products/_lib/caelus-sftp/` — `templates/_resources.tpl` (Service), `_resources.tpl`
  (sidecar container), `Chart.yaml` version, `README.md`.
- Six consuming product charts re-vendor the library and bump their own versions:
  `helloworld`, `immich`, `lemmy`, `mattermost`, `nextcloud`, `vaultwarden`. Each calls
  `caelus-sftp.resources` and `caelus-sftp.sidecar` from its own templates, so there is
  one edit in the library and no per-product template changes.

**Version records**

- Curated (`products/catalog/*.yaml` → `chart_version`): `immich`, `nextcloud`,
  `vaultwarden`.
- Non-curated (database-authored `ProductTemplateVersion`): `helloworld`, `lemmy`,
  `mattermost`. These are operator actions, not repository edits.

**Rollout**

- Existing deployments pick the fix up on their next reconcile to the new chart version.
  Nothing is retroactive; a deployment pinned to an older chart version keeps the old
  behavior until it is moved.

**Not affected**

- No API, CLI, or UI change. No change to credentials, the `Pipe`, the edge, or the
  tenant NetworkPolicy.
- `custom` does not consume `caelus-sftp` and is untouched.
