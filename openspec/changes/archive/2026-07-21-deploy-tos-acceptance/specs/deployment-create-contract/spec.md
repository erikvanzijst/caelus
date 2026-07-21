## ADDED Requirements

### Requirement: Deployment create requires prior ToS acceptance

Deployment create MUST NOT carry any ToS field, for either REST
`POST /users/{user_id}/deployments` or the equivalent CLI command. Instead it
MUST require that the owning user has already accepted the current Terms of
Service (recorded via `POST /api/me/tos-acceptance`). A create for a user who has not accepted MUST be
rejected with a client error (**400**) and MUST NOT create a deployment. This
guard is enforced server-side so the two-step accept-then-deploy flow cannot be
bypassed by a direct API or CLI client.

#### Scenario: Deploy after acceptance succeeds

- **WHEN** a user who has recorded ToS acceptance creates a deployment with an
  otherwise valid payload
- **THEN** the API creates the deployment, and its payload and response contain
  no ToS field

#### Scenario: Deploy without acceptance is rejected

- **WHEN** a user who has not accepted the Terms attempts to create a deployment
- **THEN** the API responds **400** and no deployment is created

#### Scenario: CLI deploy without acceptance is rejected

- **WHEN** an operator runs the CLI create-deployment command for a user who has
  not accepted
- **THEN** the command fails without creating a deployment
