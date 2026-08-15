## Purpose

How the client chooses which Freepod instance it is talking to, and why that choice is
a closed set of named environments rather than a caller-supplied address.

## ADDED Requirements

### Requirement: The client targets one of two named environments

The client SHALL support exactly two environments, `prod` and `dev`, each carrying its
own API base address, OAuth2 client identifier, and issuer. The environment SHALL be
selectable per invocation and SHALL default to `prod`.

The client SHALL NOT accept a caller-supplied API base address. An access token is bound
by its audience to exactly one environment, so an arbitrary address would additionally
require the issuer and client identifier to be discovered, which the platform does not
publish.

#### Scenario: Production is the default target

- **WHEN** a command runs with no environment selected
- **THEN** the client targets the production environment

#### Scenario: The environment can be selected explicitly

- **WHEN** a command runs with the environment selected as `dev`
- **THEN** the client targets the development API, client identifier, and issuer

#### Scenario: The environment can be selected through the environment variable

- **WHEN** `FREEPOD_ENV` names an environment and no explicit selection is made
- **THEN** the client targets that environment

#### Scenario: An unknown environment is refused

- **WHEN** a command runs with an environment name that is not `prod` or `dev`
- **THEN** the client refuses with a usage error naming the accepted values

### Requirement: State is never shared between environments

The client SHALL keep credentials and project state separated per environment, so that
material obtained for one environment is never presented to the other.

#### Scenario: Credentials do not cross environments

- **WHEN** the client holds a credential for one environment and a command targets the
  other
- **THEN** the credential for the targeted environment is used, or authentication is
  requested for it
- **AND** the other environment's credential is never sent

#### Scenario: A token issued for one environment is rejected by the other

- **WHEN** an access token issued for the development environment reaches the production
  API
- **THEN** the request is refused, because audience verification fails
