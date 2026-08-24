# deployment-vars-data-model Specification

## Purpose
Defines how a deployment's runtime configuration values ("vars") are stored: an
append-only, encrypted record per deployment, an effective set derived from it, and an
immutable per-release snapshot that makes a release reproducible.
## Requirements
### Requirement: Vars are recorded per deployment in an append-only history
A deployment's vars SHALL be stored as immutable rows anchored to that deployment. A
value MUST NOT be updated in place: setting a key to a new value SHALL insert a new row
carrying the same key. Each row SHALL record the user who wrote it and the instant it
was written. Deleting a key SHALL insert a tombstone row — a row with no value — rather
than removing history.

Immutability is defined at the plaintext level: a row's plaintext MUST NOT change once
written, while its stored representation MAY be rewritten for key rotation (see
"The keyring can be rotated without invalidating stored values").

Var rows SHALL be removed when their deployment is deleted.

#### Scenario: Setting a key that already has a value
- **WHEN** a var `LOG_LEVEL` with value `info` is set to `debug`
- **THEN** a new row is inserted for `LOG_LEVEL` with the new value
- **AND** the row carrying `info` remains, with its original author and timestamp

#### Scenario: Deleting a key
- **WHEN** a var `LOG_LEVEL` is deleted
- **THEN** a tombstone row with no value is inserted for `LOG_LEVEL`
- **AND** no earlier row for `LOG_LEVEL` is removed or altered

#### Scenario: Deleting the deployment
- **WHEN** a deployment is deleted
- **THEN** its var rows and their release bindings are removed with it

### Requirement: The effective set of vars is the newest row per key, excluding tombstones
The **head** of a deployment SHALL be the set containing, for each key, the most
recently inserted row for that key, excluding any key whose most recent row is a
tombstone. Head is the deployment's desired runtime configuration and is what every
read of a deployment's vars reports.

#### Scenario: A key written three times
- **WHEN** `LOG_LEVEL` has rows `info`, `warn`, then `debug`
- **THEN** head contains `LOG_LEVEL` with value `debug` only

#### Scenario: A key deleted and re-created
- **WHEN** `LOG_LEVEL` is set, deleted, then set again to `trace`
- **THEN** head contains `LOG_LEVEL` with value `trace`
- **AND** the tombstone remains in history between the two live rows

#### Scenario: A key whose newest row is a tombstone
- **WHEN** `LOG_LEVEL`'s most recent row is a tombstone
- **THEN** head does not contain `LOG_LEVEL`
- **AND** no read of the deployment's vars reports `LOG_LEVEL`

### Requirement: Var writes for one deployment are serialized
Concurrent writes MUST NOT produce a head that reflects neither writer's intent. Every
operation that inserts var rows, and every operation that binds a release snapshot,
SHALL first acquire an exclusive lock on the owning deployment, giving a total order
per deployment. Ordering across different deployments is not constrained.

#### Scenario: Two clients set the same key concurrently
- **WHEN** two requests set `LOG_LEVEL` at the same time
- **THEN** both rows are recorded with their own author
- **AND** head reports exactly one of them, not a mixture

#### Scenario: A var write races release creation
- **WHEN** a var write and a release creation for the same deployment overlap
- **THEN** the var row is either wholly included in that release's snapshot or wholly
  excluded from it
- **AND** it is never partially applied

### Requirement: Every stored value is encrypted at rest
A var's value SHALL be stored encrypted, **including** values not marked sensitive.
Plaintext MUST NOT be persisted in any column, and the plaintext of a sensitive var MUST
NOT be written to logs at any level.

#### Scenario: A non-sensitive var is stored
- **WHEN** a var with `sensitive: false` is written
- **THEN** its value is stored encrypted, in the same column and by the same code path
  as a sensitive one

### Requirement: A stored value records the identity of the key that encrypted it
Each encrypted row SHALL record an identifier of the encryption key that produced it,
because the ciphertext does not carry one. That identifier MUST be derived from the key
material itself and MUST NOT be a position or index within the configured key list.

A positional identifier would be invalidated by the rotation it exists to support: keys
are introduced by prepending, which would silently renumber every historical row.

#### Scenario: A row is written
- **WHEN** a value is encrypted with the current key
- **THEN** the row records that key's fingerprint, derived from the key material

#### Scenario: A new key is introduced
- **WHEN** a new key is added ahead of the existing keys
- **THEN** the identifiers stored on existing rows are unchanged
- **AND** every existing row still decrypts with the key it names

### Requirement: The keyring can be rotated without invalidating stored values
The service SHALL accept an ordered list of encryption keys. The first SHALL be the
only key used to encrypt; all of them SHALL be available to decrypt. A row SHALL be
decrypted with the key its own identifier names.

Re-encrypting a row under a newer key SHALL update its stored value and key identifier
in place and MUST NOT change the row's plaintext, its position in history, or its
bindings to any release. A partially re-encrypted store MUST remain fully readable.

#### Scenario: Rotation in progress
- **WHEN** some rows have been re-encrypted under the new key and others have not
- **THEN** every row is still readable
- **AND** reads return the same plaintext as before rotation began

#### Scenario: Retiring a key
- **WHEN** no stored value names a given key's fingerprint
- **THEN** that key can be removed from the configured list with no loss of readability

### Requirement: The service refuses to start when the keyring cannot cover stored values
At startup, every process that reads or writes vars SHALL verify its keyring and refuse
to start when it cannot serve the stored data. Specifically it SHALL fail when two
configured keys produce the same identifier, when the list is empty while any reachable
product template declares vars, or when any key identifier present in storage is not
configured.

Failing at startup is required rather than optional: a row whose key is absent can never
be decrypted again, and that must surface to whoever changed the configuration rather
than inside a tenant's later rollout.

#### Scenario: A key still referenced by stored data is dropped
- **WHEN** a key is removed from the configuration while rows still name its fingerprint
- **THEN** the process refuses to start and names the missing fingerprint

#### Scenario: Two configured keys collide
- **WHEN** two configured keys produce the same identifier
- **THEN** the process refuses to start

### Requirement: A release's var snapshot is immutable and independent of later changes
A release SHALL be bound to the specific var rows that were in head when it was created.
That binding MUST NOT change afterwards. Tombstones MUST NOT be bound to any release.
Later writes, deletions, or rotations MUST NOT alter what an existing release's snapshot
resolves to.

#### Scenario: Vars change after a release
- **WHEN** a release is created and vars are then changed or deleted
- **THEN** that release's snapshot still resolves to the values it was created with

#### Scenario: A key deleted after a release
- **WHEN** a key bound to release 4 is deleted
- **THEN** release 4's snapshot still includes it
- **AND** head does not
