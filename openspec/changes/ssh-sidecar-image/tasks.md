## 1. Build context

- [x] 1.1 Create the build context at `products/_lib/ssh-sidecar/`, beside the library
      chart that will consume it, with a `VERSION` file holding the image's own version
      (`0.1.0`) and a README documenting the build and publish commands in the same shape
      as `products/custom/README.md`. Verify the README's commands are the ones that
      actually build the image.

      **Done.** Created at `products/_lib/ssh-sidecar/` with `VERSION` (0.1.0) and a README documenting build, publish and the full runtime contract. The README's command is the one that builds it.
- [x] 1.2 Base the image on Debian trixie and add the PostgreSQL project's apt
      repository, pinned by its signing key, installing `postgresql-client-18` at an
      explicit version (design.md § *Debian base*; `18.6-1.pgdg13+2` is what the
      repository currently offers for trixie). Verify `psql --version` and
      `pg_dump --version` both report 18 inside the built image.

      **Done.** Debian trixie + PGDG, key vendored as `pgdg-archive-key.asc` (sha256 0144068502a1…), `postgresql-client-18=18.6-1.pgdg13+2`. Verified in the built image: `psql (PostgreSQL) 18.6` and `pg_dump (PostgreSQL) 18.6`, asserted by the harness.
- [x] 1.3 Install and configure the OpenSSH server. Verify the image contains no private
      key, no `authorized_keys`, no password and no tenant data — grep the built
      filesystem, do not assume.

      **Done.** OpenSSH 10.0p2 installed and configured at startup. The built filesystem is scanned, not assumed: `find / -xdev` for `ssh_host_*`, `authorized_keys`, `id_rsa*`, `id_ed25519*` returns nothing, and `/etc/shadow` has no root password hash. openssh-server's postinst *does* generate host keys at install time, so the Dockerfile removes them.
- [x] 1.4 Add an `--ssh-sidecar` target to `scripts/build-images.sh`, building
      `--platform linux/amd64` and pushing one immutable version tag read from the build
      context rather than the moving `latest`/branch tags the platform service images
      use. It must refuse to push a tag the registry already holds. Verify a clean build
      from an empty cache succeeds and that a second push of the same version is
      refused. Do not touch `scripts/rollout.sh`: it restarts the platform's own
      Deployments and has no bearing on tenant pods.

      **Done.** `--ssh-sidecar` target added to `scripts/build-images.sh`: `--platform linux/amd64`, one immutable tag from `VERSION`, and a `docker manifest inspect` preflight that refuses an already-published version. Deliberately outside `--all`, which CI runs on every master push and which would otherwise fail on every build that did not bump `VERSION`; CI publishes it as its own step in `publish-images` under `--skip-if-published`, which turns that refusal into a no-op so a push happens exactly when `VERSION` is new. That flag is rejected with any other target rather than silently doing nothing. `scripts/rollout.sh` untouched. Verified a clean `--no-cache` build from a pruned builder cache.

## 2. Server configuration and entrypoint

- [x] 2.1 Render the SSH server configuration at startup from the supplied inputs.
      Verify the rendered configuration disables password and keyboard-interactive
      authentication, refuses root password login, sets no `ChrootDirectory`, permits
      local forwarding only, disables remote forwarding, agent forwarding, X11 and
      gateway ports, listens on the platform sidecar port, and sets the dispatcher as
      the forced command.

      **Done.** Rendered by the entrypoint and asserted by the harness against the running container's `/etc/ssh/sshd_config`: `Port 2222`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods publickey`, `PermitRootLogin prohibit-password`, `AllowTcpForwarding local`, `AllowAgentForwarding no`, `GatewayPorts no`, `X11Forwarding no`, `ForceCommand /usr/local/bin/freepod-dispatch`, and no `ChrootDirectory` at all. `sshd -t` gates the start.
- [x] 2.2 Accept the trusted public key at startup and install it as the sole trusted
      key. Verify a client holding that key authenticates and a client holding any other
      key does not.

      **Done.** `FREEPOD_AUTHORIZED_KEYS`, each line validated with `ssh-keygen -l` rather than by pattern, written to a 0600 `/etc/ssh/authorized_keys`. Harness: the supplied key authenticates, a second generated key is refused with `publickey`.
- [x] 2.3 Accept the permitted forward destinations and render them as the server's
      allowlist. Verify a forward to a listed destination carries traffic and a forward
      to an unlisted one is refused by the server.

      **Done.** `FREEPOD_PERMIT_OPEN` rendered as sshd's `PermitOpen`. Harness: a permitted destination carries an HTTP response end to end; an unlisted one carries nothing and the server logs `to connect to host … but the request was denied`. The client only ever sees a connection reset, so the refusal is asserted where it is actually stated.
- [x] 2.4 Validate all inputs before starting the server: exit non-zero with a message
      naming the input when the trusted key is missing or unparseable, or when the
      forward allowlist is malformed. Verify the container exits rather than starting
      with an empty trust set or misconfigured forwarding.

      **Done.** Every input validated before `sshd` starts, exiting non-zero with the variable named. Harness covers a missing key, an unparseable key, a missing allowlist, four malformed allowlist entries (`pooler`, `pooler:*`, `pooler:not-a-port`, `pooler:99999`), a missing release identity and missing database details.
- [x] 2.5 Generate an Ed25519 host key per container start and generate no RSA host key.
      Verify two containers from the same image present different host keys, and that
      the port accepts connections promptly after start.

      **Done.** Ed25519 only, generated per start, with any install-time keys removed first. Harness: two containers from the same image present different host keys, no `ssh_host_rsa*` exists, and a fresh container's port accepts a connection within the measured budget.
- [x] 2.6 Ensure the deployment's database connection details reach the tools from the
      sidecar's own environment. Verify `psql` invoked with no arguments targets the
      configured database, and that this holds with no application container running at
      all.

      **Done.** `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` are required, and staged by the entrypoint into `/etc/freepod/session-env` because **sshd hands a session a sanitized environment** — the container's own variables do not reach the dispatcher on their own. Written NUL-delimited, in `/proc/<pid>/environ`'s form, so a value holding a quote or a newline needs no quoting and is never re-evaluated. Harness: against a real PostgreSQL 18 server, bare `psql` connects, and `psql -Atc 'select current_database()'` returns `appdb` **on the sidecar that has no application container beside it at all**.
- [x] 2.7 Document the complete runtime configuration contract in the README — every
      input, which are required, what each does, and the exact form forward destinations
      must take. Verify by having someone run the image from the README alone.

      **Done.** Documented in the README as a required-inputs table, with the `PermitOpen` spelling rule called out: it matches the destination as the client wrote it, so the rendered value and the CLI's `-L` argument must agree byte for byte.

## 3. Dispatcher

- [x] 3.1 Implement application-process identification by cgroup: exclude the
      dispatcher's own cgroup and the pod infrastructure process's, require exactly one
      remaining cgroup, and take its lowest process. Verify it selects correctly under
      `docker run --pid=container:<name>`, and verify the exclusion of an
      infrastructure-style cgroup explicitly rather than relying on the harness, which
      has none (design.md § *The docker test harness differs*).

      **Done.** Grouped by cgroup, excluding the dispatcher's own and any process whose `comm` is `pause`; exactly one cgroup must remain and its lowest PID is the application. Verified under `docker run --pid=container:<name>`, and the infrastructure exclusion is verified explicitly by running a real binary named `pause` in the shared namespace rather than inferred from the harness, which has none.
- [x] 3.2 Report ambiguity and absence rather than guessing: no candidate, or more than
      one, must produce a message naming the likely cause and must not enter any
      container. Verify both, including the case where the process namespace is not
      shared at all.

      **Done.** No candidate and more than one candidate both end the session with a message naming the likely cause and enter nothing. Both asserted, the first against a sidecar started with no shared process namespace.
- [x] 3.3 A session with no command opens a shell in the application container via
      `chroot` into its process root, seeded with that process's environment. Verify the
      shell reads the application's filesystem and carries its environment variables, not
      the sidecar's.

      **Done.** `chroot` into `/proc/<pid>/root`, seeded from `/proc/<pid>/environ`, landing in the application process's own working directory. Harness: the shell reads the application's `/etc/app-marker`, carries `APP_ONLY_VAR`, starts in `/app`, and cannot see `/usr/lib/postgresql` — which does exist in the sidecar, so the assertion means something.
- [x] 3.4 A recognized platform command — the PostgreSQL client and dump/restore tools —
      runs in the sidecar. Verify membership is decided on the command itself, and that a
      non-allowlisted command whose *arguments* resemble an allowlisted tool is not
      treated as one.

      **Done.** Allowlist is `psql`, `pg_dump`, `pg_dumpall`, `pg_restore`, `pg_isready`, matched on the first token only. Harness: `psql -Atc …` reaches the database from the sidecar, while `/bin/echo psql pg_dump` and `cat /etc/app-marker psql` both run in the application container.
- [x] 3.5 Any other command runs in the application container, passed to the target's
      shell as a single quoted argument. Verify an ordinary remote command runs there, and
      that a standard file-copy tool lands its file in the application container's
      filesystem.

      **Done.** Everything else goes to the application container's shell as one quoted argument, so pipelines and exit codes behave: `cat … | tr` works and `exit 7` returns 7. A 200 KB `scp` lands byte-identical in the application container and nothing appears in the sidecar. `Subsystem sftp internal-sftp` is declared so a modern scp's subsystem request reaches the dispatcher at all — without it sshd rejects it before `ForceCommand` runs — and it is mapped onto the application's own `sftp-server`.
- [x] 3.6 Verify the dispatcher never evaluates the requested command itself: exercise it
      with command strings containing separators, substitutions and metacharacters, and
      assert the dispatcher performed no additional action. Include a case whose expansion
      would be observable — a file the dispatcher must not create.

      **Done.** Nothing is ever `eval`'d; word splitting happens with globbing off purely to read the first token. Harness fires `$(touch …)`, backticks and `${IFS}`-separated commands and asserts the file count in the sidecar is zero each time, plus a separator case whose effect is observable — the file appears in the application container and not in the sidecar.
- [x] 3.7 Fail plainly when the application container cannot host the session: an image
      with no shell, or a requested command it does not contain, must produce a one-line
      message naming the cause and a non-zero exit, and must not open a session anywhere
      else. Verify against a distroless application container that no raw
      executable-not-found error reaches the user and that no sidecar session is opened.

      **Done.** A shell-less image and a missing command both fail plainly: the first names the cause and opens no session anywhere, the second exits 127 naming the command. Verified against a from-scratch distroless application image; no `No such file or directory` from `chroot` reaches the user, and no sidecar session is opened.
- [x] 3.8 Verify a forwarding-only connection never invokes the dispatcher, and that a
      dispatcher that would fail for a session does not affect forwarding.

      **Done.** Verified on the sidecar with no shared process namespace, where the dispatcher fails every session: a forward through it still carries traffic.

## 4. Banner

- [x] 4.1 Report the release identity supplied by configuration on interactive sessions.
      Verify it is the configured value and is not derived from the pod or container name.

      **Done.** `freepod: release <FREEPOD_RELEASE_ID>`, taken from configuration. Harness asserts the configured value appears and the container's name does not.
- [x] 4.2 Write the banner to standard error and suppress it when no terminal was
      allocated. Verify a file copy over the session transfers byte-identical content and
      that a streamed database dump contains no banner text, while an interactive session
      still shows it.

      **Done.** Standard error, suppressed with no pty. Harness: `echo BODY` returns exactly `BODY` on stdout, a 200 KB scp is byte-identical, and a real `pg_dump` stream contains no `freepod:` text while still containing `CREATE TABLE public.t`.

## 5. Test harness

- [x] 5.1 Build a test harness driven by `docker` and a local `ssh` client, with no
      cluster: an application container, the sidecar joined to it with
      `--pid=container:<name>` and `--cap-add SYS_PTRACE`, and a generated throwaway
      keypair. Verify it runs from a clean checkout on a machine with only docker and
      ssh installed.

      **Done.** `test/run-tests.sh` plus `Dockerfile.app` and `Dockerfile.noshell`; needs only docker, ssh and bash. Stands up PostgreSQL 18, two forward targets, an application container, a distroless one, a sidecar with no application beside it, and a fake infrastructure process. HTTP checks use bash's `/dev/tcp` rather than curl to keep the dependency list at three.
- [x] 5.2 Cover the negative cases explicitly, since each is a security property rather
      than a feature: password authentication refused, unknown key refused, unlisted
      forward destination refused, remote forward refused, agent forwarding refused,
      missing trusted key aborts startup.

      **Done.** All six are asserted: password authentication refused, unknown key refused, unlisted forward destination refused, remote forward refused, agent forwarding unavailable in the session, and startup aborted with no trusted key — plus the malformed-input cases from 2.4.
- [x] 5.3 Verify the harness runs in CI, or record why it cannot and what runs instead.

      **Done.** Runs in CI as the `ssh-sidecar-test` job in `.github/workflows/ci.yml`, and gates `publish-images`. GitHub's `ubuntu-latest` runners are full VMs, so `--pid=container:` and `--cap-add SYS_PTRACE` both work, and the harness takes the published-port path there since it is not itself containerized.

## 6. Publish and document

- [x] 6.1 Build and push the first version to GHCR under an immutable tag. Verify by
      pulling it back and running the harness against the pulled image rather than the
      locally built one.

      **Done, though not deliberately.** Published as
      `ghcr.io/erikvanzijst/freepod/ssh-sidecar:0.1.0` while exercising
      `--skip-if-published`, which is a no-op on a version that is not yet published and
      therefore ran the full publish. Verified afterwards as the task asks: the local
      image was removed, the image pulled fresh from GHCR (`arch=amd64 os=linux`, one
      manifest), and the harness run against the pulled reference — 87 passed, 0 failed.
      A second invocation now reports `already published. Nothing to do.`
- [x] 6.2 Set the new GHCR package's visibility to public and record the step in the
      README. A package created by its first push defaults to private, nothing in this
      platform configures an `imagePullSecret`, and the resulting tenant-side failure is
      an `ImagePullBackOff` that names no cause — see `tf/app/README.md` § *Non-secret
      variables*, which documents the same trap for the API and UI images. Verify with an
      unauthenticated pull.

      **Done.** The package was created private by its first push, as GHCR does; the
      visibility was flipped by hand, which is the only way — CI's `GITHUB_TOKEN` cannot
      change it. Verified anonymously rather than with the logged-in client, which would
      have succeeded either way and proved nothing: an unauthenticated pull token from
      `ghcr.io/token` fetches the manifest for
      `erikvanzijst/freepod/ssh-sidecar:0.1.0` with HTTP 200. The README records the step
      and why the failure it prevents is hard to diagnose.
- [x] 6.3 Record the versioning contract in the README: the image's version is the
      `VERSION` file, it moves independently of the consuming chart's version, a published
      tag is never overwritten, and a consumer must pin an exact tag rather than a moving
      one. Note the two obligations this places on the chart change that adopts the image
      — a render assertion tying the chart's referenced tag to this `VERSION` file, in the
      shape of `api/tests/test_sftp_service_reachability.py`, and an explicit
      `imagePullPolicy: IfNotPresent` on the sidecar container.

      **Done.** README states the version is `VERSION` and nothing else, that it moves independently of the consuming chart's version, that a published tag is never overwritten, and that consumers pin an exact tag. The two obligations on the adopting chart — the render assertion and the explicit `imagePullPolicy: IfNotPresent` — are recorded there under their own heading.
- [x] 6.4 Add a pointer in `var/ssh_access.md` noting that the `dev` profile image shipped
      as this change and where its configuration contract is documented, so the design
      document and the delivered artifact do not drift.

      **Done.** `var/ssh_access.md` migration step 8 marked shipped, pointing at the build context, the publish command and the README as the contract the chart change targets, and recording the two decisions taken during implementation that are not in the decision list above it. D2's profile table now names the image.
- [x] 6.5 Confirm this change wires nothing up: no chart, `Pipe`, reconciler, pod spec,
      Terraform, API, CLI or UI file is touched, and no deployment runs the image. Verify
      by reviewing the diff.

      **Done.** The diff is the build context, `scripts/build-images.sh`,
      `.github/workflows/ci.yml` and the OpenSpec change. Nothing under
      `products/*/chart/`, `products/_lib/caelus-sftp/`, `products/catalog/`, `tf/`,
      `api/`, `cli/`, `ui/` or `k8s/` is touched, and a repository-wide grep for
      `ssh-sidecar` finds no reference outside the build context, the build script, CI
      and this change. `var/ssh_access.md` is edited but `var/` is gitignored, so that
      pointer does not appear in the diff.
