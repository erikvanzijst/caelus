# A stand-in for a tenant's application container: an ordinary image with a
# shell and a filesystem of its own, and **no file-transfer tooling at all** —
# which is what the image the platform's own build pipeline produces looks
# like. A transfer that succeeds against this proves it was served from the
# sidecar rather than from anything the tenant supplied.
FROM debian:trixie-slim
RUN set -eux; \
    echo "application-container" > /etc/app-marker; \
    # A real binary named `pause`, so the harness can reproduce a pod
    # infrastructure process rather than assume the rule that excludes it.
    cp /bin/sleep /bin/pause; \
    # Asserted here as well as in the suite: an image that quietly regained a
    # helper would turn every transfer test into a test of the tenant's image.
    for helper in sftp-server scp rsync; do \
        if command -v "$helper" >/dev/null 2>&1 || \
           [ -x "/usr/lib/openssh/$helper" ] || [ -x "/usr/libexec/openssh/$helper" ]; then \
            echo "Dockerfile.app must contain no $helper." >&2; exit 1; \
        fi; \
    done
WORKDIR /app
CMD ["sleep", "infinity"]
