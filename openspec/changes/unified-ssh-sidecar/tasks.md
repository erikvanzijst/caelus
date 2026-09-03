## 1. The image: session root, transfer, and routing

- [x] 1.1 Take `FREEPOD_SESSION_ROOT` as a required input in `entrypoint.sh`, accepting
      `app-container` or `volume:<absolute path>` and nothing else. Reject an unknown value,
      a relative path, and a `volume:` path that is not a directory at startup. Verify with
      the image's test harness that each malformed form exits non-zero naming the input, and
      that an absent value is not defaulted.
- [x] 1.2 Resolve the loader, library and server paths for the sidecar's own `sftp-server`
      from `ldd` at build time and record them in the image, rather than hardcoding a path in
      `dispatch.sh`. Verify the recorded paths exist in the built image.
- [x] 1.3 Stage the session jail at build time from that same resolution: the loader,
      libraries and server under `/srv/session/.freepod`, plus `dev/null` and a one-line
      `etc/passwd`. Verify with a transfer through the jail during the build, so a base image
      whose library layout moved fails the build rather than a tenant's session.
- [x] 1.4 Serve every file-transfer request from the sidecar's own `sftp-server`, chrooted
      into the session root, via the loader indirection (design.md § D3) — prefixed from
      `/proc` for an application root and from the jail for a volume root. Remove the search
      of `$app_root` for a helper. Verify a transfer succeeds against a target image
      containing no `sftp-server`, `scp` or `rsync`.
- [x] 1.5 Derive read-only from the declared path's own filesystem rather than from a flag,
      and not from the chroot root, which for a volume session is the jail. Verify a
      read-only mount declines writes and a writable root accepts them, with no configuration
      distinguishing the two.
- [x] 1.6 Route on the declared session root before anything else: under `volume:`, refuse a
      shell, refuse any remote command, and decline the database tooling by name; under
      `app-container`, serve them as now. Verify each refusal names its reason, and verify a
      `volume:`-rooted container refuses a shell even when the pod shares a process namespace
      and the container holds `PG*` variables.
- [x] 1.7 Split the database-tooling gate in two: the session root decides whether the
      tooling is offered, `PGHOST` decides whether there is a database to reach. Verify an
      `app-container` deployment without connection details still declines by naming the
      absent database, and a `volume:` deployment declines by naming the session root.
- [x] 1.8 Refuse to serve from the sidecar's own filesystem when an `app-container` root
      cannot be resolved. Verify the message names the likely cause and that no session opens.
- [x] 1.9 Extend `test/run-tests.sh` to run the whole matrix: both session roots × (shell,
      remote command, database tool, file transfer, forward), against a target image with no
      transfer tooling. Verify the suite fails if any refusal becomes a silent success.
- [x] 1.10 Update `products/_lib/ssh-sidecar-image/README.md` for the new input and the
      routing table, and bump `VERSION`. Verify the documented contract matches what
      `entrypoint.sh` validates.

## 2. The library chart: one helper set

- [x] 2.1 Replace `ssh-sidecar.sftp.*` and `ssh-sidecar.dev.*` with one helper set taking
      `sessionRoot`, failing the render when it is absent or malformed. Verify a chart
      calling it without one does not render.
- [x] 2.2 Render the platform sidecar image, pinned from a system value, for every session
      root. Verify a tenant value cannot change the image reference.
- [x] 2.3 Accept mounts only for a `volume:` session root, rendering each `readOnly: true`,
      and refuse mounts alongside `app-container`. Verify both.
- [x] 2.4 Stop rendering the credentials Secret and the sshd-init ConfigMap; pass the trusted
      key, the login account, both release identity spellings and the session root as
      environment. Verify a rendered deployment carries no Secret or ConfigMap for SSH and
      that the sidecar starts.
- [x] 2.5 Keep the shared Service helper unchanged — name, port, `publishNotReadyAddresses`,
      selector override — and keep the liveness and startup probes. Verify the rendered
      Service is byte-identical to today's for every consumer.
- [x] 2.6 Bump the library chart version and update `products/_lib/ssh-sidecar-chart`'s
      README for the single helper set. Verify `helm lint` passes.

## 3. Products

- [x] 3.1 Move `helloworld`, `immich`, `lemmy`, `mattermost`, `nextcloud` and `vaultwarden`
      to the single helper with `sessionRoot: volume:<path>`, preserving each product's
      existing mounts and `subPath`, and dropping `internalUid`/`internalGid`. Verify each
      renders and that `nextcloud`'s session still exposes only its data subdirectory.
- [x] 3.2 Move `products/custom` to `sessionRoot: app-container`, keeping
      `shareProcessNamespace: true`, the allowlist and the database environment. Verify its
      rendered pod is unchanged apart from the new input.
- [x] 3.3 Vendor the new library version into every consumer and update each `Chart.lock`.
      Verify `helm template` succeeds for all seven charts.
- [x] 3.4 Replace the hand-listed `CONSUMERS` map in `api/tests/test_sftp_service_reachability.py`
      with an exhaustive classification over `products/*/chart`: every chart is
      volume-rooted, application-rooted, or renders no SSH resource, each pinned. Verify the
      suite fails for a product added without a classification, and fails if a product's
      rendered session root differs from its pinned one.
- [x] 3.5 Assert that no chart renders `atmoz/sftp`, no chart renders an SSH credentials
      Secret or sshd-init ConfigMap, and `matrix` and `naas` render no SSH resource and no
      `-ssh` Service. Verify against a rendered manifest, not against chart source.

## 4. The client

- [ ] 4.1 Add `freepod cp SRC DST` to `cli.py`, resolving the deployment with
      `_project_deployment` and the connection with `_connection_setup`. Verify the assembled
      argv carries `IdentitiesOnly=yes`, the client's own `UserKnownHostsFile`, exactly one
      `-i`, and no allocated terminal.
- [ ] 4.2 Parse the remote marker: a path is remote iff it starts with `:` or
      `<deployment>:`. Verify both directions, a local path containing a colon, the long form
      naming this project's deployment, the long form naming a different one, neither side
      marked, and both marked — each refusal naming which case it was.
- [ ] 4.3 Drive `sftp` for the transfer, in both directions, for a file and for a directory
      tree with no recursion flag. Verify a binary round-trips byte-for-byte and an
      executable stays executable.
- [ ] 4.4 Report a missing local source and an unwritable local destination before
      connecting; report a missing remote path as the deployment's, distinguishably from a
      local miss; report missing local `sftp` as a named prerequisite. Verify each.
- [ ] 4.5 Exit non-zero on an incomplete transfer and print no success line for one. Verify
      with an interrupted stream.
- [ ] 4.6 Add `cp` to `test_surface.py`'s command inventory and to `cli/README.md`'s command
      table, with a file-transfer section replacing the `freepod shell cat`/`tar` recipes.
      Verify the surface test passes and the examples run as written.

## 5. Documentation

- [ ] 5.1 Rewrite `products/custom/README.md` § SSH access for the served transfer: `scp`,
      `sftp` and `freepod cp` work with nothing added to the image; drop the pipe-over-shell
      recipes and the helper-in-your-image rule. Verify the examples run against a stock
      deployment.
- [ ] 5.2 Update each curated product's README where it describes file access: the platform
      sidecar rather than `atmoz/sftp`, no credentials Secret or sshd-init ConfigMap, and the
      session root it mounts. `immich` and `vaultwarden` also still list an sshpiper `Pipe`
      that no chart renders; drop it. Verify each README's stated objects and path match what
      the chart renders.
- [ ] 5.3 Add `cp` to the instructions `freepod skill` installs. Verify the installed text
      names the command.

## 6. Cut over

- [ ] 6.1 Publish the sidecar image at its new version and repoint every chart's pinned tag.
      Verify the referenced tag is one that was built.
- [ ] 6.2 Roll the seven charts in one release and confirm on a live deployment of each
      product: a curated deployment lists and downloads its data and is refused a shell; a
      `custom` deployment gets a shell, `scp` in both directions, `psql`, and a database
      forward. Verify a curated deployment stays reachable while its application container is
      crash-looping.
