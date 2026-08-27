## Purpose

The `freepod` client will shortly need to open SSH connections on the user's behalf, and
it must offer exactly one key when it does — the edge answers every offered key with
"partial success", so a client that tries several exhausts the server's authentication
budget and is denied before reaching the right one. This capability covers the `freepod
key` command group and, more importantly, the local record it maintains: registration is
the one moment at which the client knows both halves of a pair, so it is where the link
between a registered public key and a local private key is established rather than
guessed later.

## ADDED Requirements

### Requirement: `freepod key` manages the account's keys
The client MUST provide a `key` command group with subcommands to add, list and remove the authenticated account's SSH keys, operating against the environment the invocation targets.

`list` MUST show enough to identify a key for revocation — its fingerprint and label at minimum — and MUST indicate which of the listed keys, if any, this machine holds locally.

#### Scenario: User lists their keys
- **WHEN** a user runs the list subcommand
- **THEN** their registered keys are shown with fingerprint and label

#### Scenario: Local key is marked
- **WHEN** a user runs the list subcommand on a machine that holds a registered key
- **THEN** that key is distinguished from the others in the output

#### Scenario: No keys registered
- **WHEN** a user with no registered keys runs the list subcommand
- **THEN** the client reports that plainly and says how to add one, rather than printing an empty table with no guidance

### Requirement: Adding with no argument generates a key the client owns
`freepod key add` invoked with no key argument MUST generate a new Ed25519 keypair in the client's own configuration directory, register the public half, and record it as this machine's key. The user MUST NOT be required to have, choose, or understand an existing key to get working access.

The generated private key MUST be written with owner-only permissions, and the client MUST NOT generate a passphrase-less key outside its own configuration directory or write into the user's `~/.ssh`.

A machine that already holds a client-generated registered key MUST NOT silently generate a second one; the command MUST report the existing key instead.

#### Scenario: First-time setup on a new machine
- **WHEN** a user with no local key runs the add subcommand with no argument
- **THEN** a keypair is generated in the client's configuration directory, the public half is registered, and the client reports the resulting fingerprint

#### Scenario: Generated private key is protected
- **WHEN** the client generates a keypair
- **THEN** the private key file is readable and writable only by its owner

#### Scenario: Re-running add does not duplicate
- **WHEN** a user runs the add subcommand with no argument on a machine that already holds a registered client-generated key
- **THEN** no new key is generated and the client reports the key it already holds

### Requirement: Adding an existing key records where it came from
`freepod key add <path>` MUST accept a path to an existing **public** key file, register it, and record that path locally as this machine's key. Supplying a private key path MUST be refused with an error that says so and names the corresponding public key file.

Recording the path at registration time is what makes later key selection deterministic. The client MUST NOT defer this to connection time, where it would have to guess among the user's keys.

#### Scenario: Existing public key is registered and remembered
- **WHEN** a user runs the add subcommand naming an existing public key file
- **THEN** the key is registered and the client records that file as this machine's key

#### Scenario: Private key path is refused
- **WHEN** a user names a private key file
- **THEN** the client refuses, explains that a public key is required, and names the expected `.pub` file

### Requirement: The local record is per environment and lives beside the token cache
The client MUST store its record of the local key in its existing configuration directory, alongside the token cache, and MUST key that record by **environment**. An account on one environment is not the same account as on another, so a key registered against one MUST NOT be presented as this machine's key for another.

The record MUST hold enough to select the key later — the fingerprint of the registered key and the path to the local file — and MUST NOT hold private key material.

#### Scenario: Environments do not share a record
- **WHEN** a user registers a key against one environment and then lists keys against another
- **THEN** the client does not report the first environment's key as this machine's key for the second

#### Scenario: Record survives across invocations
- **WHEN** a user registers a key and later runs any command that needs it
- **THEN** the client resolves the same local key without prompting or searching

### Requirement: A lost local record is recovered by fingerprint, not by guessing
When the local record is absent or no longer matches a registered key — a new machine, a cleared configuration directory, or a key registered through the web UI — the client MUST attempt recovery by comparing fingerprints: it computes the fingerprint of each candidate **public** key file available to it and looks for one the account has registered.

Recovery MUST operate on public key files, never on private ones, so that keys whose private half exists only in an agent or on a hardware token are still matched.

If exactly one candidate matches, the client MUST adopt it and record it. If none matches, the client MUST say so and direct the user to register a key, rather than attempting a connection that will fail. If several match, the client MUST ask rather than choose.

#### Scenario: New machine with an already-registered key
- **WHEN** a user runs a command needing a key on a machine holding a public key file whose fingerprint is registered on the account
- **THEN** the client adopts that key and records it, without the user re-registering

#### Scenario: Hardware-backed key is matched
- **WHEN** the only local material for a registered key is its public key file, the private half being held in an agent or on a security key
- **THEN** the client matches it by fingerprint and uses it

#### Scenario: No local key matches
- **WHEN** no available public key file matches any registered key
- **THEN** the client reports that no registered key is available on this machine and names the command that registers one

#### Scenario: Ambiguous match is not resolved silently
- **WHEN** more than one local public key file matches a registered key
- **THEN** the client asks which to use rather than picking one

### Requirement: Removal names a key without needing local material
`freepod key rm` MUST accept the identifier shown by `list` and MUST work for keys this machine does not hold — revoking a lost laptop's key is done from a different machine, which is the point.

When a user removes the key this machine holds, the client MUST clear the corresponding local record so that it does not later present a revoked key as available.

#### Scenario: Revoking another machine's key
- **WHEN** a user removes a key that was registered from a different machine
- **THEN** the key is removed from the account

#### Scenario: Removing this machine's key clears the record
- **WHEN** a user removes the key this machine holds
- **THEN** the client no longer reports a local key for that environment

### Requirement: The client never displays or transmits private key material
A `freepod` command MUST NOT print, log, copy, or transmit an SSH private key, in any output mode including verbose and debug. This matches the existing rule that the client renders token claims but never raw token material.

#### Scenario: Verbose output stays clean
- **WHEN** any key subcommand runs with verbose output enabled
- **THEN** no private key material appears in its output
