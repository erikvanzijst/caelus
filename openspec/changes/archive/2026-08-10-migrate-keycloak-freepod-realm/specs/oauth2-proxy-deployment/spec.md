## MODIFIED Requirements

### Requirement: oauth2-proxy authenticates against Keycloak
The system SHALL configure oauth2-proxy to use the Keycloak `freepod` realm as
its OIDC provider, with the client ID and client secret selected per Terraform
workspace so that each environment authenticates against its own Keycloak
client.

#### Scenario: oauth2-proxy is configured with Keycloak OIDC
- **WHEN** oauth2-proxy deployment configuration is inspected
- **THEN** `oidc-issuer-url` is
  `https://keycloak.freepod.eu/realms/freepod`
- **AND** the client ID is configured
- **AND** the client secret references a Kubernetes Secret

#### Scenario: Each environment uses its own client
- **WHEN** oauth2-proxy is deployed from the `prod` workspace
- **THEN** it is configured with the `freepod-prod` client ID and secret
- **WHEN** oauth2-proxy is deployed from the `default` workspace
- **THEN** it is configured with the `freepod-dev` client ID and secret

#### Scenario: Issuer is reachable before rollout
- **WHEN** oauth2-proxy starts
- **THEN** the configured issuer's OIDC discovery document resolves
- **AND** a discovery failure prevents the pod from becoming ready, so the realm
  and clients MUST exist before this configuration is applied

## ADDED Requirements

### Requirement: The development environment is gated by group membership
The system SHALL restrict access to `dev.freepod.eu` to members of the
`freepod-dev` Keycloak group by configuring oauth2-proxy `allowed_groups` in the
non-prod workspace only. The production environment SHALL remain ungated,
because Freepod is a public service.

#### Scenario: Dev is gated
- **WHEN** oauth2-proxy configuration in the `default` workspace is inspected
- **THEN** `allowed_groups` contains `freepod-dev`

#### Scenario: Prod is not gated
- **WHEN** oauth2-proxy configuration in the `prod` workspace is inspected
- **THEN** no `allowed_groups` restriction is configured

#### Scenario: Group member reaches the dev application
- **WHEN** a member of `freepod-dev` authenticates and requests a protected
  route on `dev.freepod.eu`
- **THEN** the forward-auth check returns 202 with `X-Auth-Request-Email` set
- **AND** the request reaches the upstream application

#### Scenario: Non-member is denied on the dev environment
- **WHEN** an authenticated user who is not a member of `freepod-dev` requests a
  protected route on `dev.freepod.eu`
- **THEN** the forward-auth check denies the request
- **AND** the oauth2-proxy session cookie is cleared

#### Scenario: Group names are unqualified
- **WHEN** `allowed_groups` values are inspected
- **THEN** they are bare group names such as `freepod-dev`
- **AND** they are not slash-prefixed paths, matching the realm's group mapper
  which emits bare names

#### Scenario: Membership changes take effect immediately
- **WHEN** a user is removed from the `freepod-dev` group
- **THEN** their next request is denied, because authorization is evaluated on
  every forward-auth check rather than only at login

### Requirement: Public routes remain reachable on the gated environment
The system SHALL accept that routes listed in `skip_auth_routes` bypass
authorization entirely, so genuinely public reads stay anonymously reachable on
`dev.freepod.eu` even while group gating is active. These routes expose no
tenant data.

#### Scenario: Anonymous catalog read succeeds on dev
- **WHEN** an unauthenticated client requests a route matched by
  `skip_auth_routes` on `dev.freepod.eu`, such as the product catalog
- **THEN** the request succeeds
- **AND** group gating is not applied, because the skip rule short-circuits
  before the authorization check

#### Scenario: Identity is never trusted on skipped routes
- **WHEN** a request to a skipped route carries a client-supplied
  `X-Auth-Request-Email` header
- **THEN** no endpoint matched by a skip rule uses that header for
  authorization, since oauth2-proxy neither injects nor strips it on these
  routes
