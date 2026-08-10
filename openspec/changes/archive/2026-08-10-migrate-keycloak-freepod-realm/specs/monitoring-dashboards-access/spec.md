## MODIFIED Requirements

### Requirement: Keycloak-authenticated access with a user whitelist

The system SHALL expose Grafana at `grafana.freepod.eu` and authenticate users
via native Keycloak OIDC against the `freepod` realm, restricting access to
members of a designated Keycloak group (the whitelist). Users outside the group
SHALL be denied. Because Grafana authenticates against the same realm as
Freepod, an operator needs only one account.

#### Scenario: Whitelisted user signs in

- **WHEN** a user who is a member of the `freepod-observability` Keycloak group
  authenticates through Grafana's OIDC login
- **THEN** they are granted access with a mapped Grafana role

#### Scenario: Non-whitelisted user is denied

- **WHEN** a user who is not a member of the group attempts to sign in
- **THEN** Grafana refuses the login (strict role/group enforcement), granting
  no default access

#### Scenario: Whitelist is managed in Keycloak

- **WHEN** an operator needs to grant or revoke a user's Grafana access
- **THEN** it is done by adding/removing that user from the Keycloak group, with
  no Terraform apply or Grafana user-list change required

#### Scenario: Grafana targets the Freepod realm

- **WHEN** Grafana's generic OAuth configuration is inspected
- **THEN** its authorization, token and userinfo URLs all reference
  `https://keycloak.freepod.eu/realms/freepod`
- **AND** none of them reference the `master` realm

#### Scenario: One account serves Grafana and Freepod

- **WHEN** a user with an account in the `freepod` realm is added to
  `freepod-observability`
- **THEN** they sign in to Grafana with that same account
- **AND** no separate Grafana-only Keycloak account is required

#### Scenario: Group claim reaches Grafana

- **WHEN** the Grafana Keycloak client is inspected
- **THEN** the `groups` scope is assigned as a default client scope
- **AND** Grafana is configured to read the `groups` claim, without which its
  group extraction returns an empty list and every login is rejected
