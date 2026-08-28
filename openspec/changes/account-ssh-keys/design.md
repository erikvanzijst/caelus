## Context

See `proposal.md` § Why, and `var/ssh_access.md` D7–D10 for the wider SSH design this
serves.

Four existing facts shape the approach.

1. **`cryptography` is already a dependency** (`api/pyproject.toml`), and its
   `load_ssh_public_key` covers exactly the algorithms this change wants to accept:
   `ssh-ed25519`, `ssh-rsa`, `ecdsa-sha2-nistp256/384/521`, and both security-key
   variants `sk-ssh-ed25519@openssh.com` and `sk-ecdsa-sha2-nistp256@openssh.com`. It
   also knows `ssh-dss`, which this change rejects by policy. Verified against
   cryptography 50.0.0 in this repo's environment: those eight are the whole of
   `serialization.ssh._KEY_FORMATS`. No new dependency is needed.
2. **The client already has a per-environment configuration directory.**
   `config_dir()` resolves `${XDG_CONFIG_HOME:-~/.config}/freepod` and `token_cache_path()`
   puts the token cache inside it, keyed by environment. The key record belongs beside it,
   keyed the same way.
3. **A SHA256 fingerprint is not URL-safe.** It is base64 without padding, so it draws
   from an alphabet containing `+` and `/`. Measured over 2000 random digests, 976
   contained `/` and 971 contained `+` — about half of all keys, not an edge case. This
   is a fact about the identifier the design chose, and it constrains how that identifier
   can appear in a route.
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

## API Surface

Four routes under `/api`, all nested under the user. `user_id` is an `int`, matching
`require_self` (`api/app/deps.py`).

| Method   | Path                                               | Authorization          | Success                               |
|----------|----------------------------------------------------|------------------------|---------------------------------------|
| `GET`    | `/api/users/{user_id}/ssh-keys`                    | owner or administrator | `200` — a JSON array of `SshKeyRead`  |
| `POST`   | `/api/users/{user_id}/ssh-keys`                    | **owner only**         | `201` — `SshKeyRead`, plus `Location` |
| `GET`    | `/api/users/{user_id}/ssh-keys/{fingerprint:path}` | owner or administrator | `200` — `SshKeyRead`                  |
| `DELETE` | `/api/users/{user_id}/ssh-keys/{fingerprint:path}` | owner or administrator | `204` — no body                       |

The single-key `GET` is not strictly required by the capability, which asks only for
list, add and delete. It exists because `POST` returns a `Location` and a `Location`
pointing at a route that does not exist is a defect; it costs one handler over the
service call `DELETE` already makes.

### Request body — `SshKeyCreate`

```jsonc
{
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... alice@laptop",
  "label": "Work laptop"        // optional; defaults from the key's comment
}
```

`extra="forbid"`, following `TosAcceptanceCreate` and the `builds` collection, which
documents `422` for a body carrying an unexpected field. A submission that includes a
`fingerprint` is therefore **rejected**, not accepted-and-ignored: the fingerprint is
derived, and a client that believes it can supply one is wrong in a way worth telling it
about.

### Response body — `SshKeyRead`

One representation, returned identically by list, add and single read, so a client never
special-cases the path it arrived by.

```jsonc
{
  "fingerprint": "SHA256:I+OIdSrkELx6Vi3MfCKmBGRF3wfVbOAweblLYeXXV2Q",
  "key_type": "ssh-ed25519",
  "bits": 256,
  "label": "alice@laptop",
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...",
  "created_at": "2026-08-27T10:12:03Z"
}
```

`bits` is carried so a surface can render "RSA 2048" and so the 2048-bit floor is visible
rather than discoverable only by rejection.

### Status codes and error codes

| Condition                                                | Status | `code`                 |
|----------------------------------------------------------|--------|------------------------|
| Not a well-formed OpenSSH public key line                | 400    | `malformed_key`        |
| PEM or OpenSSH private-key delimiters present            | 400    | `private_key_material` |
| More than one key line in the submission                 | 400    | `multiple_keys`        |
| `ssh-dss`, or an algorithm outside the allowlist         | 400    | `unsupported_key_type` |
| Declared prefix disagrees with the algorithm in the blob | 400    | `key_type_mismatch`    |
| RSA below 2048 bits                                      | 400    | `key_too_short`        |
| Caller is not the owner                                  | 403    | —                      |
| No such user                                             | 404    | —                      |
| No such key on this account (single read, delete)        | 404    | —                      |
| The key is already registered on this account            | 409    | `duplicate_key`        |
| Body carries an unexpected field, or is shaped wrong     | 422    | —                      |

## Decisions

### Validation parses the key; it does not trust the prefix

A submission is validated by base64-decoding the blob and loading it with
`load_ssh_public_key`. The stored key type comes from **the parsed key**, never from the
text before the blob, so a submission whose prefix disagrees with its body is rejected
rather than mislabeled. `ssh-dss` is rejected by explicit policy even though the parser
accepts it, and RSA keys are additionally checked against `key_size >= 2048`.

Using the parser rather than a regex is what gets the security-key variants right for
free, and it means a malformed key fails at the boundary instead of at the point where
the key is projected into an `authorized_keys` file — where the failure would be a
sidecar that rejects every login for reasons nobody can see.

Probed against the installed cryptography 50.0.0, the parser handles two of the three
policy checks on its own and **not the third**:

- a prefix/blob mismatch raises `ValueError: Invalid key format`;
- a private key file raises `UnsupportedAlgorithm: Unsupported key type: b'-----BEGIN'`;
- **a two-line submission is accepted, and the first key is silently taken.**

So the multi-key rejection is ours to implement, before the parser rather than after it.
Left to the parser, a user pasting two lines would have one of them registered and the
other silently dropped — which on a revocation surface is the wrong kind of surprise.

Alternative considered: hand-rolling a length-prefixed blob reader. Fewer lines, no
dependency on the parser's algorithm coverage, and it would still identify a key
correctly — but it cannot compute RSA key sizes or reject structurally invalid keys, so
it only moves work rather than removing it.

### The fingerprint is the address

Keys are addressed for deletion by their `SHA256:` fingerprint, computed as the SHA256
digest of the raw blob, base64 without padding — byte-identical to `ssh-keygen -lf`,
verified against the tool.

This is what lets a client revoke the key it holds without a prior lookup, and what lets
the CLI recognize a registered key from a local file without sending key material
anywhere. Both alternatives are worse: a database identifier forces a list call before
every delete and leaks an internal handle into the client's stored state, and a label is
not unique and is user-editable, so deletion by label is ambiguous exactly when it
matters.

### The fingerprint occupies a `path` segment, not an ordinary one

The route is `/{fingerprint:path}`, using Starlette's path converter. This is the repo's
first such route and the reason is Context 3: about half of all fingerprints contain a
`/`.

The three candidate forms were run against both `TestClient` and a real uvicorn server,
with the fingerprint fully percent-encoded:

| Form                           | Result                              |
|--------------------------------|-------------------------------------|
| `/ssh-keys/{fingerprint}`      | **404** — the segment never matches |
| `/ssh-keys/{fingerprint:path}` | 200, fingerprint intact             |
| `/ssh-keys?fingerprint=...`    | 200, fingerprint intact             |

The ordinary segment fails outright for half of all keys, whether the client sends a raw
`/` or a `%2F`, because the ASGI server percent-decodes the path before routing and a
`str` path parameter cannot span a `/`.

The query form works but fails *worse* when a client is imperfect: with an unencoded
`+` — which a client that did not think about encoding will send, and which about half
of fingerprints contain — the server receives `SHA256:I OI/Srk…`, the `+` having been
decoded as a space by ordinary form decoding. That returns a confident `404 no such key`
for a key that exists. A silent mis-parse on the one security-critical operation in this
capability is not an acceptable failure mode, and it is invisible in exactly the case
that matters: a user revoking a lost laptop and being told the key is not there.

The path converter has the further virtue of accepting the fingerprint whether the
front-end proxy hands us a raw `/` or a preserved `%2F`, so it does not depend on how
Traefik and oauth2-proxy normalize the path. A trailing empty match or an over-greedy
multi-segment match resolves to no key and answers `404`, which is already the correct
answer.

### Errors carry a machine-readable code

`_exception_handler` (`api/app/api/util.py`) currently renders every application error as
`{"detail": "<prose>"}`, leaving the HTTP status as the only thing a client can branch
on. That is not enough here: *malformed*, *private key material*, *multiple keys*,
*unsupported type*, *type mismatch* and *too short* are all `400`, and both the API and
the UI capabilities require them to be told apart — the UI has to say "that is a private
key" rather than "invalid input".

So `CaelusException` gains an optional `code`, and the handler emits it when the
exception carries one. The change is additive: `detail` is unchanged and every existing
error simply omits `code`.

The alternative — spreading the conditions across more status codes — does not work,
because there are six `400`-shaped rejections and no honest way to give them six
statuses. The alternative of having clients match on prose is what the requirement
explicitly forbids, and it breaks the first time a message is reworded.

### Stored key material is normalized to type and blob

What is stored and returned in `public_key` is the two-token form `<type> <blob>`, with
any trailing comment stripped.

The comment has already been consumed: it is where `label` defaults from. Keeping it a
second time in the key body would mean the same text stored twice and drifting apart the
moment a user renames the label. Uniqueness is on the blob for the same reason, so the
comment is already not part of the key's identity. The later `authorized_keys`
projection can render `<type> <blob> <label>` and get a comment the user actually
controls, rather than whatever their machine stamped in when the key was generated.

### There is no per-account key limit

The number of keys an account may hold is not bounded, and no limit is enforced, stored
or advertised.

### Administrators may revoke, not grant

Read and delete follow the platform's usual `require_self` / `require_admin` pattern.
Add is restricted to the owner even for administrators.

### Uniqueness is per user, not global

Two accounts may hold the same public key; one account may not hold it twice. Equality
is on the blob, so comment and whitespace differences do not create a second key.

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
judgment rather than a technical one.

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
- **An account's key count is unbounded** → the eventual `authorized_keys` projection
  renders every key an account holds, so a pathological account makes a large payload.
  Accepted deliberately: the cost lands in the projection, which can measure it and add a
  bound then. Nothing about the store forecloses that.
- **`{fingerprint:path}` is the repo's first path-converter route** → a reviewer may read
  it as sloppy routing rather than a deliberate answer to a measured problem. Mitigated
  by recording the measurement here and by a test that registers and deletes a key whose
  fingerprint contains a `/`, so a later refactor to an ordinary segment fails loudly
  instead of half the time.
- **An error `code` is a new convention** → it appears first on this capability and will
  read as inconsistent until other endpoints adopt it. Accepted: the alternative is prose
  matching, which the API capability forbids outright.
- **Fingerprint recovery could match a key the user did not intend** → the client adopts
  a local key only when exactly one candidate matches a *registered* fingerprint, and asks
  when several do. It never adopts on a near match.

## Migration Plan

1. Data model and Alembic migration; service module under `api/app/services/` holding all
   validation, fingerprinting and uniqueness logic, so API, `caelus` and any later
   projection share one implementation.
2. REST endpoints and `caelus` parity over that service, plus the `code` field on the
   shared exception handler.
3. `freepod key` command group and the local record.
4. Settings page, nav entry, and the SSH keys panel.

Steps 3 and 4 are independent of each other and both depend only on step 2.

**Rollback**: the feature grants nothing, so rollback is removing the surfaces. The table
can be left in place harmlessly, or dropped by reverting the migration; no other subsystem
reads it.

## Open Questions

- **Should `list` show a key's last use?** Useful for deciding which key to revoke, but
  there is no usage signal to populate it until the edge reports authentications. Purely
  additive later; it changes no requirement here.
