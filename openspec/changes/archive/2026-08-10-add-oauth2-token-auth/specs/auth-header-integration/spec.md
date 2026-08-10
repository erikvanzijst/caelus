## ADDED Requirements

### Requirement: forward-auth forwards the Authorization request header

The system SHALL configure the Traefik `forward-auth` middleware to include
`Authorization` among the request headers it copies to oauth2-proxy's auth
endpoint. Without it a bearer token never reaches the component that verifies
it, and every other part of token authentication is inert.

#### Scenario: Authorization is among the forwarded request headers

- **WHEN** the `forward-auth` middleware definition is inspected
- **THEN** its forwarded request headers include both `Cookie` and
  `Authorization`

#### Scenario: A bearer token reaches the verifier

- **WHEN** a client sends a request to a protected route with an
  `Authorization: Bearer` header
- **THEN** oauth2-proxy receives that header on the auth sub-request
- **AND** it is able to verify the token and return an authentication decision

### Requirement: The raw bearer token does not leak past the edge

The system SHALL ensure that whether the upstream application receives an
`Authorization` header is determined by the edge rather than by the client. The
application authenticates on `X-Auth-Request-Email` and has no use for the
token, so the edge SHALL NOT pass a client-supplied `Authorization` header
through unexamined.

#### Scenario: Upstream authorization is edge-controlled

- **WHEN** a bearer-authenticated request reaches the upstream application
- **THEN** any `Authorization` header it carries is the one determined by the
  forward-auth response, not the raw header the client sent

#### Scenario: The application does not authenticate on the token

- **WHEN** the API receives a request
- **THEN** it derives the caller solely from `X-Auth-Request-Email`
- **AND** it does not inspect the `Authorization` header

## MODIFIED Requirements

### Requirement: oauth2-proxy injects X-Auth-Request-Email header
The system SHALL configure oauth2-proxy to set the X-Auth-Request-Email header
with authenticated user email, whether the request was authenticated by the
oauth2-proxy session cookie or by a verified bearer token. The upstream
application SHALL NOT be able to tell the two apart, so that token support
requires no application change.

#### Scenario: X-Auth-Request-Email header is set
- **WHEN** oauth2-proxy configuration includes `SET_XAUTHREQUEST=1`
- **AND** `SET_XAUTHREQUEST` is enabled
- **THEN** the header `X-Auth-Request-Email` is present in requests to upstream

#### Scenario: Header is set from a cookie session
- **WHEN** a request is authenticated by the oauth2-proxy session cookie
- **THEN** `X-Auth-Request-Email` carries the session's email

#### Scenario: Header is set from a bearer token
- **WHEN** a request is authenticated by a verified bearer token
- **THEN** `X-Auth-Request-Email` carries the token's `email` claim
- **AND** its form is indistinguishable from the cookie-authenticated case

### Requirement: Caelus receives X-Auth-Request-Email header
The system SHALL ensure Caelus backend receives the X-Auth-Request-Email header,
and that the value is always one the edge determined. A value supplied by the
client SHALL NOT reach the application on any route that the edge authenticates.

#### Scenario: Backend receives email header
- **WHEN** a request is made through oauth2-proxy to Caelus
- **THEN** the `X-Auth-Request-Email` header is present in the request to the
  upstream service

#### Scenario: A client-supplied identity header is overwritten
- **WHEN** a client sends a request to an authenticated route carrying its own
  `X-Auth-Request-Email` header
- **THEN** the value that reaches the application is the one derived from the
  session or the verified token, not the client's
- **AND** this holds whether the request was authenticated by cookie or by
  bearer token

#### Scenario: Skipped routes remain outside this guarantee
- **WHEN** a request is matched by an oauth2-proxy `skip_auth_routes` rule
- **THEN** oauth2-proxy neither injects nor strips `X-Auth-Request-Email`
- **AND** no endpoint matched by such a rule uses the header for authorization
