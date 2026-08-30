# The SSH auth resolver. Static binary on scratch: it runs as a sidecar in the
# SSH edge's pod, which terminates the platform's public SSH port, and there is
# nothing else it needs to be able to do.
#
# Immutable version tag from VERSION, never re-pushed: rolling the edge back
# means pointing Terraform at the previous version, which only works while that
# version is still the image it was.
FROM golang:1.25-bookworm AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .

# CGO off so the result is a static binary with no libc to carry; -s -w drops
# the symbol table and DWARF, which nothing in the pod can read anyway.
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /ssh-auth .

FROM scratch
# Only for a database URL that turns out to want TLS. Nothing else in here
# speaks to anything outside the pod.
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /ssh-auth /ssh-auth

# Loopback by default: the edge's sshpiperd reaches it inside the pod, and
# nothing else should. Terraform sets the rest.
ENV CAELUS_SSH_RESOLVER_LISTEN="127.0.0.1:50051"

USER 65534:65534
ENTRYPOINT ["/ssh-auth"]
