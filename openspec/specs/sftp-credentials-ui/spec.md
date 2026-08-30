## Purpose

Users interact with their deployments through the web UI, so file-access credentials must be surfaced there. This capability adds a dedicated SFTP panel to the deployment detail view that displays the host, port and username with copy affordances, states that access is authenticated by an SSH key registered on the account, and communicates that access is read-only. It shows no credential, because none exists. The panel appears only for deployments that actually have file access, driven by the credentials API's absence semantics, and is implemented as its own reusable component rather than inlined into a page-level component.

## Requirements

### Requirement: Deployment view shows SFTP access details and how to authenticate
The deployment detail view MUST display an SFTP/file-access panel for deployments that have SFTP access, showing host, port and username, with copy-to-clipboard affordances. The panel MUST be implemented as its own component under `ui/src/components/` (not inlined into page-level components).

The panel MUST NOT display a password field, masked or otherwise, and MUST NOT present the absence of one as missing information. It MUST state that access is authenticated by an SSH key registered on the account, and MUST link to where those keys are managed.

When the owning account has no registered key, the panel MUST say so and MUST make that the prominent instruction, because in that state no connection can succeed and the connection details alone are useless.

#### Scenario: Owner views SFTP details
- **WHEN** the owner opens the detail view of a deployment with file access
- **THEN** the panel shows the host and port reported by the API (`freepod.eu:22` in prod, `dev.freepod.eu:23` in dev) and the username
- **AND** no password field is shown

#### Scenario: Panel explains key authentication
- **WHEN** the panel renders
- **THEN** it states that access uses an SSH key registered on the account and links to where keys are managed

#### Scenario: Account with no key is told what to do
- **WHEN** the owning account has no registered SSH key
- **THEN** the panel prominently says a key must be registered before connecting, and links to where to do it

#### Scenario: Absence of a password is not an error
- **WHEN** the panel renders
- **THEN** nothing presents the missing password as a failure or a pending value

### Requirement: Panel is absent for deployments without file access
When the API reports that SFTP is not available for a deployment, the UI MUST NOT render the SFTP panel or any placeholder implying file access exists.

#### Scenario: Zero-PVC product deployment
- **WHEN** the owner opens the detail view of a deployment whose product exposes no files
- **THEN** no SFTP panel is shown

### Requirement: Read-only nature is communicated
The panel MUST state that access is read-only (browse and download), so users do not attempt uploads and report them as failures.

#### Scenario: User reads the panel
- **WHEN** the SFTP panel is rendered
- **THEN** it includes a brief note that file access is read-only
