## Why

The platform is moving SSH access — SFTP today, shell and database forwarding next — off
per-deployment generated passwords and onto public keys the user registers once
(`var/ssh_access.md` D7, D9). Nothing can move until there is somewhere to put a key.

Registering a key is also the only moment at which the client knows both halves of a
pair, so this is where the `freepod` CLI must record which local private key belongs to
the account. Without that, a later `ssh -i` has to guess among a dozen files in
`~/.ssh`, and guessing is not an option: the edge answers *every* offered key with
"partial success", so a client that tries several exhausts `MaxAuthTries` and is denied
before reaching the right one (`var/ssh_access.md` D10).

The user has no account settings surface at all today — the UI has Dashboard, Admin and
the legal pages, and nothing else — so this change introduces one.

## What Changes

- A **user-owned SSH public key** resource: the key material, a user-supplied label, and
  a server-computed SHA256 fingerprint. Keys belong to the account, not to a deployment.
- **REST endpoints** under the user, following the platform's nested-resource
  convention: list, add, and delete. The fingerprint is part of the read model.
- **`freepod key add | list | rm`**, plus the CLI-side record of which local key belongs
  to this account on this machine, written beside the existing token cache and keyed by
  environment.
- **An account settings page** in the UI, reachable from the app shell, whose first
  panel manages SSH keys.
- Public key material only. The API rejects anything that parses as a private key, and
  no surface ever accepts, stores, displays, or transmits one.

**This change grants no access.** No `Pipe` reads these keys and no sidecar trusts them
yet; SSH authentication is unchanged and still uses the per-deployment passwords.
Registering a key has no observable effect on connecting until the auth-swap change
lands. That is deliberate — it keeps this change additive and independently reversible.

## Capabilities

### New Capabilities

- `ssh-key-data-model`: what an account SSH key is — accepted algorithms, validation,
  fingerprint derivation, per-user uniqueness, labels, limits, and deletion semantics.
- `ssh-key-api`: the deployment-independent REST surface for listing, adding and
  deleting an account's keys, and its authorization rules.
- `cli-ssh-keys`: the `freepod key` command group, generation of a CLI-owned keypair,
  registration of an existing key, and the local record that makes later key selection
  deterministic.
- `account-settings-ui`: an account settings page reachable from the app shell, and the
  SSH keys panel it hosts.

### Modified Capabilities

None. No existing requirement changes behavior; SFTP authentication is untouched.

## Impact

**API**

- New table and Alembic migration for account SSH keys.
- New service module under `api/app/services/`, per the repository's rule that all
  DB/ORM logic lives there and API and CLI are thin facades over it.
- New routes under `/api/users/{user_id}/ssh-keys`, guarded by the existing
  `require_self` / `require_admin` dependencies.
- `caelus` CLI parity for the same operations, per the API/CLI lockstep convention.

**Client CLI (`cli/`)**

- New `key` command group alongside `var` and `skill`.
- New files in `${XDG_CONFIG_HOME:-~/.config}/freepod`: a CLI-generated private key and
  a record of which key is registered, keyed by environment like the token cache.
- The package ships on its own cadence; the new commands must learn host and limits
  from the platform rather than embedding them.

**UI (`ui/`)**

- A new `/settings` route and page, plus an entry in the app shell's user menu — the
  first non-admin account surface in the application.
- An `SshKeysPanel` component under `ui/src/components/`, not inlined into the page.

**Not affected**

- No chart, no `Pipe`, no reconciler, no NetworkPolicy, no edge configuration.
- SFTP credentials, their API, and their UI panel are unchanged and keep working.
