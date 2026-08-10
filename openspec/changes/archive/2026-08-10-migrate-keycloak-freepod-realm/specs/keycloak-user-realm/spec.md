## RENAMED Requirements

### Requirement: Keycloak has a Caelus realm
- **FROM:** Keycloak has a Caelus realm
- **TO:** Keycloak has a Freepod realm

### Requirement: OAuth2 proxy client is configured
- **FROM:** OAuth2 proxy client is configured
- **TO:** Per-environment OAuth2 proxy clients are configured

### Requirement: Client scopes map email claim
- **FROM:** Client scopes map email claim
- **TO:** Client scopes map email and groups claims

## MODIFIED Requirements

### Requirement: Keycloak has a Freepod realm
The system SHALL authenticate Freepod end users against a dedicated Keycloak
realm named `freepod`. End-user accounts SHALL NOT be created in the built-in
`master` realm, which is Keycloak's administrative realm and governs the whole
instance.

#### Scenario: Freepod realm exists
- **WHEN** Keycloak admin API is queried for realms
- **THEN** a realm named `freepod` exists

#### Scenario: Realm discovery document is reachable
- **WHEN** `https://keycloak.freepod.eu/realms/freepod/.well-known/openid-configuration`
  is requested
- **THEN** it returns a valid OIDC discovery document whose `issuer` is
  `https://keycloak.freepod.eu/realms/freepod`

#### Scenario: End users are not created in master
- **WHEN** a user self-registers through Freepod
- **THEN** the account is created in the `freepod` realm
- **AND** no account is created in the `master` realm

### Requirement: Local user registration is enabled
The system SHALL enable self-registration in the `freepod` realm, because
Freepod is a public service that accepts sign-ups from anyone.

#### Scenario: Self-registration is enabled
- **WHEN** the `freepod` realm settings are inspected
- **THEN** `registrationAllowed` is set to `true`

#### Scenario: Registration is not restricted per environment
- **WHEN** an operator seeks to close registration for one environment only
- **THEN** it is understood that `registrationAllowed` is a realm-level setting
  with no per-client equivalent
- **AND** per-environment restriction is achieved through group-based
  authorization instead

### Requirement: Email verification is required
The system SHALL require email verification for new user accounts in the
`freepod` realm. Because the email claim is the sole join key between Keycloak
and Freepod's own user records, an unverified email is a privilege-escalation
vector and verification SHALL NOT be relaxed.

#### Scenario: Email verification is required
- **WHEN** the `freepod` realm settings are inspected
- **THEN** `verifyEmail` is set to `true`

#### Scenario: Email is the identity join key
- **WHEN** Freepod resolves an authenticated caller to a user record
- **THEN** the lookup is performed on the verified email claim
- **AND** no Keycloak subject identifier is persisted by Freepod

### Requirement: SMTP is configured for email sending
The system SHALL configure SMTP on the `freepod` realm through Terraform, so
that email verification and self-service password reset both function. A realm
without SMTP fails these flows silently.

#### Scenario: SMTP is configured
- **WHEN** the `freepod` realm SMTP settings are inspected
- **THEN** host, port, from address, and credentials are configured
- **AND** the values are supplied from Terraform variables, not entered by hand

#### Scenario: Password reset is self-service
- **WHEN** a user without a credential requests a password reset from the login
  page
- **THEN** `resetPasswordAllowed` is enabled on the realm
- **AND** Keycloak emails an action-token link that allows the user to set a
  password

### Requirement: Per-environment OAuth2 proxy clients are configured
The system SHALL create one Keycloak client per Freepod environment in the
`freepod` realm: `freepod-prod` for `freepod.eu` and `freepod-dev` for
`dev.freepod.eu`. A single client SHALL NOT serve both environments, so that a
session or token issued for one environment is not interchangeable with the
other.

#### Scenario: Both environment clients exist
- **WHEN** Keycloak clients are listed for realm `freepod`
- **THEN** clients with client IDs `freepod-prod` and `freepod-dev` exist
- **AND** each client protocol is `openid-connect`
- **AND** each access type is `confidential`

#### Scenario: Redirect URIs are scoped to one host each
- **WHEN** the `freepod-prod` client is inspected
- **THEN** its valid redirect URIs reference only `freepod.eu`
- **WHEN** the `freepod-dev` client is inspected
- **THEN** its valid redirect URIs reference only `dev.freepod.eu`

#### Scenario: Unnecessary grants are disabled
- **WHEN** either environment client is inspected
- **THEN** `directAccessGrantsEnabled` is `false`, because the browser flow does
  not use the resource owner password credentials grant
- **AND** PKCE is required with challenge method `S256`

### Requirement: Client scopes map email and groups claims
The system SHALL assign the client scopes needed for both identity and
authorization to each environment client. The `email` scope carries the identity
that Freepod resolves users by; the `groups` scope carries the membership that
per-environment access gating depends on.

#### Scenario: Email scope is assigned
- **WHEN** the client scopes of `freepod-prod` and `freepod-dev` are inspected
- **THEN** the `email` scope is assigned as a default client scope on each

#### Scenario: Groups scope is assigned
- **WHEN** the client scopes of `freepod-prod` and `freepod-dev` are inspected
- **THEN** the `groups` scope is assigned as a default client scope on each
- **AND** an access token issued to either client carries a `groups` claim

#### Scenario: Group claim carries bare names
- **WHEN** the realm's group membership protocol mapper is inspected
- **THEN** `full.path` is `false`, so the claim carries bare group names such as
  `freepod-dev` rather than paths such as `/freepod-dev`

## ADDED Requirements

### Requirement: Freepod theme is applied to the realm
The system SHALL configure the `freepod` realm to use the `freepod` login, email
and account themes, so that migrated and new users see Freepod branding rather
than stock Keycloak.

#### Scenario: Themes are set
- **WHEN** the `freepod` realm settings are inspected
- **THEN** `loginTheme`, `emailTheme` and `accountTheme` are each set to
  `freepod`

### Requirement: A dev access group governs the development environment
The system SHALL define a Keycloak group named `freepod-dev` in the `freepod`
realm whose membership determines who may access `dev.freepod.eu`. Membership
SHALL be the sole administrative control for granting and revoking development
access.

#### Scenario: Group exists
- **WHEN** groups are listed for realm `freepod`
- **THEN** a group named `freepod-dev` exists

#### Scenario: Access is granted by group membership
- **WHEN** an operator needs to grant or revoke a user's access to
  `dev.freepod.eu`
- **THEN** it is done by adding or removing that user from the `freepod-dev`
  group
- **AND** no Terraform apply and no second user account are required

### Requirement: The observability group is hosted in the Freepod realm
The system SHALL define the `freepod-observability` group in the `freepod` realm
so that Grafana access is governed by the same user database as Freepod itself,
requiring no separate account.

#### Scenario: Group exists in the Freepod realm
- **WHEN** groups are listed for realm `freepod`
- **THEN** a group named `freepod-observability` exists

#### Scenario: One account serves both Freepod and Grafana
- **WHEN** a user holds membership of both `freepod-dev` and
  `freepod-observability`
- **THEN** the same single account authenticates them to Freepod and to Grafana

### Requirement: Migrated accounts are seeded with a verified, enabled identity
When seeding the existing accounts into the `freepod` realm, the system SHALL
create each user with a verified email and enabled status, SHALL NOT set an
`UPDATE_PASSWORD` required action, and SHALL NOT migrate role mappings. An
account seeded without a credential obtains a password through the self-service
reset flow.

#### Scenario: Seeded account shape
- **WHEN** a migrated account is created in the `freepod` realm
- **THEN** `emailVerified` is `true` and `enabled` is `true`
- **AND** `requiredActions` is empty

#### Scenario: Required actions would lock the account out
- **WHEN** an operator considers setting `requiredActions: ["UPDATE_PASSWORD"]`
  on a credential-less account
- **THEN** it is understood that required actions execute only after successful
  authentication
- **AND** such an account could never reach the action and would be locked out

#### Scenario: Role mappings are not carried over
- **WHEN** a migrated account is created in the `freepod` realm
- **THEN** no role mapping from the `master` realm is applied
- **AND** in particular the `master` realm `admin` role is not granted, since an
  end-user account holding instance-wide administrative rights is the privilege
  concern this migration resolves

#### Scenario: User sets their own password
- **WHEN** a migrated user without a credential requests a password reset from
  the login page
- **THEN** Keycloak emails an action-token link
- **AND** the user sets a password and can sign in

### Requirement: Password hash carry-over is optional and confined to seeding
Password-hash carry-over SHALL be optional per user, and when exercised SHALL be
performed during seeding, through the Keycloak admin API, gated on verifying one
account before any further account receives a credential. Carrying a hash over
spares the user a password reset; omitting it leaves them the self-service reset
flow.

#### Scenario: Carried credential authenticates unchanged
- **WHEN** an account is seeded with its exported `secretData` and
  `credentialData`
- **THEN** the user signs in with their pre-migration password
- **AND** no password reset is required of them

#### Scenario: One account gates the rest
- **WHEN** hash carry-over is attempted
- **THEN** exactly one account is seeded with its credential and verified to
  sign in before any further account is seeded with a credential
- **AND** on failure the remaining accounts are seeded without credentials and
  use the self-service reset flow

#### Scenario: Carry-over is per user and optional
- **WHEN** an operator chooses to carry hashes for some accounts and not others
- **THEN** each account is seeded independently
- **AND** accounts seeded without a credential remain fully usable through
  self-service reset

#### Scenario: Carry-over happens only during seeding
- **WHEN** cutover has completed and users have begun resetting passwords
- **THEN** hash carry-over is not performed, because writing an exported
  credential at that point would silently revert a password the user has already
  changed

#### Scenario: Credentials are written through the admin API
- **WHEN** a credential is carried over
- **THEN** it is written using the Keycloak admin API rather than by direct SQL,
  so that the Infinispan `users` cache is invalidated correctly and no
  `credential` row is hand-assembled

### Requirement: The master realm is retained then decommissioned for end users
The system SHALL leave the `master` realm intact, including its original
credentials, for a soak period after cutover so that it serves as the rollback
path. After the soak period, self-registration SHALL be disabled on `master` and
the migrated end-user accounts removed.

#### Scenario: Rollback remains available during soak
- **WHEN** a problem is discovered after cutover but during the soak period
- **THEN** reverting the issuer configuration restores working authentication
- **AND** users sign in with their pre-migration credentials with no data
  reconstruction

#### Scenario: Registration is closed on master after soak
- **WHEN** the soak period has elapsed
- **THEN** `registrationAllowed` is `false` on the `master` realm
- **AND** the migrated end-user accounts have been deleted from `master`

#### Scenario: The instance administrator remains in master
- **WHEN** end-user accounts are removed from `master`
- **THEN** the `admin` account is retained, because it is the Keycloak instance
  administrator and must reside in the administrative realm

## REMOVED Requirements

### Requirement: Google identity provider is configured
**Reason**: Never implemented. The live realm has zero identity providers
configured and social login is not part of this change. Leaving an unbuilt
requirement in the spec is what allowed the `master`-realm drift to go unnoticed
— the spec asserted a `caelus` realm that never existed.
**Migration**: None. No Google identity provider was ever deployed, so no user
holds a federated identity through it. If social login is wanted later it should
be proposed as its own change.

### Requirement: Apple identity provider is configured
**Reason**: Never implemented; see above.
**Migration**: None. No Apple identity provider was ever deployed and no user
holds a federated identity through it.

### Requirement: Microsoft identity provider is configured
**Reason**: Never implemented; see above.
**Migration**: None. No Microsoft identity provider was ever deployed and no
user holds a federated identity through it.

### Requirement: Caelus client is configured (optional future use)
**Reason**: A speculative `MAY` requirement for a `caelus-api` service-account
client that was never created. Machine access to the Freepod API is being
designed properly in a dedicated follow-up change covering OAuth2 token
authentication for external clients, which supersedes this placeholder.
**Migration**: None. No `caelus-api` client exists, so nothing depends on it.
