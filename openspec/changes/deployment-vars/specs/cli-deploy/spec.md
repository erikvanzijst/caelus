## ADDED Requirements

### Requirement: Deploy can roll a deployment without rebuilding it
`freepod deploy --no-build` SHALL create a release from the deployment's current image,
skipping the project archive upload and the build. This is what applies a staged
configuration change, and it also rolls a deployment whose source has not changed.

The command SHALL carry the applied release's build reference forward: it SHALL submit
the same image and the same build the applied release named, so that the new release
still records which build produced the code it is running.

`--no-build` SHALL be refused when the deployment has no applied release to take an image
from.

#### Scenario: Applying a staged var change
- **WHEN** a developer runs `freepod deploy --no-build` on a deployment with staged vars
- **THEN** a release is created from the current image, with no build
- **AND** the staged vars take effect

#### Scenario: The build reference is preserved
- **WHEN** `freepod deploy --no-build` rolls a deployment whose applied release named a
  build
- **THEN** the new release names the same build

#### Scenario: No image to roll
- **WHEN** a developer runs `freepod deploy --no-build` on a deployment that has never
  been applied
- **THEN** the command fails and explains that there is nothing to roll
