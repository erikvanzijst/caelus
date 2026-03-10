# keycloak-user-realm Specification

## Purpose
Configure Keycloak realm with local user registration, email validation, and social identity providers.

## ADDED Requirements

### Requirement: Keycloak has a Caelus realm
The system SHALL create a dedicated Keycloak realm named `caelus`.

#### Scenario: Caelus realm exists
- **WHEN** Keycloak admin API is queried for realms
- **THEN** a realm named `caelus` exists

### Requirement: Local user registration is enabled
The system SHALL enable self-registration in the Caelus realm.

#### Scenario: Self-registration is enabled
- **WHEN** Keycloak realm settings are inspected
- **THEN** `registrationAllowed` is set to `true`

### Requirement: Email verification is required
The system SHALL require email verification for new user accounts.

#### Scenario: Email verification is required
- **WHEN** Keycloak realm settings are inspected
- **THEN** `verifyEmail` is set to `true`

### Requirement: SMTP is configured for email sending
The system SHALL configure Keycloak SMTP settings for sending verification emails.

#### Scenario: SMTP is configured
- **WHEN** Keycloak realm SMTP settings are inspected
- **THEN** host, port, from address, and credentials are configured

### Requirement: Google identity provider is configured
The system SHALL add Google as an OIDC identity provider.

#### Scenario: Google IDP exists
- **WHEN** Keycloak identity providers are listed for realm `caelus`
- **THEN** a provider with alias `google` exists
- **AND** client ID and secret are configured

### Requirement: Apple identity provider is configured
The system SHALL add Apple as an OIDC identity provider.

#### Scenario: Apple IDP exists
- **WHEN** Keycloak identity providers are listed for realm `caelus`
- **THEN** a provider with alias `apple` exists
- **AND** client ID and secret are configured

### Requirement: Microsoft identity provider is configured
The system SHALL add Microsoft (Azure AD) as an OIDC identity provider.

#### Scenario: Microsoft IDP exists
- **WHEN** Keycloak identity providers are listed for realm `caelus`
- **THEN** a provider with alias `microsoft` exists
- **AND** client ID, tenant, and secret are configured

### Requirement: OAuth2 proxy client is configured
The system SHALL create a client in Keycloak for oauth2-proxy.

#### Scenario: oauth2-proxy client exists
- **WHEN** Keycloak clients are listed for realm `caelus`
- **THEN** a client with client ID `oauth2-proxy` exists
- **AND** client protocol is `openid-connect`
- **AND** access type is `confidential`
- **AND** valid redirect URIs include the oauth2-proxy callback URL
- **AND** web origins are configured

### Requirement: Client scopes map email claim
The system SHALL configure client scopes to ensure email is included in tokens.

#### Scenario: Email scope is assigned to oauth2-proxy client
- **WHEN** oauth2-proxy client scopes are inspected
- **THEN** the `email` scope is assigned

### Requirement: Caelus client is configured (optional future use)
The system MAY create a service account client for Caelus API access.

#### Scenario: Caelus client exists (if created)
- **WHEN** Keycloak clients are listed for realm `caelus`
- **THEN** a client with client ID `caelus-api` exists (if configured)
- **AND** service accounts enabled is `true`
