## Why

Freepod can now build a container image from an uploaded project archive and run it
through the `custom` product, but nothing puts that pipeline in a developer's hands.
The three endpoints involved — `POST /api/artifacts`, `POST /api/builds`, and
`PUT /api/users/{id}/deployments/{id}` — have to be driven in sequence, with a
presigned form upload, byte-range log polling, and a deployment state machine in
between. That is a client's job, not a user's.

The only client that exists today is `cli/freepod_cli.py`, a deliberately
dependency-free demo that authenticates and lists deployments. It proves the OAuth2
flows work; it does not deploy anything.

This change adds `freepod`, a standalone command-line client that takes a local project
directory to a running deployment in two commands.

## What Changes

- **New standalone Python package at `cli/`** — `pyproject.toml`, `src/freepod/`,
  console script `freepod`. It shares **no code** with `api/` and depends only on the
  public REST API. Runtime dependencies are `click`, `httpx`, and `pathspec>=1.0`; all
  are pure Python, so every wheel is universal and a Homebrew formula stays short.

- **New `freepod login` / `logout` / `whoami`** — the authorization-code-with-PKCE
  loopback flow and the device authorization grant, auto-selected by whether a browser
  is reachable. Refresh tokens cache at
  `${XDG_CONFIG_HOME:-~/.config}/freepod/tokens.json`, mode `0600`, **keyed by
  environment**, because an access token is audience-bound to exactly one environment.

- **New `freepod init`** — resolves the `custom` product by slug, reads its template's
  `values_schema_json`, prompts for every required field, normalizes and validates the
  hostname against `GET /api/hostnames/{fqdn}`, and writes `.freepod.json`. It makes
  **no writes to the API**: a command called `init` must not provision a billable
  resource, and splitting creation across two commands would leave an orphan deployment
  behind on a failed file write.

- **New `freepod deploy`** — preflight, pack, upload, build, release. It creates the
  deployment on first run and updates it thereafter, so `git clone && freepod deploy`
  works for a second developer.

- **New `.freepod.json` project file** — JSON, committed, holding the environment, the
  deployment pointer (`id` and the immutable `name`), and `user_values` as declared
  intent. The build's `image` is deliberately **never** written to it.

- **Two named environments, no `--baseurl`.** `prod` (default) and `dev`, each with its
  hardwired Keycloak client id and issuer. A free-form base URL would need issuer and
  client-id discovery to accompany it, and this change explicitly does **not** add a
  discovery endpoint to the API.

- **Deleted: `cli/freepod_cli.py`.** Its authentication module is lifted into
  `src/freepod/auth.py` essentially unchanged, and its README — the two flows, the
  status-code contract, the security notes — folds into the package README. Keeping a
  second thing named "the CLI" in the same directory would only create ambiguity about
  which one is real.

**No API, database, Terraform, or UI change.** Every endpoint this client calls already
exists and is unmodified. Distribution to PyPI, Homebrew, and Chocolatey is out of
scope here: this change produces an installable package and builds it in CI, and
publication becomes its own operational change once the client is proven.

## Capabilities

### New Capabilities

- `cli-distribution`: The package's shape, dependency budget, Python floor, console
  entry point, and the cross-cutting conventions every command obeys — stream
  discipline, exit codes, retry policy, timeouts, and color.
- `cli-environments`: The two named environments, their audience binding, the absence
  of a caller-supplied base URL, and the production default.
- `cli-authentication`: The two OAuth2 flows, flow auto-detection, the per-environment
  token cache and its file permissions, and the status-code contract the client must
  act on — including the 401/403 inversion and the bounded refresh rule that keeps it
  from becoming a login loop.
- `cli-project-file`: The `.freepod.json` format, project-root discovery, environment
  pinning, and the rule that build outputs never enter the file.
- `cli-init`: Product resolution by slug, schema-driven prompting, hostname
  normalization and availability checking, and the guarantee that `init` writes nothing
  server-side.
- `cli-project-archive`: How a project directory becomes a tar stream — archive root
  layout, the four-level ignore precedence, gitignore matching semantics including the
  re-inclusion rule, deterministic ordering, and the single size limit a client is
  entitled to know.
- `cli-build-submission`: Minting and consuming an upload slot, creating a build,
  recognizing an idempotent re-attach, and streaming the log by byte range until a
  terminal status.
- `cli-deploy`: The deploy pipeline's ordering and its release semantics — build before
  touching the deployment, create-or-update, canonical template targeting, whole-document
  user values, and rollout polling.

### Modified Capabilities

None. No existing requirement changes.

## Impact

- **New**: `cli/pyproject.toml`, `cli/src/freepod/**`, `cli/tests/**`, rewritten
  `cli/README.md`.
- **Removed**: `cli/freepod_cli.py`.
- **Updated**: `AGENTS.md` — the monorepo layout section currently lists `api/`, `ui/`,
  and `tf/` only, and does not mention `cli/` at all.
- **Dependencies**: `click`, `httpx`, `pathspec>=1.0` (MPL-2.0, pure Python), scoped to
  `cli/` and installed independently of `api/`'s `uv` environment.
- **Unchanged**: the API, the database, Terraform, the UI, and the Keycloak clients.
  `freepod-cli-prod` and `freepod-cli-dev` already exist with the redirect URIs, PKCE
  requirement, device grant, and audience mappers this client needs.
- **External prerequisites**, tracked separately and required before the client is
  usable end to end: the `custom` product must be curated with slug `custom` and
  `public` visibility, and it must have a plan whose current template is
  `price_cents: 0`.
