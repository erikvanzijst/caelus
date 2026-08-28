## 1. Data model

- [x] 1.1 Add the account SSH key table to `api/app/models/` — owner FK to `user` with
      cascade on delete, key type, key blob, `SHA256:` fingerprint, label, `created_at`.
      Verify the model imports and the relationship from `UserORM` resolves.
- [x] 1.2 Add a uniqueness constraint on (owner, key blob) — not on the whole key line,
      so comment differences do not create a second key — and an index supporting lookup
      of one key by (owner, fingerprint), which is how deletion addresses a key. Verify
      by asserting a duplicate insert raises and a differing-comment insert also raises.
- [x] 1.3 Write the Alembic migration and verify `alembic upgrade head` then
      `alembic downgrade -1` round-trips cleanly on a scratch database.
- [x] 1.4 Verify keys are removed when their owner is deleted, matching the requirement
      that no key outlives its owner — add a test that deletes a user holding keys and
      asserts none remain in any state.

## 2. Service layer

All validation, fingerprinting and uniqueness logic lives here so the API, the `caelus`
CLI and any later projection share one implementation.

- [x] 2.1 Implement parsing and validation in a new `api/app/services/` module using
      `cryptography`'s `load_ssh_public_key`: derive the key type from the **parsed key**
      and reject a submission whose text prefix disagrees with its blob. Verify with
      tests covering ed25519, RSA and ECDSA accepted; prefix/blob mismatch rejected.
- [x] 2.2 Reject by policy: `ssh-dss`, RSA below 2048 bits, anything containing private
      key material or PEM private-key delimiters, multi-key submissions, and malformed
      input. Each rejection carries its own `code`. Verify each is a distinct, identifiable
      error — not one generic failure — and that no rejected input is written to any log.
- [x] 2.3 Reject multi-key submissions **before** handing the text to
      `load_ssh_public_key`. Verified against cryptography 50.0.0: the parser accepts a
      two-line submission and silently returns the first key, so left to the parser a user
      pasting two lines would have one registered and the other dropped without a word.
      Verify a two-line submission is rejected and that neither line is stored.
- [x] 2.4 Implement fingerprint derivation: SHA256 of the raw blob, base64 without
      padding, `SHA256:` prefixed. Verify against `ssh-keygen -lf` output for generated
      keys of each accepted type, asserting byte equality.
- [x] 2.5 Implement label defaulting from the key's trailing comment, and store **no**
      label when the key carries no comment and none was supplied. Verify both paths, and that an unlabeled key still reads and deletes.
- [x] 2.6 Normalize stored key material to the two-token `<type> <blob>` form, dropping any
      trailing comment, since the comment has already been consumed as the default label
      and is not part of the key's identity. Verify a key registered with a comment reads
      back without one, and that the label carries it instead.
- [x] 2.7 Implement delete-by-fingerprint with a distinct not-found outcome, and verify a
      delete for an unheld fingerprint reports "no such key" rather than succeeding.

## 3. REST API

- [x] 3.1 Add the collection under `/api/users/{user_id}/ssh-keys`: `GET` (list), `POST`
      (add), `GET /{fingerprint:path}` (read one), `DELETE /{fingerprint:path}`. The single
      `GET` exists so the `Location` returned by `POST` addresses a route that resolves.
      Verify there is no root-level collection and no `user_id` query-parameter
      alternative.
- [x] 3.2 Address a single key with a **path-converter** segment, `{fingerprint:path}`,
      not an ordinary one (design.md § *The fingerprint occupies a `path` segment*). Verify
      with a key whose fingerprint contains `/` and one whose fingerprint contains `+`:
      register, read back and delete each by fingerprint. Roughly half of all fingerprints
      contain each character, so an ordinary segment would 404 half the time — the test is
      what keeps a later refactor from reintroducing that.
- [x] 3.3 Return the collection as a **plain array** of the same representation `POST` and
      the single `GET` return. Verify all three responses carry the same field set with the
      same meanings, and that an account with no keys gets an empty array rather than a 404.
- [x] 3.4 Add an optional `code` to `CaelusException` and emit it from
      `register_exception_handlers` in `api/app/api/util.py` when the exception carries
      one. Verify `detail` is unchanged, that an error raised without a `code` omits the
      field entirely, and that existing endpoints' error bodies are byte-identical to
      before.
- [x] 3.5 Reject an add body carrying any field other than `public_key` and `label` with
      `extra="forbid"`, per `TosAcceptanceCreate`. Verify a body supplying `fingerprint` is
      rejected rather than accepted with the value ignored.
- [x] 3.6 Wire authorization: `require_self` for read and delete so owners and admins
      both pass. Verify a non-owner is refused with the platform's standard error.
- [x] 3.7 Restrict **add** to the owner, so an administrator cannot install a credential
      that authenticates as another user. Verify an admin add against another account is
      refused and that the refusal is distinguishable from a validation error.
- [x] 3.8 Verify no response on any path contains private key material, and that a delete
      for a fingerprint the account does not hold answers not-found rather than forbidden.
- [x] 3.9 Add `caelus` CLI parity for the same operations over the same service, per the
      API/CLI lockstep convention. Verify an operator delete removes the key exactly as
      the API would and that invalid input is rejected identically on both paths.

## 4. `freepod key` commands

- [x] 4.1 Add the `key` group alongside `var` and `skill`. Verify `freepod key --help`
      lists add, list and rm.
- [x] 4.2 Implement the local record: stored in the existing config directory beside the
      token cache, **keyed by environment**, holding a fingerprint and a path and no key
      material. Verify a key registered against one environment is not reported as this
      machine's key for another.
- [x] 4.3 `key add` with no argument generates an Ed25519 keypair in the config directory
      with owner-only permissions, registers the public half, and records it. Verify the
      private key file mode is 0600, that nothing is written to `~/.ssh`, and that
      re-running reports the existing key instead of generating a second.
- [x] 4.4 `key add <path>` registers an existing **public** key and records its path.
      Verify a private key path is refused with an error naming the expected `.pub` file.
- [x] 4.5 `key list` shows fingerprint and label and marks the key this machine holds.
      Verify the no-keys case prints guidance rather than an empty table.
- [x] 4.6 Implement fingerprint-based recovery when the local record is missing or stale:
      match candidate **public** key files against registered fingerprints; adopt and
      re-record on exactly one match; report and point at `key add` on none; ask on
      several. Verify all four outcomes, including that a key whose private half is absent
      (agent- or hardware-held) is still matched.
- [x] 4.7 `key rm` accepts the identifier `list` shows and works for keys this machine
      does not hold; removing this machine's key clears the local record. Verify both.
- [x] 4.8 Verify no command prints private key material in any mode, including verbose.

## 5. Settings page and SSH keys panel

- [ ] 5.1 Add a `/settings` route and page available to every authenticated user, composed
      of panels in the same shape the admin area uses. Verify a non-administrator can
      open it directly by URL.
- [ ] 5.2 Add the entry to the app shell's account menu, presented as the user's own
      account rather than an administrative feature. Verify it is visible to a
      non-administrator.
- [ ] 5.3 Implement `SshKeysPanel` as its own component under `ui/src/components/`, not
      inlined into the page. Verify the page composes it rather than defining it.
- [ ] 5.4 List keys with label, `SHA256:` fingerprint, type and registration time, with an
      explanatory empty state for accounts holding none. A key with no label is presented
      by its fingerprint rather than a placeholder. Verify all three render.
- [ ] 5.5 Add-key form accepting a pasted public key and optional label, surfacing the
      platform's distinct validation failures as distinct messages selected from the
      returned `code`, never by matching on the message text. Verify duplicate, unsupported
      type and private-key-material each read differently, and that an unrecognized `code`
      still produces a readable fallback rather than a blank error.
- [ ] 5.6 Detect pasted private key material client-side, warn, and do not submit. Verify
      with an OpenSSH private key block.
- [ ] 5.7 Delete requires a confirmation identifying the key and stating that any machine
      holding it loses access. Verify the key survives a cancelled confirmation and is
      removed on a confirmed one.
- [ ] 5.8 Verify the panel offers no in-browser key generation and directs users to the
      client instead.

## 6. Verification and documentation

- [ ] 6.1 Confirm this change grants nothing: no chart, `Pipe`, reconciler, NetworkPolicy
      or edge configuration is touched, and SFTP authentication still uses the existing
      per-deployment passwords. Verify by connecting over SFTP to an existing dev
      deployment before and after, unchanged, and by reviewing the diff for any file
      under `products/`, `tf/` or the reconciler.
- [ ] 6.2 Verify end to end on dev: register a key with `freepod key add`, see it in
      `freepod key list` marked as this machine's, see it in the settings panel with a
      matching fingerprint, delete it from the UI, and confirm `freepod key list` no
      longer reports a local key.
- [ ] 6.3 Update `api/README.md` with the collection, its authorization rules — including
      why administrators may revoke but not add — the fingerprint addressing scheme and why
      it needs a path converter, and the `code` field now available on error bodies.
- [ ] 6.4 Update `cli/README.md` (end-user surface: the new commands) and
      `cli/DEVELOPMENT.md` (the local record's location, its per-environment keying, and
      the recovery rule).
- [ ] 6.5 Update `ui/README.md` with the settings page and the panel component.
- [ ] 6.6 Update `AGENTS.md`: note that account SSH keys exist, are user-owned rather than
      deployment-scoped, and that no subsystem consumes them yet — so the next change
      knows exactly what it is building on.
