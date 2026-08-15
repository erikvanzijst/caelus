# freepod

Take a local project directory to a running Freepod deployment.

```bash
freepod login
freepod init
freepod deploy
```

`deploy` packs the working tree, uploads it, builds an image on the platform,
and creates or updates the deployment that serves it. Everything a cheap read
can refuse is refused before a build is spent.

## Install

```bash
pip install freepod          # or: uv tool install freepod
```

Python 3.9 or newer. Depends on `click`, `httpx`, and `pathspec`.

From a checkout:

```bash
cd cli
uv run freepod --help
```

## Commands

| Command | What it does |
| --- | --- |
| `login` | Authenticate and cache the credential. Offers the terms if outstanding. |
| `logout` | Discard the **local** credential for the selected environment. |
| `whoami` | Report who the cached credential authenticates as. Never opens a browser. |
| `init` | Write `.freepod.json` for the current directory. Reads only — creates nothing. |
| `deploy` | Preflight → pack → upload → build → release. |

Global flags: `--env`, `--verbose`, `--quiet`, `--timeout`.
`deploy` adds `--recreate` and `--no-gitignore`; `init` adds `--force`.

### Streams

Results go to **stdout**, everything else to **stderr** — so `deploy` prints one
line you can capture:

```bash
URL=$(freepod deploy)      # https://myapp.freepod.eu
```

The build log, the upload progress bar, and every status line are diagnostics
and go to stderr. `--quiet` silences all of it and leaves the result and any
error. Colour is suppressed automatically when stdout is not a terminal, and
whenever `NO_COLOR` is set.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | error |
| 2 | usage error |
| 3 | not authenticated |
| 4 | the build failed |
| 5 | the rollout failed |

A **timeout is not a failure** and does not get its own code. `--timeout` bounds
how long the client waits, never what the platform does: when it elapses, the
build or rollout is still running on the platform, uncancelled, and the message
says so. Re-running picks it back up.

`--timeout` applies to whichever wait is in progress, which means something
different per command — login 300s, build 1800s, rollout 600s by default.

## Environments

Two public clients, one per environment. They hold no client secret — PKCE
proves client identity instead, and is mandatory on both.

| Env | Client ID | API base |
| --- | --- | --- |
| `prod` (default) | `freepod-cli-prod` | `https://freepod.eu` |
| `dev` | `freepod-cli-dev` | `https://dev.freepod.eu` |

Issuer: `https://keycloak.freepod.eu/realms/freepod`. Select with `--env` or
`FREEPOD_ENV`. There is no flag for an arbitrary base URL: a token is bound to
one environment by its `aud` claim, and an arbitrary address would need the
issuer and client id to travel with it.

Both clients register identical redirect URIs, so **the audience is the only
thing separating dev from prod** — a dev token presented to `freepod.eu` is
rejected, and vice versa.

`.freepod.json` records which environment it belongs to, and a command targeting
a different one stops rather than guessing: a deployment id minted on dev is
meaningless on prod.

## The two flows

The flow is auto-detected, and the client always logs which one it picked and
why (`Using the device flow — running in a container (/.dockerenv present).`).
Override with `--loopback` or `--device`.

### Loopback + PKCE — when a browser is reachable

Binds an ephemeral port on `127.0.0.1`, opens your browser to the authorization
endpoint with `redirect_uri=http://127.0.0.1:<port>/callback`, waits for the
redirect, verifies the `state` parameter, and exchanges the code with the
`code_verifier`.

> **The callback path must be exactly `/callback`.** The registered redirect
> URIs are the port-less forms `http://127.0.0.1/callback` and
> `http://localhost/callback`. Keycloak relaxes *port* matching for loopback
> hosts (RFC 8252 §7.3) so any ephemeral port works, but the **path is matched
> exactly**, and `127.0.0.1` and `localhost` are distinct host strings. Any
> other path fails with `invalid redirect_uri`.

The listener binds `127.0.0.1` only, never `0.0.0.0`, stops as soon as the
callback arrives (or `--timeout` elapses, so it cannot hang forever), and
answers `404` to anything that is not `/callback` — which keeps a browser's
speculative `/favicon.ico` fetch from consuming the one request it waits for.

### Device authorization grant — when there is no shared browser

For containers, SSH sessions, and CI. The client prints a URL and a short user
code; you approve on whatever device has a browser, and nothing secret transits
the terminal.

> **Keycloak requires PKCE on the device endpoint too.** RFC 8628 has no
> redirect and therefore no PKCE, but these clients mandate PKCE and Keycloak
> enforces it here as well. The `code_challenge` and `code_challenge_method`
> go to the *device* endpoint, and the `code_verifier` goes with every poll.
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

**How "no browser" is detected**, in order: `/.dockerenv` exists → a container
runtime appears in `/proc/1/cgroup` → on Linux, none of `DISPLAY` /
`WAYLAND_DISPLAY` / `BROWSER` is set → `webbrowser.get()` raises. Any hit
selects the device flow. A container is disqualifying even when a browser binary
is installed: the redirect would land on the *container's* `127.0.0.1`, which
your browser cannot reach.

## Tokens and storage

Scopes requested: `openid email profile offline_access`. Access tokens live
**300 seconds**; `offline_access` yields an offline refresh token (`typ:
Offline`) with no absolute expiry, valid as long as it is used at least once
every 30 days.

The refresh token is cached at:

```
${XDG_CONFIG_HOME:-~/.config}/freepod/tokens.json     (mode 0600, in a 0700 dir)
```

Entries are **keyed by environment**, so dev and prod credentials never collide.

Raw tokens are never printed. `--verbose` shows decoded *claims* (`aud`, `azp`,
`email`, `exp`, `groups`, …) — decoded for display only, never used to make a
trust decision. The edge is what verifies tokens.

## The project file

`init` writes `.freepod.json`, and it is meant to be committed:

```json
{
  "version": 1,
  "env": "prod",
  "deployment": {"id": "40bd8dea-…", "name": "custom-app-d8dtx4"},
  "user_values": {"hostname": "myapp.freepod.eu"}
}
```

It holds **intent**, and nothing a deploy would rewrite. In particular the
built image is never written here: it is a build output, not intent, and
persisting it would mean a rewritten committed file on every deploy.

Edit it directly to change a value — the next `deploy` asserts it. `deploy`
prompts for anything the product template requires that is missing, and records
the answer, rather than sending you back to `init`, which would discard the
deployment pointer.

If the deployment is deleted on the platform, `deploy --recreate` discards the
stale pointer and creates a new one.

## What gets packed

In order, later rules winning:

1. **Hard excludes** — `.git/`. Never packable, not overridable.
2. **Built-in defaults** — `node_modules/`, `.venv/`, `venv/`, `__pycache__/`,
   `*.pyc`, `.pytest_cache/`, `target/`, `dist/`, `build/`, `.DS_Store`,
   `*.swp`, `.env.local`, `.env.*.local`.
3. **`.gitignore`**, layered per directory (disable with `--no-gitignore`).
4. **`.freepodignore`**, same syntax, applied last so it outranks the rest.

`.env` is **not** excluded by default. A committed `.env` in a repo is a
deliberate choice, usually holding public configuration, and silently dropping
it produces a build that fails for reasons nothing on screen explains. Exclude
it yourself if it holds secrets.

Excluded directories are *pruned*, not walked and filtered — packing a tree with
a 480 MB `node_modules` never enumerates it.

### Re-including something

A negation must **name the path** into the excluded directory. This is the part
that catches people:

```gitignore
!keep.txt                      # ✗ does nothing
!node_modules/keep.txt         # ✓ re-includes exactly that file
!node_modules/deep/keep.txt    # ✓ works at any depth — name the path
```

An unanchored `!keep.txt` never reaches inside a default-excluded directory,
because the directory is pruned before anything under it is considered, and
nothing tells the walk that a file called `keep.txt` might be worth descending
for.

**`**` does not substitute for naming the path.** Anchoring is needed at every
level it must reach, so:

```gitignore
!node_modules/**/keep.txt      # re-includes node_modules/keep.txt only
                               # — NOT node_modules/deep/keep.txt
```

The literal prefix is what lets the walk decide to descend, and `**` ends it.

Excluding a directory **yourself** is stricter than the built-in default, and
matches git exactly: nothing under it can be re-included.

```gitignore
node_modules/                  # your own exclusion — a hard wall
!node_modules/keep.txt         # ✗ ignored, exactly as git would

node_modules/*                 # exclude the contents instead
!node_modules/keep.txt         # ✓ now this works
```

The client enforces exactly one limit — the archive's packed size — and learns
it from the platform at upload time rather than carrying its own copy. The
entry-count and uncompressed ceilings live in the builder and are reported in
the build log.

## Status codes — read these carefully

```
200   ok
401   no credential  OR  authenticated but not authorized
403   token expired, malformed, or unverifiable
```

**This inverts the usual HTTP reading, deliberately.** `403` is the signal to
refresh or re-authenticate; `401` is not.

The client acts accordingly: on an edge `403` it refreshes and retries **once**,
falling back to a full login if the refresh is rejected. On `401` it stops and
explains, because re-authenticating would succeed and change nothing.

The refresh is bounded at once per request on purpose. The API issues its own
`403`s too — with a JSON `detail` body, where the edge's is plain text — and an
unbounded "403 means refresh" rule would refresh, fail, re-login, and loop on a
request no credential can satisfy.

`dev.freepod.eu` additionally requires membership of the `freepod-dev` Keycloak
group. A non-member with a perfectly valid token gets `401` — indistinguishable
by status code from sending no credential at all. If dev returns `401` while
prod works, check group membership before suspecting the token.

## Terms of Service

The platform will not create a deployment for an account that has not accepted
its terms. `login` offers them when they are outstanding; `deploy` requires them
before your **first** deployment, and never asks again.

The version accepted is whatever the platform reports as current — the client
carries no copy of it, so a revision of the terms never locks an older client
out.

There is **no flag that accepts on your behalf.** A deploy with no terminal to
ask on fails rather than proceeding unaccepted, in CI as anywhere else.

## Security notes

**A token grants full account authority.** The API authorizes on user identity
alone and has no notion of OAuth scopes, so a token cannot be narrowed to
read-only or to a single deployment — it is equivalent to a browser session for
that user. Think carefully before pasting one into CI.

`freepod logout` only discards the **local** copy. Server-side revocation is
through the Keycloak account console (Applications → offline sessions), which
lists sessions issued to `freepod-cli-*`. Revoking stops further refresh; an
already-issued access token stays valid for up to its remaining 300 seconds.

## Development

```bash
cd cli
uv run pytest          # the full suite
uv run freepod --help
```

The package depends on nothing in `api/`. It is a client, and it talks to a
deployed platform over HTTP like any other.
