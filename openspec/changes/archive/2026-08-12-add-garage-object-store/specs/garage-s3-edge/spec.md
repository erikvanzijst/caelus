## Purpose

External exposure of the Garage S3 API at the cluster edge, so clients outside the cluster can
upload and download objects with native S3 authentication — including presigned URLs minted by
the Caelus API — without passing through the platform's oauth2-proxy session layer.

## ADDED Requirements

### Requirement: The S3 API is reachable externally over TLS at a wildcard-covered hostname

The Garage S3 API SHALL be published through Traefik at `blob.freepod.eu` and served over HTTPS.
In-cluster-only reachability is not sufficient: the primary client is an external CLI running on
a developer's laptop.

The hostname SHALL be a **single-label** subdomain of `freepod.eu`. Traefik's default
certificate store serves the `*.freepod.eu` wildcard certificate for any SNI without a more
specific certificate, so a single-label host requires **no per-app cert-manager Certificate and
no ACME challenge**. A multi-label host such as `blob.objects.freepod.eu` falls outside the
wildcard and would require per-app certificate issuance for no functional gain.

Plain HTTP requests to the host SHALL be redirected to HTTPS by the existing cluster-wide
redirect; the S3 API SHALL NOT be served unencrypted.

#### Scenario: HTTPS request reaches Garage with a valid certificate

- **WHEN** an external client issues an HTTPS request to `https://blob.freepod.eu/`
- **THEN** TLS is negotiated with a valid, publicly trusted certificate covering
  `blob.freepod.eu`
- **AND** the request is served by Garage's S3 endpoint

#### Scenario: No per-app certificate is created

- **WHEN** the Garage Terraform module is inspected
- **THEN** it declares no cert-manager `Certificate` and no TLS secret of its own
- **AND** the ingress relies on Traefik's default wildcard certificate store

#### Scenario: HTTP is redirected, not served

- **WHEN** a plain HTTP request is made to `http://blob.freepod.eu/`
- **THEN** the response is a redirect to the HTTPS URL
- **AND** no S3 response body is served over the unencrypted connection

### Requirement: The S3 ingress deliberately omits the forward-auth middleware

The Garage ingress SHALL NOT attach the `forward-auth` middleware, and SHALL NOT attach any
other middleware that inspects, rewrites, adds or removes request headers, the request URI or
the query string.

This omission is deliberate and load-bearing. Garage authenticates requests with AWS SigV4,
either from an `Authorization` header or from a presigned URL's query-string signature. Routing
those requests through oauth2-proxy breaks them **twice over**: oauth2-proxy sees no session
cookie and returns `401` before Garage is ever reached, and — even if it did not — it injects
`X-Auth-Request-*` headers and alters the request, so the SigV4 signature computed by the
client no longer verifies against what Garage receives.

Because an ingress that silently lacks authentication is a landmine for the next reader, the
reason for the omission SHALL be recorded in an in-line comment on the ingress resource itself,
following the precedent set by the webhooks ingress in `tf/app/caelus/ingress.tf`, which bypasses
oauth2-proxy for the same class of reason and documents why in place.

Authentication is not weakened, only relocated: every request is verified by Garage's own SigV4
check, and the ability to obtain a presigned URL is controlled by the Caelus API.

#### Scenario: No auth middleware is attached

- **WHEN** the Garage Ingress resource is inspected
- **THEN** it carries no `forward-auth` middleware annotation
- **AND** it carries no other request-mutating middleware

#### Scenario: The omission is justified in place

- **WHEN** the Garage ingress source in `tf/deps/garage/` is read
- **THEN** an in-line comment states that S3 SigV4 and presigned-URL signatures are
  incompatible with oauth2-proxy, and that the omission is intentional

#### Scenario: A signed request authenticates end to end

- **WHEN** an external client issues a SigV4-signed S3 request through `https://blob.freepod.eu`
  with valid credentials
- **THEN** Garage verifies the signature and serves the request
- **AND** no oauth2-proxy redirect or `401` is returned by the edge

#### Scenario: An unsigned request is rejected by Garage, not by the edge

- **WHEN** an unauthenticated request is made to a private object through the edge
- **THEN** the response is an S3-formatted access-denied error produced by Garage
- **AND** the response is not an oauth2-proxy login redirect

### Requirement: Large request bodies traverse the edge unbuffered and uncapped

The edge path to Garage SHALL NOT impose a request-body size limit and SHALL NOT buffer request
bodies to disk or memory before forwarding them. Uploads of tens to low hundreds of megabytes
must stream through to Garage.

Concretely: no Traefik `buffering` middleware and no `maxRequestBodyBytes` setting may be
present on the Garage router, on its entrypoint, or as a default middleware in the Traefik Helm
values. Read and idle timeouts on the entrypoint MUST be permissive enough that a large upload
over a slow residential uplink is not severed mid-transfer.

Buffering would also defeat the purpose of the design: the point of a presigned URL is that
bytes flow directly from the client to storage rather than being staged anywhere in between.

#### Scenario: No buffering middleware or body cap in the path

- **WHEN** the Traefik Helm values, the cluster's default middlewares, and the Garage ingress
  annotations are inspected
- **THEN** no `buffering` middleware is applied to the Garage router
- **AND** no request-body size limit is configured anywhere in that path

#### Scenario: A large upload completes through the edge

- **WHEN** an external client uploads an object of at least 100 MB through
  `https://blob.freepod.eu`
- **THEN** the upload completes successfully
- **AND** the object's size and checksum match the source

#### Scenario: A slow upload is not timed out

- **WHEN** a large upload proceeds slowly but continuously through the edge
- **THEN** the connection is not severed by an edge read or idle timeout before completion

### Requirement: Presigned URLs, PostObject and multipart upload all work through the edge

All three externally-facing S3 upload and download mechanisms SHALL function end to end through
the public ingress, not merely from inside the cluster. All three are implemented by Garage;
this requirement is about the edge not breaking them.

- **Presigned GET and PUT** — the core primitive. The Caelus API mints a time-limited URL; the
  external client uses it with no other credentials. The signature lives in the query string, so
  the edge must not alter the URI or query.
- **`PostObject`** — browser-style form upload. Required specifically because its policy document
  supports `content-length-range`, which enforces an upload size cap **server-side**. Without it,
  a size cap is merely a client-side promise the client can decline to keep.
- **Multipart upload** — how any competent S3 client transfers a large object, and what makes an
  interrupted upload resumable rather than restartable. This includes initiate, part upload,
  complete and abort.

#### Scenario: Presigned PUT from outside the cluster

- **WHEN** a presigned PUT URL is minted for a provisioned bucket and used by an external client
  holding no other credentials
- **THEN** the object is stored
- **AND** a subsequent presigned GET for the same key returns the identical bytes

#### Scenario: Expired presigned URL is refused

- **WHEN** a presigned URL is used after its expiry
- **THEN** Garage refuses the request with an S3 authentication error
- **AND** no object is written or returned

#### Scenario: PostObject enforces content-length-range server-side

- **WHEN** a `PostObject` upload is performed with a policy specifying a `content-length-range`
  and the submitted body exceeds the stated maximum
- **THEN** the upload is rejected by Garage
- **AND** no object is stored

#### Scenario: Multipart upload completes through the edge

- **WHEN** an external client uploads a large object through the edge using multipart upload
- **THEN** initiate, all part uploads, and complete succeed
- **AND** the assembled object is readable and byte-identical to the source

#### Scenario: Aborted multipart upload leaves no committed object

- **WHEN** a multipart upload is initiated through the edge and then aborted
- **THEN** no object appears at the target key
