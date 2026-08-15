## Context

See `proposal.md` § Why for motivation. What shapes the approach:

- **Every endpoint already exists and is unmodified.** `POST /api/artifacts`,
  `POST /api/builds`, `GET /api/builds/{id}/log`, the deployment routes under
  `/api/users/{user_id}/deployments`, and the public product, plan, hostname, and domain
  reads. This is a client written against a frozen server.
- **The OAuth2 groundwork is done.** `freepod-cli-prod` and `freepod-cli-dev` exist as
  public Keycloak clients with PKCE mandatory, the device grant enabled, port-less
  loopback redirect URIs, audience mappers, and `offline_access`. See
  `openspec/specs/oauth2-token-auth/spec.md`.
- **A working reference implementation of the hard part exists.** `cli/freepod_cli.py`
  already implements both flows, browser detection, and the token cache correctly, and
  its README documents the traps. That code is lifted, not rewritten.
- **Three API behaviors constrain the command flow** and are not obvious from the route
  list: deployment update is accepted only while the deployment is `ready` or `error`;
  `user_values_json` replaces wholesale rather than merging; and the public hostname
  check has no way to exclude the deployment that already holds the name.

The full working draft this design was distilled from is `var/cli.md`.

## Goals / Non-Goals

**Goals:**

- `git clone && freepod deploy` works for a second developer with no extra steps.
- A first deploy performs exactly one rollout and never shows a placeholder page.
- Every limit, schema, and identifier the client acts on comes from the API at runtime,
  so the platform can retune itself without a client release.
- The client is honest about what it is waiting for, what it interrupted, and what
  continues to run without it.

**Non-Goals:**

- No API, database, Terraform, or UI change — including no client-configuration
  discovery endpoint.
- No paid plans, checkout, or subscription handling.
- No registry publication. This change produces an installable package and builds it in
  CI; PyPI, Homebrew, and Chocolatey are a later operational change.
- No command surface beyond `login`, `logout`, `whoami`, `init`, and `deploy`. See
  [Deferred](#deferred).

## Decisions

### D1. A conventional package with dependencies, not a single dependency-free file

The demo client's zero-dependency constraint existed so it could be curl'd and run
unchanged on a host and inside a devcontainer. A shipped product needs multipart form
uploads with progress, retry with backoff, gitignore-syntax matching, and Windows path
handling; hand-rolling those on `urllib` is a tax paid forever.

```
cli/
  pyproject.toml
  README.md
  src/freepod/
    __init__.py        __main__.py
    cli.py             # click entry point, global flags
    config.py          # environments, ~/.config/freepod paths
    auth.py            # PKCE loopback + device flow, token cache (lifted from the demo)
    api.py             # HTTP client: auth, retries, 401/403 handling
    project.py         # .freepod.json load/save/discovery
    values.py          # schema walk, prompting, hostname normalization (init + deploy)
    archive.py         # ignore rules + deterministic tgz
    build.py           # artifact upload, build creation, log streaming
    deploy.py          # create-or-update deployment, rollout polling
  tests/
```

|                |                                                                                                 |
|----------------|-------------------------------------------------------------------------------------------------|
| Python         | 3.9+ (the demo client's floor), tested on 3.13                                                  |
| Runtime deps   | `click`, `httpx`, `pathspec>=1.0`                                                               |
| Console script | `freepod`                                                                                       |
| Later channels | PyPI → `pipx` / `uv tool`; Homebrew formula from the sdist; a PyInstaller `.exe` for Chocolatey |

Every dependency is pure Python, so wheels are universal and a Homebrew formula's
vendored `resources` list stays short. Progress bars come from `click.progressbar` rather
than `rich`, keeping that list shorter still.

`values.py` exists as its own module because both `init` and `deploy` prompt for required
schema values — see D5.

*Alternative considered: keep the single-file, zero-dependency form.* Rejected. The
correctness-critical part (gitignore matching, D10) is precisely what should not be
hand-rolled, and "standalone" is better served by the distribution being standalone than
by the source having no imports.

### D2. Two named environments, no caller-supplied base URL

| `--env`            | Client ID          | API base                 | Issuer                                       |
|--------------------|--------------------|--------------------------|----------------------------------------------|
| `prod` *(default)* | `freepod-cli-prod` | `https://freepod.eu`     | `https://keycloak.freepod.eu/realms/freepod` |
| `dev`              | `freepod-cli-dev`  | `https://dev.freepod.eu` | same                                         |

Overridable with `FREEPOD_ENV`. A free-form `--baseurl` would need the issuer and client
id to travel with it, which means either a discovery endpoint — explicitly out of scope —
or asking the user for three values instead of one.

**The default flips relative to the demo client**, which defaults to `dev` because it is
a developer's tool. A released client must default to production.

### D3. Lift the demo client's auth module, then delete the demo

`auth.py` is `cli/freepod_cli.py`'s authentication code essentially unchanged: the
loopback listener on an ephemeral `127.0.0.1` port with the exactly-`/callback` path, the
device grant with PKCE on the device endpoint (which Keycloak requires and which
surprises most implementations), the browser-reachability detection, and the token cache
at `${XDG_CONFIG_HOME:-~/.config}/freepod/tokens.json` — mode `0600` in a `0700`
directory, keyed by environment.

The demo is then removed. Its README's substance — the two flows, the loopback path trap,
the device-code display rationale, the status codes, the security notes — folds into
`cli/README.md`.

*Alternative considered: keep the demo alongside as a reference.* Rejected: two things
named "the CLI" in one directory, with nothing indicating which is real.

### D4. `.freepod.json` holds intent, and nothing a deploy would rewrite

```json
{
  "version": 1,
  "env": "prod",
  "deployment": {
    "id": "40bd8dea-54f3-430d-8ee0-f1689f9629cb",
    "name": "custom-d8dtx4"
  },
  "user_values": {
    "hostname": "myapp.freepod.eu"
  }
}
```

Before the first deploy, `"deployment"` is `null`.

- **`image` is never written.** It is a build output, not intent. Persisting it means a
  rewritten committed file on every deploy — git churn and a merge conflict for any team
  of two. It is not written as `null` either: the platform's schema declares it
  `type: "string"` under `additionalProperties: false`, so a null fails validation.
- **`name` accompanies `id`** because it is immutable and far more legible in output.
- **`env` is in the file** because a deployment id is meaningless in the other
  environment. A mismatch with the selected environment is an error, not a guess — the
  same audience-scoping problem as the token cache, one level up.
- **The project root** is the nearest ancestor containing `.freepod.json`, git-style,
  and is also the tar root.

### D5. `init` only reads; `deploy` creates

`init` resolves the `custom` product by slug, reads `product.template.values_schema_json`,
prompts for each `required` property, normalizes and checks the hostname, and writes the
file:

```
1.  GET /api/products                      → first product with slug == "custom"
2.  product.template.values_schema_json    → the fields a deployment needs
3.  GET /api/domains                       → wildcard suffixes, e.g. ["freepod.eu"]
4.  prompt for each name in values_schema_json.required
5.  GET /api/hostnames/{fqdn}              → validate the hostname interactively
6.  write .freepod.json
```

It creates nothing. A command called `init` should not quietly provision a billable
resource, and splitting creation across two commands means a failed file write leaves an
orphan the user cannot see. It also makes `git clone && freepod deploy` work.

Hostname handling: identify the property by `"title": "hostname"` (case-insensitive — the
same rule the platform uses to derive and claim the hostname), lowercase it, append `.` +
the first `GET /api/domains` entry when it contains no dot, then check
`GET /api/hostnames/{fqdn}`, which always answers 200 with `{fqdn, usable, reason}`.

The prompting loop is schema-driven rather than hardcoded, so a new required field
appears without a client release. Today `required` is exactly `["hostname"]`.

**`init --force` discards the whole file including the deployment pointer**, which is why
a missing value at deploy time is answered by prompting rather than by sending the user
back to `init` — hence `values.py` being shared (D1).

### D6. Build first, then create or update the deployment

The obvious ordering — create in `init`, update in `deploy` — is worse in both
directions:

- Update is guarded by an atomic `WHERE status IN ('ready','error')`, so a deployment
  created moments earlier is `provisioning` and the update 409s.
- Creating first rolls out the placeholder image and *then* the real one: two rollouts
  and a visible placeholder page on a user's very first deploy.

Building first collapses that to one rollout, because `image` can be supplied at
creation. The phases are therefore preflight → pack → upload → build → release.

Preflight (before packing) does the cheap reads: `GET /api/me`, `GET /api/products`, the
recorded deployment if any, the plan (on a first deploy only), the
missing-required-value prompt, and the hostname check when it applies (D14). A deployment
deleted out from under the file is caught here rather than after a four-minute build.

The plan read belongs here for the same reason, and this was learned rather than
designed: the `custom` product on dev publishes no plans at all, so selecting the plan at
release time — where the create request needs it — meant a guaranteed refusal arriving
after a full build. An instance with no free plan refuses every deploy, every time; one
extra `GET /api/products/{id}/plans` turns four wasted minutes into an immediate answer.
It is read only when a deployment has to be created, since an update reuses the
deployment's existing subscription and never sends `plan_template_id`.

**First deploy:**

```
POST /api/users/{user_id}/deployments
{
  "desired_template_id": <product.template.id>,
  "plan_template_id":    <first plan whose template.price_cents == 0>,
  "user_values_json":    { "hostname": "myapp.freepod.eu", "image": "5@sha256:…" }
}
< 201  { "deployment": { … }, "checkout_url": null }
```

`GET /api/products/{id}/plans` returns plans ordered by `sort_order`, each embedding its
current `template` with `price_cents` — one call, no second lookup. Write `id` and `name`
back to the project file immediately.

**Subsequent deploys:** wait for `ready`/`error`, then `PUT` the same route.

### D7. Always target the product's canonical template

`desired_template_id` is `product.template.id` on create and on update alike. On create
the API requires it; on update, both it and the deployment's current template satisfy the
no-downgrade rule, and pinning to the deployment's own would freeze it on whatever
version it was created against — the opposite of what backwards-compatible template
upgrades exist for.

When the canonical template has moved, the client says so rather than performing it
silently:

```
→  Product template 4 → 5 (chart custom 0.1.0 → 0.2.0)
```

Preflight validates the *target* template's `required` list against local values first,
so an upgrade that merely needs a new value asks one question up front instead of
failing the release after the build. That check is **narrower than the promise it
rests on**: it catches an added required key and nothing else. A tightened `pattern`, a
property removed under `additionalProperties: false`, or any other narrowing still
reaches the release request and is refused there.

The residual risk is therefore carried by the platform's guarantee that template
upgrades are backwards compatible, which the client cannot verify. What the client owes
in return is an unambiguous report when the guarantee does not hold — see the release
409 handling, where a schema failure is indistinguishable by status from "retry in a
moment" and must not be reported as one.

### D8. User values are submitted as a complete document

Omitting `user_values_json` entirely makes the server reuse stored values, but a partial
object does **not** merge: sending `{"image": …}` alone fails validation because
`hostname` is required. The client composes the project file's `user_values` plus
`image`. This is also the mechanism by which a hostname edited in the file takes effect —
the file is intent, and every deploy asserts it.

### D9. Materialize the archive; do not stream it

The tar goes to a `tempfile.SpooledTemporaryFile` (in memory below ~32 MiB, spilling to
disk beyond). Two independent reasons: the presigned POST's policy carries a
`content-length-range` condition the store evaluates against the request, and **a stream
cannot be retried** — re-packing a tree that may have changed produces a different
archive.

The upload itself is a **presigned POST**, not a PUT:

```
POST /api/artifacts
< 201
{
  "artifact_id": "3f6c1e9a4b2d47c8a1e05d9f7b3c2a10",
  "url": "https://blob.freepod.eu/caelus-artifacts",
  "fields": { "key": "…", "policy": "…", "x-amz-algorithm": "…",
              "x-amz-credential": "…", "x-amz-date": "…", "x-amz-signature": "…" },
  "max_bytes": 104857600,
  "expires_in": 900
}
```

Send `multipart/form-data` with every `fields` entry verbatim and in order, file part
named `file` last. Mint the slot **after** packing — it lives 900s and 100 MiB over a
domestic uplink can outlive that — and minting persists nothing, so an unused slot costs
nothing. A 403 from the store means an expired slot or a policy violation: re-mint once
and retry.

**The retry must send the archive again, and what guarantees that is seekability.**
An earlier draft of this paragraph said the client must `seek(0)` before resubmitting
or it would send zero bytes. Measured against `httpx`, that is wrong: its multipart
encoder rewinds a file field itself — `FileField.render_data` calls `self.file.seek(0)`
whenever the object has a `seek` — so a resubmission from a fully consumed handle
already sends the whole archive.

The requirement that does bind is that whatever file-like object reaches the encoder
**exposes `seek` and `tell`**. The client wraps the archive in a reader that reports
upload progress, and that wrapper is where the property can be lost. Without them
`httpx` neither rewinds nor sizes the body, so the retry becomes a chunked, zero-byte
upload — and the policy's lower bound is 1
(`["content-length-range", 1, artifact_max_bytes]`, `api/app/services/artifacts.py:133`),
so the store refuses it and the client, per D12, reports the store's own message. The
failure therefore reads as "the freshly minted slot was rejected too", blaming the
platform for a client bug.

Two consequences for tests. Assert the retry's **byte count**, not merely that a retry
occurred — the count is the only thing separating a real replay from an empty one. And
assert the wrapper is seekable, because that is the actual invariant; an explicit
`seek(0)` in the client is worth keeping as belt-and-braces against a transport change,
but it is not what makes the retry work today and a test that only pins it would pass
while the real guard was removed.

The archive must carry project files at the **archive root**; the builder extracts with
no strip-components and runs `railpack prepare` on the extraction root, so a nested
top-level directory presents as "no project detected".

### D10. Ignore rules mirror Railway and `gcloud`; `pathspec` matches, we walk

Precedence, last match wins:

1. **Hard excludes**, never overridable: `.git/`.
2. **Built-in defaults**: `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`,
   `.pytest_cache/`, `target/`, `dist/`, `build/`, `.DS_Store`, `*.swp`, `.env.local`,
   `.env.*.local`.
3. **`.gitignore`**, honored by default including nested ones; `--no-gitignore` disables.
4. **`.freepodignore`**, applied last, so `!` negations can re-include anything except a
   hard exclude.

`.freepod.json` is included — it holds no secrets, and excluding it would surprise.

**Matching is `pathspec`.** The standard library has nothing close: `fnmatch`'s `*`
crosses `/`, and none of `fnmatch`, `glob`, or `PurePath.match` implement the anchoring
rule, directory-only trailing `/`, negation with last-match-wins, or per-directory ignore
files. `glob.translate()` is 3.13+, below our floor, and still is not gitignore.
Hand-rolling means owning `**` in three positions, character classes, backslash escapes,
and trailing-space rules, where each mistake silently ships or omits files.

`pathspec` is the de facto Python implementation (mypy and black depend on it), pure
Python, `Requires-Python: >=3.9`. Use `pathspec.GitIgnoreSpec.from_lines(…)`;
`GitWildMatchPattern` / `"gitwildmatch"` is deprecated as of 1.0. It is MPL-2.0, which is
fine as an unmodified dependency and fine inside a PyInstaller bundle.

**The walk is ours**, and owns two things pathspec does not: per-directory layering (git
evaluates each `.gitignore` relative to its own directory, so the walk carries a stack of
specs rewritten relative to the project root), and **pruning** — not descending into an
excluded directory, which is the difference between a fast pack and a `node_modules` stat
storm.

Pruning also settles a semantic question, because pathspec and git genuinely disagree
here. Measured, not assumed: given `node_modules/` followed by `!node_modules/keep.txt`,
`git check-ignore` reports `keep.txt` as ignored and `git add -A` skips it, while
`GitIgnoreSpec.match_file()` re-includes it. Pruning yields git's answer. **Match git** —
"`.freepodignore` behaves exactly like `.gitignore`" is the only rule a user can hold in
their head — and document the idiom that does work:

```
node_modules/*            ← exclude the entries, not the directory itself
!node_modules/keep.txt    ← re-inclusion now applies
```

**The built-in defaults must yield to that idiom, or it does not work.** The
documented workaround names `node_modules`, which is also a level-2 default — so
the default would prune the directory before the user's negation could ever be
consulted, and the one escape hatch the docs offer would silently do nothing. The
rule is therefore split by *which level* excluded the directory:

| Excluded by | Prunes |
|-------------|--------|
| Hard exclude (`.git/`) | always |
| The project's own `.gitignore` / `.freepodignore` | always — this is git's behavior, and the reason the idiom exists |
| A built-in default | only when the project negates nothing beneath it |

Git has no equivalent of the level-2 defaults, so nothing about this weakens git
parity: on any tree whose paths do not collide with a default, the client and
`git add -A` select identically. That equivalence is worth testing differentially
against real `git` rather than against hand-written expectations, since git is the
only trustworthy oracle for what git does.

The archive is deterministic within a run: entries sorted by path, `uid`/`gid` normalized
to 0, `uname`/`gname` blank. Entries the builder's `data` filter would refuse — sockets,
FIFOs, device nodes, symlinks resolving outside the project — are dropped locally with
their path named, because there they fail the whole extraction and here they are one
sentence.

### D11. `.env` is not excluded by default

Only the `*.local` variants are, matching Vercel. The build runs on the platform, and a
static front end typically bakes `.env` values into its `dist` during that build, so
dropping the file produces a silently misconfigured bundle rather than an error. The
ignore stack already does the right thing without a special case: a `.env` that is
gitignored is excluded by rule 3, and a `.env` that is committed is intent.

### D12. The client enforces exactly one limit, and learns it at runtime

`max_bytes`, echoed by the upload slot, compared against the packed size after minting
and before a byte is sent, reporting both numbers on refusal.

The archive's entry count and uncompressed ceiling live in the builder's environment
(`CAELUS_MAX_ENTRIES`, `CAELUS_MAX_EXTRACTED_BYTES`) and are never exposed to a client.
**Do not hardcode them.** A client carrying its own copy drifts the moment the platform
retunes one, and drifts in the worst direction: refusing archives the platform would have
accepted, with a message no operator can override. When one trips, the builder says so in
the build log the client is already streaming.

### D13. Stream raw log bytes; defer incremental decoding

```
GET /api/builds/{build_id}/log
Range: bytes={offset}-
< 206
X-Build-Status: running
```

Start at offset 0, advance by `len(chunk)`. `X-Build-Status` is on every response, so no
extra request asks whether the build is done; stop on `succeeded`, `failed`, `canceled`.
A range starting at the current end returns an empty 206, not a 416 — the steady state,
needing no special case.

Chunks go straight to `sys.stdout.buffer` and are flushed. The client does **not**
accumulate the log to decode it safely: the point of a build log is that it streams.
Terminals are UTF-8 in practice and a split multi-byte character costs one garbled glyph.
Incremental decoding is Deferred.

Poll every 1s while output arrives (the build worker's own loop is 1s), backing off to 3s
while empty; print `Queued…` while the status is `queued`. A 200 rather than 201 from
build creation means an in-flight build was returned unchanged — report it as
re-attaching, which is what makes a retry safe. On Ctrl-C the build keeps running: print
its id and say so.

### D14. The hostname is checked only when it changes

`GET /api/hostnames/{fqdn}` calls `require_valid_hostname_for_deployment` **without**
`exclude_deployment_id` — an exclusion the API passes only on its own update path — so
re-checking an unchanged hostname reports `in_use` against ourselves. Compare the project
file's hostname to the deployment's and check only on a difference, or when no deployment
exists yet.

This also skips `_check_cname`'s live DNS lookups for custom domains, which are slow and
transiently failure-prone, in the case where they could only confirm what we already know.

### D15. Bounded refresh, and `/api/me` first

The platform's status codes invert the usual reading; the full contract and its origin
are in [Appendix A](#appendix-a-the-401403-inversion). Two implementation rules follow:

- **Refresh at most once per request.** The API issues its own 403s (`require_self`,
  `require_admin`, JSON body with `detail`) which collide with the edge's plain-text 403.
  An unbounded "403 means refresh" rule would refresh, fail, re-login, and loop on a
  request no credential can satisfy. If the retry also 403s, report a permission error
  and stop.
- **`GET /api/me` before any public read.** Most of what `init` reads — products, plans,
  hostnames, domains — is on the edge's `skip_auth_routes` list, so those requests are
  anonymous however good or bad the token is and will never report a credential problem.
  `/api/me` is the first request that actually exercises the token.

### D16. One `--timeout`, resolved against a per-operation default

Three waits are bounded — the loopback listener, the build, and the rollout — and
they want wildly different numbers. Rather than three flags, `--timeout` is a single
global override that applies to whichever wait is in progress. Unset, each operation
falls back to its own default:

| Operation        | Default |
|------------------|---------|
| login (loopback) | 300s    |
| build            | 1800s   |
| rollout          | 600s    |

The alternative, one number for every wait, would turn an abandoned login into a
thirty-minute hang; separate `--login-timeout` / `--build-timeout` /
`--rollout-timeout` flags buy precision nobody has asked for. The cost accepted is
that `--timeout` means something different in `login` than in `deploy`, which the
help text states.

## Risks / Trade-offs

**The `custom` product is not yet curated with a slug** → `init` cannot resolve it, since
`slug` is written only by `CatalogReconciler` and is not settable through the API.
Tracked as an external prerequisite in `proposal.md` § Impact; the client's failure mode
is a clear "this instance does not offer user-supplied deployments" rather than a crash.

**A 100 MiB archive is held in memory or a temp file** → D9 spills to disk above ~32 MiB,
and the temp file is removed on both success and failure. The alternative, streaming,
cannot be retried.

**Pruning excluded directories diverges from `pathspec`'s own matcher** → D10 chooses
git's behavior deliberately and documents the working idiom. The divergence is measured
and covered by tests, not left to chance.

**Streaming raw bytes can garble a multi-byte character at a chunk boundary** → accepted
for the first release, since the cost is one glyph and the benefit is a log that actually
streams. Incremental decoding is Deferred and is a contained change.

**An interrupted deploy leaves a build running with no way to re-attach** → the client
says so and names the build id, but `freepod logs` does not exist yet. This is the
strongest argument for prioritizing it next.

**The client hardcodes two environments** → adding a third, or supporting self-hosted
instances, requires a client release. Accepted: the alternative is a discovery endpoint,
which this change deliberately does not add.

**A deploy silently adopts a newer product template** → D7 announces the move, and
preflight validates the target schema first. The platform's guarantee that template
upgrades are backwards compatible is what makes this acceptable.

## Migration Plan

Nothing to migrate: no server-side state, schema, or configuration changes.

1. Build the package in `cli/` alongside the existing demo client.
2. Verify both flows against `dev` end to end — login, init, deploy — before prod.
3. Delete `cli/freepod_cli.py` and rewrite `cli/README.md` once the package covers it.
4. Update `AGENTS.md`, whose monorepo layout does not currently mention `cli/`.

Rollback is deleting the package directory; no user or platform state depends on it. A
user who has authenticated can remove `~/.config/freepod/` and revoke the offline session
in the Keycloak account console.

## Deferred

Each is independently specifiable and none blocks this change:

- `status`, `logs [--follow]`, `open`, `destroy`, `builds`. `logs` is what makes an
  interrupted deploy recoverable rather than merely survivable.
- `deploy --image <ref>` to promote or roll back a previous build without rebuilding —
  the API's build listing exists precisely for this.
- `--json` output and a documented machine-readable error envelope.
- Incremental UTF-8 decoding of the build log (`codecs.getincrementaldecoder`).
- Canceling a build. The API has a `canceled` status but nothing reaches it from a client.
- Paid plans: plan selection, `checkout_url`, and the `pending` state.
- CI credentials via `FREEPOD_REFRESH_TOKEN`, with a loud note that an offline token
  carries full account authority.
- Local development against a self-hosted API, which authenticates on
  `X-Auth-Request-Email` rather than bearer tokens and is therefore a separate credential
  path, not a `--baseurl` flag.
- Registry publication: PyPI, a Homebrew formula from the sdist, and a PyInstaller `.exe`
  for Chocolatey.

## Appendix A. The 401/403 inversion

Recorded because every future client author will ask, and because the answer determines
whether the client works around it or waits for a fix.

**Where it was decided.** `openspec/changes/archive/2026-08-10-add-oauth2-token-auth/design.md`
§ D6, pinned in `openspec/specs/oauth2-token-auth/spec.md` § *Token errors are
machine-readable*. The only lever Freepod pulled is one boolean in `tf/app/login/main.tf`:
`bearer_token_login_fallback = false`. Both status codes come from oauth2-proxy (v7.14.2,
chart 10.1.4) and neither is configurable:

- `pkg/middleware/jwt_session.go` — with the fallback disabled, `denyInvalidJWTs` makes a
  token that fails verification a hardcoded **403**. With the fallback at its default,
  that request is merely session-less and gets the same **401** an anonymous one gets.
- The `/oauth2/auth` handler — a session that exists but fails the `allowed_groups` check
  is a hardcoded **401**. The group check runs *after* the session has been built from the
  token, so it never reaches the JWT loader's deny path. Confirmed empirically on dev.

So the decision was "make a broken credential distinguishable from no credential", and it
worked. The inversion is a side effect: RFC 6750 §3.1 wants `invalid_token` → 401 with a
`WWW-Authenticate` header and `insufficient_scope` → 403, exactly backwards from what
these paths emit. oauth2-proxy sets no `WWW-Authenticate` on either — both are a bare
`http.Error` with a plain-text body — so the header-based disambiguation the RFC intends
is unavailable.

**The resulting contract**, which the client implements:

| Status                                 | Answered by | Meaning                                                                                 | Client action                                                       |
|----------------------------------------|-------------|-----------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| 401                                    | edge        | no credential — or, on `dev` only, a valid credential for a non-member of `freepod-dev` | stop and explain; do not re-authenticate                            |
| 403, `text/plain`                      | edge        | token expired, malformed, or unverifiable                                               | refresh once and retry                                              |
| 403, JSON `detail`                     | API         | authenticated but not permitted on that resource                                        | stop                                                                |
| 404, `{"detail": "Not authenticated"}` | API         | no identity reached the API                                                             | only reachable on a skipped route; a bug report, not a login prompt |

**It is smaller than it looks.** The genuinely confusing row exists **only on dev** —
`tf/app/main.tf:15` sets `allowed_groups = local.is_prod_workspace ? [] : ["freepod-dev"]`.
On prod the mapping is unambiguous: 401 means you sent nothing, 403 means refresh. The
expired-access-token case, which every prod user hits after roughly 300 seconds idle, is
cleanly signalled.

**Options, in descending order of preference:**

1. **Leave it; document it.** The client's rules are safe under either behavior and the
   ambiguous case is dev-only. This is what this change does.
2. **Move the dev group gate from oauth2-proxy into Keycloak** — an authentication-flow
   override on the dev clients with a group condition and a *Deny Access* execution. A
   non-member then never obtains a token: they are refused on the login screen, when they
   can act on it, instead of getting a bare 401 on every API call forever. This fixes the
   user-facing problem rather than the status code and deletes the ambiguous row. Worth
   doing the next time dev auth is touched; not worth a change of its own.
3. **Revert the fallback to its default.** Everything becomes 401 — conventional-looking
   and strictly worse, since the client loses the refresh/stop distinction that is the
   entire point of D6.
4. **Remap the status at the edge.** Traefik's `forwardAuth` propagates the auth server's
   status verbatim, so this needs a plugin or a patched oauth2-proxy. Not worth it for a
   two-row table.
