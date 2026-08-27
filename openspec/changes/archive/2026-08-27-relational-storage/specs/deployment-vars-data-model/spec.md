## MODIFIED Requirements

### Requirement: The keyring can be rotated without invalidating stored values
The service SHALL accept an ordered list of encryption keys. The first SHALL be the
only key used to encrypt; all of them SHALL be available to decrypt. A row SHALL be
decrypted with the key its own identifier names.

Re-encrypting a row under a newer key SHALL update its stored value and key identifier
in place and MUST NOT change the row's plaintext, its position in history, or its
bindings to any release. A partially re-encrypted store MUST remain fully readable.

The keyring covers more than deployment vars. Every column encrypted under it SHALL be
declared in one registry, and the rotation SHALL re-encrypt every declared column rather
than a named table, so that a sweep reporting nothing left to rotate means it for the
whole store.

#### Scenario: Rotation in progress
- **WHEN** some rows have been re-encrypted under the new key and others have not
- **THEN** every row is still readable
- **AND** reads return the same plaintext as before rotation began

#### Scenario: Rotation covers every encrypted column
- **WHEN** values encrypted under an older key exist in more than one encrypted column
- **THEN** the rotation re-encrypts all of them
- **AND** reports nothing left to rotate only once no column names the older key

#### Scenario: A sweep interrupted between columns resumes
- **WHEN** a rotation is interrupted after one encrypted column is swept and before another is
- **THEN** every value remains readable
- **AND** re-running the rotation completes the remaining column

#### Scenario: Retiring a key
- **WHEN** no stored value names a given key's fingerprint
- **THEN** that key can be removed from the configured list with no loss of readability

### Requirement: The service refuses to start when the keyring cannot cover stored values
At startup, every process that reads or writes values encrypted under the keyring SHALL
verify its keyring and refuse to start when it cannot serve the stored data.
Specifically it SHALL fail when two configured keys produce the same identifier, when
the list is empty while any encrypted value is stored or any reachable product template
declares vars, or when any key identifier present in storage is not configured.

The check SHALL cover every declared encrypted column, not deployment vars alone: a key
still named by any stored value is equally unretirable, and a column the check does not
know about would pass startup and strand its plaintext the moment that key is dropped.

Failing at startup is required rather than optional: a row whose key is absent can never
be decrypted again, and that must surface to whoever changed the configuration rather
than inside a tenant's later rollout.

#### Scenario: A key still referenced by stored data is dropped
- **WHEN** a key is removed from the configuration while rows still name its fingerprint
- **THEN** the process refuses to start and names the missing fingerprint

#### Scenario: A key referenced only outside deployment vars is dropped
- **WHEN** a key is removed while it is named only by an encrypted column other than deployment vars
- **THEN** the process refuses to start and names the missing fingerprint and the column

#### Scenario: The keyring is emptied while encrypted values are stored
- **WHEN** the configured key list is empty and any encrypted value exists in storage
- **THEN** the process refuses to start

#### Scenario: Two configured keys collide
- **WHEN** two configured keys produce the same identifier
- **THEN** the process refuses to start
