# The `dev` access profile's SSH sidecar: an OpenSSH server, a session
# dispatcher, and the platform's PostgreSQL toolbox at the tenant cluster's own
# major version. See README.md for the runtime configuration contract and
# var/ssh_access.md D2-D4, D6, D14 and D17 for the access design it implements.
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

COPY entrypoint.sh /usr/local/bin/freepod-sshd
COPY dispatch.sh /usr/local/bin/freepod-dispatch
RUN chmod 0755 /usr/local/bin/freepod-sshd /usr/local/bin/freepod-dispatch

EXPOSE 2222
ENTRYPOINT ["/usr/local/bin/freepod-sshd"]
