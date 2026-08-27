## Purpose

Users and the `freepod` client need to manage the SSH keys on an account without going
near a deployment. This capability defines the REST surface for that: a collection under
the user resource for listing, adding and deleting keys, the shapes it returns, and who
may call it. It deliberately mirrors the platform's existing user-scoped resources so
that authorization, error semantics and CLI parity need no special cases.

## ADDED Requirements

### Requirement: Keys are a user-scoped collection
The API MUST expose an account's SSH keys as a collection under the user resource (`/users/{user_id}/ssh-keys`), following the platform's nested-route convention. It MUST support listing the collection, adding a key to it, and deleting a single key.

A key MUST be addressed for deletion by its **fingerprint**, not by a label and not by a database identifier, so that a client which knows only the key it holds can revoke it without a prior lookup.

There MUST NOT be a root-level keys collection, and there MUST NOT be a `user_id` query parameter as an alternative to the path segment.

#### Scenario: Owner lists their keys
- **WHEN** a user requests their own SSH key collection
- **THEN** the response lists their keys, each with its fingerprint, label, key type, and the time it was registered

#### Scenario: Owner adds a key
- **WHEN** a user submits a valid public key to their own collection
- **THEN** the key is stored and the response describes the stored key including its computed fingerprint

#### Scenario: Owner deletes a key by fingerprint
- **WHEN** a user deletes a key from their own collection, addressing it by fingerprint
- **THEN** the key is removed and subsequent listings omit it

#### Scenario: Empty collection is not an error
- **WHEN** a user who has registered no keys lists their collection
- **THEN** the response is a successful empty list, not a not-found

### Requirement: Reads never return private key material and never re-return raw key bodies unnecessarily
A read of the collection MUST return, for each key, its fingerprint, label, key type and registration time. It MUST NOT return private key material under any circumstance, since none is ever stored.

The full public key body MAY be returned. Whatever the choice, it MUST be consistent across list and add responses so that a client can compare what it holds against what is registered without special-casing the two paths.

#### Scenario: No private material in any response
- **WHEN** any SSH key endpoint returns a key
- **THEN** the response contains no private key material

#### Scenario: List and add agree on shape
- **WHEN** a client adds a key and then lists the collection
- **THEN** the added key's representation in the list carries the same fields, with the same meanings, as the add response

### Requirement: Authorization follows the platform's user-resource rules, with adds restricted to the owner
Reading and deleting an account's keys MUST follow the platform's existing user-resource authorization: the owning user may do both, administrators may do both for any account, and any other caller MUST be refused with the platform's standard authorization error.

Adding a key MUST be restricted to the owning user. An administrator MUST NOT add a key to another user's account: doing so would install a credential that authenticates as that user, which is impersonation rather than administration. Administrative access to the collection exists so that a compromised key can be revoked, not so that one can be granted.

#### Scenario: Non-owner is refused
- **WHEN** an authenticated user requests another account's SSH keys
- **THEN** the request is refused with the platform's standard authorization error

#### Scenario: Administrator may read and revoke
- **WHEN** an administrator lists or deletes keys on another user's account
- **THEN** the request succeeds

#### Scenario: Administrator may not add
- **WHEN** an administrator submits a key to another user's collection
- **THEN** the request is refused, and the refusal is distinguishable from a validation error

### Requirement: Validation failures are distinguishable from authorization and absence
A rejected submission MUST report why in a form a client can act on and a user can read: an unsupported key type, an undersized key, a malformed key, private key material, a duplicate, or the per-account limit. These MUST be distinguishable from one another and from authorization failures and from a missing user.

Deleting a key that does not exist on an existing, authorized account MUST be reported as a missing key rather than as an authorization failure.

#### Scenario: Client can distinguish a duplicate from a limit
- **WHEN** a submission is rejected because the key is already registered, and another because the account is at its limit
- **THEN** the two responses are distinguishable without parsing prose

#### Scenario: Missing key on an authorized account
- **WHEN** the owner deletes a fingerprint that is not in their collection
- **THEN** the response indicates the key was not found, not that access was denied

### Requirement: The API advertises the per-account key limit
The API MUST make the configured maximum number of keys per account discoverable to clients, rather than requiring a client to learn it by hitting the error. The `freepod` client ships on its own release cadence, so a limit compiled into it would be wrong the first time the platform retunes it.

#### Scenario: Client learns the limit without failing
- **WHEN** a client needs to tell a user how many keys they may register
- **THEN** it can obtain the current limit from the platform without provoking a rejected submission

### Requirement: Operator CLI parity
The `caelus` operator CLI MUST offer the same key operations as the REST API, with the same validations, by calling the same service layer. This preserves the platform's API/CLI lockstep convention, and it is what allows an operator to revoke a key for a user during an incident without going through the web UI.

#### Scenario: Operator revokes a key
- **WHEN** an operator deletes a user's key through the `caelus` CLI
- **THEN** the key is removed exactly as it would have been through the API, and subsequent API reads omit it

#### Scenario: Same validation on both paths
- **WHEN** an invalid key is submitted through the `caelus` CLI
- **THEN** it is rejected for the same reason the API would have rejected it
