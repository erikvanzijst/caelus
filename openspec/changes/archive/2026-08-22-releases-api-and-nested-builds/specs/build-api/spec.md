## ADDED Requirements

### Requirement: Builds are addressed under their owning user

A build is owned by a user, and the system SHALL address the build endpoints
under that user, as it already does for every other user-owned resource. The
owner named in the request path SHALL be what scopes the request; the system
SHALL NOT accept a separate query parameter selecting whose builds to act on.

Two ways of expressing the same ownership is one too many: with the owner in the
path, the platform's existing self-or-administrator guard applies to builds
unchanged, instead of each build endpoint re-deriving the scope for itself.

The previous root-level build paths SHALL cease to exist rather than remaining
as aliases. A client built against them is not partially compatible — it must be
upgraded — and leaving the old paths answering would hide that from the very
clients that need to know.

#### Scenario: Builds are reached under their owner

- **WHEN** a client acts on builds — creating, listing, reading one, or reading its log
- **THEN** the request is addressed under the owning user, and the owner in the path is what scopes it

#### Scenario: The root-level build paths are gone

- **WHEN** a client requests the former root-level build path
- **THEN** no build endpoint answers it

#### Scenario: Acting under another account is refused

- **WHEN** a non-administrator addresses a build endpoint under another user's account
- **THEN** the request is refused as forbidden, before any build is created or read

#### Scenario: Creation still takes its owner from the session

- **WHEN** an authenticated user creates a build under their own account
- **THEN** the build is owned by the authenticated caller, and the path identifies whose account is being acted on rather than supplying the owner as input

## MODIFIED Requirements

### Requirement: A user can list their own builds

The system SHALL provide an endpoint listing the builds of the user named in the
request path, most recent first. Builds owned by other users MUST NOT appear.
A caller MAY list their own builds; administrators MAY list any user's builds,
by naming that user in the path rather than by any other means.

Without enumeration a client can only ever reference a build whose identifier it still
holds, so a previously produced image becomes unreachable once the client forgets it —
which is what a redeploy or a rollback needs.

#### Scenario: Caller lists their builds

- **WHEN** an authenticated user lists builds under their own account
- **THEN** their own builds are returned, most recent first

#### Scenario: Listing excludes other users' builds

- **WHEN** an authenticated user lists builds while other users also have builds
- **THEN** only the caller's own builds are returned

#### Scenario: An administrator lists another user's builds

- **WHEN** an administrator lists builds under another user's account
- **THEN** that user's builds are returned, most recent first

#### Scenario: A non-administrator cannot list another user's builds

- **WHEN** a non-administrator lists builds under another user's account
- **THEN** the request is refused as forbidden
