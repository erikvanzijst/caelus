# cli-project-file Specification

## Purpose
The committed file that records what a project deploys as and where, so that a checkout
of the repository is enough to deploy it again, and so that the file stays free of
anything a deploy would have to rewrite.
## Requirements
### Requirement: A project is described by a committed JSON file

The client SHALL record a project's deployment intent in a file named `.freepod.json`
at the project root, in JSON. The file SHALL carry a format version, the environment it
belongs to, a deployment pointer, and the user-supplied configuration values for the
deployment.

The file SHALL contain no credentials or other secrets, so that committing it to version
control is safe and expected.

#### Scenario: The file describes a project before its first deploy

- **WHEN** a project has been initialized but never deployed
- **THEN** `.freepod.json` carries its format version, environment, and user values
- **AND** its deployment pointer is empty

#### Scenario: The file is safe to commit

- **WHEN** `.freepod.json` is inspected
- **THEN** it contains no token, key, or other credential material

### Requirement: The project root is discovered by walking upwards

The client SHALL locate the project by searching the current directory and then its
ancestors for `.freepod.json`. The directory containing that file SHALL be the project
root for every subsequent operation.

#### Scenario: A command works from a subdirectory

- **WHEN** a command runs from a subdirectory of an initialized project
- **THEN** the project root is the directory holding `.freepod.json`

#### Scenario: An uninitialized directory is reported clearly

- **WHEN** a command that requires a project runs where no `.freepod.json` exists in the
  directory or its ancestors
- **THEN** the client reports that the project is not initialized and names the command
  that initializes it

### Requirement: A project file is pinned to one environment

The project file SHALL record the environment its deployment belongs to. When a command
targets a different environment than the file records, the client SHALL refuse rather
than proceed, because a deployment identifier has no meaning in another environment.

#### Scenario: A mismatched environment is refused

- **WHEN** a deploy targets an environment other than the one recorded in the project
  file
- **THEN** the client refuses and reports both environments
- **AND** no deployment is created or modified

### Requirement: Build outputs are never recorded in the project file

The project file SHALL hold declared intent only. The image reference produced by a
build SHALL NOT be written to it — neither as a value nor as an explicit null, since the
platform's schema declares that field as a string and would reject a null.

#### Scenario: A successful deploy does not modify user values

- **WHEN** a deploy completes successfully and releases a newly built image
- **THEN** the project file's user values are unchanged
- **AND** they contain no image field

### Requirement: The deployment pointer records both identifier and name

Once a deployment exists, the client SHALL record its identifier and its
platform-assigned name in the project file. The name SHALL be used when referring to the
deployment in output, because it is immutable and more legible than the identifier.

#### Scenario: The pointer is written on first deploy

- **WHEN** a deploy creates the deployment
- **THEN** the project file records the deployment's identifier and name
- **AND** it is written before the client waits for the rollout to finish

