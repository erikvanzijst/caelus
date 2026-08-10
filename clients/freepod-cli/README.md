# freepod-cli

A small demo client for the Freepod API. It authenticates against Keycloak with
OAuth2, then calls two endpoints:

```
GET /api/me                       → who you are
GET /api/users/{id}/deployments   → your deployments
```

It exists to show how a non-browser client gets a credential. The protocol
reference is `api/README.md` § "External API clients (OAuth2 tokens)"; the
reasoning behind the design is in
`openspec/changes/archive/2026-08-10-add-oauth2-token-auth/design.md`.

## Requirements

Python 3.9 or newer. **Nothing else** — standard library only, no virtualenv, no
`pip install`. That is deliberate, so the same file runs unchanged on a host
machine and inside a devcontainer.

(Tested on 3.13. The 3.9 floor comes from the newest API used,
`urlopen(...).status`, rather than from testing on 3.9 itself.)

## Usage

```bash
./freepod_cli.py                  # dev (default)
./freepod_cli.py --env prod
```

First run sends you through a browser login; after that the cached refresh token
is used silently.

```
usage: freepod_cli.py [-h] [--env {dev,prod}] [--loopback | --device]
                      [--login] [--logout] [--json] [--verbose]
                      [--timeout SECONDS]
```

| Flag | Effect |
| --- | --- |
| `--env dev\|prod` | Target environment. Default `dev`. |
| `--loopback` | Force the browser flow. |
| `--device` | Force the device flow. |
| `--login` | Ignore any cached token and re-authenticate. |
| `--logout` | Discard the cached token for `--env` and exit. |
| `--json` | Print raw JSON instead of a table. |
| `--verbose` | Show token claims and extra progress detail. |
| `--timeout` | How long the loopback listener waits. Default 300s. |

Progress and diagnostics go to **stderr**, results to **stdout**, so
`./freepod_cli.py --json > out.json` gives you clean JSON.

## Environments

Two public clients, one per environment. They hold no client secret — PKCE
proves client identity instead, and is mandatory on both.

| Env | Client ID | API base |
| --- | --- | --- |
| `dev` (default) | `freepod-cli-dev` | `https://dev.freepod.eu` |
| `prod` | `freepod-cli-prod` | `https://freepod.eu` |

Issuer: `https://keycloak.freepod.eu/realms/freepod`.

A token is bound to one environment by its `aud` claim. Both clients register
identical redirect URIs, so **the audience is the only thing separating dev from
prod** — a dev token presented to `freepod.eu` is rejected, and vice versa.

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

The listener binds `127.0.0.1` only, never `0.0.0.0`, and stops as soon as the
callback arrives (or the `--timeout` elapses, so it cannot hang forever). It
answers `404` to anything that is not `/callback`, which keeps a browser's
speculative `/favicon.ico` fetch from consuming the one request it is waiting
for.

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
ask the user to confirm it matches — an anti-phishing check that the device is
really in the user's hands (§5.4). **Keycloak 24 does not do that half.** It
consumes the code from the query string and goes straight to sign-in and
consent, so the code appears nowhere on screen.

Here the code is therefore a *fallback*, and the client says so rather than
telling you to confirm something you will never see. If the long URL is mangled
by terminal wrapping, or you would rather type a short one on a phone, open
`https://keycloak.freepod.eu/realms/freepod/device` — that page has a code-entry
field — and enter the code there.

Keycloak does implement the other §5.4 mitigation: the consent screen names the
client ("Grant Access to Freepod CLI (production)"), so an unexpected
authorization prompt is still recognizable as one you did not start.

`urn:ietf:wg:oauth:2.0:oob` (print-and-paste) is **not** an option — Keycloak
removed it before 24.0 and it is not registered on these clients.

### How "no browser" is detected

In order: `/.dockerenv` exists → a container runtime appears in `/proc/1/cgroup`
→ on Linux, none of `DISPLAY` / `WAYLAND_DISPLAY` / `BROWSER` is set →
`webbrowser.get()` raises. Any hit selects the device flow.

A container is disqualifying even when a browser binary is installed: the
redirect would land on the *container's* `127.0.0.1`, which your browser cannot
reach.

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
On startup the client loads the cache, refreshes, and falls back to a full login
if that fails.

Raw tokens are never printed. `--verbose` shows decoded *claims* (`aud`, `azp`,
`email`, `exp`, `groups`, …) — decoded for display only, never used to make a
trust decision. The edge is what verifies tokens.

## Status codes — read these carefully

```
200   ok
401   no credential  OR  authenticated but not authorized
403   token expired, malformed, or unverifiable
```

**This inverts the usual HTTP reading, deliberately.** `403` is the signal to
refresh or re-authenticate; `401` is not.

The client acts accordingly: on `403` it refreshes and retries once, falling
back to a full login if the refresh is rejected. On `401` it stops and explains,
because re-authenticating would succeed and change nothing.

`dev.freepod.eu` additionally requires membership of the `freepod-dev` Keycloak
group. A non-member with a perfectly valid token gets `401` — indistinguishable
by status code from sending no credential at all. If dev returns `401` while
prod works, check group membership before suspecting the token.

## Security notes

**A token grants full account authority.** The API authorizes on user identity
alone and has no notion of OAuth scopes, so a token cannot be narrowed to
read-only or to a single deployment — it is equivalent to a browser session for
that user. Think carefully before pasting one into CI.

`--logout` only discards the *local* copy. Server-side revocation is through the
Keycloak account console (Applications → offline sessions), which lists sessions
issued to `freepod-cli-*`. Revoking stops further refresh; an already-issued
access token stays valid for up to its remaining 300 seconds.

## Example

```
$ ./freepod_cli.py --env dev
Environment 'dev': client_id=freepod-cli-dev api=https://dev.freepod.eu
No cached credential for 'dev'.
Using the device flow — running in a container (/.dockerenv present).

To sign in, open this URL in any browser — on this machine or another:

    https://keycloak.freepod.eu/realms/freepod/device?user_code=WMJW-QHHV

  That link already carries the code WMJW-QHHV, so Keycloak will
  not ask you for it. To type it in by hand instead, open
  https://keycloak.freepod.eu/realms/freepod/device and enter WMJW-QHHV

Waiting up to 600s for approval (polling every 5s)...
Approved.

Authenticated as erik.van.zijst@gmail.com (user id 1, admin)
  flow       : device
  credential : fresh login

NAME       HOSTNAME                    STATUS   ID
---------  --------------------------  -------  --
immich     photos.example.freepod.eu   running  3
nextcloud  cloud.example.freepod.eu    running  7

2 deployments.
```
