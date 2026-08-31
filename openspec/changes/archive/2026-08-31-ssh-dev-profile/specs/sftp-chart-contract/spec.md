## RENAMED Requirements

### Requirement: Products without exposable PVCs render no SFTP resources
- **FROM:** Products without exposable PVCs render no SFTP resources
- **TO:** Products render SSH resources only when they declare an access profile

## MODIFIED Requirements

### Requirement: Products render SSH resources only when they declare an access profile
A chart MUST render a sidecar, a credentials Secret and a Service when its product declares an access profile, and MUST render none of them when it declares no profile.

The trigger is the declared profile, not the presence of a user-visible PVC. Keying it on PVCs was correct while the only profile served files, and it excludes the `dev` profile by construction: `custom` has no persistent volume and is the product that profile exists for.

A product on the `sftp` profile that declares no exposable PVC MUST still render nothing, because that profile's whole purpose is exposing one — its sidecar would offer an empty session.

#### Scenario: Zero-PVC product
- **WHEN** a product without exposable PVCs and without a declared profile is deployed
- **THEN** its namespace contains no SSH-related resources
- **AND** its release name is not routable at the SSH entry point

#### Scenario: Zero-PVC product on the dev profile
- **WHEN** a product without exposable PVCs that declares the `dev` profile is deployed
- **THEN** its namespace contains that profile's sidecar, Secret and Service, and its release name is routable

#### Scenario: sftp profile with nothing to expose
- **WHEN** a product declaring the `sftp` profile exposes no PVC
- **THEN** it renders no SSH resources

### Requirement: Per-deployment Service targets the sidecar
The chart MUST render a ClusterIP Service targeting the sidecar's SSH port (2222), as part of the Helm release so it is created, upgraded, and deleted with the deployment. It MUST NOT render any routing object: the edge resolves where a username goes at connection time, so nothing in the release describes the route.

The Service's name MUST follow the platform's single naming convention, which the SSH edge uses to derive a deployment's upstream address. The convention is shared with the edge and MUST NOT be changed on one side alone: a chart rendering a name the edge does not expect produces a deployment that authenticates and then reaches nothing.

The whole of what a deployment contributes to SSH access is therefore inside its Helm release, and uninstalling the release removes all of it. No object survives the deployment, so nothing has to be swept for objects that do.

The Service MUST publish not-ready addresses, so its endpoints include the deployment's pod whenever that pod exists, irrespective of the pod's readiness. This Service does not front the application: it fronts an administrative sidecar whose availability is deliberately independent of the application's, so application readiness MUST NOT gate routing to it.

#### Scenario: Service is rendered by the chart
- **WHEN** the Helm release is installed
- **THEN** a ClusterIP Service targeting the sidecar on port 2222 exists in the deployment's namespace

#### Scenario: Service name matches what the edge derives
- **WHEN** the edge derives a deployment's upstream address
- **THEN** it names the Service the chart rendered for that deployment

#### Scenario: Chart renders no routing object
- **WHEN** the chart's output is rendered
- **THEN** it contains no `Pipe` and no other object describing an SSH route

#### Scenario: Uninstall removes everything the deployment contributed
- **WHEN** the Helm release is uninstalled
- **THEN** the Service and sidecar are removed with it, the username stops being routable, and no object remains for the platform to clean up

#### Scenario: Service endpoints include a not-ready pod
- **WHEN** the deployment's pod exists but is not ready
- **THEN** the SFTP Service's endpoints still include that pod's address, and traffic to the Service reaches the sidecar
