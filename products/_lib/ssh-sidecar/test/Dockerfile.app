# A stand-in for a tenant's application container: an ordinary image with a
# shell, a filesystem of its own, and the helpers a file-transfer tool needs on
# the remote side.
FROM debian:trixie-slim
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends openssh-client openssh-sftp-server rsync; \
    rm -rf /var/lib/apt/lists/*; \
    echo "application-container" > /etc/app-marker; \
    # A real binary named `pause`, so the harness can reproduce a pod
    # infrastructure process rather than assume the rule that excludes it.
    cp /bin/sleep /bin/pause
WORKDIR /app
CMD ["sleep", "infinity"]
