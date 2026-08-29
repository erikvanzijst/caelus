# Caelus API: Agent Onboarding Guide

This document is for engineers and coding agents who need to become productive in
this API codebase quickly.

## What This Project Is

`api/` is the control plane for provisioning user-owned web app instances on
Kubernetes.

It exposes two interfaces over the same business logic:
- FastAPI REST endpoints (`app/api/*.py`)
- Typer CLI commands (`app/cli.py`)

Core design rule: API and CLI are functionally equivalent for product/user/template/
deployment lifecycle operations. Both call the same service layer.

## Design Goals

- Keep API and CLI behavior in lockstep.
- Keep HTTP/CLI layers thin; put domain logic in `app/services/`.
- Treat database as source of truth for desired deployment state.
- Reconcile desired state to platform state through a queue-driven workflow.
- Enforce ownership boundaries: templates are scoped under products.
- Enforce ownership boundaries: deployments are scoped under users.

## Codebase Map

- `app/main.py`: FastAPI app wiring, routers, exception handlers.
- `app/cli.py`: Typer CLI commands; mirrors REST operations.
- `app/models.py`: SQLModel ORM + API read/write models.
- `app/db.py`: engine/session helpers and DB init.
- `app/api/`: REST route handlers.
- `app/services/`: domain services (single source of behavior).
- `app/services/reconcile.py`: deployment reconciliation orchestration.
- `app/services/jobs.py`: reconcile job queue operations.
- `app/services/builds.py`: build lifecycle (create, read, list, log slice).
- `app/services/artifacts.py`: presigned upload slots and artifact lookup.
- `app/services/build_jobs.py`: build Job manifest + the kubectl seam.
- `app/build_worker.py`: the build worker's claim/advance/recover pass.
- `app/provisioner.py`: Kubernetes/Helm adapter facade.
- `app/proc.py`: subprocess runner wrapper + command error normalization.
- `alembic/`: database migration history.
- `tests/`: API, CLI, service, and adapter tests.

## Authentication

Most API endpoints require authentication via the `X-Auth-Request-Email`
header and return `404` when it is absent. A small set of read-only
endpoints are intentionally public (`/api/docs`, `/api/static`, and the
product/plan reads — see "Public endpoints and the production `skip-auth`
footgun" below).

### How it works

- In production, Traefik routes requests through oauth2-proxy, which
  injects `X-Auth-Request-Email` after Keycloak authentication.
- Keycloak authenticates end users against the **`freepod` realm**, not the
  built-in `master` realm. `master` is Keycloak's administrative realm and
  holds only the instance administrator; no end-user account lives there.
- Each environment has its own Keycloak client — `freepod-prod` for
  `freepod.eu`, `freepod-dev` for `dev.freepod.eu` — so a session issued for
  one environment is not valid for the other.
- **`dev.freepod.eu` additionally requires membership of the `freepod-dev`
  Keycloak group**, enforced at the edge by oauth2-proxy `allowed_groups`.
  Authentication is shared (one realm, one signup, one account); only
  *authorization* differs per environment. Granting or revoking dev access is
  a group membership change in the Keycloak admin console — no Terraform
  apply and no second account. Note that `skip_auth_routes` bypass this check
  entirely (see the footgun below), so dev's anonymous reads stay public.
- In local development, the frontend sets this header from localStorage
  after the user enters their email in the dialog.
- The backend trusts the header unconditionally — behavior is identical
  regardless of header source.

The application stores no Keycloak identifier: `UserORM` holds only `email`,
and `deps.py` resolves the caller by `lower(email)`. That is what allowed
Keycloak identity to be rebuilt underneath Freepod without touching a single
application row — and it is why the email claim is security-critical. The
realm sets `verifyEmail = true`; do not relax it, because an account whose
email could be changed to another user's would take over that Freepod
account.

### Public endpoints and the production `skip-auth` footgun

Several read-only endpoints are intentionally anonymous (no
`get_current_user` dependency) so the public landing page — and the
deploy UI's live validators — can work before/without per-request auth:

- Products & templates: `GET /api/products`, `GET /api/products/{id}`,
  `GET /api/products/{id}/templates`,
  `GET /api/products/{id}/templates/{tid}`,
  `GET /api/products/{id}/icon`
- Plans: `GET /api/products/{id}/plans`, `GET /api/plans/{id}`,
  `GET /api/plans/{id}/templates`
- Hostname/domain helpers: `GET /api/hostnames/{fqdn}`,
  `GET /api/domains`, `GET /api/cname-target`
- Docs & schema: `GET /api/docs`, `GET /api/redoc`,
  `GET /api/openapi.json`
- Static files: `GET /api/static/*` (including product icons)

`GET /api/me` is a related special case: it *does* run
`get_current_user`, returning the user when the header is present and
`404` when anonymous — that `404` is the signal the SPA uses to show the
landing page instead of the dashboard.

The authoritative public list is the union of "no `get_current_user` in
the route" (this codebase) and oauth2-proxy's `skip_auth_routes`
(`tf/app/login/main.tf`). Those two **must** match — see the footgun
below.

In production there are **two authentication layers in series**:

1. **Edge** (Traefik forward-auth → oauth2-proxy): rejects anonymous
   requests *before they reach FastAPI* and injects a trusted
   `X-Auth-Request-Email`.
2. **App** (`Depends(get_current_user)`): authorizes using that header.

Because the edge gate runs first, marking an endpoint public in the
FastAPI code is **not sufficient** to make it anonymously reachable in
production — the edge would still block it. The genuinely-public routes
are therefore *also* listed in oauth2-proxy's `skip_auth_routes` (see
`tf/app/login/main.tf`).

**⚠️ Footgun:** `skip_auth_routes` bypasses oauth2-proxy entirely for
matching requests, which has two dangerous consequences:

- **No trusted identity, no sanitization.** oauth2-proxy does not inject
  `X-Auth-Request-Email` on skipped routes, *and* it does not strip a
  client-supplied one. Never read `X-Auth-Request-Email` for
  authorization on any endpoint matched by a skip rule — a caller could
  spoof it.
- **Bearer tokens are ignored, not rejected.** The same bypass applies to
  `Authorization: Bearer`: a skipped route neither verifies the token nor
  derives an identity from it, so the request is anonymous no matter how
  valid the token is. A skipped route therefore cannot be made to behave
  differently for an authenticated client, and group gating on
  `dev.freepod.eu` does not apply to it either.
- **Two lists that must stay in sync.** Whether an endpoint is public is
  decided in *two* places — the FastAPI dependency (app layer) and the
  `skip_auth_routes` regexes (edge layer, in Terraform) — and they can
  drift:
  - Adding `Depends(get_current_user)` to a route still in the skip list
    makes it permanently anonymous in prod (the API `404`s every call).
  - Adding a new sensitive route under an overly-broad skip regex (e.g.
    `^/api/static/.*`, or a loose `^/api/products`) makes it anonymously
    reachable *and* identity-spoofable.

Keep skip regexes **anchored and narrow** (e.g. `GET=^/api/products$`,
`GET=^/api/products/[0-9]+/plans$`) and treat any change to which
endpoints are public as one that must be mirrored in **both** the API
code and `tf/app/login/main.tf`.

### GET /api/me

Session initialization endpoint. Returns the authenticated user or `404`.

- If the email matches an existing user: returns `200` with `UserRead`.
- If the email is new: auto-creates a user record, returns `200`.
- If no header: returns `404`.
- Email matching is case-insensitive.

### FastAPI dependency: `get_current_user`

Defined in `app/deps.py`. Resolves `X-Auth-Request-Email` to a `UserORM`
with auto-creation. Injected into all endpoint functions via
`Depends(get_current_user)`.

### CLI authentication

The CLI authenticates via the `CAELUS_USER_EMAIL` environment variable.
An optional `--as-user` flag overrides the env var:

```bash
# Via environment variable
export CAELUS_USER_EMAIL=alice@example.com
caelus list-users

# Via flag (overrides env var)
caelus --as-user bob@example.com list-users
```

Commands that require user context exit with code 1 and a clear error
when neither is configured.

Note this is an **operator** mechanism, not authentication: the CLI talks to
the database directly and simply asserts who it is acting as. It must run
next to the database and grants whatever the asserted email can do. External,
remote clients use OAuth2 tokens instead — see below.

**`caelus` is therefore not a security boundary.** It bypasses the API
entirely and only runs inside the Caelus containers, so anyone who can invoke
it is already an operator with database access — there is no privilege for a
missing check to escalate. Where a command does scope by acting user (`build
list`, `list-releases`, `get-release`), that is for consistency with the REST
behavior and to keep output useful, not to enforce anything. A command that
omits such a check is not a vulnerability, and neither is one that adds it.

### External API clients (OAuth2 tokens)

Non-browser clients authenticate with a Keycloak access token presented as
`Authorization: Bearer <token>`. oauth2-proxy verifies the token at the edge
and injects `X-Auth-Request-Email` from its `email` claim, so the API is
unchanged and cannot tell a token-authenticated request from a browser one.

**Clients authenticate directly against Keycloak — not through
`/oauth2/start`.** That endpoint exists to mint a browser *cookie session* and
gives a client no tokens. A client is a first-class OAuth2 client and talks to
the realm's own endpoints.

Two public clients, one per environment. They hold no client secret (a
distributed client cannot keep one); PKCE proves client identity instead and
is **mandatory**:

| Environment | Client ID | Base URL |
| --- | --- | --- |
| Production | `freepod-cli-prod` | `https://freepod.eu` |
| Development | `freepod-cli-dev` | `https://dev.freepod.eu` |

Realm endpoints (issuer `https://keycloak.freepod.eu/realms/freepod`):

```
authorization : /protocol/openid-connect/auth
device        : /protocol/openid-connect/auth/device
token         : /protocol/openid-connect/token
revocation    : /protocol/openid-connect/revoke
```

A token is bound to one environment by its `aud` claim. A `freepod-cli-dev`
token presented to `freepod.eu` is rejected, and vice versa — the two clients
register identical loopback redirect URIs, so the audience is the *only* thing
separating them.

#### Interactive: authorization code + PKCE over loopback

1. Bind an HTTP listener on `127.0.0.1:0` (any ephemeral port).
2. Generate a `code_verifier` and its S256 `code_challenge`.
3. Open the browser to the authorization endpoint with
   `redirect_uri=http://127.0.0.1:<port>/callback`,
   `scope=openid email offline_access`, and the challenge.
4. Receive `?code=...` on the listener, then POST it to the token endpoint
   with the `code_verifier`.

The callback path is **`/callback`** and the registered redirect URIs are
port-less (`http://127.0.0.1/callback`, `http://localhost/callback`).
Keycloak relaxes port matching for loopback hosts per RFC 8252 §7.3, so any
port matches — but the **path must match exactly**, and `127.0.0.1` and
`localhost` are matched as distinct host strings.

#### Headless: device authorization grant

For SSH sessions, containers and CI, where no local browser exists. Nothing
secret passes through the terminal.

**Keycloak requires PKCE on the device endpoint too.** RFC 8628 has no
redirect and therefore no PKCE, but the client's mandatory-PKCE setting is
enforced here as well — omitting the challenge fails with
`Missing parameter: code_challenge_method`. This surprises most
implementations.

```bash
ISS=https://keycloak.freepod.eu/realms/freepod
VERIFIER=$(head -c30 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=')
CHALLENGE=$(printf %s "$VERIFIER" | openssl dgst -binary -sha256 \
            | base64 | tr '+/' '-_' | tr -d '=')

# 1. Request a device code
curl -s -X POST "$ISS/protocol/openid-connect/auth/device" \
  -d client_id=freepod-cli-dev \
  -d "scope=openid email profile offline_access" \
  -d "code_challenge=$CHALLENGE" -d code_challenge_method=S256
# → {"device_code":"...","user_code":"WMJW-QHHV",
#    "verification_uri_complete":"https://keycloak.freepod.eu/realms/freepod/device?user_code=WMJW-QHHV",
#    "expires_in":600,"interval":5}

# 2. Show verification_uri_complete to the user, then poll every `interval`
#    seconds until it stops returning authorization_pending:
curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=urn:ietf:params:oauth:grant-type:device_code \
  -d client_id=freepod-cli-dev \
  -d "device_code=$DEVICE_CODE" -d "code_verifier=$VERIFIER"

# 3. Call the API
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://dev.freepod.eu/api/me
```

#### Tokens and refresh

Access tokens live **300 seconds**. Request the `offline_access` scope to get
an offline refresh token (`typ: Offline`) with no absolute expiry — it stays
valid as long as it is used at least every 30 days, which is what makes a
stored credential practical. Refresh with `grant_type=refresh_token`.

#### Status codes

| Condition | Status |
| --- | --- |
| Valid token, authorized | `200` |
| No credential at all | `401` |
| Valid token, user not in `freepod-dev` (**dev only**) | `401` |
| Expired, malformed or unverifiable token | `403` |

Note the inversion: **an authorization failure returns `401`, not `403`.**
The group check rejects a session the edge already built, so it never reaches
the token-verification failure path. On `dev.freepod.eu` this means "you are
not in the `freepod-dev` group" is indistinguishable by status code from "you
sent no credential" — and re-authenticating, the natural response to a `401`,
will succeed and change nothing. Check group membership before assuming a
token problem.

`403` is the signal to re-authenticate or refresh; `401` is not.

#### Scope of access, and revocation

**A token grants exactly what a browser session grants** for the same user —
full account authority. The API authorizes on user identity alone and has no
notion of OAuth scopes, so a token cannot be narrowed to read-only or to a
single deployment. Treat one as equivalent to the user's password, and think
carefully before pasting one into CI.

There is no token management UI in Freepod. **Revocation is through Keycloak's
account console** (Applications → offline sessions), which lists sessions
issued to `freepod-cli-*` and can revoke them. Revoking there stops further
refresh; an already-issued access token remains valid for up to its 300-second
lifetime.

Requests matched by `skip_auth_routes` ignore bearer tokens entirely — see the
footgun section above.

## Request Flow (How Work Actually Moves)

1. API or CLI receives a command.
2. Facade calls a service in `app/services/`.
3. Service validates input and persists desired state.
4. For deployment-changing operations, service enqueues a reconcile job.
5. Reconciler applies/deletes resources via provisioner adapters.
6. Deployment status and reconcile metadata are persisted back to DB.

## Per-Deployment Object Storage

Deployments of a product whose template sets `system_values.objectStorage.enabled` get
a private bucket and a dedicated access key on the shared Garage instance,
provisioned by the reconciler as part of the apply path:

```
_reconcile_apply
    ensure_namespace
    ensure_tenant_isolation
    ensure_object_storage    ← key, bucket, grant, quota + CORS
    upsert_secret            ← credentials into the tenant namespace
    helm_upgrade_install     ← values carry only references
```

The ordering is load-bearing at both ends. The Secret is written **after** the
namespace exists and **before** Helm runs, so no pod ever starts expecting a
Secret that is not there. On delete, `teardown_object_storage` deletes the key
**before** setting the bucket's expiry rule — a key with write access can
replace its own bucket's lifecycle configuration, so revoking second would leave
a window in which the tenant could strip the rule off.

**The secret access key never enters Helm values.** Merged values are logged in
full at INFO and are persisted by Helm into a release Secret in the tenant's own
namespace; only the bucket, endpoint, region and the Secret's *name* travel that
way. `services/object_storage.py` holds the policy, `services/garage.py` the
transport.

### Blast radius of the provisioning credential

`CAELUS_GARAGE_ADMIN_TOKEN` is scoped by Terraform to the bucket and key
operations above — it cannot read cluster status, cannot alter the cluster
layout, and cannot mint further admin tokens. Within that scope it **can read
back the secret of any access key it can see**, so compromise of this process is
compromise of every tenant bucket. That is inherent to automated provisioning
and is stated here rather than left to be discovered.

## Per-Deployment Relational Storage

Deployments of a product whose template sets
`system_values.relationalStorage.enabled` get their own PostgreSQL database and
login role on the shared **tenant cluster** — a separate instance from
`caelus-postgres`, deployed per Terraform workspace, reached only through a
PgBouncer pair. Provisioning sits in the same place in the apply path as object
storage:

```
_reconcile_apply
    ensure_namespace
    ensure_tenant_isolation
    ensure_object_storage    ← key, bucket, grant, quota + CORS
    ensure_database          ← role, database, revocation, session limits
    upsert_secret            ← credentials into the tenant namespace
    helm_upgrade_install     ← values carry only references
```

`services/relational_storage.py` holds the policy,
`services/postgres_admin.py` the transport.

### What the pod gets

The reconciler writes `<deployment.name>-database` into the tenant's namespace
and the chart consumes it with `envFrom`:

| Variable | What it is |
| --- | --- |
| `DATABASE_URL` | `postgresql://<role>:<password>@<pooler>:6432/<database>` |
| `PGHOST` / `PGPORT` | the **pooler**, never the PostgreSQL server |
| `PGUSER` / `PGDATABASE` | both are `dpl_` plus the deployment UUID without hyphens |
| `PGPASSWORD` | platform-generated, re-asserted on every reconcile |

The URL covers every ORM; the discrete variables are what libpq, `psql` and
`pg_dump` read unaided. **The password never enters Helm values** — merged
values are logged in full and persisted into the tenant's namespace, so they
carry host, port, database name, role name and the Secret's name and nothing
else.

### What the isolation rests on

PostgreSQL grants `CONNECT` to `PUBLIC` on every new database, so
database-per-tenant is not isolation by itself. Provisioning revokes it, and
then **reads the privilege back and fails the provision if `PUBLIC` still holds
it**. That check is not decoration: the revoke is owner-scoped, and issued
without assuming the owner's role it does not error — it warns and does
nothing.

The role is created with every attribute negated. `NOCREATEDB` is what stops a
tenant provisioning around its own quota. Session limits (`temp_file_limit`,
`statement_timeout`, `idle_in_transaction_session_timeout`) are re-applied on
every reconcile, so a tenant's `RESET` does not survive one.

No platform process holds a pooler administrative credential, and none is
configured. Everything the platform does is expressed against PostgreSQL.

### The quota ladder

`plan_template_version.database_bytes` bounds the database. It is a **separate**
allowance from `storage_bytes`, which already means two things (the Garage
bucket quota and the chart's PVC size), and neither is derived from the other. A
relational-storage deployment whose plan declares no positive allowance fails to
provision rather than getting an unbounded database.

`caelus db-worker` measures every database and applies the state it lands in:

| Usage | State | What happens | Email |
| --- | --- | --- | --- |
| < 80% | `ok` | — | — |
| 80%, 90% | `warned` | — | yes, once per threshold |
| 100% | `readonly` | `default_transaction_read_only` on the database | yes |
| 150% | `blocked` | role set `NOLOGIN`, its backends terminated | no |

Read-only is deliberately soft — the owner can clear it on their own database,
and a tenant who does keeps growing until the hard block, which is what makes
crossing 150% an abuse signal rather than an arbitrary number. It is therefore
re-asserted on every evaluation. The reconcile runs the *same* evaluation with
notification suppressed, so redeploying cannot buy an over-quota tenant a write
window.

A threshold's suppression marker only moves once the relay accepted the
message, so an SMTP outage is retried on the next sweep rather than swallowing
the one notification a tenant gets.

**There is no recovery path other than a larger allowance.** Read-only blocks
`DELETE`, `DROP TABLE` and `VACUUM`, and no operation currently changes a
deployment's plan, so crossing 100% is presently terminal for that deployment's
data.

### Deletion, and what destroys data

Deleting a deployment revokes access and destroys nothing: the role is set
`NOLOGIN`, its backends are terminated, and a `purge_after` deadline is
recorded. The database and every byte in it survive the grace period
(`deployment_database_purge_grace_days`, matching
`deployment_bucket_expiry_days` so `legal/` can state one retention period).

`caelus db-worker`'s purge tick is the only thing that destroys tenant data. It
refuses a row with no deadline or one still inside its window, caps how many it
will purge per run, and logs every drop with its deployment id. Its orphan tick
reports cluster objects no `deployment_database` row accounts for — roles as
well as databases, because provisioning creates the role first and writes the
row last.

**No backups exist that a tenant can reach.** An accidental `DROP TABLE` is
unrecoverable for them.

## Reading a Deployment's Database Connection Details

`GET /api/users/{user_id}/deployments/{deployment_id}/database` returns the
deployment's database connection details together with its quota state and
usage. It is a **read** of what already exists: nothing is provisioned,
rotated, or re-evaluated by it.

## Deployment Vars (Runtime Configuration)

A **var** is one entry in a deployment's process environment. Vars are the
single channel into a pod's environment; `user_values_json` configures the
*chart*, not the process.

### Two tables, and the difference between them

```
deployment_var   append-only history. Setting a key inserts a row; deleting one
                 inserts a tombstone (a row with no value). Nothing is ever
                 updated in place except the re-encryption sweep, which rewrites
                 a row's representation and never its plaintext.

release_var      the snapshot: which var rows a release was created with. That
                 binding never changes, which is what makes a release
                 reproducible after later writes and deletions.
```

**Head** is the effective set: the newest row per key, tombstones excluded.

- A **deployment read** reports head — desired state, matching
  `user_values_json` beside it.
- A **release read** reports that release's snapshot.

### Routing markers

There is no second schema. `values_schema_json` gains a per-property marker and
the server derives two projections from it by partitioning the root's
`properties` and `required`:

```yaml
properties:
  host:                              # unmarked -> chart value
    type: string
  ADMIN_TOKEN:
    type: string
    x-caelus-target: runtime         # -> environment variable
    x-caelus-sensitive: true         # -> write-only
```

`x-caelus-target` defaults to `chart`, so every existing catalog schema keeps
working with no edit. `x-caelus-vars-additional: true` at the root opens the
vars projection to undeclared keys — `custom` is its only expected user, since
it runs tenant-supplied code and cannot enumerate that code's environment.

Runtime markers are legal only on a **top-level scalar** property whose name
matches `^[A-Za-z_][A-Za-z0-9_]{0,63}$` and is not reserved (`CAELUS_`, `AWS_`,
`S3_`, `RAILPACK_`, `BUCKET_NAME`, `PORT`). The property name *is* the
environment variable name; nothing flattens or renames it. Bad markers are
rejected at template creation and at catalog load, so they fail in front of
their author rather than at some tenant's next deployment.

### Write-only, and what that costs

A var marked sensitive is **never readable again through any endpoint, by
anyone, including an administrator**. Reads omit the `value` field entirely —
not a mask.

Omission gives a third state and the rule that follows from it: **an absent
`value` on write means "leave unchanged"**, which is what makes
`freepod var list --json` output safely writable.

Every value is encrypted at rest, sensitive or not — one column, one code path,
no per-row branch on where the plaintext lives. Each row records the
*fingerprint* of the key that encrypted it (`services/var_crypto.py`).

The API and the reconcile worker both refuse to start when their keyring cannot
cover what is stored. See `tf/README.md` § Deployment var encryption keyring
for the two-phase procedure for introducing a key.

### How a var reaches a pod

```
_reconcile_apply
    ensure_namespace
    ensure_tenant_isolation
    ensure_object_storage
    ensure_vars_secret       ← the applied release's snapshot, decrypted
    helm_upgrade_install     ← values carry only the Secret's name
    reap_vars_secrets        ← superseded releases' Secrets, on success only
```

The Secret is named per **release** (`{deployment}-vars-{number}`). A shared
Secret updated in place would be written before Helm runs and would not be
rolled back when Helm fails, leaving the reverted pod spec paired with the
failed release's values — harmless until the next pod starts, then silently
wrong. Per-release naming makes a rollback land on a Secret this apply never
touched, and makes a var-only change alter the pod template so the rollout
restarts the pod. Superseded Secrets are deleted after a *successful* apply
only (`_reap_vars_secrets`), scoped by the deployment's instance label; a
failure there is logged, since litter is cheaper than a wrong pod.

Only `caelus.vars.secretName` is projected into the values, for the same reason
the object-storage credential is not: merged values are logged in full at INFO
and persisted by Helm into a tenant-namespace object. Every row is decrypted
before anything is written, so a keyring that cannot read one row leaves the
previous Secret untouched — a pod holding some of its variables is worse than
one that does not start.

An empty snapshot produces no Secret and no values block at all, so a chart
that requires vars fails visibly instead of rendering an empty `envFrom`. In
`products/custom/chart` the vars Secret is the **first** `envFrom` source with
platform sources after it, because a later source overrides an earlier one and
an explicit `env` entry beats them all — a var named like a platform credential
cannot displace it.

## API and CLI Parity

Parity is achieved by sharing service functions, not by duplicating logic.

REST routes:
- Products: `POST/GET /products`, `GET/PUT/DELETE /products/{product_id}`
- Templates: `POST/GET /products/{product_id}/templates`,
  `GET/DELETE /products/{product_id}/templates/{template_id}`
- Users: `POST/GET /users`, `GET/DELETE /users/{user_id}`
- Deployments: `POST/GET /users/{user_id}/deployments`,
  `GET/PUT/DELETE /users/{user_id}/deployments/{deployment_id}`
- Admin: `GET /deployments` (admin-only, all non-deleted deployments)
- Artifacts: `POST /artifacts` (mint an upload slot)
- Releases: `GET /users/{user_id}/deployments/{deployment_id}/releases`,
  `GET /users/{user_id}/deployments/{deployment_id}/releases/{number}`
  (addressed by the per-deployment release **number**, not the uuid; the
  single-release read and the listing both inline the build)
- Builds: `POST/GET /users/{user_id}/builds`,
  `GET /users/{user_id}/builds/{build_id}`,
  `GET /users/{user_id}/builds/{build_id}/log` (plain text, HTTP Range)
- SSH keys: `POST/GET /users/{user_id}/ssh-keys`,
  `GET/DELETE /users/{user_id}/ssh-keys/{fingerprint}` (addressed by the
  `SHA256:` fingerprint; see [Account SSH Keys](#account-ssh-keys))
- Database: `GET /users/{user_id}/deployments/{deployment_id}/database` (see
  [Reading a Deployment's Database Connection Details](#reading-a-deployments-database-connection-details);
  pooler host/port, database/role names, password, quota state and usage;
  password withheld from administrators — different rule from the SFTP
  endpoint, by design)

CLI equivalents (`caelus ...`):
- `create-user`, `list-users`, `get-user`, `delete-user`
- `create-product`, `list-products`, `get-product`, `update-product`, `delete-product`
- `create-template`, `list-templates`, `get-template`, `delete-template`
- `create-deployment`, `list-deployments`, `get-deployment`,
  `update-deployment`, `delete-deployment`
- `list-releases`, `get-release` (by per-deployment release number)
- `build list|show|log|submit` — `submit` performs all three upload phases
- `ssh-key list|add|rm`
- `reconcile` (CLI-only operational command to run one reconcile pass)
- `build-worker` (CLI-only; the build worker's process entry point)
- `catalog apply|curate|lint` (CLI-only; intentionally exempt from parity — see
  [Product Catalog](#product-catalog-curated-products))

Example:

```bash
caelus --help
caelus create-user alice@example.com
```

CLI output contract:
- Successful command output on stdout is YAML-encoded entity payloads (single
  object or list, mirroring REST JSON responses).
- Logs and errors are emitted on stderr.

**yq filtering tip**

The CLI prints YAML‑encoded entities to stdout. You can pipe that output through `yq` to extract only the fields you care about.
For example:

```bash
caelus list-deployments | yq -y '.[] | {id, domainname, status}'
id: 1
domainname: hello3.freepod.eu
status: deleted
---
id: 2
domainname: test3.example.com
status: deleting
```

This works for any `caelus` command that returns a YAML list or object.

## Account SSH Keys

An SSH public key is owned by a **user**, never by a deployment. A user's keys
apply to every deployment that user owns, including ones created after the key
was registered, and stop applying to deployments the user ceases to own.

**Nothing reads these keys yet.** SSH access still authenticates with the
per-deployment credentials the SFTP endpoint issues. This table is a store, not
yet a credential; the switch happens in a later change.

### The collection

| Method | Path | Who |
| --- | --- | --- |
| `GET` | `/api/users/{user_id}/ssh-keys` | owner or admin |
| `POST` | `/api/users/{user_id}/ssh-keys` | **owner only** |
| `GET` | `/api/users/{user_id}/ssh-keys/{fingerprint}` | owner or admin |
| `DELETE` | `/api/users/{user_id}/ssh-keys/{fingerprint}` | owner or admin |

Listing returns a plain array. A read carries the fingerprint, key type, size
in bits, label, the normalized public key body and the registration time. No
response ever contains private key material, because none is ever stored.

### Administrators may revoke, not grant

Reads and deletes follow the usual `require_self` rule, so an administrator can
revoke a compromised key during an incident. **Adding is restricted to the
owner even for administrators.** Installing a key on someone's account creates
a credential that authenticates *as that user*, which is impersonation rather
than administration, and is exactly what an attacker holding an admin session
would want.

### The fingerprint is the address, and it needs a path converter

Keys are addressed by their `SHA256:` fingerprint — the SHA256 digest of the
raw key blob, base64 without padding, byte-identical to `ssh-keygen -lf`. That
is what lets a client revoke the key it holds without a prior lookup, and
recognize a local key without transmitting key material.

The route is `/{fingerprint:path}`, the only path-converter route in the API,
and the reason is arithmetic: a fingerprint is unpadded base64, so roughly half
of all fingerprints contain a `/` and roughly half contain a `+`. Measured over
2000 random digests, 976 contained `/` and 971 contained `+`.

An ordinary path segment **404s** for those keys, because the ASGI server
percent-decodes the path before routing and a `str` path parameter cannot span
a `/`. A query parameter is worse: an unencoded `+` arrives decoded as a space,
so the server answers a confident "no such key" for a key that exists — a
silent mis-parse on the one operation that revokes a lost laptop. The path
converter also accepts the fingerprint whether an intermediary forwards the
separator encoded or decoded, so it does not depend on how Traefik and
oauth2-proxy normalize the path.

If you ever refactor that route back to an ordinary segment, the tests that
register and delete a key whose fingerprint contains `/` and `+` will fail
loudly rather than the endpoint failing for half of real users.

### What is accepted

Ed25519, ECDSA over NIST P-256/384/521, RSA of at least 2048 bits, and the
FIDO security-key variants of Ed25519 and ECDSA. `ssh-dss` is refused by
policy.

The key type is read out of the **key blob's own first string field**, not from
the text before it, and must match the declared prefix. This matters for the
security-key variants specifically: `cryptography`'s `load_ssh_public_key`
strips the `sk-*` wrapper and hands back a plain Ed25519 or EC key that
re-serializes with a *different blob*. Normalizing through the parser would
store something that can never authenticate, so the submitted blob is preserved
verbatim.

The parser also accepts a multi-line submission and silently returns only the
first key, so the "one key at a time" check runs **before** it.

The stored body is normalized to `<type> <blob>` with the comment stripped: the
comment has already been consumed as the default label, and keeping it twice
would let the two drift apart.

### Labels are optional

A label defaults from the key's trailing comment. When there is no comment and
none was supplied, the key is stored **without** a label and reads back as
`null`. The platform does not invent one — a generated string naming the
algorithm is not information about the key, and it denies each surface the
chance to decide how an unlabeled key should read. A key's identity is its
fingerprint, so an absent label costs nothing.

### Uniqueness is per user

One account may not hold the same key twice; two accounts may. Equality is on
the blob, so comment and whitespace differences are the same key. Global
uniqueness would add no protection — registering someone's public key on your
own account grants them nothing — while creating a cross-account oracle for
whether some other account holds a given key.

The unique index is on `(user_id, fingerprint)` rather than on the blob. The
guarantee is identical, since the fingerprint is a digest of that blob, and a
btree row tops out at 2704 bytes while an RSA-16384 line is 2772.

### Deletion

Immediate and permanent: the row is removed, not tombstoned, so no later
projection can mistake it for a live key. Deliberately **not** idempotent,
unlike deleting a var — deleting a fingerprint the account does not hold
answers `404`, because reporting success for a key that was never there would
tell someone they had revoked a laptop they had not.

Keys are removed with their owner by `ON DELETE CASCADE`: no key may outlive an
accountable holder, in any state.

### Errors carry a code

Six of this collection's rejections are all `400`, so the body carries a stable
`code` alongside `detail`:

| `code` | Status |
| --- | --- |
| `malformed_key` | 400 |
| `private_key_material` | 400 |
| `multiple_keys` | 400 |
| `unsupported_key_type` | 400 |
| `key_type_mismatch` | 400 |
| `key_too_short` | 400 |
| `duplicate_key` | 409 |

Branch on `code`, never on `detail` — the prose is free to be reworded. The
field comes from an optional `code` attribute on `CaelusException`, emitted by
`register_exception_handlers`, and is **omitted entirely** for any error that
does not set one, so every other endpoint's error body is unchanged.

## Product Catalog (Curated Products)

Products come in two kinds, and the difference is a single column, `curated`.

| | Non-curated (`curated = false`) | Curated (`curated = true`) |
|---|---|---|
| Authored in | The database, via admin UI or CLI | Git, in `products/catalog/<slug>.yaml` |
| Changed by | Editing directly | A pull request, applied on rollout |
| Editable via API/CLI/UI | Yes, as always | No — except `visibility` |
| Intended for | Products under development | Published products |

Non-curated is the staging stage: admin-only, tight iteration, exactly today's
behavior. Curated is the published stage: reviewed, with a real diff to approve,
and upgradable by an autonomous release-detection agent. Nothing changes for a
product until its catalog file exists and has been rolled out.

### The catalog file

One YAML file per published product, named `<slug>.yaml`, where the stem must
equal `product.slug`. Icons are committed as image files beside it so that an
icon change reviews as an image diff rather than as encoded text:

```yaml
# yaml-language-server: $schema=./catalog.schema.json
schema_version: 1
product:
  slug: immich
  name: Immich
  description: Your own photo hosting
  category: Photos
  replaces: Google Photos · iCloud Photos
  icon: icons/immich.png          # relative to the catalog directory
upstream:                          # release detection only; never applied
  source:
    type: github-release           # or docker-tag, helm-chart
    repo: immich-app/immich
  match: ^v(?P<version>\d+\.\d+\.\d+)$
  version_path: template.system_values.immich.controllers.main.containers.main.image.tag
template:
  chart_ref: oci://registry.home:80/helm/immich
  chart_version: 2.5.5
  system_values: { ... }           # applied verbatim; pins the app image tag
  values_schema: { ... }           # JSON Schema for the user values form
```

Notes:
- **`visibility` is not a catalog field and is rejected if present.** The
  catalog owns what a product *is*; the database owns whether it is *currently
  offered*. Withdrawing a product is often incident response and must not wait
  for a merge, build, and rollout.
- `system_values` and `values_schema` are written to the template row verbatim.
  There is no templating engine, so review is WYSIWYG.
- `upstream.match` must compile and define a `version` capture group. It is
  consumed only by release-detection tooling and never reaches the cluster.
- `catalog.schema.json` is **generated** from the Pydantic models in
  `app/services/catalog.py` and exists only for editor completion.
  `catalog lint` fails if it has drifted; regenerate with
  `caelus catalog lint --write-schema`.

### Commands

```bash
caelus catalog lint                 # validate files only; no database needed (CI)
caelus catalog apply [--dry-run]    # reconcile the catalog into the database
caelus catalog curate <slug|name>   # generate a catalog file from database state
```

These are operator and build tooling, not tenant-facing surface, so they are
CLI-only and exempt from the REST parity convention (`apply` is run by an init
container). The protections they rely on live in the service layer, so no parity
gap is introduced.

### Graduating a product (`catalog curate`)

The path from hand-tuned to published:

1. Build the product the usual way — create it, iterate on system values and the
   chart until it works. It stays non-curated and fully editable throughout.
2. `caelus catalog curate immich --dir products/catalog` writes the YAML and the
   icon from current database state. **This does not curate the product**: it
   only writes files. `curated` and `slug` are untouched.
3. Complete the emitted `upstream` block — release-detection metadata is not
   derivable from the database, so curate emits a placeholder.
4. Commit, review, merge.
5. The rollout's `catalog` init container applies it. The reconciler matches the
   existing template by spec equality, inserts nothing, and flips the product to
   `curated = true`.

Step 5 being a verified no-op is the point: `catalog curate` round-trips
exactly, so a product's first pull request changes no template rows. Confirm
with `caelus catalog apply --dry-run`, which reports the plan and writes
nothing — expect `product-adopted` and no `template-inserted`.

Releasing a product is the mirror image: **delete its catalog file**. There is
no `uncurate` command, because file presence is the sole carrier of curation and
two writers would deadlock. Uncuration is shallow — templates, canonical
`template_id`, `visibility`, and deployments are all left untouched — so
restoring a dropped file simply re-adopts the product by name.

### How reconciliation behaves

`CatalogReconciler` has exactly two verbs, **insert** and **repoint**:

- It matches a catalog file's template against existing rows by a hash over
  `chart_ref`, `chart_version`, `chart_digest`, `system_values_json`, and
  `values_schema_json`, computed at read time with sorted keys. Key order in the
  YAML is irrelevant, and matching ignores how a row was created — that is what
  lets it recognize the hand-made template a file was generated from.
- On no match it inserts a new row (stamped with `GIT_COMMIT`) and repoints
  `product.template_id`. It **never** updates a template's spec fields and
  **never** soft-deletes one, so the table is an append-only ledger and running
  deployments keep resolving their `applied_template_id`.
- It resolves a product by `slug`, else adopts a non-curated product whose name
  matches case-insensitively, else creates one. Created products start
  `visibility = admin`, so merging a catalog change can never by itself put a
  product in front of end users. Visibility is never written again.
- Every product-selecting query filters `curated = true`. Non-curated products
  are provably untouched by a run.
- A catalog directory that does not exist or cannot be read is an **error**, not
  an empty desired state — otherwise a mistyped path would uncurate everything
  at once. An *empty* directory is valid and simply means nothing is
  catalog-managed.
- The whole run is one transaction under a Postgres advisory lock, so concurrent
  init containers cannot double-insert.

### Break-glass: `--force`

Curated products reject writes through the REST API, the CLI, and the admin UI
alike, because the guard lives in `app/services/products.py` and `templates.py`
rather than in the UI. The error names the catalog file to edit instead.

For urgent intervention, modifications accept an override — `?force=true` on the
REST endpoints (a query parameter, never a body field, since the delete
endpoints carry no body and product update is multipart) and `--force` on
`update-product`, `create-template`:

```bash
caelus update-product 2 --description "hotfix" --force
```

Every forced write is logged at WARNING with the acting user and product slug.
A template created this way leaves `catalog_commit` **null**, which is what makes
the drift visible: hand-made rows stay distinguishable from catalog-produced
history. The drift is also **self-healing** — the next rollout re-applies the
catalog and repoints `product.template_id` back to the template matching the
file, with no manual cleanup.

**Deletion is never forceable.** Deleting a curated product or one of its
templates is refused even with `--force`, because the override cannot achieve
what the operator intends: the reconciler resolves products by slug among
non-deleted rows, so a force-deleted product is not found, is not adopted, and
is recreated under a new id on the next rollout — while existing deployments go
on referencing templates belonging to the old row. A force-deleted template is
likewise reinserted whenever its spec still matches. The supported path is to
remove the catalog file, let the rollout release the product, then delete it
normally.

### Rollout

`products/catalog/` is baked into the API image (the image builds from the
repository root for exactly this reason) and applied by a `catalog` init
container that runs after `migrate`. This means no cluster credentials in CI and
no runtime git access, and it makes catalog-versus-code skew structurally
impossible. A malformed catalog exits non-zero, the pod never becomes ready, and
the previous ReplicaSet keeps serving — rollback for free.

> The master image build must never gain `paths:` filters. A commit touching
> only `products/catalog/` still needs an image build, or the merged change
> would never roll out.

## Product Icon and Static File Serving

### Static File Endpoint
- `GET /api/static/{path}` serves files from `STATIC_PATH` (configurable via `STATIC_PATH` env var, defaults to `./static`).
- Path traversal outside `STATIC_PATH` is blocked.
- Responses include `ETag` headers and support `If-None-Match` for `304 Not Modified`.
- Public access (no auth required).

### Product Icon Workflow
- **Create with icon**: `POST /api/products` accepts multipart form with:
  - `payload`: JSON object with product data (`name`, `description`, `template_id`)
  - `icon`: optional image file
- Atomic create: if icon processing fails, no product is persisted.
- Icon processing: decode, normalize orientation, center-crop to square, downscale to max 256x256, output PNG.
- Icon size limit: 10MB max.
- Resolution limit: 2048x2048 max source dimensions.
- Icon files are immutable and content-addressed: uploads are stored as content-hash files, and existing files remain.

### Icon Endpoints
- `PUT /api/products/{product_id}/icon`: Upload/replace icon for existing product.
- `GET /api/products/{product_id}/icon`: Returns `302` redirect to `/api/static/{rel_icon_path}` or `404` if no icon.

### Configuration
- `STATIC_PATH`: Root directory for static files (default: `./static` in dev, `/var/static` in production).
- Static files are served at `/api/static`.

## Core Data Model

### User

- Identity: `email` (unique among non-deleted users).
- Soft deletion: `deleted_at`.
- Role: `is_admin` exists in schema (policy hooks for future use).

### Product

- Represents an application family (e.g. Nextcloud).
- Fields: `name` (active-unique), `description`, optional canonical `template_id`, optional `icon_url`.
- `visibility` (`public` | `admin`) controls whether the product appears in the
  end-user product list. Admins always see every non-deleted product. New
  products default to `admin`, so onboarding is never visible before it is ready.
- `slug` (active-unique, nullable) and `curated` join the row to its catalog
  file. Both are written **only** by the reconciler — see
  [Product Catalog](#product-catalog-curated-products).
- Owns many template versions.
- Icon support: Products can have an icon uploaded. The icon is stored as an immutable file in `STATIC_PATH/icons/` with a content-hash filename. The API exposes `icon_url` (absolute path like `/api/static/icons/<sha1>.png`) in read responses but does not expose the internal `rel_icon_path` field.

### ProductTemplateVersion

- Scoped to one product.
- Chart identity: `chart_ref`, `chart_version`, optional immutable `chart_digest`.
- Values contract includes `system_values_json`.
- Values contract includes `values_schema_json`.
- `catalog_commit` records the git commit whose catalog inserted the row. Audit
  metadata only: never read by application logic, never part of template
  matching, and null for hand-authored rows.
- Soft deletion via `deleted_at`.

### Deployment

- Scoped to one user.
- Points to desired template (`desired_template_id`) and last applied template
  (`applied_template_id`).
- Stable runtime identity: `name` (Helm release name, max 27 chars) and
  `namespace` (K8s namespace, max 30 chars), both DNS-label-safe.
- User values are stored in `user_values_json`.
- Tracks workflow metadata: `status`, `generation`, `last_error`,
  `last_reconcile_at`, `deleted_at`.
- Names two releases: `desired_release_id` (**NOT NULL**) and
  `applied_release_id` (nullable). See DeploymentRelease.

### DeploymentRelease

The record of **one rollout**. Created by the request that asks for it — `POST`
and `PUT /deployments`, in the same transaction as the deployment write — and
completed later by the reconciler that applies it. **The reconciler creates no
releases**; it reads `deployment.desired_release_id`, applies it, records the
outcome, and on success sets `deployment.applied_release_id`.

- `id` is a `uuid4`, generated before anything exists in the cluster to carry
  it, and is the value stamped on the pod as `caelus.dev/release-id`. That is
  why it must be unguessable.
- `number` is a per-deployment integer from 1, the handle presented to and
  accepted from users, and the ordering key in preference to timestamps.
- `build_id` is nullable and routinely null — builds exist only for products
  deploying tenant-supplied code. Validated for **ownership only**: a named
  build must belong to the caller. Nothing is checked against the deployment's
  values, because `image` is one chart's value rather than a platform concept.
- `values_json` snapshots the **user** values, not the merged values.

> **No column is ever revised, and there is no `status` column.** The request
> writes identity and intent; the reconciler writes outcome (`started_at`,
> `ended_at`, `error`, `helm_revision`). `started_at` is write-if-null, so a
> lease reclaim after a worker died mid-Helm records when work *first* began —
> how many attempts there were is `deployment_reconcile_job.attempt`.
>
> **Do not add a status column.** It would need a transition written when
> something *else* changes — notably `superseded → live` when an atomic
> rollback restores an earlier release — by code that is not watching. Status
> derives instead:
>
> | Condition                             | Status     |
> |---------------------------------------|------------|
> | `started_at IS NULL`                  | queued (including awaiting payment) |
> | started, not ended                    | in flight, or abandoned past the job lease |
> | ended with `error`                    | failed     |
> | ended without `error`                 | succeeded  |
>
> **Liveness is the opposite case and *is* stored.** `applied_release_id` is
> written by the reconciler in the same transaction as `deployment.status`,
> recording an action it just completed rather than a system it observes. On
> failure it is left untouched, which is *correct* rather than a missed update:
> `--atomic` has already restored the release it still names. It costs one
> column and no subquery, where deriving liveness would cost a query per row on
> a listing.

The two tables reference each other, so both foreign keys on `deployment` are
`DEFERRABLE INITIALLY DEFERRED` and declared with `use_alter`. Both primary
keys are Python-generated `uuid4`, so the deployment is inserted already naming
a release that does not exist yet, the release second, and the check happens at
COMMIT. `tests/test_deployment_release_ledger.py` exercises that ordering
directly, including the commit-time rejection of a dangling
`desired_release_id`.

### DeploymentReconcileJob

- Queue item for reconciliation work.
- Lifecycle: `queued -> running -> done|failed`.
- Reasons: `create|update|delete`.
- Unique partial index prevents multiple open jobs (`queued` or `running`) per
  deployment.
- `locked_by`/`locked_at` are the worker lease; `attempt` counts how often the
  job was reclaimed after that lease expired (see Reconcile Queue Semantics).

## Critical Invariants

- Active user emails are unique (`deleted_at IS NULL` scoped uniqueness).
- Active product names are unique (`deleted_at IS NULL` scoped uniqueness).
- Active product slugs are unique (`deleted_at IS NULL` scoped uniqueness).
- `product.slug` and `product.curated` are written only by `CatalogReconciler`;
  no REST endpoint, CLI command, or UI action sets them, including under
  `--force`. Catalog file presence is the single source of truth for curation.
- `product_template_version` is append-only with respect to the reconciler: it
  inserts and repoints, never updates spec fields and never soft-deletes.
- Active template `(chart_ref, chart_version, product_id)` combinations are
  unique.
- Only one open reconcile job (`queued` or `running`) may exist per deployment.
- Domain names are unique for deployments that are not in `deleted` status.
- Deployment identity requires DNS-safe `name` (max 27 chars) and `namespace`
  (max 30 chars). Active deployments have a unique `(namespace, name)` pair.
- Kubernetes namespace is `deployment.namespace`; Helm release name is
  `deployment.name`.

## Deployment Lifecycle and State Transitions

### Create

- `create_deployment()` validates user + template + user values.
- REST/CLI create payloads do not accept top-level `domainname`.
- Service derives persisted `domainname` from `user_values_json` by recursively
  scanning template `values_schema_json` for the first field whose `title`
  matches `domainname` case-insensitively.
- Generates `name` from product name + random suffix, and `namespace` from
  user email + random suffix.
- Persists deployment with status `provisioning`.
- Enqueues job with reason `create`.

### Update (Upgrade)

- Only allows forward template changes (`desired_template_id` must increase).
- Allowed from `ready` or `error` status (not during `provisioning` or `deleting`).
- Requires same product lineage between current and target template.
- REST/CLI update inputs do not accept top-level `domainname`.
- Service re-derives persisted `domainname` from effective
  `user_values_json` using the same recursive schema-title rule as create.
- Revalidates values against target schema.
- Sets status `provisioning`, increments `generation`, enqueues `update` job.

### Delete

- Marks status `deleting`, sets `deleted_at`, increments `generation`.
- Enqueues `delete` job.
- Repeated delete is idempotent if already `deleting`/`deleted`.
- `GET` on a deleted deployment returns `404`.

### Reconcile Outcome

- Apply path: ensure namespace, `helm upgrade --install` -> status `ready` and
  `applied_template_id = desired_template_id`.
- Delete path: `helm uninstall`, delete namespace -> status `deleted`.
- Failure path: catches exception, stores status `error` and `last_error`.

## Reconcile Queue Semantics

- Enqueue runs inside same transaction as deployment mutation.
- Claiming uses `FOR UPDATE SKIP LOCKED`.
- Guarantees no double claim for the same job under parallel workers, covered
  by `test_claim_next_job_never_double_claims_under_parallel_workers` (sixteen
  threads against eight jobs).
- A job is claimable when it is `queued` and due (`run_after <= now`), **or**
  when it is still `running` but its lease has expired.

### Lease expiry

A worker that dies mid-reconcile (pod restart, OOM kill, node eviction) leaves
its job at `running` with `locked_by` naming a process that never returns.
Without a lease that job is never retried and its deployment stays in
`provisioning`/`deleting` forever, holding its hostname against re-creation.

- Lease length: `CAELUS_RECONCILE_JOB_LEASE_SECONDS`, default `600` (10 min).
  Never set this below `HELM_TIMEOUT_SEC` (300s): a healthy worker may
  legitimately spend the whole Helm budget inside one reconcile, and a shorter
  lease would let a second worker steal a live job.
- Reclaims bump `attempt` and log at WARNING with the previous `locked_by` /
  `locked_at`; grep worker logs for `Reclaimed expired reconcile job lease`.
- Reclaims are not capped: only a completed reconcile can move a deployment out
  of `provisioning`/`deleting`, so retries continue (once per lease interval)
  until the job reaches `done` or `failed`.
- `mark_job_done` / `mark_job_failed` take an optional `worker_id`; when given,
  the write is conditional on the job still being leased to that worker, so a
  wedged worker that wakes up late cannot overwrite the new owner's result.

## Builds (Project Archive → Container Image)

Turns a user's project directory into a digest-pinned container image in the
internal registry. Builds belong to a **user**, never to a deployment: most
products build nothing, a single deployment may consume several images, and
**nothing here triggers a rollout** — the client takes a successful build's
`image` and submits it to the deployment update endpoint itself.

### The three-phase upload

Uploads never pass through the API; the bytes go straight to object storage.

```
1. POST /api/artifacts                → { artifact_id, url, fields, max_bytes, expires_in }
2. POST {url}  (multipart/form-data)  → every entry of `fields` first, file part LAST
3. POST /api/users/{uid}/builds       → { artifact_id }; 201 (or 200 for a retry)
```

The endpoint takes **no request body**. The object key is composed server-side
from the authenticated caller and a generated identifier
(`artifacts/{user_id}/{artifact_id}.tgz`), so an artifact is bound to its
uploader by construction — there is no key, path, or URL a client could supply,
and therefore no ownership check to bypass.

Phase 2 is a presigned **POST**, not a PUT, because only POST carries a policy
document and only a policy can express `content-length-range`. That is what
puts the size cap at the object store rather than in a client that may ignore
it. Send the form fields verbatim, file part last.

Phase 3 confirms the artifact is actually present before creating the build, so
an upload that silently failed surfaces immediately rather than minutes later
as a fetch error inside a build container. Creating a build for an artifact
whose build is still `queued`/`running` returns that build with **200** instead
of creating a second one; once every build for the artifact is terminal, a
repeat creates a new one — so a transient failure can be rebuilt without
re-uploading.

`caelus build submit <dir>` does all three phases in one command.

### State machine

`queued → running → succeeded | failed`. `canceled` is reserved and
unreachable. Terminal states are final and a failed build is **never retried
automatically** — recovery is creating a new build.

`image` is null until `succeeded`, then carries the flat string
`{user_id}@sha256:<64 hex>` — a real image reference **with the registry host
stripped off**. That value is byte-identical to what the client submits as the
`custom` product's `image` user value; withholding the host is what stops a
tenant pointing a deployment at an arbitrary registry, and the chart asserts
the `{user_id}` half matches the deployment's owner.

### The log endpoint

`GET /api/users/{uid}/builds/{id}/log` serves `text/plain; charset=utf-8` and
supports HTTP
Range, so a client polls for output appended since its last read:

```bash
curl -H "Range: bytes=${read_so_far}-" .../log   # 206 + Content-Range: bytes N-M/*
```

- The total length is reported as **unknown** (`/*`) while the build runs — it
  is still growing, so asserting a total would be a lie.
- Polling at the current end returns an **empty 206**, not a 416. That is
  deliberately outside RFC 7233: for a growing resource, "nothing new yet" is
  the steady state of a polling loop, not an error. `Content-Range` is omitted
  there, since the grammar cannot express a zero-length range.
- **Every** response carries `X-Build-Status`, so a client learns the build has
  finished without a second request. Stop polling on a terminal status.
- Offsets are **bytes, not characters**. The log is stored as `bytea` and served
  unmodified: container output is a tenant-controlled byte stream that may
  contain invalid UTF-8 or NUL bytes (Postgres `text` cannot even store the
  latter). Concatenate chunks and decode the result, rather than decoding each
  chunk on its own.
- Output is capped at `CAELUS_BUILD_LOG_MAX_BYTES` (10 MiB) and ends with an
  explicit truncation marker; truncation never affects the build's own outcome.

### The layer cache

BuildKit runs inside each build's pod and dies with it, so no local cache
survives to the next build. Each build instead imports from and exports to a
registry cache at `{registry}/cache/{builds_namespace}/{user_id}:latest` —
**one repository per owner per environment, never shared**, since a build cache
two tenants can reach is a way to hand one tenant's build a step result chosen
by another. The builds namespace is in the path because dev and prod keep
separate databases behind one registry, so their user id sequences are
independent and the owner alone does not identify a tenant; the worker passes
it as `CAELUS_CACHE_SCOPE`. The builds NetworkPolicy already reaches the
registry, so nothing new is opened up for it.

An absent cache is the normal first build for an owner and is not an error, and
a failed export never fails a build (the image is pushed before the cache is
written). Both properties mean the cache repository can be deleted at any time
to force a cold rebuild. The cost is registry disk, on the registry host rather
than the cluster node, and it is currently unbounded per owner. See
`products/custom/builder/README.md` for the full reasoning and the failure
modes worth knowing.

### The ghcr.io mirror

The builder configures its ephemeral daemon to treat the internal
registry as a **mirror for ghcr.io**, and `scripts/mirror-railpack-images.sh`
copies those images in.

See `products/custom/builder/README.md`.

### The build worker

A separate process (`caelus build-worker`, deployed as `caelus-build-worker`)
running one repeating, **non-blocking** pass:

1. advance every `running` build — mirror its Job's output into the log, adopt
   its outcome if the Job finished, and apply the deadline backstop;
2. claim queued builds while below `CAELUS_BUILD_MAX_IN_FLIGHT`, creating one
   Kubernetes Job per build.

Advancing happens before claiming, so a slot freed this pass is reused
immediately. Nothing follows a log stream: blocking for the duration of a build
would make recovery a second writer racing the follower, and at an in-flight
limit of 1 a single long build would suspend recovery entirely.

Concurrency is `CAELUS_BUILD_MAX_IN_FLIGHT`, **not** a process or replica
count — one pass advances any number of running builds, so a second replica
would only contend.

Recovery is not a separate step: visiting every running build on every pass
*is* the recovery. A worker that dies mid-build strands nothing — the next pass
adopts a Job that has since succeeded rather than failing it. The log is a
**mirror** of the Job's current output, re-read in full each pass, which needs
no offset bookkeeping and self-heals after a gap; a read that comes back
shorter than what is stored is discarded, since a container runtime may rotate
output away and clients have already read the longer version.

The build container holds **no database, Kubernetes, or long-lived registry
credential**. Its only credential is an expiring presigned GET for one object,
and it reports its result through the pod's termination message
(`{"image": "..."}`), which the worker parses. A failure reports `{"error": ...}`
with no `image` key, so it can never be mistaken for a success — and tenant
build output cannot forge it, because it comes from pod status rather than the
log.

Deadlines are enforced by Kubernetes (`activeDeadlineSeconds`), because
Kubernetes is the one participant guaranteed to be present. The worker only
intervenes past a grace period, as a backstop for Kubernetes having failed.

### Node prerequisites (not captured by Terraform)

Two node-level settings are required for builds to work at all, and **a rebuilt
node fails at two separate points with unrelated-looking errors**:

1. `/etc/sysctl.d/99-buildkit-userns.conf` —
   `kernel.apparmor_restrict_unprivileged_userns=0`. Ubuntu 24.04 ships this at
   `1`, which transitions any unconfined process calling `userns_create` into a
   restrictive AppArmor profile that then denies `CAP_SYS_ADMIN` in the new
   namespace, so rootless BuildKit fails on `/proc/self/uid_map`. Setting the
   pod's `appArmorProfile: Unconfined` does **not** help — the transition fires
   *from* the unconfined profile.
2. `/etc/rancher/k3s/registries.yaml` — `insecure_skip_verify` for the internal
   registry, whose certificate is valid for a different name. Scope it to that
   one host; a `"*"` entry would strip verification from ghcr.io and docker.io,
   where every real image comes from. Requires `systemctl restart k3s`, and
   lands in `/var/lib/rancher/k3s/agent/etc/containerd/certs.d/<host>/hosts.toml`,
   **not** `config.toml`.

The build Job additionally sets both `seccompProfile: Unconfined` and
`appArmorProfile: Unconfined`, which cover the *container* profile blocking
`mount`/`unshare` — a separate mechanism from the host sysctl above, and why
the builds namespace runs under Pod Security `privileged`. See
`products/custom/builder/README.md` for the builder image itself.

## Provisioning Boundary

`app/provisioner.py` is the boundary to external systems.

- `KubeAdapter`: namespace existence/create/delete via `kubectl`.
- `HelmAdapter`: install/upgrade/uninstall/status via `helm`.
- `Provisioner`: facade used by reconciler.

Important:
- Command execution is centralized in `app/proc.py`.
- Adapter errors are normalized into `AdapterCommandError` with truncated detail.

## Values and Schema Rules

User-editable values are intentionally scoped under `values.user.*`.

Rules enforced by `app/services/template_values.py`:
- `user_values_json` must be an object.
- If user values are provided, template schema must define `properties.user`.
- Final Helm values are merged as `defaults` + `{ "user": user_values }` +
  `system_overrides`.
- Final merged object is validated against full template schema.

## Error Handling

Domain exceptions live in `app/services/errors.py`:
- `IntegrityException` -> HTTP 409
- `DeploymentInProgressException` -> HTTP 409
- `NotFoundException` -> HTTP 404

FastAPI exception mapping is registered in `app/api/utils.py`.
CLI catches domain exceptions and exits with code `1`.

## Logging

- Shared logging setup: `app/logging_config.py`.
- Configured at API and CLI entrypoints.
- Colorized levels on TTY (disabled if `NO_COLOR` is set).
- Level control via `CAELUS_LOG_LEVEL` (default `INFO`).
- High-signal logs cover external commands and provisioning actions.
- High-signal logs cover reconcile start/fail/finish.
- High-signal logs cover job queue operations.
- High-signal logs cover deployment mutation side effects.

## Local Development

From `api/`:

- Install deps: `uv sync`
- Run API: `uv run python3 app/main.py`
- Run CLI help: `uv run caelus --help`
- Run tests: `uv run pytest`

Docs UI:
- `GET /` redirects to `/docs`.

## Database and Migrations

- Runtime DB URL: `CAELUS_DATABASE_URL`. Postgres is the only supported
  database — in production, in dev, and under test.
- Schema comes from Alembic, always. There is no `create_all` helper: the test
  suite migrates its database with the real chain, so drift between the models
  and the migrations fails the suite instead of hiding.
- Alembic config: `alembic.ini`, scripts in `alembic/versions/`.

Migration commands:
- New migration: `alembic revision --autogenerate -m "message"`
- Upgrade DB: `alembic upgrade head`

## Testing Strategy

### Running the suite

The suite runs against a real PostgreSQL database. Inside the devcontainer
everything is already in place — `docker-compose.yml` sets
`CAELUS_TEST_DATABASE_URL` and the compose `postgres` service is running, so
`uv run --no-sync pytest` is all it takes.

Outside the devcontainer, start a Postgres and point the suite at it:

```bash
docker compose up -d postgres
export CAELUS_TEST_DATABASE_URL=postgresql+psycopg://caelus:caelus@localhost:5432/caelus_test
cd api && uv run --no-sync pytest
```

The connecting user must hold `CREATEDB` (or be a superuser): `conftest.py`
creates the test database itself if it is missing, migrates it with
`alembic upgrade head`, and resets it between tests — which also needs
`session_replication_role`, a superuser setting. The compose image's `caelus`
user is a superuser, so dev and CI are both covered.

There is no in-memory or SQLite mode. A run without a reachable Postgres fails
with an explanatory error rather than skipping tests or reporting a false pass.
The test database is separate from the dev `caelus` database and is wiped
constantly, so never point the variable at a database you care about.

Test execution is serial: one shared test database, one cleaner. `pytest-xdist`
is not supported as-is.

### What lives where

- `tests/test_api.py`: REST behavior and validation.
- `tests/test_cli.py`: CLI parity and error handling.
- `tests/test_deployments.py`: deployment mutation semantics.
- `tests/test_reconcile_service.py`: reconcile state transitions.
- `tests/test_jobs_service.py`: queue/claim/mark semantics, including
  concurrent claiming under sixteen parallel workers.
- `tests/test_deployment_release_ledger.py`: the deferred foreign keys between
  `deployment` and `deployment_release`, checked at COMMIT.
- `tests/test_schema_drift.py`: the migration chain and the models must
  describe the same schema.
- `tests/test_platform_adapters.py`: Kubernetes/Helm adapter behavior.

## Conventions for Contributors

- Keep API + CLI features in parity.
- Put business logic in `app/services/`; keep facades thin.
- Add/adjust tests for any behavior change.
- Keep ownership scopes explicit in routes and queries.
- Prefer stable domain errors over ad hoc exceptions.
- Update migrations when schema changes.

## Known Gaps and Current TODOs

- Namespace lifecycle is still exposed on `Provisioner`; intended direction is to
  make install/uninstall manage namespaces transparently.
- API create-deployment route has a TODO note to tighten product/template scope
  validation at facade level (service already validates template existence).

## First 30 Minutes for a New Agent

1. Read `app/models.py` to understand entities and constraints.
2. Read `app/services/deployments.py`, `jobs.py`, `reconcile.py` in that order.
3. Skim `app/provisioner.py` and `app/proc.py` for external-system behavior.
4. Run `pytest` and inspect failing tests if any.
5. For feature work, implement in services first, then expose in both API and CLI.
