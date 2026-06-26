## MODIFIED Requirements

### Requirement: HostnameField displays validation status icon
The component MUST display a status indicator icon on the right side of the input field:
- **Green check** (MUI CheckCircle): `reason === null` (hostname is usable)
- **Red error** (MUI Error icon) with tooltip: `reason !== null` (hostname cannot be used)
- **Spinner** (MUI CircularProgress): API call is in flight

The tooltip on the red error icon MUST display a human-readable message corresponding to the reason:
- `"invalid"` → "Invalid hostname format"
- `"reserved"` → "Hostname is reserved"
- `"in_use"` → "Already in use"
- `"not_resolving"` → "Create a CNAME record pointing to <cname-target>", where `<cname-target>` is the platform's CNAME target domain fetched from `GET /api/cname-target` (e.g. `freepod.eu` in prod, `dev.freepod.eu` in dev), falling back to `freepod.eu` when the value is empty/unavailable
- `"nested_subdomain"` → "Only a single subdomain level is allowed"

#### Scenario: Usable hostname shows green check
- **WHEN** the API returns `{"fqdn": "myapp.freepod.eu", "reason": null}`
- **THEN** a green CheckCircle icon is displayed

#### Scenario: Taken hostname shows red error with tooltip
- **WHEN** the API returns `{"fqdn": "taken.freepod.eu", "reason": "in_use"}`
- **THEN** a red Error icon is displayed with tooltip text "Already in use"

#### Scenario: Not-resolving hostname shows CNAME instruction in tooltip
- **WHEN** the API returns `{"fqdn": "myapp.example.com", "reason": "not_resolving"}` and `GET /api/cname-target` returned `"dev.freepod.eu"`
- **THEN** a red Error icon is displayed with tooltip text "Create a CNAME record pointing to dev.freepod.eu"

#### Scenario: Nested subdomain shows error with tooltip
- **WHEN** the API returns `{"fqdn": "foo.bar.dev.freepod.eu", "reason": "nested_subdomain"}`
- **THEN** a red Error icon is displayed with tooltip text "Only a single subdomain level is allowed"

#### Scenario: Loading state shows spinner
- **WHEN** an API call is in flight
- **THEN** a CircularProgress spinner is displayed in place of the status icon

## ADDED Requirements

### Requirement: HostnameField shows CNAME setup instructions in custom domain mode
When the component is in custom FQDN mode, it MUST display static helper text below the input instructing the user to create a CNAME record pointing their domain to the platform's CNAME target domain (fetched from `GET /api/cname-target`, falling back to `freepod.eu` when empty/unavailable). This text MUST be visible as soon as custom mode is active, regardless of validation state.

#### Scenario: Helper text visible immediately on switching to custom mode
- **WHEN** the user switches to custom domain mode and `GET /api/cname-target` returned `"dev.freepod.eu"`
- **THEN** helper text "Point your domain at Freepod: create a CNAME record → dev.freepod.eu" is visible below the input field

#### Scenario: Helper text visible while typing in custom mode
- **WHEN** the user is typing a custom FQDN
- **THEN** the CNAME instruction helper text remains visible

#### Scenario: Helper text not shown in wildcard mode
- **WHEN** the component is in wildcard (free domain) mode
- **THEN** no CNAME instruction helper text is displayed
