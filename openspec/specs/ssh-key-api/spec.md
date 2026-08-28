# ssh-key-api Specification

## Purpose

Users and the `freepod` client need to manage the SSH keys on an account without going
near a deployment. This capability defines the REST surface for that: a collection under
the user resource for listing, adding and deleting keys, the shapes it returns, and who
may call it. It deliberately mirrors the platform's existing user-scoped resources so
that authorization, error semantics and CLI parity need no special cases.

## Requirements

### Requirement: Keys are a user-scoped collection
The API MUST expose an account's SSH keys as a collection under the user resource (`/api/users/{user_id}/ssh-keys`), following the platform's nested-route convention. It MUST support listing the collection, adding a key to it, reading one key, and deleting one key.

A key MUST be addressed by its **fingerprint**, not by a label and not by a database identifier, so that a client which knows only the key it holds can revoke it without a prior lookup.

Listing MUST return a plain array of keys, like every other collection in the API. It MUST NOT wrap the array in an envelope.

There MUST NOT be a root-level keys collection, and there MUST NOT be a `user_id` query parameter as an alternative to the path segment.

#### Scenario: Owner lists their keys
- **WHEN** a user requests their own SSH key collection
- **THEN** the response is an array in which each entry carries its fingerprint, label, key type, size in bits, public key body, and the time it was registered

#### Scenario: Owner adds a key
- **WHEN** a user submits a valid public key to their own collection
- **THEN** the key is stored, the response describes the stored key including its computed fingerprint, and the response points at the stored key's own address

#### Scenario: Owner deletes a key by fingerprint
- **WHEN** a user deletes a key from their own collection, addressing it by fingerprint
- **THEN** the key is removed and subsequent listings omit it

#### Scenario: Empty collection is not an error
- **WHEN** a user who has registered no keys lists their collection
- **THEN** the response is a successful empty array, not a not-found

### Requirement: A fingerprint survives being placed in a URL
A SHA256 fingerprint is base64 without padding, so roughly half of all fingerprints contain a `/` and roughly half contain a `+`. The route that addresses a single key MUST accept such a fingerprint intact.

The addressing scheme MUST NOT silently alter the fingerprint it received. A request naming a key that exists MUST NOT be answered as though no such key exists because a character was dropped, decoded or re-interpreted in transit — a revocation reported as "no such key" is the most dangerous failure this capability can have, because the user concludes they have nothing to revoke.

The scheme MUST behave identically whether an intermediary forwards the separator encoded or decoded, since the platform's requests pass through a reverse proxy and an authentication proxy before reaching the API.

#### Scenario: Fingerprint containing a slash addresses its key
- **WHEN** a user registers a key whose fingerprint contains `/` and then deletes it by that fingerprint
- **THEN** the key is removed, exactly as for a fingerprint without one

#### Scenario: Fingerprint containing a plus addresses its key
- **WHEN** a user reads or deletes a key whose fingerprint contains `+`
- **THEN** the request resolves to that key, and the `+` is not interpreted as any other character

#### Scenario: A wrong fingerprint is still a clean miss
- **WHEN** a request names a fingerprint the account does not hold
- **THEN** the response reports that no such key exists, and no other key is affected

### Requirement: Reads return one representation, and never private key material
A read MUST return, for each key, its fingerprint, label, key type, size in bits, public key body and registration time. It MUST NOT return private key material under any circumstance, since none is ever stored.

The representation MUST be identical across listing, adding and reading a single key, so that a client can compare what it holds against what is registered without special-casing the path it arrived by.

The public key body MUST be returned in its normalized `<type> <blob>` form, without a trailing comment. The comment is not part of a key's identity — uniqueness is on the blob — and it has already been consumed as the default label, so returning it again would carry the same text twice under two fields that drift apart as soon as the label is edited.

#### Scenario: No private material in any response
- **WHEN** any SSH key endpoint returns a key
- **THEN** the response contains no private key material

#### Scenario: List, add and single read agree on shape
- **WHEN** a client adds a key, lists the collection, and reads that key on its own
- **THEN** the key's representation carries the same fields with the same meanings in all three responses

#### Scenario: The returned body omits the comment
- **WHEN** a user registers a key carrying a trailing comment and then reads it back
- **THEN** the returned public key body is the type and blob only, and the comment appears as the label instead

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

### Requirement: Rejections carry a machine-readable code
A rejected submission MUST report why in a form a client can branch on without reading prose: an unsupported key type, a key type that disagrees with its own blob, an undersized key, a malformed key, private key material, more than one key in one submission, and a duplicate MUST each be identifiable as a distinct, named condition.

A status code alone is insufficient, because most of these are the same class of failure and would share one status. The identifier MUST be stable across rewordings of the human-readable message, so that a client which branches on it does not break when the message is improved.

Validation failures MUST be distinguishable from authorization failures and from a missing user. Deleting a key that does not exist on an existing, authorized account MUST be reported as a missing key rather than as an authorization failure.

#### Scenario: Client distinguishes two rejections without parsing prose
- **WHEN** one submission is rejected as a duplicate and another as private key material
- **THEN** the two responses carry different machine-readable identifiers, and a client can tell them apart without matching on the message text

#### Scenario: Message wording is not the contract
- **WHEN** a rejection's human-readable message is reworded
- **THEN** the machine-readable identifier for that condition is unchanged

#### Scenario: Missing key on an authorized account
- **WHEN** the owner deletes a fingerprint that is not in their collection
- **THEN** the response indicates the key was not found, not that access was denied

### Requirement: A submission may not supply derived fields
The add request MUST accept the public key and an optional label, and nothing else. A body carrying any other field — a fingerprint, a key type, a user identifier — MUST be rejected rather than accepted with the extra field ignored.

The fingerprint and the key type are derived from the key material by the platform. A client that believes it can supply either is wrong in a way worth reporting: silently ignoring the field would let that client keep its mistaken belief until the day the two disagree.

#### Scenario: Supplied fingerprint is rejected
- **WHEN** a submission includes a fingerprint field alongside the public key
- **THEN** the request is rejected for carrying an unexpected field, and no key is stored

#### Scenario: Label remains optional
- **WHEN** a submission carries only the public key
- **THEN** it is accepted, and the label is taken from the key's comment when it has one and is otherwise absent

### Requirement: Operator CLI parity
The `caelus` operator CLI MUST offer the same key operations as the REST API, with the same validations, by calling the same service layer. This preserves the platform's API/CLI lockstep convention, and it is what allows an operator to revoke a key for a user during an incident without going through the web UI.

#### Scenario: Operator revokes a key
- **WHEN** an operator deletes a user's key through the `caelus` CLI
- **THEN** the key is removed exactly as it would have been through the API, and subsequent API reads omit it

#### Scenario: Same validation on both paths
- **WHEN** an invalid key is submitted through the `caelus` CLI
- **THEN** it is rejected for the same reason the API would have rejected it
