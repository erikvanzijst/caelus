# cli-vars Specification

## Purpose
Defines the `freepod var` command group: how a developer reads, sets and removes a
deployment's runtime configuration from the CLI, and when doing so rolls the deployment.
## Requirements
### Requirement: The CLI reads a deployment's vars
`freepod var list` SHALL print the deployment's current vars, and `freepod var get KEY`
SHALL print one. A sensitive var SHALL be listed by key with its value shown as hidden,
because the platform does not return it.

`freepod var list --json` SHALL emit the platform's wire shape verbatim, so that its
output can be fed back into `freepod var set` without deleting or altering any sensitive
var.

#### Scenario: Listing a mixture
- **WHEN** a deployment holds one sensitive and one ordinary var
- **THEN** both keys are listed
- **AND** the sensitive one shows no value

#### Scenario: Round-tripping through JSON
- **WHEN** the output of `freepod var list --json` is submitted through
  `freepod var set -f -`
- **THEN** no var is deleted and no value changes

### Requirement: Setting and removing vars applies by default and can be staged
`freepod var set` and `freepod var rm` SHALL write the vars and then roll the deployment,
so the change takes effect. `--stage` SHALL write the vars without rolling, reporting how
many vars are pending and how to apply them.

Several vars given in one invocation SHALL produce one rollout, not one per var.

A var write that would roll a deployment which is not ready SHALL be refused with an
error that suggests `--stage`; a staged write SHALL be accepted whatever the deployment's
state, since it touches no release.

#### Scenario: Setting a var
- **WHEN** a developer runs `freepod var set LOG_LEVEL=debug`
- **THEN** the var is written and the deployment is rolled

#### Scenario: Setting several at once
- **WHEN** a developer runs `freepod var set A=1 B=2`
- **THEN** both are written and exactly one release is created

#### Scenario: Staging
- **WHEN** a developer runs `freepod var set A=1 --stage`
- **THEN** the var is written, no release is created, and the pending count is reported

#### Scenario: Setting while a rollout is in flight
- **WHEN** a developer runs `freepod var set A=1` against a deployment that is
  provisioning
- **THEN** the command fails and suggests `--stage`

### Requirement: A secret value need not appear in the shell history
`freepod var set` SHALL accept a bare `KEY` with no value and, on an interactive
terminal, prompt for the value without echoing it. It SHALL also accept `-f FILE`
carrying either the platform's wire shape or `KEY=VALUE` lines, and `-` for standard
input.

`--secret` SHALL mark the vars written by that invocation as sensitive. For a deployment
whose product declares sensitivity in its schema, `--secret` SHALL be ignored with a
warning, since the schema decides.

#### Scenario: Prompting
- **WHEN** a developer runs `freepod var set ADMIN_TOKEN` on a terminal
- **THEN** the value is prompted for without echo and does not appear in the command line

#### Scenario: Marking a var sensitive
- **WHEN** a developer runs `freepod var set ADMIN_TOKEN=... --secret`
- **THEN** the var is stored as sensitive and is not returned by later reads

### Requirement: The CLI reports pending vars before rolling a deployment
`freepod deploy` SHALL report, before it rolls, when the deployment has vars that are not
yet running, so a developer is not surprised by a staged change taking effect alongside a
code change.

#### Scenario: Deploying with staged vars
- **WHEN** a developer runs `freepod deploy` on a deployment with two staged vars
- **THEN** the CLI reports that two vars will be applied by this rollout
