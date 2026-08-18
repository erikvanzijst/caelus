# freepod client — development notes

Everything about maintaining `cli/`: the invariants, the contracts with the
platform, and the reasoning behind the parts that look odd.

`README.md` is a different document with a different audience. It ships to PyPI
as the package's landing page and is written for a developer deploying their own
project, so it stays short and carries no platform internals. **New detail
belongs here, not there.** `README.md` changes only when the end-user surface
does.

The *behavioral contract* is specified in `openspec/specs/cli-*`:
`cli-authentication`, `cli-build-history`, `cli-build-submission`, `cli-delete`,
`cli-deploy`, `cli-distribution`, `cli-environments`, `cli-init`,
`cli-project-archive`, `cli-project-file`, `cli-terms-acceptance`. Those say
what must be true. This file says how it is
arranged and why, and carries the operational detail specs do not.

The original design discussion, with the numbered decisions the source comments
cite (D2, D4, D6, D10, D14, …), is in
`openspec/changes/archive/2026-08-15-add-freepod-cli/design.md`.

## Working in this package

```bash
cd cli
uv sync
uv run pytest          # the full suite
uv run freepod --help
```

Four rules hold the package's shape. Each is pinned by a test in
`tests/test_package.py`, so breaking one fails CI rather than shipping.

1. **Nothing imports the API server.** The client talks to a deployed platform
   over HTTP like any third-party consumer would. It shares no code with `api/`,
   not even constants.
2. **Runtime dependencies are exactly `click`, `httpx`, `pathspec`** — all pure
   Python, so installation needs no compiler and every wheel works everywhere.
3. **Python 3.9 is the floor.** The rest of the monorepo targets ≥3.11 and uses
   syntax 3.9 rejects outright; this package must not. CI runs the suite on 3.9
   and 3.13.
4. **Every error class carries its exit code** (`__init__.py`), so the exit-code
   table is a property of the exception hierarchy rather than a `main()` that
   has to remember.

A fifth rule is not testable but matters more than any of them: **the client
learns platform values at runtime rather than embedding them.** The archive size
limit comes from the upload slot, the current ToS version from the platform, the
required project values from the product template's schema, the wildcard domains
from the API. The client ships on its own cadence, so a constant baked in here
is wrong the first time the platform retunes it — and wrong in the direction
that locks users out until they upgrade.

## Module map

| Module        | Holds                                                                                       |
|---------------|---------------------------------------------------------------------------------------------|
| `__init__.py` | The error hierarchy and the exit codes. A leaf module, so the imports stay acyclic.         |
| `cli.py`      | The `click` entry point: flags, per-command wiring, and `main()`'s error→exit-code mapping. |
| `config.py`   | The two environments, the OAuth client ids, wait defaults, and on-disk paths.               |
| `auth.py`     | Both OAuth2 flows, the token cache, and `Session` — acquisition and renewal only.           |
| `api.py`      | The HTTP client, the 401/403 contract, and retries for safe methods.                        |
| `project.py`  | `.freepod.json`: load, save, project-root discovery.                                        |
| `values.py`   | Schema-driven prompting and hostname normalization.                                         |
| `archive.py`  | Packing the working tree: ignore layering, pruning, and the tar stream.                     |
| `build.py`    | Upload slot, presigned POST, build creation, and log streaming.                             |
| `deploy.py`   | The pipeline: preflight → pack → upload → build → release, plus rollout following.          |
| `delete.py`   | The teardown: confirming it, requesting it, and following it to gone.                       |
| `history.py`  | The build history: reading the account's builds and rendering the table.                    |
| `logs.py`     | `freepod log`: SSE parsing, the resume cursor, and reconnection.                            |
| `tos.py`      | Terms acceptance: the gate, the prompt, and recording an acceptance.                        |
| `skill.py`    | The packaged agent instructions: reading `assets/SKILL.md`, and where to install it.        |

## Environments

Two named environments and no caller-supplied base URL: an access token is bound
by its audience to one environment, so an arbitrary address would need the
issuer and client id to travel with it — a discovery endpoint the platform does
not publish (design D2).

| Name   | API base                 | OAuth client       | Notes                                      |
|--------|--------------------------|--------------------|--------------------------------------------|
| `prod` | `https://freepod.eu`     | `freepod-cli-prod` | The default.                               |
| `dev`  | `https://dev.freepod.eu` | `freepod-cli-dev`  | Gated on the `freepod-dev` Keycloak group. |

Selection is `--env`, then `FREEPOD_ENV`, then `prod`. Both clients are public:
PKCE proves client identity and no secret exists. The issuer is
`https://keycloak.freepod.eu/realms/freepod` for both.

The dev gate is `allowed_groups` in `tf/app/main.tf`, empty on prod. A non-member
holding a perfectly valid token gets a bare 401 on every request, which is why
the 401 message names the group.

Credentials are cached per environment, so `logout` discards only the selected
one.

## The command surface

| Command  | What it does                                                                   | Adds                                |
|----------|--------------------------------------------------------------------------------|-------------------------------------|
| `login`  | Authenticate and cache the credential. Offers the terms if outstanding.        | `--loopback`, `--device`, `--force` |
| `logout` | Discard the **local** credential for the selected environment.                 |                                     |
| `whoami` | Report who the cached credential authenticates as. Never opens a browser.      |                                     |
| `init`   | Write `.freepod.json` for the current directory. Reads only — creates nothing. | `--force`                           |
| `deploy` | Preflight → pack → upload → build → release.                                   | `--recreate`, `--no-gitignore`      |
| `delete` | Tear down the project's deployment, and follow the teardown to gone.           | `--yes/-y`, `--no-wait`             |
| `builds` | List the **account's** builds, marking the one this project runs.              | `--limit`, `--all`                  |
| `log`    | Stream the project deployment's application output.                            | `-f`, `-n`, `-r`, `-t`              |

Global: `--env`, `--verbose`, `--quiet`, `--timeout`, `--version`, `-h/--help`.
`--verbose` and `--quiet` together are a usage error.

> **A negative flag needs `is_flag=True` and an inverted variable, not
> `flag_value=False, default=True`.** That declaration resolves to `True` on
> click 8.1 (the Python 3.9 leg) and to `False` on 8.3+, so `--no-gitignore`
> was silently *on* for everyone on a current click — deploy packed everything
> `.gitignore` excludes. `pyproject.toml` asks only for `click>=8.0`, so both
> versions are live. `tests/test_cli.py` pins the resolved default of every
> negative flag rather than its spelling.

`--version` reports the *installed* distribution metadata rather than a literal,
so it only answers correctly for an installed package — which `uv run` arranges.

### Streams

Results go to **stdout**, everything else to **stderr**, so a piped stdout
carries only the result:

```bash
URL=$(freepod deploy)      # https://myapp.freepod.eu
```

`builds` follows the same rule: the table is the result and goes to stdout,
while the legend and the "showing N of M" note are diagnostics on stderr.
`delete` writes nothing to stdout at all — a deletion has no result to pipe.

The build log, the upload progress bar, and every status line are diagnostics.
`--quiet` silences all of it and leaves the result and any error; a quiet deploy
discards the build log through a sink rather than buffering it, so a large build
does not accumulate in memory purely to be thrown away.

Color is suppressed when stdout is not a terminal and whenever `NO_COLOR` is
set — `ctx.color = False` rather than leaving it to click, which would still
color a terminal that asked not to be.

`tests/test_surface.py` pins all of this.

### Exit codes

| Code | Meaning            |
|------|--------------------|
| 0    | success            |
| 1    | error              |
| 2    | usage error        |
| 3    | not authenticated  |
| 4    | the build failed   |
| 5    | the rollout failed |

`130` on interrupt. A **timeout is not a failure** and has no code of its own:
`--timeout` bounds how long the client waits, never what the platform does. When
it elapses the build or rollout is still running, uncanceled, and the message
says so. Re-running picks it back up — and for a build, re-uploading the same
archive re-attaches to the build already in flight rather than starting a second.

`--timeout` applies to whichever wait is in progress, so it means something
different per command: login 300s, build 1800s, rollout 600s by default.
`DEFAULT_HTTP_TIMEOUT` (30s) is a separate, per-request bound.

## Authentication

The flow is auto-detected, and the client always logs which one it picked and
why (`Using the device flow — running in a container (/.dockerenv present).`).
Override with `--loopback` or `--device`.

`Session` (`auth.py`) owns acquisition and renewal only. Interpreting the API's
responses is `api.py`'s job, which drives `refresh()` and `login()` from there.

### Loopback + PKCE — when a browser is reachable

Binds an ephemeral port on `127.0.0.1`, opens the browser to the authorization
endpoint with `redirect_uri=http://127.0.0.1:<port>/callback`, waits for the
redirect, verifies `state`, and exchanges the code with the `code_verifier`.

> **The callback path must be exactly `/callback`.** The registered redirect
> URIs are the port-less forms `http://127.0.0.1/callback` and
> `http://localhost/callback`. Keycloak relaxes *port* matching for loopback
> hosts (RFC 8252 §7.3) so any ephemeral port works, but the **path is matched
> exactly**, and `127.0.0.1` and `localhost` are distinct host strings. Any
> other path fails with `invalid redirect_uri`.

The listener binds `127.0.0.1` only, never `0.0.0.0`, stops as soon as the
callback arrives (or the wait elapses, so it cannot hang forever), and answers
`404` to anything that is not `/callback` — which keeps a browser's speculative
`/favicon.ico` fetch from consuming the one request it waits for.

### Device authorization grant — when there is no shared browser

For containers, SSH sessions, and CI. The client prints a URL and a short user
code; approval happens on whatever device has a browser, and nothing secret
transits the terminal.

> **Keycloak requires PKCE on the device endpoint too.** RFC 8628 has no
> redirect and therefore no PKCE, but these clients mandate PKCE and Keycloak
> enforces it here as well. The `code_challenge` and `code_challenge_method` go
> to the *device* endpoint, and the `code_verifier` goes with every poll.
> Omitting them fails with `invalid_request` / `Missing parameter:
> code_challenge_method`. This surprises most implementations.

Polling handles `authorization_pending`, `slow_down` (backs the interval off by
5s), `expired_token`, and `access_denied`. The device code lives 600 seconds.

**Why the code is printed even though Keycloak never asks for it.** RFC 8628
§3.3.1 says clients *MUST* display the `user_code` even when offering
`verification_uri_complete`, because the server is expected to echo it back and
ask the user to confirm it matches — an anti-phishing check (§5.4). **Keycloak
24 does not do that half.** It consumes the code from the query string and goes
straight to sign-in and consent, so the code appears nowhere on screen. Here the
code is therefore a *fallback*: if the long URL is mangled by terminal wrapping,
open `https://keycloak.freepod.eu/realms/freepod/device` and type it in.

`urn:ietf:wg:oauth:2.0:oob` (print-and-paste) is **not** an option — Keycloak
removed it before 24.0 and it is not registered on these clients.

### How "no browser" is detected

In order, first hit wins, all in `detect_browser()`:

1. `/.dockerenv` exists.
2. `docker`, `containerd`, `kubepods`, or `libpod` appears in `/proc/1/cgroup`.
3. On Linux, none of `DISPLAY`, `WAYLAND_DISPLAY`, `BROWSER` is set.
4. `webbrowser.get()` raises.

Any hit selects the device flow. A container is disqualifying even when a
browser binary is installed: the redirect would land on the *container's*
`127.0.0.1`, which the user's browser cannot reach.

### Tokens and storage

Scopes requested: `openid email profile offline_access`. Access tokens live
**300 seconds**; `offline_access` yields an offline refresh token (`typ:
Offline`) with no absolute expiry, valid as long as it is used at least once
every 30 days.

The refresh token is cached at `${XDG_CONFIG_HOME:-~/.config}/freepod/tokens.json`,
in a directory created `0700` — and re-`chmod`ed on every use, because `mkdir`
applies its mode only when it creates the directory and one earlier loose
creation would otherwise be inherited forever. Reading the cache must never
create anything.

`revokeRefreshToken` is false on this realm, so a refresh response may omit a
new refresh token; `Session.apply()` keeps the one it already holds in that
case.

Raw tokens are never printed. `--verbose` shows decoded *claims* (`aud`, `azp`,
`email`, `exp`, `groups`, …) — decoded for display only, never used to make a
trust decision. The edge is what verifies tokens.

**A token grants full account authority.** The API authorizes on user identity
alone and has no notion of OAuth scopes, so a token cannot be narrowed to
read-only or to a single deployment — it is equivalent to a browser session for
that user. Worth weighing before one goes into CI.

`freepod logout` discards only the **local** copy. Server-side revocation is
through the Keycloak account console (Applications → offline sessions), which
lists sessions issued to `freepod-cli-*`. Revoking stops further refresh; an
already-issued access token stays valid for up to its remaining 300 seconds.

## The API status-code contract

| Status                                 | Answered by | Client action                    |
|----------------------------------------|-------------|----------------------------------|
| 401                                    | edge        | stop and explain; do not re-auth |
| 403, non-JSON body                     | edge        | refresh once and retry           |
| 403, JSON `detail`                     | API         | stop — a permission error        |
| 404, `{"detail": "Not authenticated"}` | API         | report a platform condition      |

**This inverts the usual HTTP reading, deliberately.** `403` is the signal to
refresh or re-authenticate; `401` is not — on a 401 either no credential reached
the edge, or (on dev) a valid one belongs to a non-member of the gating group,
and re-authenticating would succeed and change nothing.

The two 403 rows are why the rule cannot simply be "403 means refresh": the API
issues its own 403s from `require_self` / `require_admin`, and an unbounded
refresh rule would refresh, fail, re-login, and loop on a request no credential
can satisfy. Hence **refresh at most once per request**, falling back to a full
login only if the refresh is rejected.

Which side answered is identified by **body shape**, not `Content-Type`: the
edge's refusals are a bare `http.Error` with a plain-text body and no reliable
content type, while every refusal the API itself issues is a FastAPI JSON
document carrying `detail`.

One asymmetry to keep in mind when adding a request: most reads the client
performs — products, plans, hostnames, domains — are on the edge's
`skip_auth_routes` list and are answered **anonymously** whatever credential
the request carried. They cannot return 401 or 403, so none of the machinery
above ever fires on them. That is exactly why `GET /api/me` must come first in
any command that needs a credential to be real (design D15).

Retries: safe methods only (`GET`, `HEAD`, `OPTIONS`), `MAX_ATTEMPTS = 3`
including the first, backoff starting at 0.5s and doubling. Anything that could
create or duplicate state fails to the caller instead.

## The deploy pipeline

`preflight → pack → upload → build → release`, in that order, so that everything
a cheap read can refuse is refused before a build is spent.

Preflight, cheapest and most fatal first:

1. The project file, and that it belongs to this environment.
2. `GET /api/me` — the first request that actually exercises the credential.
3. `GET /api/products` — the `custom` product and its canonical template.
4. The recorded deployment, so one deleted out of band is reported here rather
   than after a four-minute build.
5. On a create only: a free plan, then the terms.
6. Any newly required value, by asking.
7. The hostname, but only when it is new or changed.

Then the archive is packed, uploaded, and built, and only then is the deployment
created or updated. Building **before** the deployment is touched collapses a
first deploy to a single rollout and never shows a placeholder page (design D6).

Things worth knowing about each step:

- **Hostname checks are conditional** (design D14). `GET /api/hostnames/{fqdn}`
  runs without `exclude_deployment_id`, so re-checking a name we already hold
  reports `in_use` against ourselves — and for a custom domain it performs a
  live DNS lookup that is slow and transiently failure-prone. A value just
  prompted for was already checked inside the prompt loop.
- **Only free plans.** `select_free_plan` takes the first plan whose current
  template is priced at zero. Anything priced puts the deployment in `pending`
  behind a checkout page this client cannot drive. Plans are read in preflight
  rather than at release so an instance with no free plan refuses instantly —
  observed, not hypothetical: the `custom` product on dev published no plans.
- **User values are submitted whole.** The platform replaces stored values
  wholesale; omitting the key reuses what is stored, but a partial object does
  not merge, so sending `{"image": …}` alone fails on the missing required
  hostname (design D8).
- **The rollout is followed by generation, not by status.** `generation` is
  incremented atomically by the update and returned with it; a `ready` carrying
  an older generation belongs to the previous rollout, and reporting it would
  announce an address still serving the old image.
- **An update is refused unless the deployment is settled.** The guard is
  server-side and atomic (`WHERE status IN ('ready','error')`), so the client's
  `SETTLED_STATUSES` is a mirror of it, not the authority.
- **What preflight cannot catch** is a template that narrowed rather than grew:
  a tightened `pattern`, or a property removed under `additionalProperties:
  false`, passes every check and is refused at release, after the build is
  spent. That refusal is a 409 indistinguishable by status from "retry in a
  moment", which is why `describe_conflict()` reads the `detail` string and not
  the code, and why each mapping is pinned by a test. Anything unrecognized is
  quoted verbatim rather than guessed at — an invented message would be wrong
  exactly when it mattered most.

`--recreate` discards the recorded deployment pointer in memory and creates a
new deployment; the discard is not persisted until the creation succeeds, since
losing the old pointer to a failed create is strictly worse than holding a
pointer to something that may already be gone. The new pointer is written
**before** the rollout is awaited: a deployment that exists but is not recorded
is one the project can never address again.

## Deleting a deployment

`delete` is the only destructive thing this client does, and it addresses the
deployment recorded in `.freepod.json` and nothing else. A command that could
name an arbitrary deployment would be one whose worst typo is unrecoverable,
and the project file is the only place the client knows a deployment by anyway.

Four things about it are deliberate:

- **Nothing is deleted without an answer.** `--yes` is the only way to confirm
  in advance; without a terminal and without it, the command refuses rather
  than proceeding. An unattended run that deletes because nobody was there to
  object is the one behavior this must not have. `--quiet` silences the
  preamble, which is why the question itself names the deployment.
- **A decline is not a failure.** It returns 0 and says nothing was deleted.
  The user was asked and answered.
- **The teardown is followed to gone by default.** `DELETE` answers 204 and
  moves the deployment to `deleting`; the reconciler uninstalls the release and
  removes the namespace afterwards, and the **hostname stays claimed until that
  lands**. A `delete` that returned early would collide with itself on the next
  `deploy`. `--no-wait` opts out and says so.
- **The pointer is cleared the moment the platform accepts the deletion**, not
  once the teardown finishes. From that instant the deployment can never serve
  this project again — an update is refused for anything outside `ready`/`error`
  — so keeping the pointer would only make the next `deploy` fail on something
  the user already asked to be rid of. The user values stay: the hostname is
  intent, and re-deploying should re-claim the same name.

Three answers mean "already gone", and all three end the same way — the stale
pointer is cleared and nothing is deleted twice: a **404 on the read** (which
is what a fully torn-down deployment gives; the platform stops serving the
record rather than returning `deleted`), a read that comes back `deleting` or
`deleted`, and a **404 on the `DELETE`** itself.

A failed teardown lands in `error` with `last_error` set, exactly as a failed
rollout does, so the wait reads that as the failure it is instead of waiting
out the timeout reporting "still deleting". The 409 is the same
`DeploymentInProgressException` a release can hit, so it is read through
`deploy.describe_conflict` rather than a second copy of the same mapping.

## The build history

`builds` lists what `GET /api/builds` answers, which is **the account's**
builds and not a project's. The platform has no notion of a project at all — a
build is owned by a user, never by a deployment — so a project-scoped history
is not a thing the API can be asked for, and pretending otherwise would mean
inventing a filter with nothing behind it.

What makes the listing project-relevant instead is the marker: the build whose
image the current project's deployment is running is flagged `*`. That is the
only reason the deployment is read at all, and every way of not knowing answers
`None` rather than failing — no project file, one belonging to another
environment, no deployment recorded yet, or a deployment the platform no longer
has. The annotation is a convenience; the listing is the result.

Details worth keeping:

- **The platform's order is kept.** Most recent first is the endpoint's
  contract. Re-sorting would mean parsing every timestamp to reproduce an
  answer already given, and would reorder rows the moment one failed to parse.
- **`--limit` is a display bound, not a query one.** The endpoint has no
  pagination and returns everything; the note about what was hidden goes to
  stderr.
- **Timestamps arrive naive and are UTC by construction**, so a missing offset
  is read as UTC and rendered in the reader's own zone. Reading it as local
  would misreport every duration by the reader's offset. `Z` is handled by
  hand: `fromisoformat` only learned it in 3.11 and 3.9 is the floor.
- **Duration is measured from `started_at`**, not `created_at`. The wait for a
  worker is queueing, and counting it would report a five-second build as a
  five-minute one whenever the queue was busy.
- **Digests are abbreviated to twelve characters** with the truncation marked.
  A full reference is 75 characters of which 64 are a digest, which would make
  that column wider than every other one together. `--verbose` prints it whole.

## The project file

`.freepod.json`, written by `init`, meant to be committed:

```json
{
  "version": 1,
  "env": "prod",
  "deployment": {"id": "40bd8dea-…", "name": "custom-app-d8dtx4"},
  "user_values": {"hostname": "myapp.freepod.eu"}
}
```

It holds **intent** and nothing a deploy would rewrite (design D4). In
particular `image` is never written here — it is a build output, and persisting
it would mean a rewritten committed file on every deploy, which is git churn and
a merge conflict for any team of two. `image` is stripped on write even if a
caller passes one, because the platform's schema declares it under
`additionalProperties: false`, so neither a value nor an explicit null belongs
in a file that is committed and diffed.

`deploy` prompts for a required value the file lacks and records the answer,
rather than sending the user back to `init` — which would discard the deployment
pointer, the one thing in the file that cannot be reconstructed. `init --force`
warns by name about the deployment it is about to orphan.

Required values come from the product template's `values_schema_json`, walked at
runtime, so a newly required property appears without a client release. Today
`required` is exactly `["hostname"]`. The hostname property is recognized by
`"title": "hostname"`, case-insensitively — the same rule the platform and the
UI use. A bare label is completed with the platform's first wildcard domain; a
value containing a dot is taken as already qualified, since it may be a custom
domain served via CNAME.

## Packing

Four levels of precedence, last match wins:

1. **Hard excludes** — `.git/`. Never packable, not overridable.
2. **Built-in defaults** — `node_modules/`, `.venv/`, `venv/`, `__pycache__/`,
   `*.pyc`, `.pytest_cache/`, `target/`, `dist/`, `build/`, `.DS_Store`,
   `*.swp`, `.env.local`, `.env.*.local`.
3. **`.gitignore`**, layered per directory (disable with `--no-gitignore`).
4. **`.freepodignore`**, same syntax, applied last so its negations outrank
   everything except the hard excludes, which are re-applied after it.

`.env` is deliberately **not** excluded (design D11). Front-end tooling commonly
reads it while producing its distributable output, so dropping it yields a
silently misconfigured build rather than an error; a genuinely secret `.env` is
already excluded by the project's own `.gitignore`.

Matching is `pathspec`; the walk is ours, and it owns the two things `pathspec`
does not do: per-directory layering, and **pruning**. Pruning is not merely an
optimization — `pathspec` and git genuinely disagree about `node_modules/`
followed by `!node_modules/keep.txt`, where git reports `keep.txt` as ignored
and `GitIgnoreSpec.match_file()` re-includes it. Pruning yields git's answer,
which is the one a user can hold in their head, and it is what keeps a 480 MB
`node_modules` from ever being enumerated.

Pruning is also why a negation must **name the path** it re-includes:

```gitignore
!keep.txt                      # ✗ does nothing
!node_modules/keep.txt         # ✓ re-includes exactly that file
!node_modules/deep/keep.txt    # ✓ works at any depth — name the path
```

An unanchored `!keep.txt` never reaches inside a default-excluded directory,
because the directory is pruned before anything under it is considered, and
nothing tells the walk that a file called `keep.txt` might be worth descending
for. `**` does not substitute for naming the path, because the literal prefix is
what lets the walk decide to descend and `**` ends it:

```gitignore
!node_modules/**/keep.txt      # re-includes node_modules/keep.txt only
                               # — NOT node_modules/deep/keep.txt
```

`tests/test_archive.py` pins this, including a parametrized case asserting that
an unanchored negation does *not* force traversal. That test is intentional and
carries the reason in its docstring: honoring a depth-independent negation would
mean descending into every default-excluded tree on every pack — the stat storm
the defaults exist to avoid, reintroduced by a single `!*.md`.

Excluding a directory **yourself** is stricter than the built-in default, and
matches git exactly: nothing under it can be re-included. Exclude the contents
instead if an exception is needed:

```gitignore
node_modules/                  # your own exclusion — a hard wall
!node_modules/keep.txt         # ✗ ignored, exactly as git would

node_modules/*                 # exclude the contents instead
!node_modules/keep.txt         # ✓ now this works
```

Entries the platform's extraction would refuse — sockets, FIFOs, device nodes,
symlinks resolving outside the project — are omitted locally and each reported
by path. Left in, one of them fails the entire extraction; omitted here, it is a
single legible message.

The archive spools in memory up to 32 MiB and to disk beyond it. The client
enforces exactly one limit — the packed size — and learns it from the upload
slot's `max_bytes` at runtime. The entry-count and uncompressed ceilings live in
the builder's environment (`CAELUS_MAX_ENTRIES`, `CAELUS_MAX_EXTRACTED_BYTES`),
are never reported to a client, and are reported in the build log when hit.

## Builds

Three phases (designs D9, D12, D13):

1. **Mint an upload slot** — `POST /api/artifacts`, *after* the archive is
   packed. A slot lives 900s and 100 MiB over a domestic uplink can outlive
   that. Minting persists nothing, so an unused slot costs nothing.
2. **Submit the archive** — a presigned form POST straight to the object store,
   every field verbatim and in order with the file part last. The store is a
   different host with a different credential model, so it is reached with a
   plain `httpx.Client`, not `ApiClient` — no bearer token, and none of the
   401/403 contract, which describes the platform's edge. A `403` means an
   expired slot or a policy violation: mint one fresh slot and submit once more.
3. **Create and follow the build** — `POST /api/builds` with the artifact id
   alone, then read the log by byte range until `X-Build-Status` is terminal.
   A **200** rather than 201 means the platform handed back a build already
   queued or running for this artifact instead of creating a second one, which
   is what makes re-running a deploy safe; the client says so rather than
   silently following.

`_ProgressReader.seek`/`tell` are load-bearing, not conveniences: `httpx` uses
`seek` to rewind the field before rendering it, and seek/tell to size the body
so the request carries a `Content-Length` for the policy's
`content-length-range` condition. Drop them and a retry becomes a zero-byte
upload that the policy's lower bound refuses — reported as "the fresh slot was
rejected too", blaming the platform for a client bug. `fileno` is deliberately
*not* exposed, so an archive that spilled to disk and one that did not are sized
by the same code path.

The log offset advances by **bytes read**, never by a decoded length: a chunk
boundary can fall inside a multi-byte character. Tenant build output is stored
faithfully by the platform, control characters and all, so it is written to the
stream as bytes and never decoded here. `image` is null until the build
succeeds, so it is read from the build record afterwards rather than from the
creation response.

## Terms of Service

The platform refuses to create a deployment for an account that has never
accepted the terms: `POST /api/users/{id}/deployments` answers **400** with
`Terms of Service must be accepted before deploying`. That refusal would arrive
after the archive was packed, uploaded, and built, so the client settles it in
preflight instead.

Two things stay separate because they need different knowledge: the **gate** is
`tos_accepted_version is not None` — the platform requires *some* acceptance,
not the current one — while **recording** an acceptance requires submitting the
exact current version, which the client reads from the same document and never
carries its own copy of. A stale copy would 409 every user of that client until
they upgraded, locking them out of deploying entirely.

Only a create is gated; an update is not, so the client asks only when it is
about to create a deployment rather than nagging on every deploy. `login` offers
the terms when they are outstanding but never requires them — it is also how a
headless box gets a credential, and how someone who only wants `whoami` gets
one. A decline is recorded nowhere.

There is **no flag that accepts on the user's behalf.** A deploy with no
terminal to ask on fails rather than proceeding unaccepted, in CI as anywhere
else.

## The agent skill

`freepod skill install` writes `assets/SKILL.md` into the skills directory of
every supported coding agent it finds on the machine. `freepod skill show`
writes the same text to stdout for a runtime that keeps such files elsewhere.

`SKILL.md` with YAML frontmatter is a **cross-agent format** — Claude Code,
Codex, OpenCode, Amp and Gemini all read the same document — so there is one
skill and `skill.py` is little more than a table of destinations:

| Agent       | Detected by            | User skills                    | `--project`       |
|-------------|------------------------|--------------------------------|-------------------|
| Claude Code | `~/.claude`            | `~/.claude/skills`             | `.claude/skills`  |
| Codex       | `~/.codex`             | `~/.codex/skills`              | `.codex/skills`   |
| OpenCode    | `~/.config/opencode`   | `~/.config/opencode/skills`    | `.opencode/skills`|
| Amp         | `~/.config/amp`        | `~/.config/agents/skills`      | `.agents/skills`  |
| Gemini CLI  | `~/.gemini`            | `~/.gemini/skills`             | `.gemini/skills`  |

`CLAUDE_CONFIG_DIR` and `CODEX_HOME` override their rows; `XDG_CONFIG_HOME`
moves the two under `~/.config`. **Amp is the row where detection and
destination differ**: its own directory is what says Amp is installed, but it
reads user-level skills from `~/.config/agents/skills`.

Detection is the *configuration* directory rather than the skills directory, so
an agent the user has run but never given a skill to still counts. Selecting
nothing installs for what is detected; `--agent` and `--all` override that, and
`--dest` bypasses the table for an agent that is not listed — which is the
escape hatch that keeps a user from being blocked on a release when one of
these conventions moves. Two agents resolving to one directory are written once
and reported once.

**These paths are external conventions this package does not control**, and
they are young enough to still be moving — `.agents/skills/` is visibly
emerging as a shared location, and several agents already read each other's.
`test_skill.py` therefore asserts the *shape* — one directory per agent,
`<dir>/<name>/SKILL.md`, detection by configuration directory — and pins only
the strings confirmed against a real installation of that agent.

**There is no `--force`, and an existing skill is replaced without asking.**
The path belongs to this client, the file is generated rather than authored,
and `pip install --upgrade freepod && freepod skill install` only means
something if a newer skill can supersede an older one unattended. An unchanged
file is reported rather than rewritten so a re-run stays quiet.

### Why it ships as package data

The skill documents a contract — `$PORT`, no disk, no user environment
variables, S3 for state, `.freepodignore` precedence — and an agent acting on a
stale copy of that contract is worse off than an agent with none, because it
will act confidently on something untrue. Shipping it inside the wheel makes
the instructions and the client one artifact with one version, so
`pip install --upgrade freepod && freepod skill install` is the entire update
path. A file in this repository that users copy is stale the moment the next
release changes anything.

**What belongs in it.** Only what an agent cannot discover from `--help` and
would otherwise get wrong. The bar is a wasted build cycle: the bucket name
lives in `S3_BUCKET`, which is not an `AWS_*` variable and which no SDK
supplies on its own; `init` prompts, so it needs `printf 'name\n' |` to run
unattended; there are no runtime logs, so local verification is not optional.
Everything already in `README.md` stays out of it.

`test_skill.py` pins those facts by substring. It is a coarse test and
deliberately so — the point is that an edit which drops one of them fails
loudly rather than quietly shipping instructions that no longer say the thing
that makes them worth reading.

Nothing in the file is specific to any one agent — the destination is the only
thing that varies. The `description` in the frontmatter is what every one of
them matches against a user's request, which is why it enumerates the phrasings
that should select it and why a test asserts it stays on one line: wrapped, it
truncates.

## Reading logs

`freepod log` streams a deployment's application output from
`GET /api/users/{id}/deployments/{id}/log`. The transport is **Server-Sent
Events** — a line format, not a protocol, so `httpx.iter_lines()` parses it and
the package gains no dependency. A WebSocket would have needed one (`httpx` has
none) and bought a return channel nothing would use.

**Output goes to stdout, narration to stderr** — the opposite of `deploy`, and
the reason is which of the two is the *result*. `deploy` narrates its progress
towards an address, so the address is stdout. Here the lines are what the user
asked for, so they must survive `freepod log > app.log` and a pipe into `grep`,
and anything the client says about itself must not.

### The cursor

Every event carries the nanosecond timestamp the platform recorded, and that
same field is both what `--timestamps` renders and what a reconnect resumes
from. There is deliberately no separate cursor token: two representations of
one fact drift apart, and the client parses the timestamp anyway in order to
show it.

Resumption is **inclusive** — the client hands back the last timestamp it saw,
not one nanosecond later. Every undelivered line is at or after that instant,
so an inclusive resume cannot leave a gap; its only cost is that a line sharing
the boundary nanosecond may arrive twice. That trade is deliberate and must not
be reversed: a duplicated line is cosmetic, a missing one is the one being
looked for. **The client does not deduplicate**, because suppressing a line to
avoid a repeat risks discarding one that was genuinely new.

> **Parse the timestamp with `int`, never `float`.** A nanosecond value is
> ~1.76e18 against a double's exact-integer ceiling of ~9.01e15, so any float
> round trip silently corrupts both the rendered time and the resume point.
> `tests/test_logs.py` round-trips a real value for exactly this reason.

### Silence, and how a stream ends

`DEFAULT_HTTP_TIMEOUT` (30s) is **not** applied to a followed stream. httpx
applies a read timeout per read, so it would disconnect any application quiet
for longer than an ordinary request should take — which is most of them, most
of the time, and is not a fault. `LOG_STREAM_READ_TIMEOUT` bounds the
*platform's* silence instead: the endpoint emits a keepalive comment on a fixed
interval whether or not the application says anything, so keepalives stopping
is the disconnection signal. Raising the platform's keepalive above this value
would make a healthy stream look dead, so the two move together.

Keepalives are discarded without ever reaching the output — not as a blank
line, not as an empty event — so a quiet period leaves no trace in a redirect.

A followed stream can end three ways:

| Platform says          | Client does                                              |
|------------------------|----------------------------------------------------------|
| `end` reason `lifetime` | Reconnect silently. The platform caps how long one authorization keeps serving; the user asked to watch an application, not a connection. |
| `end`, any other reason | Return. The platform said it had finished, so that is an answer. |
| nothing                 | Treat as an interruption: back off, reconnect from the cursor, and **say so on stderr**. |

Reconnection is bounded, but **progress resets the budget**: a long follow that
drops every few hours and resumes cleanly each time is working, not failing,
and counting those cumulatively would eventually abandon a healthy stream. On
exhausting its attempts the client reports an interruption and says explicitly
that this implies nothing about the application, which may still be running.

### Build provenance

`deploy` sends `build_id` alongside the image it already sends. The platform
records it on the *release*, never on the deployment. Both halves travel
together out of `build_image`, because an image reference cannot identify a
build on its own: it is `{user_id}@{digest}`, digests are content-addressed, so
image → build is many-to-one. Returning only the image, as this once did, left
every release recording a null build.

## Testing

`uv run pytest`. Around 450 cases, none of which touch the network: the API,
the object store, and Keycloak are all reached through `httpx.MockTransport`.
Two autouse fixtures in `conftest.py` make that safe to rely on — `isolated_home`
points `HOME` and `XDG_CONFIG_HOME` at a temp directory (so no test passes
because a real credential happened to be lying around) and `no_sleep` patches
`time.sleep`, so every backoff and poll interval is instantaneous.

| File                                                                  | Pins                                                                        |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `test_surface.py`                                                     | Streams, `--quiet`, color, the exit-code table, timeout semantics.          |
| `test_package.py`                                                     | The package's shape: modules, console script, no `api/` import, deps.       |
| `test_archive.py`                                                     | Git parity, layering, pruning, negation anchoring, special files.           |
| `test_deploy.py`                                                      | Preflight ordering, plan selection, conflict readings, rollout waits.       |
| `test_auth.py`                                                        | Both flows, PKCE, `state`, polling, the cache.                              |
| `test_api.py`                                                         | The 401/403 contract, single refresh, retries.                              |
| `test_build.py`                                                       | Slot minting, upload retry, log ranging, re-attachment.                     |
| `test_delete.py`                                                      | Confirmation, the pointer's fate, already-gone reads, teardown waits.       |
| `test_builds.py`                                                      | Listing, the deployed-build marker, durations, and the table's layout.      |
| `test_tos.py`                                                         | Gate, prompt, recording, and the create-only rule.                          |
| `test_values.py`                                                      | Schema walking, constraint checks, hostname normalization.                  |
| `test_project.py` / `test_init.py` / `test_cli.py` / `test_config.py` | The file format, `init`'s refusals, command wiring, environment resolution. |

The suite imports out of `src/`, which structurally cannot catch a module
missing from the wheel, an undeclared dependency, or a broken console script.
That is what the `package` job in CI is for: it builds the wheel, installs it
into a clean 3.9 venv, and runs `freepod --version` and `--help` from *outside*
the checkout, where `cli/src` cannot satisfy the import.

## CI and releasing

`.github/workflows/cli-checks.yml` is the single definition of "the client is
good": the suite on 3.9 and 3.13 (`uv run --frozen`, so a lockfile that drifted
from `pyproject.toml` fails here rather than being silently re-resolved), plus
the clean-install `package` job, which uploads the distribution as the
`freepod-dist` artifact. `ci.yml` calls it on every push and pull request.

`.github/workflows/publish-cli.yml` calls the **same** gate again on a release
tag and publishes the very artifact that run built — were the release to
re-derive its own build, the thing proven and the thing uploaded would be equal
only by coincidence. It has no checkout step at all.

The version's home is `__version__` in `src/freepod/__init__.py`;
`pyproject.toml` reads it through Hatch and `--version` reports installed
metadata.

```bash
# 1. Bump __version__, commit.
# 2. Rehearse: run the "Publish CLI" workflow by hand → uploads to TestPyPI.
# 3. Ship:
git tag freepod-v0.2.0 && git push origin freepod-v0.2.0
```

The workflow runs on `freepod-v*` tags only. A tag push is a distinct event from
a branch push, so no merge to `master` publishes anything, whether or not it
touched `cli/`. A publish refuses any tag whose version disagrees with the built
wheel, and concurrent runs of the same ref serialize rather than race, because
an upload is not idempotent.

Uploads authenticate with PyPI Trusted Publishing (OIDC) through the `pypi` and
`testpypi` GitHub environments. There is no PyPI token in the repository.

**A version number is spent the moment it is uploaded.** PyPI refuses a
re-upload of a version even after you delete it, so a botched release is fixed
by bumping, never by replacing. That is what the TestPyPI rehearsal is for.

## Known wrinkles

- `USER_AGENT` in `config.py` is a second copy of the version, as above. It
  currently reads `freepod/0.1.0` while `__version__` is `0.1.1`.
- `cli-distribution` says build output streamed from the platform is a result
  and belongs on **stdout**; the implementation puts it on **stderr**, and
  `test_surface.py::test_the_build_log_goes_to_stderr` pins that. The
  implementation's reasoning is that `$(freepod deploy)` should not capture a
  few hundred lines of buildkit output with the address buried at the end. One
  of the two has to move; don't "fix" the code against the spec without settling
  which.
- `archive.py`'s module docstring and two docstrings in `test_archive.py` point
  at the README for the `node_modules/*` re-inclusion idiom. Since the README
  was rewritten for PyPI it documents the anchoring rule only; the full
  treatment is in § Packing above.
