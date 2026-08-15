## Purpose

How the client obtains, stores, and renews a credential for a non-browser context, and
how it must interpret the platform's authentication and authorization responses — which
do not follow the conventional reading of HTTP status codes.

## ADDED Requirements

### Requirement: The client authenticates through a loopback redirect when a browser is reachable

The client SHALL support the authorization code grant with PKCE, receiving the
authorization code on an HTTP listener bound to an ephemeral port on the loopback
interface. The listener SHALL bind loopback only, SHALL use the fixed callback path the
platform's clients register, and SHALL stop once the callback arrives or the wait
elapses.

The client SHALL verify the `state` parameter returned with the callback before
exchanging the code.

#### Scenario: A browser login yields a credential

- **WHEN** a user completes authentication in the browser that was opened
- **THEN** the client exchanges the authorization code together with its PKCE verifier
- **AND** obtains an access token and a refresh token

#### Scenario: The listener does not outlive the login

- **WHEN** the configured wait elapses without a callback arriving
- **THEN** the listener stops and the command fails rather than hanging

#### Scenario: A mismatched state is refused

- **WHEN** a callback arrives whose `state` does not match the one sent
- **THEN** the client refuses it and does not exchange the code

### Requirement: The client authenticates without a local browser

The client SHALL support the device authorization grant for hosts with no reachable
browser, presenting a verification address and user code for the user to complete
elsewhere. It SHALL supply a PKCE challenge on the device authorization request and the
corresponding verifier when polling, because the platform requires PKCE on this grant.

Polling SHALL handle authorization still being pending, a request to slow down, an
expired device code, and a denied authorization, each as a distinct outcome.

#### Scenario: A headless host obtains a credential

- **WHEN** the client requests device authorization and the user approves it elsewhere
- **THEN** polling the token endpoint returns an access token and a refresh token

#### Scenario: Pending approval is not an error

- **WHEN** polling occurs before the user has approved
- **THEN** the client keeps waiting rather than failing

#### Scenario: A slow-down response widens the interval

- **WHEN** the platform answers a poll with a request to slow down
- **THEN** the client increases its polling interval before the next attempt

### Requirement: The authentication flow is auto-detected and overridable

The client SHALL choose between the loopback and device flows automatically, based on
whether a browser on this machine could actually receive the redirect. It SHALL state
which flow it chose and why. The choice SHALL be overridable per invocation.

A containerized environment SHALL select the device flow even when a browser binary is
present, because the redirect would arrive on the container's own loopback interface.

#### Scenario: A container selects the device flow

- **WHEN** the client runs inside a container
- **THEN** it selects the device flow and reports that reason

#### Scenario: The choice can be forced

- **WHEN** a flow is explicitly requested
- **THEN** that flow is used regardless of the detection outcome

### Requirement: Credentials are cached durably and privately

The client SHALL request offline access so that the refresh token survives the
interactive session, and SHALL cache it on disk **keyed by environment**. The cache file
SHALL be readable and writable only by its owner, within a directory that is likewise
owner-only.

The client SHALL never print a raw token. Decoded token claims MAY be shown for
diagnostics; they SHALL NOT be used to make a trust decision, because the platform is
what verifies tokens.

#### Scenario: A later command reuses the cached credential

- **WHEN** a command runs after a successful login for the same environment
- **THEN** it obtains an access token from the cached refresh token without user
  interaction

#### Scenario: The cache is not world-readable

- **WHEN** the credential cache is written
- **THEN** its permissions restrict access to the owning user
- **AND** the directory containing it does the same

#### Scenario: Tokens are never displayed

- **WHEN** any command runs, including in its most verbose mode
- **THEN** no access token or refresh token appears in the output

### Requirement: Sign-out discards the local credential only

The client SHALL provide a command that removes the cached credential for an
environment. It SHALL state that this does not revoke anything on the platform, and
SHALL say where server-side revocation is performed.

#### Scenario: Sign-out removes the cached credential

- **WHEN** the sign-out command runs for an environment
- **THEN** that environment's cached credential is removed
- **AND** other environments' credentials are untouched

#### Scenario: Sign-out explains its limits

- **WHEN** the sign-out command completes
- **THEN** the output states that the credential remains valid on the platform until
  revoked there

### Requirement: The client can report the authenticated identity

The client SHALL provide a command that reports who the current credential
authenticates as, including the account identifier the platform's user-scoped routes
require.

#### Scenario: The identity is reported

- **WHEN** the identity command runs with a valid credential
- **THEN** the authenticated account's email and identifier are shown

### Requirement: The client acts correctly on the platform's status codes

The platform's authentication statuses invert the conventional reading. The client SHALL
implement the following contract:

- **401** — no credential was presented, or a valid credential belongs to a user who is
  not permitted on this environment. The client SHALL stop and explain. It SHALL NOT
  re-authenticate, because re-authenticating succeeds and changes nothing.
- **403 from the edge** (a non-JSON body) — the token is expired, malformed, or
  unverifiable. The client SHALL refresh and retry.
- **403 from the API** (a JSON body carrying a detail) — the caller is authenticated but
  not permitted to act on that resource. The client SHALL stop.
- **404 carrying a "not authenticated" detail** — no identity reached the API. The
  client SHALL report it as an unexpected platform condition, not as a prompt to log in.

The client SHALL refresh at most once per request. If a retry after refreshing is
refused again, the client SHALL surface a permission error and stop, so that a status
the credential cannot satisfy never becomes a login loop.

#### Scenario: An expired access token is recovered silently

- **WHEN** a request is refused with 403 and a non-JSON body
- **THEN** the client refreshes the access token and retries the request once
- **AND** the command proceeds normally when the retry succeeds

#### Scenario: A rejected refresh falls back to a full login

- **WHEN** refreshing after a 403 is itself refused
- **THEN** the client performs a full authentication rather than failing outright

#### Scenario: An unauthorized user is not asked to log in again

- **WHEN** a request is refused with 401 while a valid credential is held
- **THEN** the client stops and explains that re-authenticating will not help
- **AND** the message names the group membership that governs access on that environment

#### Scenario: An application permission error does not trigger a refresh loop

- **WHEN** a request is refused with 403 and a JSON body describing the refusal
- **THEN** the client reports the permission error and stops
- **AND** it does not repeatedly refresh and retry

### Requirement: A credential problem surfaces on the first authenticated request

Several endpoints the client reads are public and are answered without any identity,
whatever credential the request carried. The client SHALL therefore issue an
authenticated identity request before those public reads in any command that requires
authentication, so that a bad or missing credential is reported before other work
begins.

#### Scenario: An invalid credential is reported before public reads

- **WHEN** a command that requires authentication runs with an unusable credential
- **THEN** the credential problem is reported by the first authenticated request
- **AND** the command does not proceed to read public data and fail later for an
  unrelated-looking reason
