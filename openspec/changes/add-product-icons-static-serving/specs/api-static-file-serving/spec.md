## ADDED Requirements

### Requirement: Public static endpoint SHALL serve files from STATIC_PATH root
The system MUST expose `GET /api/static/{path}` for public, unauthenticated reads of files rooted at `STATIC_PATH`.

#### Scenario: Serving an existing file
- **WHEN** a client requests `/api/static/{path}` for a file that exists under `STATIC_PATH`
- **THEN** the API SHALL return `200` with the file content

#### Scenario: Public access
- **WHEN** an unauthenticated client requests `/api/static/{path}` for an existing file
- **THEN** the API SHALL serve the file without authorization checks

### Requirement: Static path handling SHALL prevent traversal outside STATIC_PATH
The static file serving path resolution MUST reject access outside the configured static root.

#### Scenario: Path traversal attempt
- **WHEN** a client requests a path such as `../../../etc/passwd`
- **THEN** the API SHALL NOT expose files outside `STATIC_PATH` and SHALL return `404`

### Requirement: Static responses SHALL include cache validation support
The static file endpoint MUST provide validator headers and honor conditional requests.

#### Scenario: ETag present on static response
- **WHEN** a static file is served successfully
- **THEN** the response SHALL include an `ETag` header

#### Scenario: If-None-Match hit
- **WHEN** a client sends `If-None-Match` matching the current file ETag
- **THEN** the API SHALL return `304 Not Modified`

### Requirement: Static responses SHALL emit correct media type
The static endpoint MUST return content types appropriate for served files.

#### Scenario: PNG icon response
- **WHEN** a stored PNG icon is requested from `/api/static/{path}`
- **THEN** the response SHALL include `Content-Type: image/png`

### Requirement: Production runtime SHALL mount static storage only in API pods
Infrastructure MUST provide writable static storage to API runtime while excluding worker runtime.

#### Scenario: API pod configuration
- **WHEN** production Terraform manifests are applied
- **THEN** API pods SHALL mount a static PVC at `/var/static` and set `STATIC_PATH=/var/static`

#### Scenario: Worker pod configuration
- **WHEN** production Terraform manifests are applied
- **THEN** worker pods SHALL NOT mount the static PVC and SHALL NOT rely on `STATIC_PATH`
