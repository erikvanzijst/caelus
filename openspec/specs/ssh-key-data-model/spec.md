# ssh-key-data-model Specification

## Purpose

SSH access to the platform is authenticated by public keys a user registers once and
reuses everywhere, rather than by credentials generated per deployment. This capability
defines what such a key is: which key types are accepted, how a submitted key is
validated and identified, how it is labeled, and what deleting one means.
It is the storage contract the API, CLI and UI all present, and the contract a later
change relies on when it projects an account's keys into the SSH edge's view.

## Requirements

### Requirement: An SSH key belongs to an account, not to a deployment
An SSH key MUST be owned by exactly one user and MUST NOT be scoped to, or reference, any deployment. A user's keys apply uniformly to every deployment that user owns, including deployments created after the key was registered, and MUST stop applying to deployments the user ceases to own.

Registering a key MUST NOT require the user to own any deployment.

#### Scenario: Key applies to a later deployment
- **WHEN** a user registers a key and afterwards creates a new deployment
- **THEN** the key is among that user's registered keys with no further action

#### Scenario: Key may be registered with no deployments
- **WHEN** a user who owns no deployments registers a key
- **THEN** the key is accepted and stored

### Requirement: Only public key material is accepted
The system MUST accept only SSH **public** keys, in the single-line OpenSSH `authorized_keys` format (`<type> <base64 blob> [comment]`). Submissions that parse as a private key, contain PEM private-key delimiters, or carry more than one key MUST be rejected with a distinct, actionable error rather than being stored.

No component of the system may accept, store, log, display, or transmit an SSH private key.

#### Scenario: Private key is rejected
- **WHEN** a user submits text containing an OpenSSH or PEM private key block
- **THEN** the submission is rejected with an error naming the problem as "this is a private key"
- **AND** no key is stored and the submitted material does not appear in any log

#### Scenario: Multiple keys in one submission are rejected
- **WHEN** a user submits two or more key lines in a single request
- **THEN** the submission is rejected and no key is stored
- **AND** neither line is registered, so the request cannot partially succeed

#### Scenario: Malformed key is rejected
- **WHEN** a user submits text that is not a well-formed OpenSSH public key line
- **THEN** the submission is rejected with an error distinguishable from an authorization failure

### Requirement: Accepted key types are an explicit allowlist verified against the key body
Accepted key types MUST be an explicit allowlist covering Ed25519, ECDSA (NIST P-256/384/521), RSA, and the FIDO/security-key variants of Ed25519 and ECDSA. `ssh-dss` (DSA) MUST be rejected. RSA keys below 2048 bits MUST be rejected.

The key type MUST be determined by decoding the key blob and reading the algorithm name it carries, and that name MUST match the declared prefix. A submission whose prefix and blob disagree MUST be rejected.

#### Scenario: Ed25519 key is accepted
- **WHEN** a user submits a valid `ssh-ed25519` public key
- **THEN** it is stored

#### Scenario: Security-key backed key is accepted
- **WHEN** a user submits a valid `sk-ssh-ed25519@openssh.com` public key
- **THEN** it is stored, so hardware-backed keys are usable

#### Scenario: DSA key is rejected
- **WHEN** a user submits an `ssh-dss` public key
- **THEN** it is rejected with an error naming the key type as unsupported

#### Scenario: Undersized RSA key is rejected
- **WHEN** a user submits an RSA public key shorter than 2048 bits
- **THEN** it is rejected with an error naming the key as too short

#### Scenario: Prefix and blob disagree
- **WHEN** a user submits a key whose declared type does not match the algorithm encoded in its blob
- **THEN** it is rejected

### Requirement: Each key carries a server-computed SHA256 fingerprint
The system MUST compute and store a fingerprint for every key: the SHA256 digest of the raw key blob, base64-encoded without padding, presented in the conventional `SHA256:<digest>` form so that it is byte-identical to what `ssh-keygen -lf` reports for the same key.

The fingerprint MUST be computed by the platform and MUST be part of every read of a key. It MUST NOT be accepted from a client on any path: a submission that supplies one is rejected rather than silently overridden, so a client holding a mistaken belief about who derives it learns that at once instead of on the day the two disagree. It is the identifier clients use to recognize a key they hold without transmitting key material.

#### Scenario: Fingerprint matches the standard tool
- **WHEN** a key is registered
- **THEN** its stored fingerprint equals the `SHA256:` fingerprint that `ssh-keygen -lf` reports for the same public key file

#### Scenario: Client-supplied fingerprint is refused
- **WHEN** a submission includes a fingerprint field
- **THEN** the submission is rejected for carrying a derived field, rather than accepted with the supplied value ignored

#### Scenario: Fingerprint is returned on read
- **WHEN** a user's keys are listed
- **THEN** each entry includes its fingerprint

### Requirement: Keys are unique per user, and equality ignores the comment
A user MUST NOT hold two keys with the same key blob. Uniqueness MUST be determined by the key blob alone, so two submissions differing only in their trailing comment or in surrounding whitespace are the same key. A duplicate submission MUST be rejected with an error that names it as already registered.

Uniqueness MUST NOT be enforced across users. Two accounts holding the same public key is permitted: a public key is not a secret, and registering one on an account confers access only to that account's own deployments, so a global constraint would add no protection while creating a cross-account existence oracle for key material.

#### Scenario: Same key submitted twice by one user
- **WHEN** a user submits a key blob they have already registered
- **THEN** the submission is rejected as a duplicate and the existing key is left unchanged

#### Scenario: Comment differences do not create a second key
- **WHEN** a user resubmits a previously registered key with a different trailing comment
- **THEN** it is rejected as a duplicate

#### Scenario: Two users hold the same key
- **WHEN** two different users each register the same public key
- **THEN** both registrations succeed

### Requirement: A key may carry a label, defaulted from the key's comment
A key MAY carry a human-readable label, so a user reviewing their keys can tell which machine or device each one belongs to and revoke the right one. When a label is not supplied, the system MUST default it from the submitted key's trailing comment.

When a label is not supplied and the key carries no comment, the key MUST be stored **without** a label.
A key's identity is its fingerprint, so an absent label costs nothing: every surface can still name, display and revoke the key. Labels MUST NOT be required to be unique and MUST NOT be used to identify a key for deletion.

#### Scenario: Label defaults from the comment
- **WHEN** a user registers `ssh-ed25519 AAAA... alice@laptop` without supplying a label
- **THEN** the stored label is derived from `alice@laptop`

#### Scenario: Comment-less key is stored without a label
- **WHEN** a user registers a key with no trailing comment and supplies no label
- **THEN** the key is stored with no label, rather than with a generated one

#### Scenario: An unlabeled key is still identifiable
- **WHEN** a user reads or deletes a key that carries no label
- **THEN** the key is addressable and displayable by its fingerprint exactly as a labeled key is

### Requirement: Deletion is immediate and permanent
Deleting a key MUST remove it outright. A deleted key MUST NOT be recoverable, MUST NOT be returned by any read, and MUST NOT be retained in a soft-deleted state that a later projection could mistake for a live key.

Deletion is the security-critical operation of this capability: it is how a user revokes a lost or compromised device. It MUST NOT be silently tolerant — a delete naming a key that does not exist MUST report that fact rather than reporting success.

#### Scenario: Deleted key disappears
- **WHEN** a user deletes one of their keys
- **THEN** subsequent reads of that user's keys do not include it, in any state

#### Scenario: Deleting an unknown key is reported
- **WHEN** a user issues a delete for a fingerprint they do not hold
- **THEN** the request reports that no such key exists rather than succeeding silently

### Requirement: An account's keys are removed with the account
When a user is deleted, that user's SSH keys MUST be removed. No key may outlive its owner, in any state, because a surviving key is a credential with no accountable holder.

#### Scenario: User deletion removes keys
- **WHEN** a user account is deleted
- **THEN** that user's SSH keys no longer exist
