## ADDED Requirements

### Requirement: oauth2-proxy verifies bearer tokens

The system SHALL configure oauth2-proxy to accept a verified JWT bearer token as
an alternative to its session cookie, by enabling `skip_jwt_bearer_tokens`. When
a request carries a bearer token that verifies against the configured OIDC
issuer, oauth2-proxy SHALL build a session from the token's claims and allow the
request on the same terms as a cookie session.

#### Scenario: Bearer token verification is enabled

- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `skip_jwt_bearer_tokens` is enabled

#### Scenario: A valid bearer token authenticates the request

- **WHEN** a request to a protected route carries an `Authorization: Bearer`
  header with a token issued by the `freepod` realm and naming this
  environment's audience
- **THEN** the forward-auth check returns `202`
- **AND** `X-Auth-Request-Email` is set from the token's `email` claim
- **AND** no session cookie is required

#### Scenario: Cookie sessions continue to work

- **WHEN** a browser request carrying only the oauth2-proxy session cookie is
  made to a protected route
- **THEN** it is authenticated exactly as before this change

### Requirement: oauth2-proxy accepts only its environment's token audience

The system SHALL configure oauth2-proxy to accept access tokens whose `aud`
claim names its own environment's Keycloak client, and no broader audience. The
audience allowance SHALL NOT be widened to Keycloak's default `account`
audience, because every token issued in the realm carries that value and doing
so would make any realm token a valid Freepod credential.

#### Scenario: The environment audience is allowed

- **WHEN** oauth2-proxy configuration in the `prod` workspace is inspected
- **THEN** the allowed token audience is `freepod-prod`
- **WHEN** oauth2-proxy configuration in the `default` workspace is inspected
- **THEN** the allowed token audience is `freepod-dev`
- **AND** this allowance derives from oauth2-proxy's own client ID, which it
  always accepts, rather than from a separately configured extra audience

#### Scenario: No additional audience is configured

- **WHEN** oauth2-proxy configuration is inspected
- **THEN** no extra token audience is configured beyond its own client ID,
  because the audience mapper already makes issued tokens name that client

#### Scenario: The account audience is not allowed

- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `account` is not among the allowed token audiences

#### Scenario: A token for the other environment is refused

- **WHEN** a request to `freepod.eu` carries an access token whose `aud` names
  only `freepod-dev`
- **THEN** the forward-auth check denies the request

### Requirement: A failed bearer token is distinguishable from no credential

The system SHALL configure oauth2-proxy with `bearer_token_login_fallback`
disabled, so that a request carrying an unverifiable bearer token is refused
with `403`, distinct from the `401` returned for a request carrying no
credential at all. A client SHALL be able to tell from the status code alone
whether to refresh its token or to re-authenticate the user.

#### Scenario: Login fallback is disabled

- **WHEN** oauth2-proxy configuration is inspected
- **THEN** `bearer_token_login_fallback` is disabled

#### Scenario: An unverifiable bearer token yields 403

- **WHEN** a request carries an `Authorization: Bearer` header whose token does
  not verify
- **THEN** the forward-auth check returns `403`

#### Scenario: Anonymous requests are unaffected

- **WHEN** a request carries no `Authorization` header at all
- **THEN** the existing anonymous behavior applies and the response is `401`,
  so the SPA's public landing page continues to work

#### Scenario: The two failure modes are not conflated

- **WHEN** a client compares the response to a request with no credential
  against the response to a request with a bad token
- **THEN** the status codes differ, `401` and `403` respectively

### Requirement: Cookie sessions are unaffected by bearer configuration

The system SHALL leave browser session behavior unchanged by the introduction of
bearer token support. A request authenticated by the oauth2-proxy session cookie
SHALL be accepted exactly as before, and the absence of an `Authorization`
header SHALL NOT alter the outcome of any request.

It is accepted that a request presenting **both** a session cookie and an
`Authorization` header that is not a verifiable JWT is refused with `403`,
because bearer evaluation precedes session-cookie evaluation. This case does not
arise in ordinary browser traffic.

#### Scenario: A cookie-authenticated request still succeeds

- **WHEN** a browser request carrying a valid session cookie and no
  `Authorization` header is made to a protected route
- **THEN** the forward-auth check returns `202` with `X-Auth-Request-Email` set

#### Scenario: The browser login journey is unchanged

- **WHEN** a user signs in through the SPA, loads an authenticated page and
  signs out
- **THEN** each step behaves as it did before bearer support was enabled

#### Scenario: A cookie combined with a non-JWT credential is refused

- **WHEN** a request carries a valid session cookie and an `Authorization`
  header that is neither a JWT bearer token nor a Basic value containing one
- **THEN** the request is refused with `403`
- **AND** the session cookie is not consulted

## MODIFIED Requirements

### Requirement: The development environment is gated by group membership
The system SHALL restrict access to `dev.freepod.eu` to members of the
`freepod-dev` Keycloak group by configuring oauth2-proxy `allowed_groups` in the
non-prod workspace only. The production environment SHALL remain ungated,
because Freepod is a public service.

Group gating SHALL apply to bearer-authenticated requests on the same terms as
cookie sessions. Because the check reads the `groups` claim of the session
oauth2-proxy built, a bearer token that does not carry that claim is denied.

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

#### Scenario: A bearer client is gated on the same group
- **WHEN** a request to `dev.freepod.eu` carries a valid access token for a user
  who is not a member of `freepod-dev`
- **THEN** the forward-auth check denies the request with `401`

#### Scenario: A token without a groups claim is denied on dev
- **WHEN** a request to `dev.freepod.eu` carries a valid access token that
  carries no `groups` claim
- **THEN** the forward-auth check denies the request, because the gate fails
  closed rather than treating a missing claim as unrestricted
- **AND** this covers a user who belongs to no group at all, since Keycloak
  omits the `groups` claim entirely rather than emitting an empty list

#### Scenario: Authorization denial is not distinguishable from anonymity
- **WHEN** a client compares the response to a group-denied bearer request
  against the response to a request carrying no credential
- **THEN** both are `401`, because the group check rejects an authenticated
  session rather than failing token verification
- **AND** only an unverifiable token yields `403`
