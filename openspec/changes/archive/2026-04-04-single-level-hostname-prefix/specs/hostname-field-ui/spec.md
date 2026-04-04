## MODIFIED Requirements

### Requirement: HostnameField component supports dual-mode hostname input
The system MUST provide a `HostnameField` React component in `ui/src/components/HostnameField.tsx` that supports two modes of hostname entry:
1. **Caelus wildcard mode**: A text input for the hostname prefix combined with a dropdown selector for the wildcard domain suffix, concatenated as `${prefix}.${selectedDomain}`. The prefix input MUST NOT allow dot characters — dots MUST be stripped from the input value.
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

#### Scenario: Dots are stripped from wildcard prefix input
- **WHEN** the user types or pastes `foo.bar` in the wildcard-mode prefix field
- **THEN** the prefix value becomes `foobar` (dots removed) and the component emits `foobar.app.deprutser.be` via `onChange`

#### Scenario: Custom FQDN mode allows dots
- **WHEN** the user types `foo.bar.example.com` in the custom FQDN input
- **THEN** the component emits `foo.bar.example.com` via `onChange` without stripping any characters

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
- `"nested_subdomain"` -> "Only a single subdomain level is allowed"

#### Scenario: Usable hostname shows green check
- **WHEN** the API returns `{"fqdn": "myapp.app.deprutser.be", "reason": null}`
- **THEN** a green CheckCircle icon is displayed

#### Scenario: Nested subdomain shows error with tooltip
- **WHEN** the API returns `{"fqdn": "foo.bar.dev.deprutser.be", "reason": "nested_subdomain"}`
- **THEN** a red Error icon is displayed with tooltip text "Only a single subdomain level is allowed"
