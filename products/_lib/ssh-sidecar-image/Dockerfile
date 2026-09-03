# The platform's SSH sidecar: an OpenSSH server, a session dispatcher, the
# platform's PostgreSQL toolbox at the tenant cluster's own major version, and
# the file transfer every deployment is served with. One image for every
# product; what a session may do follows from the session root the chart
# declares. See README.md for the runtime configuration contract, and
# openspec/changes/unified-ssh-sidecar/design.md for the design.
FROM debian:trixie-slim

# postgresql-client must track the tenant cluster's server version (D14) and a
# rebuild must not drift onto 19 when it is released: that bump is a reviewable
# edit here, not something that happens because a build ran on a Tuesday.
ARG PG_MAJOR=18
ARG PG_CLIENT_VERSION=18.6-1.pgdg13+2

# Vendored rather than fetched, so the build depends on one external host
# instead of two and the pin itself is reviewable in a diff.
COPY pgdg-archive-key.asc /usr/share/keyrings/pgdg-archive-key.asc

RUN set -eux; \
    # amd64 only, as products/custom/builder is: the cluster node is amd64 and
    # multi-arch is an explicit non-goal. Fail here rather than emit an image
    # whose PostgreSQL client cannot exec on the node.
    arch="$(dpkg --print-architecture)"; \
    if [ "$arch" != "amd64" ]; then \
        echo "ssh-sidecar: this image is amd64 only, got $arch." >&2; \
        echo "ssh-sidecar: build with --platform linux/amd64." >&2; \
        exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates; \
    echo "deb [signed-by=/usr/share/keyrings/pgdg-archive-key.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        openssh-server \
        "postgresql-client-${PG_MAJOR}=${PG_CLIENT_VERSION}"; \
    rm -rf /var/lib/apt/lists/*; \
    # openssh-server's postinst generates host keys at install time. Baked in,
    # every deployment would present the same identity, so they are removed and
    # regenerated per container start by the entrypoint.
    rm -f /etc/ssh/ssh_host_*; \
    rm -rf /etc/ssh/sshd_config.d /etc/ssh/ssh_config.d; \
    mkdir -p /run/sshd /etc/freepod; \
    chmod 700 /etc/freepod; \
    # No password is ever set. Note this forces the "no password" hash rather
    # than locking the account: sshd refuses a locked account outright, public
    # key or not, so `passwd -l` would disable the only authentication method
    # this image has.
    sed -i 's|^root:[^:]*:|root:*:|' /etc/shadow

# The file-transfer program and everything it needs to run inside a chroot.
# `chroot(2)` runs before `execvp`, so a chrooted `sftp-server` resolves its
# loader, its libraries, /dev/null and its passwd entry inside the NEW root. An
# application container supplies all four -- the runtime mounts /dev in every
# container and the loader is reached through /proc -- but a volume mount holds
# the product's data and nothing else, so the image ships them (D3).
ARG JAIL=/srv/session
ARG JAIL_PREFIX=.freepod
RUN set -eux; \
    server=/usr/lib/openssh/sftp-server; \
    [ -x "$server" ]; \
    loader=$(ldd "$server" | awk '$1 ~ /ld-linux/ { print $1; exit }'); \
    [ -n "$loader" ] && [ -x "$loader" ]; \
    libs=$(ldd "$server" | awk '$2 == "=>" && $3 ~ /^\// { print $3 }'); \
    libpath=$(for l in $libs; do dirname "$l"; done | sort -u | paste -sd:); \
    [ -n "$libpath" ]; \
    mkdir -p /etc/freepod; \
    printf 'FREEPOD_SFTP_LOADER=%s\nFREEPOD_SFTP_LIBPATH=%s\nFREEPOD_SFTP_SERVER=%s\nFREEPOD_SESSION_JAIL=%s\nFREEPOD_SESSION_JAIL_PREFIX=%s\n' \
        "$loader" "$libpath" "$server" "${JAIL}" "/${JAIL_PREFIX}" > /etc/freepod/sftp-server.env; \
    # The jail. `install -D` follows the symlink and lands a real file at the
    # same path under the prefix, so the one invocation reaches it by prefixing
    # the recorded paths and nothing here has to be repeated in the dispatcher.
    for f in "$loader" $libs "$server"; do \
        install -D -m 0755 "$f" "${JAIL}/${JAIL_PREFIX}${f}"; \
    done; \
    mkdir -p "${JAIL}/dev" "${JAIL}/etc"; \
    mknod -m 0666 "${JAIL}/dev/null" c 1 3; \
    # getpwuid(0) is fatal in sftp-server when it fails. One entry, no shell:
    # nothing in a volume session ever executes.
    printf 'root:x:0:0:root:/:/sbin/nologin\n' > "${JAIL}/etc/passwd"; \
    chmod 0755 "${JAIL}" "${JAIL}/dev" "${JAIL}/etc"; \
    chown 0:0 "${JAIL}" "${JAIL}/dev" "${JAIL}/etc"; \
    # Prove the jail serves a transfer now, in the build that assembled it,
    # rather than in a tenant's pod.
    mkdir -p "${JAIL}/build-check"; echo staged > "${JAIL}/build-check/probe"; \
    chroot "${JAIL}" "/${JAIL_PREFIX}${loader}" \
        --library-path "$(echo "/${JAIL_PREFIX}${libpath}" | sed "s|:|:/${JAIL_PREFIX}|g")" \
        "/${JAIL_PREFIX}${server}" -R -d /build-check < /dev/null > /dev/null; \
    rm -rf "${JAIL}/build-check"

COPY entrypoint.sh /usr/local/bin/freepod-sshd
COPY dispatch.sh /usr/local/bin/freepod-dispatch
RUN chmod 0755 /usr/local/bin/freepod-sshd /usr/local/bin/freepod-dispatch

EXPOSE 2222
ENTRYPOINT ["/usr/local/bin/freepod-sshd"]
