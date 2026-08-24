## ADDED Requirements

### Requirement: Deployment create and update accept vars as a write-only field
The deployment create and update payloads SHALL accept a `vars` field carrying the same
wire shape as the vars sub-resource. The field SHALL be write-only: it MUST NOT appear on
any deployment read model.

Accepting vars on create is what allows a deployment's **first** release to run with its
configuration, rather than necessarily running once without it and picking it up on a
later rollout.

The field carries a flat map of keys, with no phase dimension: vars submitted this way
are **runtime** vars. That is not a simplification to be revisited — a value consumed
before the deployment exists cannot be supplied on the request that creates it, because
the image is built first (see `cli-deploy`).

On update, `vars` SHALL be merged into the deployment's existing vars, not replace them:
a rollout that says nothing about vars MUST NOT delete them.

Vars submitted this way SHALL be validated and stored exactly as those submitted to the
vars sub-resource, and SHALL be captured by the release the request creates.

#### Scenario: Creating a deployment with vars
- **WHEN** a caller creates a deployment with two vars
- **THEN** the deployment's head holds both
- **AND** the first release's snapshot holds both

#### Scenario: The field is not echoed
- **WHEN** a caller creates or updates a deployment with vars
- **THEN** the response does not contain the submitted `vars` field

#### Scenario: Updating without mentioning vars
- **WHEN** a caller updates a deployment and omits `vars`
- **THEN** the deployment's existing vars are unchanged and are captured by the new
  release

#### Scenario: Updating with one var
- **WHEN** a caller updates a deployment supplying one var, and head holds two others
- **THEN** all three are in head afterwards

### Requirement: A deployment read reports its vars and whether they are running
A single-deployment read SHALL report the deployment's current vars — its head, which is
desired state, matching `user_values_json` — together with a `pending` flag as defined in
`deployment-vars-api`.

Head is reported rather than the applied release's snapshot because the rest of the read
model reports intent; mixing desired chart values with applied runtime values in one
response is the confusion `pending` exists to expose.

Vars SHALL NOT be included in the deployment **list** response, which would make it a
per-row lookup and would fatten a payload that no caller reads vars from.

#### Scenario: Reading one deployment
- **WHEN** a caller reads a deployment that has vars
- **THEN** the response carries the head, with sensitive values omitted
- **AND** it carries `pending`

#### Scenario: Listing deployments
- **WHEN** a caller lists deployments
- **THEN** no deployment in the list carries vars
