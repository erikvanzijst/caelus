## ADDED Requirements

### Requirement: Deployment view shows SFTP access details
The deployment detail view MUST display an SFTP/file-access panel for deployments that have SFTP access, showing host, port, username, and password, with the password masked by default and revealable, and copy-to-clipboard affordances for each field. The panel MUST be implemented as its own component under `ui/src/components/` (not inlined into page-level components).

#### Scenario: Owner views SFTP details
- **WHEN** the owner opens the detail view of a deployment with file access
- **THEN** the SFTP panel shows the host and port reported by the API (`freepod.eu:22` in prod, `dev.freepod.eu:23` in dev), the username, and a masked password
- **AND** the password can be revealed and copied

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
