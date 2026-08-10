## ADDED Requirements

### Requirement: Per-environment public CLI clients are configured

The system SHALL create one public Keycloak client per Freepod environment in
the `freepod` realm for non-browser API clients: `freepod-cli-prod` for
`freepod.eu` and `freepod-cli-dev` for `dev.freepod.eu`. These clients SHALL be
public rather than confidential, because software distributed to end users
cannot hold a client secret.

The one-client-per-environment rule that governs the oauth2-proxy clients
applies here for the same reason: a token issued for one environment must not be
usable against the other. Both CLI clients register identical loopback redirect
URIs, so the token audience is the only thing that separates them.

#### Scenario: Both CLI clients exist
- **WHEN** Keycloak clients are listed for realm `freepod`
- **THEN** clients with client IDs `freepod-cli-prod` and `freepod-cli-dev`
  exist
- **AND** each client protocol is `openid-connect`
- **AND** each access type is `public`

#### Scenario: Loopback redirect URIs are registered
- **WHEN** either CLI client is inspected
- **THEN** its valid redirect URIs are loopback addresses registered without a
  port, so that a client binding an ephemeral port matches
- **AND** no redirect URI references a public hostname

#### Scenario: Grants are limited to the two supported flows
- **WHEN** either CLI client is inspected
- **THEN** the standard flow is enabled and PKCE is required with challenge
  method `S256`
- **AND** the OAuth 2.0 Device Authorization Grant is enabled
- **AND** `directAccessGrantsEnabled` is `false`
- **AND** `serviceAccountsEnabled` is `false`

#### Scenario: CLI clients are distinct from the proxy clients
- **WHEN** the realm's clients are compared
- **THEN** `freepod-cli-prod` and `freepod-cli-dev` are separate from
  `freepod-prod` and `freepod-dev`
- **AND** the oauth2-proxy clients remain confidential

### Requirement: Audience client scopes bind a token to one environment

The system SHALL declare one audience client scope per environment, assigned as
a default scope to that environment's CLI client, whose audience protocol mapper
adds the environment's oauth2-proxy client ID to the `aud` claim of issued
access tokens.

This exists because Keycloak's default access token carries `aud: ["account"]`
and records the requesting client only in `azp`, which the edge's audience
verification does not accept. The scope is therefore load-bearing for
authentication, not a convenience.

#### Scenario: Audience scopes exist
- **WHEN** client scopes are listed for realm `freepod`
- **THEN** an audience scope for the production environment exists whose mapper
  adds `freepod-prod`
- **AND** an audience scope for the development environment exists whose mapper
  adds `freepod-dev`

#### Scenario: Each CLI client gets only its own audience scope
- **WHEN** the default client scopes of `freepod-cli-prod` are inspected
- **THEN** the production audience scope is assigned
- **AND** the development audience scope is not assigned
- **WHEN** the default client scopes of `freepod-cli-dev` are inspected
- **THEN** the development audience scope is assigned
- **AND** the production audience scope is not assigned

#### Scenario: Issued tokens name a single environment
- **WHEN** an access token issued to either CLI client is decoded
- **THEN** its `aud` claim contains exactly one Freepod environment client ID

### Requirement: CLI clients carry the identity and membership scopes

The system SHALL assign the `email` and `groups` client scopes to both CLI
clients, so that tokens issued to them carry the claim Freepod resolves users by
and the claim that per-environment access gating depends on. Omitting `groups`
would deny every CLI request on the gated development environment.

#### Scenario: Email and groups scopes are assigned
- **WHEN** the client scopes of either CLI client are inspected
- **THEN** the `email` scope is assigned as a default client scope
- **AND** the `groups` scope is assigned as a default client scope

#### Scenario: Offline access is available
- **WHEN** the client scopes of either CLI client are inspected
- **THEN** `offline_access` is available to be requested, so a client can obtain
  a durable refresh token
