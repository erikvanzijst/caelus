## ADDED Requirements

### Requirement: Email chip is a dropdown menu trigger
The email display in the AppBar top-right corner SHALL be a clickable element
that opens a dropdown menu. It SHALL display the text
`<user.email>` when a user is authenticated, or `No email set`
when no user is loaded.

#### Scenario: User clicks the email element
- **WHEN** an authenticated user clicks on the email chip/button in the AppBar
- **THEN** a dropdown menu opens anchored to the element
- **AND** the menu contains a "Logout" option

#### Scenario: Menu closes on outside click
- **WHEN** the dropdown menu is open
- **AND** the user clicks outside the menu
- **THEN** the menu closes

### Requirement: Production logout navigates to oauth2-proxy sign_out
When the application is running behind oauth2-proxy (no localStorage auth
headers), clicking "Logout" SHALL navigate the browser to the oauth2-proxy
sign_out endpoint.

#### Scenario: Logout in production
- **WHEN** `getStoredAuthHeaders()` returns an empty object
- **AND** the user clicks "Logout" in the dropdown menu
- **THEN** the browser navigates to
  `/oauth2/sign_out?rd=<encodeURIComponent(window.location.origin + '/')>`
- **AND** the full server-side logout flow executes (Keycloak session
  terminated, proxy cookie cleared, redirect to app, re-authentication required)

### Requirement: Local dev logout clears stored headers and reloads
When the application is running in local development mode (localStorage auth
headers present), clicking "Logout" SHALL clear the stored auth headers and
reload the page to re-trigger the email dialog.

#### Scenario: Logout in local dev
- **WHEN** `getStoredAuthHeaders()` returns a non-empty object
- **AND** the user clicks "Logout" in the dropdown menu
- **THEN** the `caelus.auth.headers` key is removed from localStorage
- **AND** the page is reloaded
- **AND** after reload, the `EmailDialog` appears because no user session exists

### Requirement: clearStoredAuthHeaders utility
The `useAuthEmail.ts` module SHALL export a `clearStoredAuthHeaders()` function
that removes the `caelus.auth.headers` key from `window.localStorage`.

#### Scenario: Clearing headers
- **WHEN** `clearStoredAuthHeaders()` is called
- **THEN** `window.localStorage.getItem('caelus.auth.headers')` returns `null`
- **AND** subsequent calls to `getStoredAuthHeaders()` return `{}`
