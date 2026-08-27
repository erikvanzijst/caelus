## Context

See `proposal.md` § Why, and `var/ssh_access.md` D7–D10 for the wider SSH design this
serves.

Four existing facts shape the approach.

1. **`cryptography` is already a dependency** (`api/pyproject.toml`), and its
   `load_ssh_public_key` covers exactly the algorithms this change wants to accept:
   `ssh-ed25519`, `ssh-rsa`, `ecdsa-sha2-nistp256/384/521`, and both security-key
   variants `sk-ssh-ed25519@openssh.com` and `sk-ecdsa-sha2-nistp256@openssh.com`. It
   also knows `ssh-dss`, which this change rejects by policy. Verified against
   cryptography 50.0.0 in this repo's environment. No new dependency is needed.
2. **The client already has a per-environment configuration directory.**
   `config_dir()` resolves `${XDG_CONFIG_HOME:-~/.config}/freepod` and `token_cache_path()`
   puts the token cache inside it, keyed by environment. The key record belongs beside it,
   keyed the same way.
3. **`GET /me/tos-acceptance` is the precedent for platform facts in a read model.** It
   returns the caller's own acceptance *and* `current_version`, the version the platform
   currently requires, so no client hardcodes it. The key limit has the same shape of
   problem.
4. **The UI's admin area already models "a page composed of panels"** with nested
   routes. A settings page should reuse that shape rather than invent a second one.

## Goals / Non-Goals

**Goals:**

- A key registered once is usable from every surface, and identifiable afterwards
  without transmitting key material.
- The client can always answer "which local key is this account's?" deterministically.
- Revocation is unambiguous and immediate at the data layer, ready for a projection
  layer to consume.

**Non-Goals:**

- Granting access. Nothing reads these keys yet; that is the auth-swap change.
- Projecting keys into tenant namespaces or into the SSH edge's view. Deliberately
  deferred, and the shape of that projection is still open (see `var/ssh_access.md` D8
  and the outstanding `Pipe`-namespace decision) — which is precisely why this change
  stops at the store.
- SSH certificates. Unavailable to us; recorded in `var/ssh_access.md` D8.
- Per-deployment or delegated keys. A different feature.

## Decisions

### Validation parses the key; it does not trust the prefix

A submission is validated by base64-decoding the blob and loading it with
`load_ssh_public_key`. The stored key type comes from **the parsed key**, never from the
text before the blob, so a submission whose prefix disagrees with its body is rejected
rather than mislabelled. `ssh-dss` is rejected by explicit policy even though the parser
accepts it, and RSA keys are additionally checked against `key_size >= 2048`.

Using the parser rather than a regex is what gets the security-key variants right for
free, and it means a malformed key fails at the boundary instead of at the point where
the key is projected into an `authorized_keys` file — where the failure would be a
sidecar that rejects every login for reasons nobody can see.

Alternative considered: hand-rolling a length-prefixed blob reader. Fewer lines, no
dependency on the parser's algorithm coverage, and it would still identify a key
correctly — but it cannot compute RSA key sizes or reject structurally invalid keys, so
it only moves work rather than removing it.

### The fingerprint is the address

Keys are addressed for deletion by their `SHA256:` fingerprint, computed as the SHA256
digest of the raw blob, base64 without padding — byte-identical to `ssh-keygen -lf`.

This is what lets a client revoke the key it holds without a prior lookup, and what lets
the CLI recognise a registered key from a local file without sending key material
anywhere. Both alternatives are worse: a database identifier forces a list call before
every delete and leaks an internal handle into the client's stored state, and a label is
not unique and is user-editable, so deletion by label is ambiguous exactly when it
matters.

### Uniqueness is per user, not global

Two accounts may hold the same public key; one account may not hold it twice. Equality
is on the blob, so comment and whitespace differences do not create a second key.

Global uniqueness looks like a safety property and is not one. Registering a key on an
account grants access to *that account's* deployments, so registering someone else's
public key on your own account grants them nothing you did not already control and grants
you nothing new. What a global constraint would add is a cross-account oracle: a
rejection would reveal that some other account had registered a given public key.
Public keys are not secret, so this is a small leak — but it is a leak bought for no
protection.

### Administrators may revoke, not grant

Read and delete follow the platform's usual `require_self` / `require_admin` pattern.
Add is restricted to the owner even for administrators.

An administrator adding a key to another user's account installs a credential that
authenticates *as that user*. That is impersonation, and it is not made safe by being
performed by an administrator; it is exactly the action an attacker with an admin session
would want. Administrative reach over the collection exists so a compromised key can be
revoked during an incident, which is the read and delete half.

### The limit travels with the collection

The list response is an envelope carrying the caller's keys and the platform's current
per-account limit, rather than a bare array.

This follows `GET /me/tos-acceptance`, which already reports `current_version` alongside
the caller's own state for the same reason: `AGENTS.md` requires the client to learn
platform values at runtime because it ships on its own cadence, and a limit compiled into
`freepod` is wrong the first time the platform retunes it. Putting it on the call the
client already makes avoids a second round trip and a second endpoint.

This departs from the repository's usual bare-list collections. The departure is
deliberate and is the reason it is written down here.

### The client's local record is a per-environment pointer, never key material

The record lives in the existing configuration directory beside the token cache, keyed by
environment, and holds a fingerprint plus a path. It holds no key material, so it is not
a secret and its loss is recoverable.

Recovery, when the record is missing or stale, matches **public** key files by
fingerprint. Operating on `.pub` files rather than private ones is not an incidental
choice: it is what makes hardware-backed and agent-only keys work, where no private file
exists at all and `ssh -i <public key>` with `IdentitiesOnly=yes` is the documented way to
select the agent identity.

Keying by environment matters because an account on dev is not the account on prod; a key
registered against one must never be presented as this machine's key for the other.

### The generated key is passphrase-less, in the client's own directory

`freepod key add` with no argument generates an Ed25519 key with no passphrase, mode
0600, inside the client's configuration directory — not in `~/.ssh`.

A passphrase would mean an interactive prompt on every `freepod` command that opens a
connection, which is hostile for a tool meant to be scriptable, and the usual answer to
that (an agent) is exactly what a user with a passphrase-protected key already has and can
register instead. The mitigation for a passphrase-less key is that it is per machine and
independently revocable, which is why keys are account-level rather than global secrets.
A user who wants a passphrase or a hardware token registers their own key; that path is
first-class, not a fallback.

Staying out of `~/.ssh` keeps the client from writing into a directory the user curates,
and keeps `freepod`-owned material obviously distinguishable from the user's own.

### The settings page ships visible, describing what keys are for

The panel is not hidden behind a flag while the auth-swap change is outstanding. It
describes what a key is for and does not claim that adding or removing one currently
grants or withdraws access — because at this point it does neither.

Hiding it would mean shipping dead UI code and a second change to reveal it; showing it
with an overclaiming description would tell a user they had revoked access they had not.
Describing the actual state is the honest option and costs one sentence of copy. This is
the assumption most worth confirming before implementation, since it is a product
judgement rather than a technical one.

## Risks / Trade-offs

- **Registering a key appears to do nothing** → until the auth-swap change lands, a user
  who registers a key sees no change in how they connect. Mitigated by the panel's copy
  and by the CLI reporting the fingerprint it registered rather than implying access was
  granted. Not mitigable further without shipping the two changes together, which would
  defeat the decomposition.
- **Revocation likewise does nothing yet** → a user cannot use this to lock out a lost
  laptop today, because the key never granted anything. The risk is a false sense of
  security, and the mitigation is the same copy discipline. Worth re-reading when the
  auth swap lands, since the copy must change at that point.
- **A passphrase-less private key sits on disk** → mode 0600 in a directory the client
  owns, per machine, independently revocable, and never the only option. Accepted
  deliberately; see the decision above.
- **The chosen limit constrains the future projection** → an account's keys will
  eventually be rendered into an `authorized_keys` payload. A generous limit now becomes
  a large payload later. A limit in the small tens is far below any relevant ceiling, but
  the value should be picked with that downstream use in mind rather than as a free
  parameter.
- **The list envelope departs from bare-list collections** → a reviewer may read it as an
  inconsistency. Mitigated by recording the `tos-acceptance` precedent here and in the
  API's own documentation.
- **Fingerprint recovery could match a key the user did not intend** → the client adopts
  a local key only when exactly one candidate matches a *registered* fingerprint, and asks
  when several do. It never adopts on a near match.

## Migration Plan

1. Data model and Alembic migration; service module under `api/app/services/` holding all
   validation, fingerprinting and uniqueness logic, so API, `caelus` and any later
   projection share one implementation.
2. REST endpoints and `caelus` parity over that service.
3. `freepod key` command group and the local record.
4. Settings page, nav entry, and the SSH keys panel.

Steps 3 and 4 are independent of each other and both depend only on step 2.

**Rollback**: the feature grants nothing, so rollback is removing the surfaces. The table
can be left in place harmlessly, or dropped by reverting the migration; no other subsystem
reads it.

## Open Questions

- **What is the per-account key limit?** A number in the small tens. It is configuration,
  it changes nothing structural, and it can be tuned after the projection change shows
  what the payload actually costs.
- **Should `list` show a key's last use?** Useful for deciding which key to revoke, but
  there is no usage signal to populate it until the edge reports authentications. Purely
  additive later; it changes no requirement here.
