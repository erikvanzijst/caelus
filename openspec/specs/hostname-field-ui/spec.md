# hostname-field-ui Specification

## Purpose
TBD - created by archiving change hostname-validation-and-domains. Update Purpose after archive.
## Requirements
### Requirement: HostnameField component supports dual-mode hostname input
The system MUST provide a `HostnameField` React component in `ui/src/components/HostnameField.tsx` that supports two modes of hostname entry:
1. **Caelus wildcard mode**: A text input for the hostname prefix combined with a dropdown selector for the wildcard domain suffix, concatenated as `${prefix}.${selectedDomain}`.
2. **Custom FQDN mode**: A single text input for the complete FQDN.

The user MUST be able to toggle between modes.

#### Scenario: User enters hostname via Caelus wildcard mode
- **WHEN** the user types `myapp` in the prefix field and selects `app.deprutser.be` from the dropdown
- **THEN** the component emits the combined value `myapp.app.deprutser.be` via `onChange`

#### Scenario: User enters hostname via custom FQDN mode
- **WHEN** the user types `myapp.example.com` in the custom FQDN input
- **THEN** the component emits `myapp.example.com` via `onChange`

#### Scenario: Switching modes clears previous input
- **WHEN** the user switches from wildcard mode to custom mode (or vice versa)
- **THEN** the input fields are reset and `onChange` is called with the new (possibly empty) value

### Requirement: HostnameField fetches wildcard domains from API
The component MUST fetch the list of available wildcard domains from `GET /api/domains` (via React Query) and populate the domain suffix dropdown.

#### Scenario: Wildcard domains loaded successfully
- **WHEN** `GET /api/domains` returns `["app.deprutser.be"]`
- **THEN** the dropdown contains `app.deprutser.be` as a selectable option

#### Scenario: No wildcard domains available
- **WHEN** `GET /api/domains` returns `[]`
- **THEN** the wildcard mode dropdown is empty or the wildcard mode option is hidden, and the component defaults to custom FQDN mode

### Requirement: HostnameField performs debounced real-time validation
The component MUST call `GET /api/hostnames/{fqdn}` with approximately 400ms debounce after the last keystroke to validate the current hostname. The API MUST NOT be called when the input is empty.

#### Scenario: Validation triggered after typing pauses
- **WHEN** the user types `myapp.app.deprutser.be` and stops typing for ~400ms
- **THEN** the component calls `GET /api/hostnames/myapp.app.deprutser.be`

#### Scenario: Rapid typing does not flood API
- **WHEN** the user types multiple characters in quick succession (within 400ms)
- **THEN** only one API call is made for the final value

#### Scenario: Empty input does not trigger validation
- **WHEN** the hostname input is empty
- **THEN** no API call is made and no status icon is shown

### Requirement: HostnameField displays validation status icon
The component MUST display a status indicator icon on the right side of the input field:
- **Green check** (MUI CheckCircle): `reason === null` (hostname is usable)
- **Red error** (MUI Error icon) with tooltip: `reason !== null` (hostname cannot be used)
- **Spinner** (MUI CircularProgress): API call is in flight

The tooltip on the red error icon MUST display a human-readable message corresponding to the reason:
- `"invalid"` -> "Invalid hostname format"
- `"reserved"` -> "Hostname is reserved"
- `"in_use"` -> "Already in use"
- `"not_resolving"` -> "Does not resolve to Caelus"

#### Scenario: Usable hostname shows green check
- **WHEN** the API returns `{"fqdn": "myapp.app.deprutser.be", "reason": null}`
- **THEN** a green CheckCircle icon is displayed

#### Scenario: Taken hostname shows red error with tooltip
- **WHEN** the API returns `{"fqdn": "taken.app.deprutser.be", "reason": "in_use"}`
- **THEN** a red Error icon is displayed with tooltip text "Already in use"

#### Scenario: Loading state shows spinner
- **WHEN** an API call is in flight
- **THEN** a CircularProgress spinner is displayed in place of the status icon

### Requirement: UserValuesForm detects hostname fields and renders HostnameField
The `UserValuesForm` component MUST detect schema fields where `field.title` (case-insensitive) equals `"hostname"` and render a `<HostnameField>` component instead of a standard `<TextField>` for those fields.

#### Scenario: Schema field with title "hostname" renders HostnameField
- **WHEN** the template schema contains a field with `"title": "hostname"`
- **THEN** the form renders a `HostnameField` component for that field

#### Scenario: Schema field with title "Hostname" (mixed case) renders HostnameField
- **WHEN** the template schema contains a field with `"title": "Hostname"`
- **THEN** the form renders a `HostnameField` component for that field

#### Scenario: Schema field with other title renders standard TextField
- **WHEN** the template schema contains a field with `"title": "Server Name"`
- **THEN** the form renders a standard `TextField` for that field

### Requirement: HostnameField integrates with UserValuesForm state
The `HostnameField` component MUST integrate with the existing `UserValuesForm` flattened state. The `onChange` callback MUST feed the hostname value back into the form's state using the field's dot-notation path.

#### Scenario: Hostname value flows into form submission
- **WHEN** the user enters `myapp.app.deprutser.be` in the HostnameField for a field at path `ingress.host`
- **THEN** the form's unflattened output includes `{"ingress": {"host": "myapp.app.deprutser.be"}}`

## Requirements from edit-deployment-config

### Requirement: HostnameField skips validation for unchanged hostname

#### Scenario: Initial hostname skips API validation
- **WHEN** `HostnameField` receives an `initialHostname` prop and the current FQDN equals `initialHostname`
- **THEN** the component sets validation status to `valid` without calling `GET /api/hostnames/{fqdn}`

#### Scenario: Changed hostname triggers normal validation
- **WHEN** `HostnameField` receives an `initialHostname` prop and the current FQDN differs from `initialHostname`
- **THEN** the component calls `GET /api/hostnames/{fqdn}` with the normal debounce behavior

#### Scenario: Reverted hostname skips validation again
- **WHEN** the user changes the hostname away from `initialHostname` and then changes it back
- **THEN** the component sets validation status to `valid` without calling the API
