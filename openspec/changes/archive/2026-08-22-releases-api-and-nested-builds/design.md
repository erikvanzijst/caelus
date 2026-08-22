## Context

See `proposal.md` § Why for motivation. What shapes the approach:

- **The ledger is already complete.** `deployment_release` carries number,
  template, build, values, `created_at`, `started_at`, `ended_at`, `error` and
  `helm_revision`, with `uq_release_number` on `(deployment_id, number)`. Status
  is a **derived property** on `DeploymentReleaseORM`, not a column. Nothing
  here needs a schema change or an Alembic migration.
- **Number is already the user-facing identifier.** `deployment-release-ledger`
  requires it, and `GET /users/{uid}/deployments/{did}/log?release=N`
  (`api/app/api/users.py:521`) already accepts it. The new path parameter is the
  second place that rule is honored, not the first.
- **`require_self` is a path-parameter dependency.** It reads `user_id` from the
  path (`api/app/deps.py:60`), so any router whose prefix carries `{user_id}`
  gets self-or-admin authorization for free. That is precisely what the
  root-level builds router cannot use, and why it grew `_resolve_scope`.
- **The `freepod` client already knows the caller's id.** Every command calls
  `api.me()` before its reads, so re-pointing at `/users/{user_id}/…` costs the
  client nothing.
- **`caelus` is unaffected by the relocation.** It calls services in-process and
  never constructs a URL; it is affected only by the parity obligation for the
  new release reads.

## Goals / Non-Goals

**Goals:**

- One addressing rule for user-owned resources: owner in the path, scope from
  `require_self`, no per-router scope resolution.
- Reading a rollout's history costs one request; reading what a rollout shipped
  costs one more, not two.
- The `freepod` client stays free of platform constants — the new command reads
  numbers, statuses and marks from what the platform answers.

**Non-Goals:**

- **No write surface for releases.** Releases are created by the deployment
  create/update endpoints and completed by the reconciler. Nothing here creates,
  edits, cancels or re-runs one.
- **No rollback.** "Redeploy release N" is an obvious next command and is not
  this change; it needs its own decision about whether it re-uses the release's
  build or mints a new release from its values.
- **No pagination.** See D5.
- **No UI work.** `ui/` calls no build endpoint today and gains no release view
  here.
- **No client-version negotiation.** The platform does not tell clients which
  version they need, and adding that mechanism is a separate change.

## Decisions

### D1 — Release routes live in their own router module, not in `users.py`

`api/app/api/users.py` is already 602 lines carrying users, ToS, and the whole
deployment surface. The release routes go in a new `api/app/api/releases.py`
with prefix `/users/{user_id}/deployments/{deployment_id}/releases`, included in
`main.py` under `/api`.

*Alternative considered:* appending to `users.py`. Rejected — the file's growth
is already the reason the deployment routes are hard to find in it, and a
prefix this specific describes a module rather than a section.

### D2 — The number is the path parameter; the `uuid4` is never in a URL

`GET …/releases/{number}` takes an `int`, constrained `ge=1`. The ledger's
`uuid4` stays what is stamped onto pods and is never accepted from a caller —
it is unguessable by design, and putting it in a URL would make it the
identifier users learn instead.

The service looks the release up by `(deployment_id, number)`, which
`uq_release_number` makes a unique lookup. A number the deployment has never
reached is `NotFoundException`, indistinguishable from a deployment that is not
the caller's.

*Alternative considered:* accepting either a number or a UUID and
discriminating on shape. Rejected — two identifiers for one resource, and the
one it would add is the one the ledger says not to present.

### D3 — The build is loaded by an eager `LEFT OUTER JOIN`, guarded by `lazy="raise"`

The single-release read returns a detail model carrying `build: BuildRead | None`
in addition to `build_id`. The load is a **real ORM relationship**, eagerly
joined, not a second lookup:

```python
# DeploymentReleaseORM
build: Optional["BuildORM"] = Relationship(
    sa_relationship_kwargs={"viewonly": True, "lazy": "raise"}
)
```

...with `joinedload(DeploymentReleaseORM.build)` applied in the two release
queries. All of the following was measured against this repo before the decision
was written (SQLModel 0.0.32 / SQLAlchemy 2.0.46):

- **The forward reference resolves without an import cycle.** `models/build.py`
  imports `models/core.py` for `_utcnow`, so `core.py` cannot import `BuildORM`
  back — but it does not need to. SQLAlchemy resolves `Optional["BuildORM"]`
  from the mapper registry by name at `configure_mappers()` time, and the
  foreign key `build.id = deployment_release.build_id` is inferred with no
  `primaryjoin`. Extracting `_utcnow` into a leaf module to break the cycle is
  therefore unnecessary.
- **One statement, not N+1.** A six-release listing with the relationship
  touched on every row emits exactly **one** SELECT, with
  `LEFT OUTER JOIN build AS build_1 ON build_1.id = deployment_release.build_id`.
- **The join is outer, so a buildless release survives it.** The release naming
  no build came back with `build = None` rather than being dropped, which an
  inner join would have done — and most products build nothing.

**Why `lazy="raise"` and an explicit `joinedload`, rather than `lazy="joined"`
on the relationship.** `lazy="joined"` also gives one statement, but
`DeploymentORM` already carries `applied_release` **and** `desired_release` at
`lazy="joined"`, so a build join nests under each of them and every deployment
read pays for it: measured, `GET /users/{uid}/deployments` goes from **13 joins
to 15**, loading build rows that `DeploymentReleaseRead` does not even expose.
Scoping the eagerness to the queries that actually read builds keeps the
deployment listing at its baseline 13 — confirmed by re-measuring.

`lazy="raise"` then does the thing the plain relationship cannot: it makes an
N+1 **impossible to introduce silently**. Any future code path that reads
`release.build` without an explicit eager load raises
`InvalidRequestError: 'DeploymentReleaseORM.build' is not available due to
lazy='raise'` on the spot, so the regression surfaces as a failing test rather
than as a query count nobody is watching. Verified: dropping the `joinedload`
from the listing query raises rather than emitting six extra SELECTs.

The full existing suite (933 passed, 13 skipped) shows no failures with the
relationship in place — nothing today reads `release.build`.

The *response model* still uses a forward reference
(`build: Optional["BuildRead"]`) resolved by `model_rebuild()` in
`models/__init__.py` — the pattern `DeploymentRead` already uses for
`SubscriptionRead`.

**Both endpoints inline the build**, so both queries carry the `joinedload`.
The listing was originally specified to return `build_id` alone, on the grounds
that inlining meant a lookup per row; the eager join removes that cost — the
listing gets its builds on the same statement, one extra `LEFT OUTER JOIN`, no
extra round trip — so the contract now inlines there too. This is the measured
six-release case above: one SELECT, six builds.

Note what this does **not** change: `DeploymentRead.applied_release` stays typed
as the build-less `DeploymentReleaseRead`. Widening *that* is what would drag
builds into every deployment read (the 13→15 join case), and with `lazy="raise"`
it would not merely be wasteful — a deployment query carries no `joinedload`, so
serializing a `build` field there would raise. The two models are what keep the
release-as-a-resource shape and the release-embedded-in-a-deployment shape
independent.

### D4 — The whole builds router relocates; `_resolve_scope` is deleted

`api/app/api/builds.py` takes prefix `/users/{user_id}/builds` and
`Depends(require_self)` on every route. Creation keeps taking the owner from
`current_user` — the path `user_id` is the authorization subject, not the input,
which is why `require_self` (not the raw path value) is what the service is
given. The `user_id` query parameter and `_resolve_scope` both go.

For reads, the scope passed to the service becomes `None if
current_user.is_admin else user_id`, preserving today's behavior: an
administrator reads across users, everyone else is confined to their own rows,
and another user's build 404s rather than 403s.

*Note the two-layer effect:* `require_self` already 403s a non-admin naming
someone else's account, so the service-level scope is a second, independent
check rather than the only one. That is deliberate — it is the same
belt-and-braces the deployment routes have.

### D5 — No pagination on the release listing

The listing returns every release of the deployment, as `GET /builds` returns
every build. Deployments accumulate releases slowly (one per rollout, and a
rollout requires the deployment to be `ready`/`error`), so the collection is
small in practice, and adding a pagination contract to one listing while the
neighbouring ones have none would be the inconsistency, not the fix.

The **client** bounds what it *displays*, exactly as `freepod builds` does, and
says how many it withheld. See `specs/cli-releases/spec.md`.

*Revisit when:* a deployment in the wild passes a few hundred releases, at
which point pagination is worth doing across all the listings at once.

### D6 — The old build paths are removed outright, not tombstoned

Per the decision recorded in the proposal, `/api/builds*` simply ceases to
exist; a request there gets FastAPI's bare `404 {"detail":"Not Found"}`.

*Alternative considered:* keeping root-level routes that return **410 Gone**
with "this endpoint moved; upgrade `freepod`". It costs about ten lines and
turns an opaque 404 — which an old client reports as `could not create the
build: HTTP 404` **after** it has already packed and uploaded the archive
(`cli/src/freepod/build.py:232`) — into an instruction. It is not a
compatibility alias, since nothing keeps working. It is recorded here as
rejected in favour of a literal hard cut; reversing that is a small edit to
this change's `build-api` delta and one route, not a redesign.

### D7 — The client's table helpers are extracted, not duplicated

`freepod releases` renders a table with the same timestamp parsing, local-time
formatting, duration formatting and column layout as `freepod builds`. Those
helpers (`parse_time`, `format_time`, `format_duration`, `abbreviate`, `render`,
`GAP`, `BLANK`) move from `history.py` into a new leaf module
`cli/src/freepod/table.py`; `history.py` and the new `releases.py` both import
them.

*Alternative considered:* `releases.py` importing them from `history.py`.
Rejected — it would make the release listing depend on the build history for no
reason other than which module happened to be written first.

### D8 — The mark comes from the deployment, not from the listing

`freepod releases` reads the deployment (which the project file already points
at) and marks the release whose number equals `applied_release.number`. It does
**not** infer the running release from the listing — after a failed rollout the
newest release is not the applied one, and the ledger is explicit that the
desired reference must not be read as what is running.

This mirrors `freepod builds`, which reads the deployment solely to mark the
live build.

### D9 — `caelus` parity is two read commands

`caelus list-releases <user_id> <deployment_id>` and `caelus get-release
<user_id> <deployment_id> <number>`, thin shells over the same two service
functions, YAML output via `_echo_yaml_entity` like their deployment
counterparts. Ownership is enforced by passing the acting user's id as the scope
unless they are an admin, matching `list-deployments`/`get-deployment`.

## Risks / Trade-offs

- **Every installed `freepod` breaks on `deploy`** the moment the platform
  carries this change → Accepted, per the hard-cut decision. Mitigated by
  bumping and publishing the client in the same cycle and calling the break out
  in its release notes. D6 records the cheaper failure mode that was declined.
- **The break surfaces late in the old client** — after packing and uploading —
  so a user pays the upload before seeing the error → Not mitigated by design;
  this is the concrete cost D6 weighs.
- **`ReleaseStatus.ABANDONED` is time-derived**, so a listing read twice can
  report a different status for an unchanged row once the lease elapses → This
  is the ledger's existing, deliberate behavior; the API surfaces it rather
  than introducing it. The spec states it so no client treats status as stable.
- **Two authorization layers could drift** — `require_self` on the route and the
  `user_id` scope in the service → Kept deliberately (D4) and pinned by tests
  that hit both a forbidden account and a foreign resource id under the caller's
  own account.
- **An unbounded listing** grows with a long-lived deployment's history (D5) →
  Bounded at the client, revisited platform-wide if it ever bites.
- **A future reader of `release.build` forgets the eager load** and reintroduces
  an N+1 → Structurally prevented, not merely reviewed for: `lazy="raise"`
  (D3) turns that access into an immediate `InvalidRequestError`, so it fails a
  test rather than shipping as a silent query-count regression.
- **`lazy="raise"` is stricter than the repo's other relationships**, which use
  `lazy="joined"`, so a contributor adding a release read must remember the
  `joinedload` → Accepted, and cheap to diagnose: the exception names the
  attribute and the reason. The alternative it buys off is a 15-join deployment
  listing on every read (D3).

## Migration Plan

No data migration: no schema change, and the release rows the new endpoints read
already exist (the ledger's own migration backfilled one per deployment).

Deploy order matters only for the builds relocation:

1. Ship the API. From this moment `/api/builds*` is gone and installed clients
   fail on `deploy`, `builds`, and build reads.
2. Publish the bumped `freepod` (tag `freepod-v*`) so `pip install -U freepod`
   is a working answer to the failure.
3. `caelus` needs no coordination — it is in-process and ships with the API.

**Rollback:** revert the API deployment. The new clients then fail against the
old paths in the same way, so a rollback is only a real option before step 2 is
in users' hands; after that, roll forward.

## Open Questions

None. D6 is a decided trade-off rather than an open question, and is flagged
because reversing it is cheap, not because it is unresolved.
