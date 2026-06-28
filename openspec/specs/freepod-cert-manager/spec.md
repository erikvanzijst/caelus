# freepod-cert-manager Specification

## Purpose
Provision cert-manager and Let's Encrypt issuers on the freepod cluster: a Cloudflare DNS-01 `*.freepod.eu` wildcard and an HTTP-01 issuer for per-app custom-domain certs.

## Requirements
### Requirement: cert-manager is installed on the freepod cluster
The system SHALL install cert-manager (Jetstack Helm chart, with CRDs) into a dedicated
`cert-manager` namespace on the freepod cluster, managed by Terraform under `tf/deps/`. The
`helm` provider SHALL be added to `tf/deps/providers.tf`.

#### Scenario: cert-manager is running
- **WHEN** the deps Terraform is applied
- **THEN** cert-manager pods (controller, webhook, cainjector) are Running in the
  `cert-manager` namespace
- **AND** the cert-manager CRDs (`ClusterIssuer`, `Issuer`, `Certificate`) are installed

### Requirement: A Cloudflare DNS-01 ClusterIssuer issues the freepod wildcard certificate
The system SHALL define a Let's Encrypt **DNS-01** `ClusterIssuer` using a Cloudflare solver
scoped to the `freepod.eu` zone, and SHALL issue a single wildcard `Certificate` covering
`freepod.eu`, `*.freepod.eu`, and `*.dev.freepod.eu`. The Cloudflare API token SHALL be stored
as a Kubernetes Secret in the `cert-manager` namespace. A **staging** issuer variant SHALL exist
for verification.

#### Scenario: Wildcard certificate is issued via DNS-01
- **WHEN** the wildcard `Certificate` is reconciled by cert-manager
- **THEN** cert-manager completes a DNS-01 challenge via the Cloudflare API for the `freepod.eu`
  zone
- **AND** the resulting secret contains a valid certificate for `*.freepod.eu` and
  `*.dev.freepod.eu`
- **AND** no `:80`/HTTP reachability is required for issuance

#### Scenario: Staging issuer used during rollout
- **WHEN** rollout is in progress
- **THEN** the staging DNS-01 issuer can be selected to avoid Let's Encrypt production rate limits
- **AND** switching to the production issuer and forcing re-issue yields a browser-trusted cert

### Requirement: An HTTP-01 ClusterIssuer issues per-app certificates for custom domains
The system SHALL define a Let's Encrypt **HTTP-01** `ClusterIssuer` (solver via the `traefik`
ingress class) used to issue per-app certificates for user **custom domains**, for which DNS-01
is not possible (the user owns the domain's DNS). A **staging** variant SHALL exist.

#### Scenario: Custom-domain certificate is issued via HTTP-01
- **WHEN** a deployment on a custom domain (e.g. `app.example.com`) is reconciled and its
  Ingress carries the `cert-manager.io/cluster-issuer` annotation for the HTTP-01 issuer
- **THEN** cert-manager creates a solver Ingress serving `/.well-known/acme-challenge/<token>`
  on `:80`
- **AND** Let's Encrypt validates over `:80` (reachable via the homelab HAProxy edge) and issues
  the certificate into the deployment's namespace

