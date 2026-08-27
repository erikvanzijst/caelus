## 1. Library chart

- [ ] 1.1 In `products/_lib/caelus-sftp/templates/_resources.tpl`, add
      `publishNotReadyAddresses: true` to the `spec` of the Service rendered by
      `caelus-sftp.resources`. Verify with `helm template` on any consumer that the
      rendered Service carries the field.
- [ ] 1.2 In the same file, add a `startupProbe` and a `livenessProbe` to the
      `caelus-sftp.sidecar` container, both `tcpSocket` on port 2222. The startup probe
      gates liveness while `atmoz/sftp` generates host keys on every container start
      (design.md § *The probe must tolerate host-key generation on start*); size its
      `failureThreshold` × `periodSeconds` to comfortably exceed RSA-4096 key
      generation. Neither probe may reference the application container, the exposed
      PVCs, or any credential. Verify with `helm template` that both probes render on
      the `sftp` container and on no other container.
- [ ] 1.3 Bump `products/_lib/caelus-sftp/Chart.yaml` `version` to `0.2.0` and update
      `products/_lib/caelus-sftp/README.md`: state that the Service publishes not-ready
      addresses and why (the sidecar fronts administration, not the application), and
      that the sidecar is liveness-probed. Verify `helm lint products/_lib/caelus-sftp`
      passes.

## 2. Render test

- [ ] 2.1 Add `api/tests/test_sftp_service_reachability.py` following the existing
      `api/tests/test_curated_charts_ignore_release_id.py` pattern (module-scoped
      dependency-resolution fixture, `helm template`, skip when `helm` is absent).
      Assert, for each of the six consumers `helloworld`, `immich`, `lemmy`,
      `mattermost`, `nextcloud`, `vaultwarden`: the SFTP Service sets
      `publishNotReadyAddresses: true`, and the `sftp` container declares both probes on
      port 2222. Verify the test fails against the pre-change library and passes after.

## 3. Re-vendor and publish, one product at a time

Each product is independent; order does not matter, and a partially rolled-out fleet is
coherent. **Never re-push an existing chart version** — bump, then push.

- [ ] 3.1 `helloworld`: `helm dependency build products/helloworld/chart`, remove the
      stale `charts/caelus-sftp-0.1.0.tgz`, bump `Chart.yaml` `0.1.11` → `0.1.12`,
      `helm package`, `helm push … oci://registry.home/helm --insecure-skip-tls-verify`.
      Verify with `helm pull oci://registry.home/helm/helloworld --version 0.1.12` and
      record the digest.
- [ ] 3.2 `immich`: same sequence, `0.1.4` → `0.1.5`. Verify by pull; record the digest.
- [ ] 3.3 `lemmy`: same sequence, `0.4.0` → `0.4.1`. Verify by pull; record the digest.
- [ ] 3.4 `mattermost`: same sequence, `1.0.12` → `1.0.13`. Verify by pull; record the
      digest.
- [ ] 3.5 `nextcloud`: same sequence, `0.1.9` → `0.1.10`. Verify by pull; record the
      digest. Coordinate with the in-flight `nextcloud-wellknown-discovery` change,
      which also bumps this chart — whichever lands second takes the higher version.
- [ ] 3.6 `vaultwarden`: same sequence, `3.3.0` → `3.3.1`. Verify by pull; record the
      digest.

## 4. Repoint the recorded chart versions

- [ ] 4.1 Update `chart_version` in `products/catalog/immich.yaml` (`0.1.5`),
      `products/catalog/nextcloud.yaml` (`0.1.10`), and
      `products/catalog/vaultwarden.yaml` (`3.3.1`). Verify `caelus catalog lint` passes
      and `caelus catalog apply --dry-run` shows only the intended version moves.
- [ ] 4.2 **Operator action, not a repository edit:** update the
      `ProductTemplateVersion` chart version for the three non-curated products
      `helloworld` (`0.1.12`), `lemmy` (`0.4.1`) and `mattermost` (`1.0.13`) through the
      admin UI or `caelus` CLI. Verify each product's active template reports the new
      version. Without this the new charts are published but never installed.

## 5. Verification on dev

- [ ] 5.1 Deploy or redeploy one consuming product on dev at its new chart version and
      confirm normal SFTP access still works end to end: connect to `dev.freepod.eu:23`
      with the deployment's credentials, list and download a file from the exposed PVC.
- [ ] 5.2 Break that deployment's application container deliberately (an image or
      command that exits non-zero) so the pod settles at `CrashLoopBackOff` with the
      sidecar still running. Confirm `kubectl get endpointslices` shows the pod with
      `ready=true`, and that an SFTP session still connects, lists, and downloads.
      This is the behavior the change exists for.
- [ ] 5.3 Confirm the sidecar is not restarted while the application container is
      crash-looping — `restartCount` for the `sftp` container stays at 0 while the app
      container's climbs — proving the liveness probe is independent of the application.
- [ ] 5.4 Confirm the startup probe does not kill the sidecar during host-key
      generation: restart the pod several times and verify the `sftp` container reaches
      a serving state each time with no probe-induced restarts in its event stream.
- [ ] 5.5 Restore the deployment to a healthy image and confirm SFTP still works,
      leaving no test wreckage on dev.

## 6. Documentation

- [ ] 6.1 Update `products/_lib/caelus-sftp/README.md` if 1.3 left anything unstated —
      in particular that SFTP reachability is deliberately independent of application
      health, so a future refactor does not silently drop the flag.
- [ ] 6.2 Add a release/changelog note framing this as a **fix**: tenants whose
      application is crash-looping can now reach their files over SFTP. Verify it names
      the user-visible behavior rather than the Kubernetes field.
- [ ] 6.3 Add a pointer in `var/ssh_access.md` D17 recording that the SFTP half shipped
      as the `sftp-reachability` change, so the design document and the delivered work
      do not drift.
