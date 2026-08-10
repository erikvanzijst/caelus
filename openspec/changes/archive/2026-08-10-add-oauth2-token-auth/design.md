## Context

See proposal.md § Why for motivation. What follows is the state this design has
to fit into, all of it verified against the running cluster rather than read off
the Terraform.

**The edge is a decision service, not a proxy.** oauth2-proxy runs with
`upstream = static://202` and is consulted by a Traefik `forwardAuth`
middleware. It never sits in the request path; it answers `202` or a denial for
a sub-request and Traefik copies headers from that response onto the real
request. This is why token support does not require touching the data path.

**Verified facts.**

| Fact | Value | How verified |
| --- | --- | --- |
| oauth2-proxy image | `quay.io/oauth2-proxy/oauth2-proxy:v7.14.2` | `kubectl get deploy -n login,login-dev` |
| Bearer flags exist in that image | `--skip-jwt-bearer-tokens`, `--bearer-token-login-fallback`, `--oidc-extra-audience` | `kubectl exec … oauth2-proxy --help` |
| Device grant on the realm | `urn:ietf:params:oauth:grant-type:device_code` advertised | realm discovery document |
| Device code lifespan / poll interval | 600s / 5s | realm admin API |
| PKCE | `S256` supported; already required on the proxy clients | discovery + client attributes |
| `offline_access` | present as an *optional* scope on the proxy clients | client admin API |
| Offline session policy | 30-day idle, `offlineSessionMaxLifespanEnabled = false` | realm admin API |
| Access token lifespan | 300s | realm admin API |
| Refresh token rotation | `revokeRefreshToken = false` | realm admin API |
| Keycloak | 24.0, themed image `ghcr.io/erikvanzijst/caelus/keycloak` | `keycloak/Dockerfile`, cluster |

**The blocking constraint.** `tf/app/login/main.tf` declares the middleware with
`authRequestHeaders = ["Cookie"]`. Traefik forwards only that header to
`/oauth2/auth`, so a bearer token is discarded before verification is even
attempted. Everything else in this change is dead code until that list grows.

## Goals / Non-Goals

**Goals:**

- Make a Keycloak access token a first-class credential at the edge, accepted on
  exactly the terms a session cookie is accepted on today.
- Keep every line of token handling at the edge. `api/app/deps.py` must remain
  unaware that tokens exist.
- Preserve the existing environment-isolation invariant: a credential minted for
  dev must not work on prod.
- Leave the change independently verifiable with `curl`, before any client
  exists to consume it.

**Non-Goals:**

- The CLI application itself (see proposal.md § What Changes).
- Scope-based authorization. The API authorizes on identity alone; introducing
  scopes is a much larger change to `api/app/deps.py` and every route guard.
- A Freepod-native token or session management UI. Keycloak's account console is
  the revocation surface.
- Machine-to-machine credentials. `serviceAccountsEnabled` stays `false`;
  client-credentials tokens have no user and therefore no `email` claim, so they
  cannot satisfy `X-Auth-Request-Email` at all. That is a separate design.

## Decisions

### D1. Verify tokens at the edge, not in the API

oauth2-proxy verifies the JWT and synthesizes a session from its claims;
`--set-xauthrequest` then emits `X-Auth-Request-Email` exactly as it does for a
cookie session. The API sees no difference.

*Alternative considered: verify in FastAPI.* Add a dependency that accepts
either the header or a bearer token, validating against the realm JWKS. Rejected
on two grounds. It would put two independent authentication implementations in
the system, and — more seriously — it would create a path where the API trusts a
credential the edge never inspected, weakening the property that
`X-Auth-Request-Email` is only ever edge-derived. The current arrangement, where
the API's only trust anchor is a header no client can set, is worth preserving.

### D2. Per-environment public CLI clients, not one realm-wide client

A single `freepod-cli` was the first instinct: a public client holds no secret,
so there is nothing environment-specific to protect.

It does not survive contact with the audience mechanism. The audience mapper is
what makes a token verifiable, and one client can carry only one default
audience scope. A realm-wide client would have to inject both `freepod-prod` and
`freepod-dev`, at which point a token obtained against dev is accepted by prod —
directly contradicting the `keycloak-user-realm` requirement that "a session or
token issued for one environment is not interchangeable with the other."

Both CLI clients register the same loopback redirect URIs, so **the `aud` claim
is the only thing separating the environments.** That makes the mapper a
security control, and it is why the specs assert the negative case (each client
must *not* carry the other's audience scope) rather than only the positive one.

*Alternative considered: one client, two optional audience scopes*, selected by
the client at request time. Rejected — it makes environment isolation depend on
the client asking correctly, which is not an isolation property at all.

### D3. Fix the audience with a mapper, never by widening the allowance

A Keycloak access token carries `aud: ["account"]` and records the requesting
client in `azp`. oauth2-proxy verifies `aud` against its own `client_id`, so a
CLI token fails verification out of the box.

Two ways out. Add an audience protocol mapper so the token names the right
audience, or set `--oidc-extra-audience=account` so oauth2-proxy accepts the
default one.

**The second is a vulnerability, not a shortcut.** Every token Keycloak issues
in the `freepod` realm — including one minted for Grafana, or for any client
added later — carries `aud: ["account"]`. Accepting it would make any realm
token a valid Freepod credential for any user. The spec forbids it explicitly so
that a future reader who finds the mapper fiddly cannot "simplify" it away.

### D3a. Keycloak enforces PKCE on the device endpoint too

Discovered during implementation, and it will surprise whoever writes the
client. RFC 8628 has no redirect and therefore no PKCE, but Keycloak applies the
client's `pkce.code.challenge.method` attribute to the **device authorization
endpoint** as well. A device request without one is refused:

```
POST /realms/freepod/protocol/openid-connect/auth/device
  client_id=freepod-cli-dev&scope=openid email profile offline_access
→ {"error":"invalid_request",
   "error_description":"Missing parameter: code_challenge_method"}
```

So a device-flow client must generate a verifier/challenge pair, send
`code_challenge` + `code_challenge_method` to the device endpoint, and send
`code_verifier` when polling the token endpoint — exactly as in the loopback
flow. This is a consequence of requiring PKCE on the client (D2/spec), not a
reason to relax it: dropping the requirement to simplify the device flow would
also remove the protection the loopback flow depends on.

### D4. Device authorization grant for headless, not out-of-band paste

The original sketch was to print a URL and have the user paste the callback code
back into the terminal. That needs the `urn:ietf:wg:oauth:2.0:oob` redirect,
which Keycloak removed years before 24.0 — so it is not merely worse, it is
unavailable.

The device grant is the sanctioned replacement and is already enabled on the
realm. It is also the better design: nothing secret transits the terminal or
clipboard, and it works unchanged over SSH.

### D5. Register loopback redirect URIs port-less

RFC 8252 §7.3 requires a native client to bind an ephemeral port, which cannot
be known at registration time. Keycloak 24 handles this: `RedirectUtils` retries
a failed match after rewriting the requested URI to port 80 when the host is in
`{localhost, 127.0.0.1, [::1]}`. Registering the port-less form therefore
matches any port.

Confirmed by reading `RedirectUtils.java` on the `release/24.0` branch rather
than inferred:

```java
if (valid == null && "http".equals(originalRedirect.getScheme()) &&
    LOOPBACK_INTERFACES.contains(originalRedirect.getHost())) {
    String redirectWithDefaultPort = KeycloakUriBuilder.fromUri(originalRedirect)
        .port(80).buildAsString();
    valid = matchesRedirects(resolveValidRedirects, redirectWithDefaultPort,
        allowWildcards);
}
```

Two consequences for implementation. The **path still matches exactly**, so pick
one callback path and keep it stable. And register both `127.0.0.1` and
`localhost` — the relaxation is per-host-string, not a normalization, so a
client using one form does not match a registration of the other.

*Alternative considered: a wildcard redirect URI such as `http://127.0.0.1:*/`.*
Rejected — Keycloak's wildcard handling is a plain suffix match, unspecific
redirect URIs are a documented threat, and the port-less form already covers the
requirement.

### D6. `bearer_token_login_fallback = false`

Set this to make a failed bearer token distinguishable from no credential at
all. It does **not** exist to avoid a login page — in this deployment there is
no login page to avoid, and reasoning that way is how the wrong mental model
gets propagated.

Verified in `pkg/middleware/jwt_session.go` at v7.14.2:

```go
js := &jwtSessionLoader{
    denyInvalidJWTs: !bearerTokenLoginFallback,
}
...
session, err := j.getJwtSession(req)
if err != nil {
    if j.denyInvalidJWTs {
        http.Error(rw, http.StatusText(http.StatusForbidden), http.StatusForbidden)
        return
    }
}
```

With the default (`true`), an unverifiable token produces a session-less request
and `/oauth2/auth` answers `401` — the same answer an anonymous request gets. A
client then cannot tell "refresh and retry" from "your credential is broken,
re-authenticate." Disabling the fallback splits those into `403` and `401`.

The resulting contract, which the specs pin down because clients will depend on
it: no credential is `401` (the SPA already relies on this), an unverifiable
bearer token is `403`, success is `202`.

**The one confusing edge, confirmed on dev:** an *authorization* denial — a
valid, correctly-audienced token whose user is not in `allowed_groups` — also
returns `401`, not `403`. The group check rejects a session oauth2-proxy already
built, so it never reaches the JWT loader's deny path. This inverts the usual
HTTP reading, where `401` means unauthenticated and `403` means authenticated
but not permitted:

| Condition | Status |
| --- | --- |
| Valid token, authorized | `202` → `200` upstream |
| No credential at all | `401` |
| Valid token, **not in `allowed_groups`** (dev only) | `401` |
| Unverifiable / expired / malformed token | `403` |

So on `dev.freepod.eu` a client cannot distinguish "you are not in the
freepod-dev group" from "you sent nothing" by status code alone. Worth stating
in the client documentation, because the natural debugging instinct on a `401`
is to re-authenticate — which will succeed, and change nothing.

**This flag cannot affect a browser request.** `getJwtSession` returns
`(nil, nil)` when the `Authorization` header is absent, so the `denyInvalidJWTs`
branch is unreachable for cookie-only traffic. It is also worth being clear that
there is no edge-driven redirect-to-login flow in this stack to break: the
`oauth-errors` middleware is deliberately not attached to `caelus-ingress`
(`tf/app/caelus/ingress.tf`), and the `/oauth2/auth` handler returns a bare
`401` rather than a redirect. Login is initiated by the SPA.

**One narrow behavior change, accepted.** See Risks below — a request carrying
both a session cookie and a non-JWT `Authorization` header is refused where it
previously succeeded.

### D7. Apply order is `tf/deps` before `tf/app`

oauth2-proxy's readiness probe depends on OIDC discovery succeeding. Pointing it
at an audience whose client scope does not yet exist is a rollout failure, not a
warning. This is the same ordering `tf/README.md` already documents, so it needs
recording, not inventing.

## Risks / Trade-offs

**A leaked offline token is usable for a long time.** Realm policy is 30-day
idle with no maximum lifespan, and `revokeRefreshToken = false` means no
rotation on use. → Accepted for this change. Both settings are realm-wide, so
tightening them would change browser session behavior for every user, which
belongs in its own change with its own reasoning. Recorded here so the next
person finds the decision rather than the symptom.

**A bearer token carries full account authority.** There is no scope narrowing
(Non-Goals). A user who pastes a token into a CI job has granted that job
everything they can do. → Mitigated only by documentation and by Keycloak's
account console being the revocation surface. Called out in the specs so it is
not discovered later as a surprise.

**`skip_auth_routes` silently ignores bearer tokens.** Those routes bypass
oauth2-proxy entirely, so a token on them is neither verified nor rejected — it
is simply ignored, and no identity is injected. → Behavior is unchanged from
today and the footgun is already documented at `tf/app/login/main.tf`. The spec
restates it for the bearer case so the two paths stay in sync.

**~~Traefik's `authResponseHeaders` behavior for the raw token is
unconfirmed.~~ RESOLVED — the token is stripped.** Verified on dev by sending
`Authorization: Bearer <token>` through to the `echo` service and dumping the
headers the upstream received: no `authorization` header present,
`x-auth-request-email` set from the token's `email` claim. Traefik overwrites
each header named in `authResponseHeaders` with the auth response's value and
removes it when the auth response sets none; oauth2-proxy does not set
`pass_authorization_header`, so the client's header is dropped. The list is a
sanitizer, not a pass-through — removing `Authorization` from it would let a
client-supplied header reach the API untouched. Recorded at the middleware
definition in `tf/app/login/main.tf`.

**A cookie plus a non-JWT `Authorization` header now yields 403.** This is the
one place where D6 changes existing behavior, and it is not obvious from the
flag's name. `buildSessionChain` appends the JWT loader *before* the stored
(cookie) session loader, and `loadSession` short-circuits only when a session is
already present — which it is not, because the cookie loader has not run yet. So
`findTokenFromHeader` errors on any `Authorization` header that is neither
`Bearer <jwt-shaped>` nor a `Basic` value with a JWT inside, and the request is
refused before the perfectly good cookie is ever examined.

Browsers do not send `Authorization` spontaneously, so ordinary traffic is
unaffected. It is reachable through a corporate proxy injecting Basic auth, a
browser extension, or a `curl -u` habit against an authenticated route. →
Accepted. The failure is loud and self-describing (`403` on a request the user
knows carries a valid session), and the alternative — keeping the fallback
enabled — costs the 401/403 distinction that is the entire point of D6.
Verification is task 5.10; if it turns out to bite real traffic, the escape
hatch is to leave the fallback at its default and have clients treat `401` as
covering both cases.

**Dev gating fails closed if the `groups` claim is missing.** Correct behavior,
but it presents as "authentication works on prod, 403 on dev", which reads like
a token problem rather than a scope-assignment problem. → The spec asserts the
missing-claim case directly, and tasks.md verifies dev before prod so the
failure surfaces where it is cheap.

## Migration Plan

No migration in the usual sense: this is purely additive. No existing client,
session or cookie changes behavior, no realm-level setting is touched, and
nothing needs to be backfilled.

1. Apply `tf/deps` — new clients and audience scopes. Inert until an edge
   accepts them; safe to apply and leave.
2. Apply `tf/app` in the `default` workspace. Verify against `dev.freepod.eu`,
   which is group-gated and therefore exercises the strictest path.
3. Apply `tf/app` in the `prod` workspace.

**Rollback.** Revert the `tf/app` change and apply. Bearer authentication stops
being accepted; cookie sessions are untouched throughout, so a rollback is not
user-visible. The `tf/deps` resources can be left in place — unused clients and
scopes have no effect on anything — or removed separately.

**Blast radius if step 2 goes wrong.** The `authRequestHeaders` and `extraArgs`
edits are additive; the failure mode is oauth2-proxy not becoming ready, which
Traefik surfaces as denied requests on the affected environment. Verifying on
dev first bounds this to the gated environment.

## Open Questions

None outstanding.

**Resolved during planning.** The loopback callback path is `/callback`, chosen
to read consistently with the `/oauth2/callback` path oauth2-proxy already
serves on the apex host. It is recorded here because it is effectively
irreversible once clients are distributed: Keycloak matches the path exactly
(see D5), so changing it later breaks every installed client until it upgrades.
The four registered redirect URIs are therefore:

```
http://127.0.0.1/callback     (freepod-cli-prod)
http://localhost/callback     (freepod-cli-prod)
http://127.0.0.1/callback     (freepod-cli-dev)
http://localhost/callback     (freepod-cli-dev)
```
